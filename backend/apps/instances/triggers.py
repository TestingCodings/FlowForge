"""
Inbound triggers (VISION meta-model: the world → FlowForge).

The outbound counterpart to webhooks: an external system POSTs to a trigger's
secret URL to either create an instance or fire a transition, always through
the engine so rules / approvals / required-form gating still apply.

- Public fire endpoint:  POST /api/trigger/<token>/   (token is the credential)
- Authenticated CRUD:    /api/triggers/               (workflow_designer+)
"""
from django.db import models
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsViewer, require_min_role
from apps.audit.services import instance_created, rule_fired, transition_applied
from apps.notifications.services import queue_event_notifications
from apps.tasks.services import create_tasks_for_state
from apps.workflows.engine import WorkflowTransitionError, perform_transition

from .models import Trigger, WorkflowInstance
from .serializers import WorkflowInstanceSerializer


class TriggerSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source="workflow_definition.name", read_only=True)
    transition_name = serializers.CharField(source="transition.name", read_only=True, default=None)
    fire_path = serializers.SerializerMethodField()

    class Meta:
        model = Trigger
        fields = (
            "id", "name", "workflow_definition", "workflow_name",
            "action", "transition", "transition_name",
            "lookup_field", "metadata_mapping", "is_active",
            "token", "fire_path", "created_at", "last_triggered_at", "trigger_count",
        )
        read_only_fields = ("id", "token", "created_at", "last_triggered_at", "trigger_count")

    def get_fire_path(self, obj):
        # The relative URL an external system POSTs to. The host is the
        # deployment's own; clients prepend it.
        return f"/api/trigger/{obj.token}/"

    def validate(self, attrs):
        action = attrs.get("action") or getattr(self.instance, "action", None)
        transition = attrs.get("transition") or getattr(self.instance, "transition", None)
        if action == Trigger.Action.FIRE_TRANSITION and not transition:
            raise serializers.ValidationError("fire_transition triggers require a transition.")
        wf = attrs.get("workflow_definition") or getattr(self.instance, "workflow_definition", None)
        if transition and wf and transition.workflow_definition_id != wf.id:
            raise serializers.ValidationError("transition must belong to the trigger's workflow.")
        return attrs


class TriggerViewSet(viewsets.ModelViewSet):
    """Manage triggers. Reads: viewer+. Writes: workflow_designer+."""
    queryset = Trigger.objects.select_related("workflow_definition", "transition").all()
    serializer_class = TriggerSerializer
    permission_classes = [IsAuthenticated, IsViewer]
    filterset_fields = ["workflow_definition", "action", "is_active"]

    def create(self, request, *args, **kwargs):
        require_min_role(request.user, "workflow_designer", action="create a trigger")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def update(self, request, *args, **kwargs):
        require_min_role(request.user, "workflow_designer", action="edit a trigger")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        require_min_role(request.user, "workflow_designer", action="delete a trigger")
        return super().destroy(request, *args, **kwargs)


class TriggerThrottle(AnonRateThrottle):
    scope = "trigger"  # rate configured in settings DEFAULT_THROTTLE_RATES


class TriggerFireView(APIView):
    """
    POST /api/trigger/<token>/

    Unauthenticated — the token in the URL is the credential. Body is a JSON
    payload mapped into metadata per the trigger's config.
    """
    permission_classes = [AllowAny]
    throttle_classes = [TriggerThrottle]

    def post(self, request, token):
        try:
            trigger = Trigger.objects.select_related(
                "workflow_definition", "transition"
            ).get(token=token, is_active=True)
        except Trigger.DoesNotExist:
            return Response({"detail": "Unknown or inactive trigger."}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        metadata = trigger.apply_mapping(payload)

        if trigger.action == Trigger.Action.CREATE_INSTANCE:
            result = self._create_instance(trigger, metadata)
        else:
            result = self._fire_transition(trigger, payload, metadata)

        # Record the fire regardless of outcome.
        Trigger.objects.filter(id=trigger.id).update(
            last_triggered_at=timezone.now(),
            trigger_count=models.F("trigger_count") + 1,
        )
        return result

    def _create_instance(self, trigger, metadata):
        instance = WorkflowInstance.objects.create(
            workflow_definition=trigger.workflow_definition,
            created_by=None,
            metadata_json=metadata,
        )
        create_tasks_for_state(instance)
        instance_created(
            workflow_instance=instance,
            actor=None,
            payload={"reference_number": instance.reference_number, "via_trigger": trigger.name},
        )
        queue_event_notifications(
            workflow_instance=instance,
            event_trigger="instance_created",
            context_data={"instance": {"reference_number": instance.reference_number}},
        )
        return Response(
            {
                "detail": "Instance created.",
                "instance": WorkflowInstanceSerializer(instance, context={"request": None}).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def _fire_transition(self, trigger, payload, metadata):
        instance = self._lookup_instance(trigger, payload)
        if instance is None:
            return Response(
                {"detail": "No matching instance found for the trigger's lookup field."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Merge any mapped metadata so rules can read it before evaluating.
        if metadata:
            merged = dict(instance.metadata_json or {})
            merged.update(metadata)
            instance.metadata_json = merged
            instance.save(update_fields=["metadata_json", "updated_at"])

        from_state = instance.current_state.name
        try:
            result = perform_transition(instance, trigger.transition_id)
            create_tasks_for_state(instance, actions=result.actions)
        except WorkflowTransitionError as exc:
            queue_event_notifications(
                workflow_instance=instance,
                event_trigger="rule_blocked",
                context_data={
                    "instance": {"reference_number": instance.reference_number},
                    "transition": trigger.transition.name,
                    "reason": str(exc),
                },
            )
            return Response(
                {"detail": str(exc), "instance": instance.reference_number, "blocked": True},
                status=status.HTTP_409_CONFLICT,
            )

        transition_applied(
            workflow_instance=instance,
            actor=None,
            from_state=from_state,
            to_state=instance.current_state.name,
            payload={"transition_name": result.transition.name, "via_trigger": trigger.name},
        )
        for fired in result.actions:
            rule_fired(workflow_instance=instance, actor=None, payload=fired)
        queue_event_notifications(
            workflow_instance=instance,
            event_trigger="state_transition",
            context_data={
                "instance": {"reference_number": instance.reference_number},
                "from_state": from_state,
                "to_state": instance.current_state.name,
            },
        )
        return Response({
            "detail": "Transition fired.",
            "instance": instance.reference_number,
            "from_state": from_state,
            "to_state": instance.current_state.name,
        })

    @staticmethod
    def _lookup_instance(trigger, payload):
        field = trigger.lookup_field or "reference_number"
        wf_instances = WorkflowInstance.objects.filter(
            workflow_definition=trigger.workflow_definition, completed_at__isnull=True
        ).select_related("current_state")

        if field == "reference_number":
            ref = payload.get("reference_number")
            if not ref:
                return None
            return wf_instances.filter(reference_number=ref).first()

        if field.startswith("metadata."):
            key = field[len("metadata."):]
            value = payload.get(key)
            if value is None:
                return None
            # JSON containment match on the metadata key.
            return wf_instances.filter(**{f"metadata_json__{key}": value}).first()

        return None
