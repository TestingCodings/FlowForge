"""Tests for computed fields (docs/METAMODEL.md §2)."""
import pytest
from datetime import timedelta
from django.utils import timezone

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.instances.models import WorkflowInstance
from apps.workflows.compute import compute_fields
from apps.workflows.rules import evaluate_for_transition
from apps.workflows.models import Rule, State, Transition, WorkflowDefinition
from apps.workflows.ui_schema import validate_ui_schema


@pytest.fixture
def parent_with_children(db):
    user = User.objects.create_user(email="c@e.com", password="x", first_name="C", last_name="Z")
    wf = WorkflowDefinition.objects.create(name="Release", created_by=user, ui_schema={
        "computed": {
            "total_cost": {"expr": "sum", "over": "children", "field": "metadata.cost"},
            "child_count": {"expr": "count", "over": "children"},
            "max_cost": {"expr": "max", "over": "children", "field": "metadata.cost"},
            "risk": {"expr": "if", "cond": {"field": "total", "operator": "gt", "value": 100}, "then": "high", "else": "low"},
        }
    })
    root = State.objects.create(workflow_definition=wf, name="Open", is_initial=True, position_order=1)
    parent = WorkflowInstance.objects.create(workflow_definition=wf, created_by=user, metadata_json={"total": 250})
    for cost in (30, 70, 100):
        WorkflowInstance.objects.create(workflow_definition=wf, created_by=user, parent=parent, metadata_json={"cost": cost})
    return wf, parent, user


@pytest.mark.django_db
def test_children_rollups(parent_with_children):
    wf, parent, user = parent_with_children
    c = compute_fields(parent)
    assert c["total_cost"] == 200
    assert c["child_count"] == 3
    assert c["max_cost"] == 100


@pytest.mark.django_db
def test_conditional(parent_with_children):
    wf, parent, user = parent_with_children
    assert compute_fields(parent)["risk"] == "high"  # total 250 > 100
    parent.metadata_json = {"total": 10}
    assert compute_fields(parent)["risk"] == "low"


@pytest.mark.django_db
def test_age_days(db):
    user = User.objects.create_user(email="a@e.com", password="x", first_name="A", last_name="Z")
    wf = WorkflowDefinition.objects.create(name="Age", created_by=user, ui_schema={
        "computed": {"days_open": {"expr": "age_days", "from": "created_at"}}})
    State.objects.create(workflow_definition=wf, name="Open", is_initial=True, position_order=1)
    inst = WorkflowInstance.objects.create(workflow_definition=wf, created_by=user)
    WorkflowInstance.objects.filter(pk=inst.pk).update(created_at=timezone.now() - timedelta(days=3))
    inst.refresh_from_db()
    assert 2.9 <= compute_fields(inst)["days_open"] <= 3.1


@pytest.mark.django_db
def test_computed_available_to_rules(parent_with_children):
    """A rule can reference a computed value (blocks when total_cost too high)."""
    wf, parent, user = parent_with_children
    done = State.objects.create(workflow_definition=wf, name="Done", is_terminal=True, position_order=2)
    tr = Transition.objects.create(workflow_definition=wf, from_state=parent.current_state, to_state=done, name="Ship")
    Rule.objects.create(
        workflow_definition=wf, transition=tr,
        condition={"field": "total_cost", "operator": "gt", "value": 150},
        action={"type": "block_transition", "reason": "Too expensive"}, priority=10,
    )
    actions = evaluate_for_transition(parent, tr)  # total_cost=200 > 150 → block fires
    assert any(a.get("type") == "block_transition" for a in actions)


def test_validation_accepts_valid_computed():
    assert validate_ui_schema({"computed": {"t": {"expr": "sum", "over": "children", "field": "metadata.c"}}}) is None


@pytest.mark.parametrize("spec,frag", [
    ({"expr": "median", "over": "children", "field": "metadata.c"}, "expr must be one of"),
    ({"expr": "sum", "field": "metadata.c"}, "over='children'"),
    ({"expr": "sum", "over": "children"}, "requires a 'field'"),
    ({"expr": "if"}, "requires a 'cond'"),
])
def test_validation_rejects_bad_computed(spec, frag):
    err = validate_ui_schema({"computed": {"x": spec}})
    assert err and frag in err
