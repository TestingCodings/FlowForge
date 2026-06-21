from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

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


@transaction.atomic
def perform_transition(instance, transition_id):
    result = validate_transition(instance, transition_id)

    update_fields = ["current_state", "updated_at"]
    instance.current_state = result.transition.to_state

    if result.transition.to_state.is_terminal and instance.completed_at is None:
        instance.completed_at = timezone.now()
        update_fields.append("completed_at")

    instance.save(update_fields=update_fields)
    return result
