from rest_framework import serializers

from .models import Rule, State, Transition, WorkflowDefinition


class StateSerializer(serializers.ModelSerializer):
    class Meta:
        model = State
        fields = (
            "id",
            "workflow_definition",
            "name",
            "display_name",
            "is_initial",
            "is_terminal",
            "position_order",
            "requires_task",
            "task_title",
            "task_description",
            "task_assigned_role",
            "task_sla_hours",
        )
        read_only_fields = ("id",)


class TransitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transition
        fields = (
            "id",
            "workflow_definition",
            "from_state",
            "to_state",
            "name",
            "requires_approval",
        )
        read_only_fields = ("id",)


class RuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rule
        fields = (
            "id",
            "workflow_definition",
            "transition",
            "condition",
            "action",
            "priority",
        )
        read_only_fields = ("id",)


class WorkflowDefinitionSerializer(serializers.ModelSerializer):
    states = StateSerializer(many=True, read_only=True)
    transitions = TransitionSerializer(many=True, read_only=True)
    rules = RuleSerializer(many=True, read_only=True)

    class Meta:
        model = WorkflowDefinition
        fields = (
            "id",
            "name",
            "description",
            "version",
            "is_active",
            "created_by",
            "created_at",
            "states",
            "transitions",
            "rules",
        )
        read_only_fields = ("id", "created_by", "created_at")


class WorkflowDefinitionCreateSerializer(serializers.ModelSerializer):
    states = serializers.ListField(child=serializers.DictField(), write_only=True)
    transitions = serializers.ListField(child=serializers.DictField(), write_only=True)

    class Meta:
        model = WorkflowDefinition
        fields = (
            "id",
            "name",
            "description",
            "version",
            "is_active",
            "states",
            "transitions",
        )
        read_only_fields = ("id",)

    def validate_states(self, states):
        if not states:
            raise serializers.ValidationError("At least one state is required")

        initial_states = [state for state in states if state.get("is_initial")]
        if len(initial_states) != 1:
            raise serializers.ValidationError("Exactly one initial state is required")

        names = [state.get("name") for state in states]
        if len(set(names)) != len(names):
            raise serializers.ValidationError("State names must be unique")

        return states

    def validate(self, attrs):
        state_names = {state.get("name") for state in attrs.get("states", [])}
        for transition in attrs.get("transitions", []):
            from_state = transition.get("from_state")
            to_state = transition.get("to_state")
            if from_state not in state_names or to_state not in state_names:
                raise serializers.ValidationError(
                    "Transition from_state and to_state must reference existing state names"
                )
        return attrs

    def create(self, validated_data):
        state_data = validated_data.pop("states", [])
        transition_data = validated_data.pop("transitions", [])

        workflow_definition = WorkflowDefinition.objects.create(
            created_by=self.context["request"].user,
            **validated_data,
        )

        state_map = {}
        for state_payload in state_data:
            state = State.objects.create(
                workflow_definition=workflow_definition,
                name=state_payload["name"],
                display_name=state_payload.get("display_name", ""),
                is_initial=state_payload.get("is_initial", False),
                is_terminal=state_payload.get("is_terminal", False),
                position_order=state_payload.get("position_order", 1),
                requires_task=state_payload.get("requires_task", not state_payload.get("is_terminal", False)),
                task_title=state_payload.get("task_title", ""),
                task_description=state_payload.get("task_description", ""),
                task_assigned_role=state_payload.get("task_assigned_role", ""),
                task_sla_hours=state_payload.get("task_sla_hours", 48),
            )
            state_map[state.name] = state

        for transition_payload in transition_data:
            Transition.objects.create(
                workflow_definition=workflow_definition,
                from_state=state_map[transition_payload["from_state"]],
                to_state=state_map[transition_payload["to_state"]],
                name=transition_payload["name"],
                requires_approval=transition_payload.get("requires_approval", False),
            )

        return workflow_definition
