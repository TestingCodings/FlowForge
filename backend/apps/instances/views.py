from django.db import models
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import (
    IsViewer,
    require_min_role,
    require_role,
)
from apps.audit.models import AuditActionType, AuditLog
from apps.audit.services import rule_fired, transition_applied
from apps.notifications.services import queue_event_notifications
from apps.tasks.services import create_tasks_for_state
from apps.workflows.engine import WorkflowTransitionError, perform_transition
from apps.workflows.models import Transition

from .models import WorkflowInstance
from .serializers import TransitionRequestSerializer, WorkflowInstanceSerializer


class WorkflowInstanceViewSet(viewsets.ModelViewSet):
    queryset = WorkflowInstance.objects.select_related(
        "workflow_definition", "current_state", "created_by"
    ).prefetch_related("audit_logs").all()
    serializer_class = WorkflowInstanceSerializer
    # Viewer+ for reads; writes are gated per-action below
    permission_classes = [IsAuthenticated, IsViewer]
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        require_min_role(request.user, "participant", action="create a workflow instance")
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        instance = self.get_object()
        serializer = TransitionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Resolve the transition to check requires_approval before firing
        transition_id = serializer.validated_data["transition_id"]
        try:
            tr = Transition.objects.get(id=transition_id)
        except Transition.DoesNotExist:
            return Response({"detail": "Transition not found."}, status=status.HTTP_400_BAD_REQUEST)

        if tr.requires_approval:
            require_min_role(request.user, "approver", action=f"fire '{tr.name}' (requires approval)")
        else:
            require_min_role(request.user, "participant", action=f"fire '{tr.name}'")

        from_state_name = instance.current_state.name
        try:
            result = perform_transition(instance, transition_id)
            create_tasks_for_state(instance, actions=result.actions)
        except WorkflowTransitionError as exc:
            queue_event_notifications(
                workflow_instance=instance,
                event_trigger="rule_blocked",
                context_data={
                    "instance": {"reference_number": instance.reference_number},
                    "transition": tr.name,
                    "reason": str(exc),
                    "actor": request.user.email,
                },
            )
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        transition_applied(
            workflow_instance=instance,
            actor=request.user,
            from_state=from_state_name,
            to_state=instance.current_state.name,
            payload={"transition_id": str(result.transition.id), "transition_name": result.transition.name},
            ip_address=request.META.get("REMOTE_ADDR", ""),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        for fired_action in result.actions:
            rule_fired(workflow_instance=instance, actor=request.user, payload=fired_action)

        queue_event_notifications(
            workflow_instance=instance,
            event_trigger="state_transition",
            context_data={
                "instance": {"reference_number": instance.reference_number},
                "from_state": from_state_name,
                "to_state": instance.current_state.name,
                "recipient_email": request.user.email,
            },
        )

        payload = WorkflowInstanceSerializer(instance).data
        payload["transition_applied"] = {
            "id": str(result.transition.id),
            "name": result.transition.name,
            "from_state": result.transition.from_state.name,
            "to_state": result.transition.to_state.name,
        }
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="comment")
    def comment(self, request, pk=None):
        """All authenticated users with at least viewer role may comment."""
        instance = self.get_object()
        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"detail": "Comment body is required."}, status=status.HTTP_400_BAD_REQUEST)
        AuditLog.objects.create(
            workflow_instance=instance,
            actor=request.user,
            action_type=AuditActionType.COMMENT,
            from_state=instance.current_state.name,
            to_state="",
            payload={"body": body},
            ip_address=request.META.get("REMOTE_ADDR", ""),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        queue_event_notifications(
            workflow_instance=instance,
            event_trigger="comment_added",
            context_data={
                "instance": {"reference_number": instance.reference_number},
                "actor": request.user.email,
                "comment": body,
            },
        )
        return Response({"detail": "Comment added."}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="metadata")
    def update_metadata(self, request, pk=None):
        """Participant+ may edit metadata."""
        require_min_role(request.user, "participant", action="edit instance metadata")
        instance = self.get_object()
        new_meta = request.data.get("metadata_json")
        if not isinstance(new_meta, dict):
            return Response({"detail": "metadata_json must be an object."}, status=status.HTTP_400_BAD_REQUEST)

        old_meta = dict(instance.metadata_json or {})
        instance.metadata_json = new_meta
        instance.save(update_fields=["metadata_json", "updated_at"])

        AuditLog.objects.create(
            workflow_instance=instance,
            actor=request.user,
            action_type=AuditActionType.METADATA_UPDATED,
            from_state=instance.current_state.name,
            payload={"before": old_meta, "after": new_meta},
            ip_address=request.META.get("REMOTE_ADDR", ""),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return Response(WorkflowInstanceSerializer(instance).data)

    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request):
        """
        Quick search for instances by reference number or workflow name.
        Used by the relationship link picker. Returns up to 20 results.
        GET /api/instances/search/?q=TRN
        """
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            return Response([])
        qs = (
            WorkflowInstance.objects
            .select_related("workflow_definition", "current_state")
            .filter(
                models.Q(reference_number__icontains=q) |
                models.Q(workflow_definition__name__icontains=q)
            )[:20]
        )
        return Response([
            {
                "id": str(i.id),
                "reference_number": i.reference_number,
                "workflow_name": i.workflow_definition.name,
                "current_state": i.current_state.name,
                "completed": i.completed_at is not None,
            }
            for i in qs
        ])

    @action(detail=True, methods=["post"], url_path="link")
    def link(self, request, pk=None):
        """Create a relationship from this instance to another. Participant+."""
        from .relationships import create_relationship, InstanceRelationshipSerializer
        require_min_role(request.user, "participant", action="link instances")
        instance = self.get_object()

        to_ref = (request.data.get("to_instance") or "").strip()
        rel_type = (request.data.get("rel_type") or "").strip()
        notes = (request.data.get("notes") or "").strip()

        if not to_ref:
            return Response({"detail": "to_instance (reference number or id) is required."}, status=400)
        if not rel_type:
            return Response({"detail": "rel_type is required."}, status=400)

        # Resolve target by reference_number or UUID
        try:
            import uuid as _uuid
            _uuid.UUID(to_ref)
            target = WorkflowInstance.objects.get(id=to_ref)
        except (ValueError, WorkflowInstance.DoesNotExist):
            try:
                target = WorkflowInstance.objects.get(reference_number=to_ref)
            except WorkflowInstance.DoesNotExist:
                return Response({"detail": f"Instance '{to_ref}' not found."}, status=404)

        if target.id == instance.id:
            return Response({"detail": "An instance cannot be linked to itself."}, status=400)

        rel = create_relationship(
            from_instance=instance,
            to_instance=target,
            rel_type=rel_type,
            created_by=request.user,
            notes=notes,
        )
        return Response(InstanceRelationshipSerializer(rel).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"link/(?P<rel_id>[^/.]+)")
    def unlink(self, request, pk=None, rel_id=None):
        """Remove a relationship. Participant+ (or the creator)."""
        from .relationships import InstanceRelationship
        require_min_role(request.user, "participant", action="remove an instance link")
        instance = self.get_object()
        try:
            rel = InstanceRelationship.objects.get(id=rel_id)
        except InstanceRelationship.DoesNotExist:
            return Response({"detail": "Relationship not found."}, status=404)

        if rel.from_instance_id != instance.id and rel.to_instance_id != instance.id:
            return Response({"detail": "Relationship does not belong to this instance."}, status=400)

        AuditLog.objects.create(
            workflow_instance=instance,
            actor=request.user,
            action_type=AuditActionType.RELATIONSHIP_REMOVED,
            from_state=instance.current_state.name,
            payload={
                "rel_type": rel.rel_type,
                "to_reference": rel.to_instance.reference_number,
            },
        )
        rel.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
