from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.models import AuditActionType, AuditLog
from apps.audit.services import rule_fired, transition_applied
from apps.notifications.services import queue_event_notifications
from apps.tasks.services import create_tasks_for_state
from apps.workflows.engine import WorkflowTransitionError, perform_transition

from .models import WorkflowInstance
from .serializers import TransitionRequestSerializer, WorkflowInstanceSerializer


class WorkflowInstanceViewSet(viewsets.ModelViewSet):
    queryset = WorkflowInstance.objects.select_related("workflow_definition", "current_state", "created_by").all()
    serializer_class = WorkflowInstanceSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        instance = self.get_object()
        serializer = TransitionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from_state_name = instance.current_state.name
        try:
            result = perform_transition(instance, serializer.validated_data["transition_id"])
            create_tasks_for_state(instance, actions=result.actions)
        except WorkflowTransitionError as exc:
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
        for action in result.actions:
            rule_fired(workflow_instance=instance, actor=request.user, payload=action)

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
        """Add a comment to the instance audit trail. Body: {"body": "..."}"""
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
        return Response({"detail": "Comment added."}, status=status.HTTP_201_CREATED)
