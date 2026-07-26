"""Unit tests for the `set_metadata` rule action.

Before this action existed the only way a transition could write metadata was
an outbound HTTP hook, so any purely-internal state stamp ("record who
approved", "you now hold the key") needed a network round-trip. These cover
the local path.
"""
import pytest

from apps.workflows.models import Rule
from tests.factories import (
    StateFactory,
    TransitionFactory,
    WorkflowDefinitionFactory,
    WorkflowInstanceFactory,
)


def _wf_with_rule(action, condition=None):
    wf = WorkflowDefinitionFactory()
    s1 = StateFactory(workflow_definition=wf, name="Draft", is_initial=True, position_order=1)
    s2 = StateFactory(workflow_definition=wf, name="Review", position_order=2)
    t1 = TransitionFactory(workflow_definition=wf, from_state=s1, to_state=s2, name="Submit")
    Rule.objects.create(
        workflow_definition=wf, transition=t1,
        condition=condition or {"field": "anything", "operator": "is_false"},
        action=action, priority=10,
    )
    instance = WorkflowInstanceFactory(workflow_definition=wf)
    instance.current_state = s1
    instance.save(update_fields=["current_state"])
    return wf, t1, instance


@pytest.mark.django_db
class TestSetMetadataAction:
    def test_writes_values_onto_the_instance(self):
        from apps.workflows.engine import perform_transition

        wf, t1, instance = _wf_with_rule({"type": "set_metadata", "values": {"has_key": True}})
        perform_transition(instance, t1.id)
        instance.refresh_from_db()
        assert instance.metadata_json["has_key"] is True

    def test_merges_rather_than_replaces(self):
        from apps.workflows.engine import perform_transition

        wf, t1, instance = _wf_with_rule({"type": "set_metadata", "values": {"has_key": True}})
        instance.metadata_json = {"player": "Ada"}
        instance.save(update_fields=["metadata_json"])

        perform_transition(instance, t1.id)
        instance.refresh_from_db()
        assert instance.metadata_json == {"player": "Ada", "has_key": True}

    def test_does_not_fire_when_condition_is_false(self):
        from apps.workflows.engine import perform_transition

        wf, t1, instance = _wf_with_rule(
            {"type": "set_metadata", "values": {"has_key": True}},
            condition={"field": "has_key", "operator": "is_true"},
        )
        perform_transition(instance, t1.id)
        instance.refresh_from_db()
        assert "has_key" not in (instance.metadata_json or {})

    def test_ignores_a_malformed_values_payload(self):
        """A bad rule must not 500 the transition — the move still happens."""
        from apps.workflows.engine import perform_transition

        wf, t1, instance = _wf_with_rule({"type": "set_metadata", "values": "has_key"})
        perform_transition(instance, t1.id)
        instance.refresh_from_db()
        assert instance.current_state.name == "Review"
