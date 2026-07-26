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


def _check_required_form(instance):
    """Block leaving a state whose form requires submission and has none."""
    from apps.forms.models import FormDefinition, FormSubmission

    form = (
        FormDefinition.objects
        .filter(state_id=instance.current_state_id)
        .order_by("-version")
        .first()
    )
    if form is None:
        return
    if not form.schema.get("required_to_transition", True):
        return
    submitted = FormSubmission.objects.filter(
        workflow_instance=instance, form_definition=form
    ).exists()
    if not submitted:
        raise WorkflowTransitionError(
            f"Form '{form.name}' must be completed before leaving '{instance.current_state.name}'."
        )


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

    _check_required_form(instance)

    actions = evaluate_for_transition(instance, transition)
    for action in actions:
        if action.get("type") == "block_transition":
            reason = action.get("reason", "Transition blocked by rule")
            raise WorkflowTransitionError(reason)

    return TransitionResult(transition=transition, actions=actions)


def _metadata_from_actions(actions) -> dict:
    """Collect `set_metadata` rule actions into a single delta.

    Lets a transition stamp facts onto the instance without an outbound call —
    "record that approval happened", "the player now holds the key". Later
    actions win over earlier ones, matching rule priority order.

    A malformed action is skipped rather than raised: a typo in one rule
    shouldn't make the whole transition impossible.
    """
    delta: dict = {}
    for action in actions:
        if action.get("type") != "set_metadata":
            continue
        values = action.get("values")
        if isinstance(values, dict):
            delta.update(values)
    return delta


def perform_transition(instance, transition_id):
    """
    Pre-flight (no transaction): validate rules + required forms, then run
    `before` action hooks — which may call external systems and can block the
    transition (docs/HOOKS.md Part 2). Then commit atomically, re-checking
    under a row lock that the instance hasn't moved since pre-flight so a
    concurrent transition can't be clobbered.
    """
    from apps.instances.models import WorkflowInstance

    result = validate_transition(instance, transition_id)

    # `before` hooks run outside the transaction so their network calls don't
    # hold a DB transaction open. Deferred import avoids an engine↔hooks cycle.
    from apps.notifications.hooks import run_before_hooks
    # Rule-set values land first so a hook reporting external truth can
    # override a statically-declared default.
    metadata_deltas = _metadata_from_actions(result.actions)
    metadata_deltas.update(run_before_hooks(instance, result.transition))

    with transaction.atomic():
        locked = WorkflowInstance.objects.select_for_update().get(pk=instance.pk)
        if locked.current_state_id != result.transition.from_state_id:
            raise WorkflowTransitionError(
                "Instance changed state during processing; please retry the transition."
            )

        update_fields = ["current_state", "updated_at"]
        locked.current_state = result.transition.to_state
        if metadata_deltas:
            merged = dict(locked.metadata_json or {})
            merged.update(metadata_deltas)
            locked.metadata_json = merged
            update_fields.append("metadata_json")
        if result.transition.to_state.is_terminal and locked.completed_at is None:
            locked.completed_at = timezone.now()
            update_fields.append("completed_at")
        locked.save(update_fields=update_fields)

    # Keep the caller's instance in sync with what was committed.
    instance.current_state = result.transition.to_state
    instance.current_state_id = result.transition.to_state_id
    instance.metadata_json = locked.metadata_json
    instance.completed_at = locked.completed_at
    return result
