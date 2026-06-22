from django.utils import timezone
from rest_framework import serializers

from apps.audit.models import AuditActionType
from apps.audit.services import instance_created
from apps.notifications.services import queue_event_notifications
from apps.tasks.services import create_tasks_for_state
from apps.workflows.models import Transition
from .models import WorkflowInstance


def _sla_status(instance: WorkflowInstance):
    """Return sla_status dict or None if the current state has no SLA."""
    sla_hours = instance.current_state.sla_config.get("sla_hours") if instance.current_state_id else None
    if not sla_hours:
        return None

    # Find when we entered the current state: last transition-to or instance created_at
    last_transition = (
        instance.audit_logs
        .filter(action_type=AuditActionType.TRANSITION, to_state=instance.current_state.name)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    entered_at = last_transition or instance.created_at
    elapsed_hours = (timezone.now() - entered_at).total_seconds() / 3600
    pct = elapsed_hours / sla_hours
    if pct >= 1.0:
        label = "breached"
    elif pct >= 0.75:
        label = "warning"
    else:
        label = "ok"
    return {
        "status": label,
        "sla_hours": sla_hours,
        "elapsed_hours": round(elapsed_hours, 1),
        "entered_at": entered_at.isoformat(),
    }


class WorkflowInstanceSerializer(serializers.ModelSerializer):
    workflow_definition_name = serializers.CharField(source="workflow_definition.name", read_only=True)
    current_state_name = serializers.CharField(source="current_state.name", read_only=True)
    sla = serializers.SerializerMethodField()

    def get_sla(self, obj):
        if obj.completed_at:
            return None
        return _sla_status(obj)

    class Meta:
        model = WorkflowInstance
        fields = (
            "id",
            "workflow_definition",
            "workflow_definition_name",
            "current_state",
            "current_state_name",
            "reference_number",
            "created_by",
            "created_at",
            "updated_at",
            "completed_at",
            "metadata_json",
            "sla",
        )
        read_only_fields = (
            "id",
            "current_state",
            "reference_number",
            "created_by",
            "created_at",
            "updated_at",
            "completed_at",
        )

    def create(self, validated_data):
        instance = WorkflowInstance.objects.create(
            created_by=self.context["request"].user,
            **validated_data,
        )
        create_tasks_for_state(instance)
        request = self.context.get("request")
        instance_created(
            workflow_instance=instance,
            actor=request.user if request else None,
            payload={"reference_number": instance.reference_number},
            ip_address=request.META.get("REMOTE_ADDR", "") if request else "",
            user_agent=request.META.get("HTTP_USER_AGENT", "") if request else "",
        )
        queue_event_notifications(
            workflow_instance=instance,
            event_trigger="instance_created",
            context_data={
                "instance": {"reference_number": instance.reference_number},
                "recipient_email": request.user.email if request else "",
            },
        )
        return instance


class TransitionRequestSerializer(serializers.Serializer):
    transition_id = serializers.UUIDField()

    def validate_transition_id(self, value):
        if not Transition.objects.filter(id=value).exists():
            raise serializers.ValidationError("Transition does not exist")
        return value
