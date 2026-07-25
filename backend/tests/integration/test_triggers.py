"""Integration tests for inbound triggers."""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.instances.models import Trigger, WorkflowInstance
from apps.workflows.models import Rule, State, Transition, WorkflowDefinition


@pytest.fixture
def setup(db):
    designer = User.objects.create_user(
        email="d@example.com", password="StrongPass123!", first_name="D", last_name="Z",
    )
    UserRole.objects.create(user=designer, role=Role.objects.create(name=RoleName.WORKFLOW_DESIGNER))

    wf = WorkflowDefinition.objects.create(name="Deploys", created_by=designer)
    building = State.objects.create(workflow_definition=wf, name="Building", is_initial=True, position_order=1)
    done = State.objects.create(workflow_definition=wf, name="Deployed", is_terminal=True, position_order=2)
    tr = Transition.objects.create(workflow_definition=wf, from_state=building, to_state=done, name="Finish")

    client = APIClient()
    login = client.post("/api/auth/login/", {"email": designer.email, "password": "StrongPass123!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return designer, client, wf, building, done, tr


@pytest.mark.django_db
def test_designer_creates_trigger_and_gets_token(setup):
    designer, client, wf, building, done, tr = setup
    resp = client.post("/api/triggers/", {
        "name": "CI creates deploy", "workflow_definition": str(wf.id),
        "action": "create_instance", "metadata_mapping": {"build": "build_number"},
    }, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["token"]
    assert resp.data["fire_path"] == f"/api/trigger/{resp.data['token']}/"


@pytest.mark.django_db
def test_fire_transition_trigger_requires_transition(setup):
    designer, client, wf, building, done, tr = setup
    resp = client.post("/api/triggers/", {
        "name": "bad", "workflow_definition": str(wf.id), "action": "fire_transition",
    }, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_create_instance_trigger_fires_unauthenticated(setup):
    designer, client, wf, building, done, tr = setup
    trigger = Trigger.objects.create(
        name="CI", workflow_definition=wf, action=Trigger.Action.CREATE_INSTANCE,
        metadata_mapping={"build": "build_number"}, created_by=designer,
    )

    anon = APIClient()  # no credentials — the token is the credential
    resp = anon.post(f"/api/trigger/{trigger.token}/", {"build_number": "v1.2.3", "extra": "ignored"}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED

    inst = WorkflowInstance.objects.get(workflow_definition=wf)
    assert inst.metadata_json == {"build": "v1.2.3"}  # only mapped keys
    assert inst.current_state_id == building.id
    trigger.refresh_from_db()
    assert trigger.trigger_count == 1
    assert trigger.last_triggered_at is not None


@pytest.mark.django_db
def test_fire_transition_trigger_advances_instance(setup):
    designer, client, wf, building, done, tr = setup
    inst = WorkflowInstance.objects.create(workflow_definition=wf, created_by=designer)
    trigger = Trigger.objects.create(
        name="CI done", workflow_definition=wf, action=Trigger.Action.FIRE_TRANSITION,
        transition=tr, lookup_field="reference_number", created_by=designer,
    )

    anon = APIClient()
    resp = anon.post(f"/api/trigger/{trigger.token}/", {"reference_number": inst.reference_number}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["to_state"] == "Deployed"
    inst.refresh_from_db()
    assert inst.current_state_id == done.id
    assert inst.completed_at is not None


@pytest.mark.django_db
def test_fire_transition_lookup_by_metadata(setup):
    designer, client, wf, building, done, tr = setup
    inst = WorkflowInstance.objects.create(
        workflow_definition=wf, created_by=designer, metadata_json={"build": "v9"},
    )
    trigger = Trigger.objects.create(
        name="by build", workflow_definition=wf, action=Trigger.Action.FIRE_TRANSITION,
        transition=tr, lookup_field="metadata.build", created_by=designer,
    )

    resp = APIClient().post(f"/api/trigger/{trigger.token}/", {"build": "v9"}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    inst.refresh_from_db()
    assert inst.current_state_id == done.id


@pytest.mark.django_db
def test_blocked_transition_returns_reason(setup):
    designer, client, wf, building, done, tr = setup
    # Blocks the Finish transition while "approved" is not true — with no
    # approved flag in metadata, is_false fires and the block applies.
    Rule.objects.create(
        workflow_definition=wf, transition=tr,
        condition={"field": "approved", "operator": "is_false"},
        action={"type": "block_transition", "reason": "Needs approval"}, priority=10,
    )
    inst = WorkflowInstance.objects.create(workflow_definition=wf, created_by=designer)
    trigger = Trigger.objects.create(
        name="CI", workflow_definition=wf, action=Trigger.Action.FIRE_TRANSITION,
        transition=tr, created_by=designer,
    )

    resp = APIClient().post(f"/api/trigger/{trigger.token}/", {"reference_number": inst.reference_number}, format="json")
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.data["blocked"] is True
    inst.refresh_from_db()
    assert inst.current_state_id == building.id  # unchanged


@pytest.mark.django_db
def test_unknown_or_inactive_token_404(setup):
    designer, client, wf, building, done, tr = setup
    assert APIClient().post("/api/trigger/nope/", {}, format="json").status_code == status.HTTP_404_NOT_FOUND

    trigger = Trigger.objects.create(
        name="off", workflow_definition=wf, action=Trigger.Action.CREATE_INSTANCE,
        is_active=False, created_by=designer,
    )
    assert APIClient().post(f"/api/trigger/{trigger.token}/", {}, format="json").status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_missing_lookup_value_404(setup):
    designer, client, wf, building, done, tr = setup
    trigger = Trigger.objects.create(
        name="CI", workflow_definition=wf, action=Trigger.Action.FIRE_TRANSITION,
        transition=tr, lookup_field="reference_number", created_by=designer,
    )
    # Payload lacks reference_number
    resp = APIClient().post(f"/api/trigger/{trigger.token}/", {"nope": 1}, format="json")
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_creating_trigger_requires_designer(setup):
    designer, client, wf, building, done, tr = setup
    viewer = User.objects.create_user(email="v@example.com", password="StrongPass123!", first_name="V", last_name="R")
    UserRole.objects.create(user=viewer, role=Role.objects.create(name=RoleName.VIEWER))
    vc = APIClient()
    login = vc.post("/api/auth/login/", {"email": viewer.email, "password": "StrongPass123!"}, format="json")
    vc.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    resp = vc.post("/api/triggers/", {
        "name": "x", "workflow_definition": str(wf.id), "action": "create_instance",
    }, format="json")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
