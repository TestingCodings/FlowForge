from rest_framework import serializers

from .models import Task


class TaskSerializer(serializers.ModelSerializer):
    workflow_reference = serializers.CharField(source="workflow_instance.reference_number", read_only=True)
    state_name = serializers.CharField(source="state.name", read_only=True)

    class Meta:
        model = Task
        fields = (
            "id",
            "workflow_instance",
            "workflow_reference",
            "state",
            "state_name",
            "transition",
            "title",
            "description",
            "assigned_to_user",
            "assigned_to_role",
            "status",
            "priority",
            "due_at",
            "completed_at",
            "completed_by",
            "created_at",
        )
        read_only_fields = (
            "id",
            "completed_at",
            "completed_by",
            "created_at",
        )
