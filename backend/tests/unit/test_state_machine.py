"""Unit tests for apps/instances/state_machine.py (v2 spec)."""

import uuid

import pytest

from tests.factories import (
    StateFactory,
    TransitionFactory,
    UserFactory,
    WorkflowDefinitionFactory,
    WorkflowInstanceFactory,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _transitions_as_dicts(transitions):
    """Convert a queryset / list of Transition ORM objects to plain dicts."""
    return [
        {
            "id": str(t.id),
            "from_state_id": str(t.from_state_id),
            "to_state_id": str(t.to_state_id),
            "name": t.name,
        }
        for t in transitions
    ]


def _build_linear_workflow():
    """Draft --Submit--> Review --Approve--> Approved (terminal)"""
    wf = WorkflowDefinitionFactory()
    s1 = StateFactory(workflow_definition=wf, name="Draft", is_initial=True, position_order=1)
    s2 = StateFactory(workflow_definition=wf, name="Review", position_order=2)
    s3 = StateFactory(workflow_definition=wf, name="Approved", is_terminal=True, position_order=3)
    t1 = TransitionFactory(workflow_definition=wf, from_state=s1, to_state=s2, name="Submit")
    t2 = TransitionFactory(workflow_definition=wf, from_state=s2, to_state=s3, name="Approve")
    return wf, s1, s2, s3, t1, t2


# ---------------------------------------------------------------------------
# get_valid_transitions
# ---------------------------------------------------------------------------


class TestGetValidTransitions:
    """Pure Python — no DB access needed."""

    def test_returns_matching_transitions(self):
        from apps.instances.state_machine import get_valid_transitions

        state_a = str(uuid.uuid4())
        state_b = str(uuid.uuid4())
        transitions = [
            {"id": str(uuid.uuid4()), "from_state_id": state_a, "to_state_id": state_b},
            {"id": str(uuid.uuid4()), "from_state_id": state_b, "to_state_id": state_a},
        ]
        result = get_valid_transitions(state_a, transitions)
        assert len(result) == 1
        assert result[0]["from_state_id"] == state_a

    def test_returns_empty_for_terminal_state_with_no_outgoing(self):
        from apps.instances.state_machine import get_valid_transitions

        terminal_id = str(uuid.uuid4())
        transitions = [{"id": str(uuid.uuid4()), "from_state_id": str(uuid.uuid4()), "to_state_id": terminal_id}]
        assert get_valid_transitions(terminal_id, transitions) == []

    def test_returns_multiple_valid_transitions(self):
        from apps.instances.state_machine import get_valid_transitions

        state_id = str(uuid.uuid4())
        transitions = [
            {"id": str(uuid.uuid4()), "from_state_id": state_id, "to_state_id": str(uuid.uuid4())},
            {"id": str(uuid.uuid4()), "from_state_id": state_id, "to_state_id": str(uuid.uuid4())},
            {"id": str(uuid.uuid4()), "from_state_id": str(uuid.uuid4()), "to_state_id": state_id},
        ]
        result = get_valid_transitions(state_id, transitions)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# validate_transition
# ---------------------------------------------------------------------------


class TestValidateTransition:
    """Pure Python — no DB access needed."""

    def test_valid_transition_returns_true(self):
        from apps.instances.state_machine import validate_transition

        current = str(uuid.uuid4())
        target = str(uuid.uuid4())
        t_id = str(uuid.uuid4())
        transitions = [{"id": t_id, "from_state_id": current, "to_state_id": target}]

        ok, err = validate_transition(str(uuid.uuid4()), t_id, current, transitions)
        assert ok is True
        assert err == ""

    def test_nonexistent_transition_returns_false(self):
        from apps.instances.state_machine import validate_transition

        current = str(uuid.uuid4())
        transitions = [{"id": str(uuid.uuid4()), "from_state_id": current, "to_state_id": str(uuid.uuid4())}]

        ok, err = validate_transition(str(uuid.uuid4()), str(uuid.uuid4()), current, transitions)
        assert ok is False
        assert err != ""

    def test_wrong_from_state_returns_false(self):
        from apps.instances.state_machine import validate_transition

        state_a = str(uuid.uuid4())
        state_b = str(uuid.uuid4())
        state_c = str(uuid.uuid4())
        t_id = str(uuid.uuid4())
        transitions = [{"id": t_id, "from_state_id": state_a, "to_state_id": state_b}]

        # instance is at state_c, but transition expects state_a
        ok, err = validate_transition(str(uuid.uuid4()), t_id, state_c, transitions)
        assert ok is False
        assert err != ""

    def test_attempting_to_leave_terminal_state_returns_error(self):
        from apps.instances.state_machine import validate_transition

        terminal_id = str(uuid.uuid4())
        # No transitions originate from terminal_id
        transitions = [{"id": str(uuid.uuid4()), "from_state_id": str(uuid.uuid4()), "to_state_id": terminal_id}]
        any_transition_id = str(uuid.uuid4())

        ok, err = validate_transition(str(uuid.uuid4()), any_transition_id, terminal_id, transitions)
        assert ok is False


# ---------------------------------------------------------------------------
# perform_transition (requires DB)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPerformTransition:
    def _setup(self):
        wf, s1, s2, s3, t1, t2 = _build_linear_workflow()
        instance = WorkflowInstanceFactory(workflow_definition=wf)
        instance.current_state = s1
        instance.save(update_fields=["current_state"])
        return wf, s1, s2, s3, t1, t2, instance

    def test_advances_instance_to_target_state(self):
        from apps.instances.state_machine import perform_transition

        wf, s1, s2, s3, t1, t2, instance = self._setup()
        perform_transition(instance, t1, actor=None)
        instance.refresh_from_db()
        assert instance.current_state_id == s2.id

    def test_returns_updated_instance(self):
        from apps.instances.state_machine import perform_transition

        wf, s1, s2, s3, t1, t2, instance = self._setup()
        result = perform_transition(instance, t1)
        assert result.current_state_id == s2.id

    def test_invalid_from_state_raises(self):
        from apps.instances.state_machine import perform_transition
        from apps.workflows.engine import WorkflowTransitionError

        wf, s1, s2, s3, t1, t2, instance = self._setup()
        # t2 goes from s2 → s3; instance is at s1
        with pytest.raises(WorkflowTransitionError):
            perform_transition(instance, t2)

    def test_invalid_transition_does_not_change_state(self):
        from apps.instances.state_machine import perform_transition
        from apps.workflows.engine import WorkflowTransitionError

        wf, s1, s2, s3, t1, t2, instance = self._setup()
        with pytest.raises(WorkflowTransitionError):
            perform_transition(instance, t2)
        instance.refresh_from_db()
        assert instance.current_state_id == s1.id

    def test_sets_completed_at_when_entering_terminal_state(self):
        from apps.instances.state_machine import perform_transition

        wf, s1, s2, s3, t1, t2, instance = self._setup()
        # Move to Review first
        perform_transition(instance, t1)
        assert instance.completed_at is None

        instance.refresh_from_db()
        perform_transition(instance, t2)
        instance.refresh_from_db()
        assert instance.completed_at is not None
        assert instance.current_state_id == s3.id

    def test_writes_audit_log_entry(self):
        from apps.audit.models import AuditLog
        from apps.instances.state_machine import perform_transition

        wf, s1, s2, s3, t1, t2, instance = self._setup()
        user = UserFactory()

        before = AuditLog.objects.filter(workflow_instance=instance).count()
        perform_transition(instance, t1, actor=user)
        after = AuditLog.objects.filter(workflow_instance=instance).count()

        assert after == before + 1


# ---------------------------------------------------------------------------
# generate_reference_number
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGenerateReferenceNumber:
    def test_format_uses_reference_prefix(self):
        from apps.instances.models import generate_reference_number

        wf = WorkflowDefinitionFactory(reference_prefix="CLM")
        ref = generate_reference_number(wf)
        assert ref.startswith("CLM-")

    def test_format_includes_year_and_sequence(self):
        import re
        from django.utils import timezone
        from apps.instances.models import generate_reference_number

        wf = WorkflowDefinitionFactory(reference_prefix="HR")
        ref = generate_reference_number(wf)
        year = timezone.now().year
        assert re.match(rf"HR-{year}-\d{{5}}", ref), f"Unexpected format: {ref}"

    def test_sequence_increments_per_workflow(self):
        from apps.instances.models import generate_reference_number

        wf = WorkflowDefinitionFactory(reference_prefix="BUG")
        StateFactory(workflow_definition=wf, is_initial=True, position_order=1, name="Open")
        StateFactory(workflow_definition=wf, is_terminal=True, position_order=2, name="Closed")

        # Create instances to consume sequence slots
        inst1 = WorkflowInstanceFactory(workflow_definition=wf)
        inst2 = WorkflowInstanceFactory(workflow_definition=wf)

        assert inst1.reference_number != inst2.reference_number
        # Sequence numbers should differ by 1
        seq1 = int(inst1.reference_number.split("-")[-1])
        seq2 = int(inst2.reference_number.split("-")[-1])
        assert abs(seq1 - seq2) == 1
