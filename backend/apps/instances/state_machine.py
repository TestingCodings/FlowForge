"""
Pure workflow state-machine helpers (v2 spec).

No Django imports at module level — all ORM access is deferred to function
bodies so this module can be imported in isolation and unit-tested without a
fully-initialised Django app.
"""


def get_valid_transitions(current_state_id: str, all_transitions: list[dict]) -> list[dict]:
    """
    Return every transition dict whose from_state_id matches current_state_id.

    Parameters
    ----------
    current_state_id : str
        UUID (as string) of the instance's current state.
    all_transitions : list[dict]
        Flat list of transition dicts, each with at minimum the keys
        ``id``, ``from_state_id``, and ``to_state_id``.

    Returns
    -------
    list[dict]
        Subset of *all_transitions* valid from the current state.
    """
    return [t for t in all_transitions if str(t.get("from_state_id")) == str(current_state_id)]


def validate_transition(
    instance_id: str,
    requested_transition_id: str,
    current_state_id: str,
    all_transitions: list[dict],
) -> tuple[bool, str]:
    """
    Validate that *requested_transition_id* is a legal move from *current_state_id*.

    Parameters
    ----------
    instance_id : str
        UUID of the workflow instance (used for error messages only).
    requested_transition_id : str
        UUID of the transition being requested.
    current_state_id : str
        UUID of the instance's current state.
    all_transitions : list[dict]
        Full set of transitions for the workflow definition.

    Returns
    -------
    tuple[bool, str]
        ``(True, "")`` on success.
        ``(False, "<error message>")`` on failure.
    """
    valid = get_valid_transitions(current_state_id, all_transitions)
    valid_ids = {str(t.get("id")) for t in valid}

    if str(requested_transition_id) not in valid_ids:
        # Check whether the transition exists at all in the workflow
        all_ids = {str(t.get("id")) for t in all_transitions}
        if str(requested_transition_id) not in all_ids:
            return False, "Transition does not exist"
        return False, (
            f"Transition is not valid from the current state "
            f"(instance {instance_id})"
        )

    return True, ""


def perform_transition(instance, transition, actor=None):
    """
    Atomically advance *instance* to the state indicated by *transition*.

    Steps:
    1. Validate the transition is permitted from the instance's current state.
    2. Update ``instance.current_state`` to ``transition.to_state``.
    3. Set ``instance.completed_at`` if the new state is terminal.
    4. Save the instance.
    5. Write an AuditLog entry (Phase 6 call-site).

    Parameters
    ----------
    instance : WorkflowInstance
        Live ORM instance to advance.
    transition : Transition
        ORM Transition object (already validated to belong to the instance's
        workflow definition by the caller).
    actor : User | None
        The user performing the action; ``None`` for system-initiated moves.

    Returns
    -------
    WorkflowInstance
        The saved instance (same object, mutated in place).

    Raises
    ------
    apps.workflows.engine.WorkflowTransitionError
        If the transition is not valid from the instance's current state.
    """
    from django.db import transaction
    from django.utils import timezone

    from apps.workflows.engine import WorkflowTransitionError

    if instance.current_state_id != transition.from_state_id:
        raise WorkflowTransitionError(
            f"Transition '{transition.name}' is invalid from state "
            f"'{instance.current_state.name}'"
        )

    with transaction.atomic():
        update_fields = ["current_state", "updated_at"]
        instance.current_state = transition.to_state

        if transition.to_state.is_terminal and instance.completed_at is None:
            instance.completed_at = timezone.now()
            update_fields.append("completed_at")

        instance.save(update_fields=update_fields)

        # Audit call-site — Phase 6 wires the full implementation
        try:
            from apps.audit.services import transition_applied

            transition_applied(
                workflow_instance=instance,
                actor=actor,
                from_state=transition.from_state.name,
                to_state=transition.to_state.name,
                payload={"transition_id": str(transition.id)},
            )
        except Exception:
            pass

    return instance
