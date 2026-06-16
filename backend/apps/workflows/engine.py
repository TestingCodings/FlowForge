from dataclasses import dataclass

from apps.workflows.models import Transition


class WorkflowTransitionError(Exception):
    """Raised when a requested workflow transition is not valid."""


@dataclass
class TransitionResult:
    transition: Transition


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

    return TransitionResult(transition=transition)


def perform_transition(instance, transition_id):
    result = validate_transition(instance, transition_id)
    instance.current_state = result.transition.to_state
    instance.save(update_fields=["current_state", "updated_at"])
    return result
