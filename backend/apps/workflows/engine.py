from dataclasses import dataclass

from apps.workflows.models import Transition
from apps.workflows.rules import evaluate_for_transition


class WorkflowTransitionError(Exception):
    """Raised when a requested workflow transition is not valid."""


@dataclass
class TransitionResult:
    transition: Transition
    actions: list[dict]


def validate_transition(instance, transition_id):
    try:
        transition = Transition.objects.select_related("from_state", "to_state").get(id=transition_id)
    except Transition.DoesNotExist as exc:
        raise WorkflowTransitionError("Transition does not exist") from exc

    if transition.workflow_definition_id != instance.workflow_definition_id:
        raise WorkflowTransitionError("Transition does not belong to this workflow definition")

    if transition.from_state_id != instance.current_state_id:
        raise WorkflowTransitionError(
            f"Transition '{transition.name}' is invalid from state '{instance.current_state.name}'"
        )

    actions = evaluate_for_transition(instance, transition)
    for action in actions:
        if action.get("type") == "block_transition":
            reason = action.get("reason", "Transition blocked by rule")
            raise WorkflowTransitionError(reason)

    return TransitionResult(transition=transition, actions=actions)


def perform_transition(instance, transition_id):
    result = validate_transition(instance, transition_id)
    instance.current_state = result.transition.to_state
    instance.save(update_fields=["current_state", "updated_at"])
    return result
