from rest_framework import serializers

from apps.tasks.services import create_tasks_for_state
from apps.workflows.models import Transition
from .models import WorkflowInstance


class WorkflowInstanceSerializer(serializers.ModelSerializer):
    workflow_definition_name = serializers.CharField(source="workflow_definition.name", read_only=True)
    current_state_name = serializers.CharField(source="current_state.name", read_only=True)

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
            "metadata",
        )
        read_only_fields = (
            "id",
            "current_state",
            "reference_number",
            "created_by",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data):
        instance = WorkflowInstance.objects.create(
            created_by=self.context["request"].user,
            **validated_data,
        )
        create_tasks_for_state(instance)
        return instance


class TransitionRequestSerializer(serializers.Serializer):
    transition_id = serializers.UUIDField()

    def validate_transition_id(self, value):
        if not Transition.objects.filter(id=value).exists():
            raise serializers.ValidationError("Transition does not exist")
        return value
