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
    ({"expr": "sum", "field": "metadata.c"}, "over='children' or over='relationships'"),
    ({"expr": "sum", "over": "children"}, "requires a 'field'"),
    ({"expr": "if"}, "requires a 'cond'"),
])
def test_validation_rejects_bad_computed(spec, frag):
    err = validate_ui_schema({"computed": {"x": spec}})
    assert err and frag in err


# \u2500\u2500 Part 1: over="relationships" \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

@pytest.fixture
def relationship_setup(db):
    """Two instances linked together; wf computes rollups over relationships."""
    from apps.instances.relationships import create_relationship
    user = User.objects.create_user(
        email="r@e.com", password="x", first_name="R", last_name="Z"
    )
    wf = WorkflowDefinition.objects.create(name="Linked", created_by=user, ui_schema={
        "computed": {
            "linked_count":  {"expr": "count", "over": "relationships"},
            "blocks_count":  {"expr": "count", "over": "relationships", "rel_type": "blocks"},
            "linked_total":  {"expr": "sum",   "over": "relationships", "field": "metadata.cost"},
        }
    })
    State.objects.create(workflow_definition=wf, name="Open", is_initial=True, position_order=1)
    inst_a = WorkflowInstance.objects.create(
        workflow_definition=wf, created_by=user, metadata_json={"cost": 10}
    )
    inst_b = WorkflowInstance.objects.create(
        workflow_definition=wf, created_by=user, metadata_json={"cost": 20}
    )
    inst_c = WorkflowInstance.objects.create(
        workflow_definition=wf, created_by=user, metadata_json={"cost": 5}
    )
    # a blocks b (outgoing from a)
    create_relationship(inst_a, inst_b, "blocks", user)
    # c relates_to a (incoming to a)
    create_relationship(inst_c, inst_a, "relates_to", user)
    return wf, inst_a, inst_b, inst_c, user


@pytest.mark.django_db
def test_relationship_count_both_directions(relationship_setup):
    """linked_count aggregates outgoing + incoming relationships."""
    _, inst_a, _, _, _ = relationship_setup
    c = compute_fields(inst_a)
    # a -> b (blocks) and c -> a (relates_to) = 2 total
    assert c["linked_count"] == 2


@pytest.mark.django_db
def test_relationship_count_filtered_by_rel_type(relationship_setup):
    """blocks_count only counts relationships with rel_type='blocks'."""
    _, inst_a, inst_b, _, _ = relationship_setup
    ca = compute_fields(inst_a)
    # a has one 'blocks' link (outgoing)
    assert ca["blocks_count"] == 1
    # b also sees one 'blocks' link (incoming)
    cb = compute_fields(inst_b)
    assert cb["blocks_count"] == 1


@pytest.mark.django_db
def test_relationship_sum(relationship_setup):
    """linked_total sums metadata.cost across both-direction peers."""
    _, inst_a, _inst_b, _inst_c, _ = relationship_setup
    ca = compute_fields(inst_a)
    # inst_a peers: inst_b (cost=20) + inst_c (cost=5) = 25
    assert ca["linked_total"] == 25.0


def test_validation_accepts_relationships():
    schema = {
        "computed": {
            "n": {"expr": "count", "over": "relationships"},
            "t": {"expr": "sum", "over": "relationships", "field": "metadata.c", "rel_type": "blocks"},
        }
    }
    assert validate_ui_schema(schema) is None


def test_validation_rejects_bad_rel_type():
    schema = {"computed": {"n": {"expr": "count", "over": "relationships", "rel_type": ""}}}
    err = validate_ui_schema(schema)
    assert err and "rel_type" in err


# \u2500\u2500 Part 2: ?include=computed list endpoint \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

@pytest.fixture
def api_client_with_computed_wf(db):
    """Workflow with computed fields, two instances, authenticated client."""
    from rest_framework.test import APIClient
    user = User.objects.create_user(
        email="list@e.com", password="StrongPass123!", first_name="L", last_name="Z"
    )
    role = Role.objects.create(name=RoleName.VIEWER)
    UserRole.objects.create(user=user, role=role)

    wf = WorkflowDefinition.objects.create(name="ComputedList", created_by=user, ui_schema={
        "computed": {
            "child_count": {"expr": "count", "over": "children"},
        }
    })
    State.objects.create(workflow_definition=wf, name="Open", is_initial=True, position_order=1)
    parent = WorkflowInstance.objects.create(workflow_definition=wf, created_by=user)
    WorkflowInstance.objects.create(workflow_definition=wf, created_by=user, parent=parent)

    client = APIClient()
    resp = client.post(
        "/api/auth/login/",
        {"email": user.email, "password": "StrongPass123!"},
        format="json",
    )
    token = resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    return client, wf, parent


@pytest.mark.django_db
def test_list_computed_omitted_by_default(api_client_with_computed_wf):
    """Without ?include=computed the computed field is an empty dict."""
    client, wf, _ = api_client_with_computed_wf
    resp = client.get(f"/api/instances/?workflow_definition={wf.id}")
    assert resp.status_code == 200
    for inst in resp.data["results"]:
        assert inst["computed"] == {}


@pytest.mark.django_db
def test_list_computed_present_when_opted_in(api_client_with_computed_wf):
    """With ?include=computed the computed field has real values."""
    client, wf, parent = api_client_with_computed_wf
    resp = client.get(f"/api/instances/?workflow_definition={wf.id}&include=computed")
    assert resp.status_code == 200
    results = {r["id"]: r for r in resp.data["results"]}
    parent_data = results[str(parent.id)]
    assert parent_data["computed"]["child_count"] == 1


@pytest.mark.django_db
def test_list_computed_no_n_plus_one(api_client_with_computed_wf, django_assert_num_queries):
    """?include=computed must not produce per-instance queries (N+1 guard)."""
    client, wf, parent = api_client_with_computed_wf
    # Add a second parent with a child so we have 2 parents.
    user = WorkflowInstance.objects.get(pk=parent.pk).created_by
    parent2 = WorkflowInstance.objects.create(workflow_definition=wf, created_by=user)
    WorkflowInstance.objects.create(workflow_definition=wf, created_by=user, parent=parent2)

    url = f"/api/instances/?workflow_definition={wf.id}&include=computed"
    # The number must stay fixed regardless of instance count (no N+1).
    with django_assert_num_queries(9):
        resp = client.get(url)
    assert resp.status_code == 200
    # Both parents should have child_count == 1
    parents = [r for r in resp.data["results"] if r["computed"].get("child_count") == 1]
    assert len(parents) == 2
