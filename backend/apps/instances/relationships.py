"""
Serializer and service layer for InstanceRelationship.
The model lives in models.py so Django's registry picks it up automatically.
"""

from rest_framework import serializers

from apps.audit.models import AuditActionType, AuditLog

from .models import InstanceRelationship, WorkflowInstance


class InstanceRelationshipSerializer(serializers.ModelSerializer):
    from_reference  = serializers.CharField(source="from_instance.reference_number", read_only=True)
    from_workflow   = serializers.CharField(source="from_instance.workflow_definition.name", read_only=True)
    from_state      = serializers.CharField(source="from_instance.current_state.name", read_only=True)
    from_completed  = serializers.SerializerMethodField()
    to_reference    = serializers.CharField(source="to_instance.reference_number", read_only=True)
    to_workflow     = serializers.CharField(source="to_instance.workflow_definition.name", read_only=True)
    to_state        = serializers.CharField(source="to_instance.current_state.name", read_only=True)
    to_completed    = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    def get_from_completed(self, obj):
        return obj.from_instance.completed_at is not None

    def get_to_completed(self, obj):
        return obj.to_instance.completed_at is not None

    def get_created_by_name(self, obj):
        return obj.created_by.full_name if obj.created_by else ""

    class Meta:
        model = InstanceRelationship
        fields = (
            "id",
            "from_instance", "from_reference", "from_workflow", "from_state", "from_completed",
            "to_instance",   "to_reference",   "to_workflow",   "to_state",   "to_completed",
            "rel_type",
            "notes",
            "created_by_name",
            "created_at",
        )


def create_relationship(
    from_instance: WorkflowInstance,
    to_instance: WorkflowInstance,
    rel_type: str,
    created_by,
    notes: str = "",
) -> InstanceRelationship:
    rel, created = InstanceRelationship.objects.get_or_create(
        from_instance=from_instance,
        to_instance=to_instance,
        rel_type=rel_type,
        defaults={"created_by": created_by, "notes": notes},
    )
    if not created:
        return rel  # duplicate — return the existing link silently

    # Audit on both ends so the link appears in both timelines
    for inst in (from_instance, to_instance):
        other = to_instance if inst == from_instance else from_instance
        AuditLog.objects.create(
            workflow_instance=inst,
            actor=created_by,
            action_type=AuditActionType.RELATIONSHIP_ADDED,
            from_state=inst.current_state.name,
            payload={
                "rel_type": rel_type,
                "direction": "outgoing" if inst == from_instance else "incoming",
                "other_reference": other.reference_number,
                "other_workflow": other.workflow_definition.name,
            },
        )
    return rel
