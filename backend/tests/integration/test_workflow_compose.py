"""Integration tests for the builder compose (diff graph update) endpoint."""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.forms.models import FormDefinition
from apps.instances.models import WorkflowInstance
from apps.workflows.models import Rule, State, Transition, WorkflowDefinition


@pytest.fixture
def designer_client(db):
    designer = User.objects.create_user(
        email="designer@example.com",
        password="StrongPass123!",
        first_name="Designer",
        last_name="User",
    )
    role = Role.objects.create(name=RoleName.WORKFLOW_DESIGNER)
    UserRole.objects.create(user=designer, role=role)

    client = APIClient()
    login = client.post(
        "/api/auth/login/",
        {"email": designer.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return designer, client


@pytest.fixture
def workflow(db, designer_client):
    designer, _ = designer_client
    wf = WorkflowDefinition.objects.create(name="Compose WF", created_by=designer)
    draft = State.objects.create(
        workflow_definition=wf, name="Draft", is_initial=True, position_order=1,
        canvas_position={"x": 50, "y": 100},
    )
    review = State.objects.create(
        workflow_definition=wf, name="Review", position_order=2,
    )
    done = State.objects.create(
        workflow_definition=wf, name="Done", is_terminal=True, position_order=3,
    )
    t1 = Transition.objects.create(
        workflow_definition=wf, from_state=draft, to_state=review, name="Submit",
    )
    t2 = Transition.objects.create(
        workflow_definition=wf, from_state=review, to_state=done, name="Approve",
    )
    return wf, draft, review, done, t1, t2


def graph_payload(wf, states, transitions):
    return {
        "name": wf.name,
        "description": wf.description,
        "reference_prefix": wf.reference_prefix,
        "is_active": wf.is_active,
        "states": states,
        "transitions": transitions,
    }


def state_dict(state, **overrides):
    d = {
        "id": str(state.id),
        "name": state.name,
        "is_initial": state.is_initial,
        "is_terminal": state.is_terminal,
        "position_order": state.position_order,
        "sla_config": state.sla_config,
        "task_config": state.task_config,
        "canvas_position": state.canvas_position,
    }
    d.update(overrides)
    return d


def transition_dict(tr, **overrides):
    d = {
        "id": str(tr.id),
        "name": tr.name,
        "from_state": tr.from_state.name,
        "to_state": tr.to_state.name,
        "requires_approval": tr.requires_approval,
    }
    d.update(overrides)
    return d


@pytest.mark.django_db
def test_compose_updates_state_in_place_preserving_forms(designer_client, workflow):
    """Renaming a state via compose keeps its id, so attached forms survive."""
    designer, client = designer_client
    wf, draft, review, done, t1, t2 = workflow

    form = FormDefinition.objects.create(
        workflow_definition=wf, state=review, name="Review Form",
        schema={"fields": []}, created_by=designer,
    )

    payload = graph_payload(wf, [
        state_dict(draft),
        state_dict(review, name="Peer Review", canvas_position={"x": 300, "y": 100}),
        state_dict(done),
    ], [
        transition_dict(t1, to_state="Peer Review"),
        transition_dict(t2, from_state="Peer Review"),
    ])

    resp = client.put(f"/api/workflows/{wf.id}/compose/", payload, format="json")
    assert resp.status_code == status.HTTP_200_OK

    review.refresh_from_db()
    assert review.name == "Peer Review"
    assert review.canvas_position == {"x": 300, "y": 100}
    form.refresh_from_db()
    assert form.state_id == review.id  # form survived the rename


@pytest.mark.django_db
def test_compose_swapped_names_and_orders(designer_client, workflow):
    """Swapping two states' names/orders must not trip unique constraints."""
    designer, client = designer_client
    wf, draft, review, done, t1, t2 = workflow

    payload = graph_payload(wf, [
        state_dict(draft, name="Review", position_order=2, is_initial=True),
        state_dict(review, name="Draft", position_order=1, is_initial=False),
        state_dict(done),
    ], [
        transition_dict(t1, from_state="Review", to_state="Draft"),
        transition_dict(t2, from_state="Draft", to_state="Done"),
    ])

    resp = client.put(f"/api/workflows/{wf.id}/compose/", payload, format="json")
    assert resp.status_code == status.HTTP_200_OK
    draft.refresh_from_db()
    review.refresh_from_db()
    assert draft.name == "Review" and draft.position_order == 2
    assert review.name == "Draft" and review.position_order == 1


@pytest.mark.django_db
def test_compose_adds_and_deletes_states(designer_client, workflow):
    designer, client = designer_client
    wf, draft, review, done, t1, t2 = workflow

    # Drop Review (and its transitions), add a new Triage state
    payload = graph_payload(wf, [
        state_dict(draft),
        {"name": "Triage", "is_initial": False, "is_terminal": False,
         "position_order": 2, "sla_config": {"sla_hours": 8},
         "task_config": {}, "canvas_position": {"x": 200, "y": 50}},
        state_dict(done),
    ], [
        {"name": "To Triage", "from_state": "Draft", "to_state": "Triage",
         "requires_approval": False},
        {"name": "Finish", "from_state": "Triage", "to_state": "Done",
         "requires_approval": True},
    ])

    resp = client.put(f"/api/workflows/{wf.id}/compose/", payload, format="json")
    assert resp.status_code == status.HTTP_200_OK

    names = set(wf.states.values_list("name", flat=True))
    assert names == {"Draft", "Triage", "Done"}
    assert not Transition.objects.filter(id=t1.id).exists()
    triage = wf.states.get(name="Triage")
    assert triage.sla_config == {"sla_hours": 8}
    finish = wf.transitions.get(name="Finish")
    assert finish.requires_approval is True


@pytest.mark.django_db
def test_compose_deleting_transition_cascades_its_rules_only(designer_client, workflow):
    designer, client = designer_client
    wf, draft, review, done, t1, t2 = workflow

    rule_on_t1 = Rule.objects.create(
        workflow_definition=wf, transition=t1,
        condition={"field": "x", "operator": "eq", "value": 1},
        action={"block_transition": True}, priority=10,
    )
    workflow_rule = Rule.objects.create(
        workflow_definition=wf, transition=None,
        condition={"field": "y", "operator": "eq", "value": 2},
        action={"block_transition": True}, priority=20,
    )

    # Remove t1 but keep everything else
    payload = graph_payload(wf, [
        state_dict(draft), state_dict(review), state_dict(done),
    ], [
        transition_dict(t2),
    ])

    resp = client.put(f"/api/workflows/{wf.id}/compose/", payload, format="json")
    assert resp.status_code == status.HTTP_200_OK
    assert not Rule.objects.filter(id=rule_on_t1.id).exists()
    assert Rule.objects.filter(id=workflow_rule.id).exists()


@pytest.mark.django_db
def test_compose_refused_when_instances_exist(designer_client, workflow):
    designer, client = designer_client
    wf, draft, review, done, t1, t2 = workflow

    WorkflowInstance.objects.create(workflow_definition=wf, created_by=designer)

    payload = graph_payload(wf, [state_dict(draft), state_dict(review), state_dict(done)], [])
    resp = client.put(f"/api/workflows/{wf.id}/compose/", payload, format="json")
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.data["instance_count"] == 1
    # Graph untouched
    assert wf.transitions.count() == 2


@pytest.mark.django_db
def test_compose_validation_errors(designer_client, workflow):
    designer, client = designer_client
    wf, draft, review, done, t1, t2 = workflow

    # No initial state + duplicate names
    payload = graph_payload(wf, [
        state_dict(draft, is_initial=False),
        state_dict(review, name="Done"),
        state_dict(done),
    ], [])
    resp = client.put(f"/api/workflows/{wf.id}/compose/", payload, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    joined = " ".join(resp.data["detail"])
    assert "initial" in joined
    assert "unique" in joined
