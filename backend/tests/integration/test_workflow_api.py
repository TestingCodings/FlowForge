"""Integration tests for the workflow engine API (Phase 2)."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import (
    StateFactory,
    TransitionFactory,
    UserFactory,
    WorkflowDefinitionFactory,
    WorkflowInstanceFactory,
)


def _auth_client(user=None, password="StrongPass123!"):
    from conftest import give_role

    if user is None:
        user = UserFactory(password=password)
    give_role(user, "platform_admin")
    client = APIClient()
    resp = client.post(
        reverse("auth-login"),
        {"email": user.email, "password": password},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
    return client, user


def _simple_workflow(user=None):
    """Create a Draft -> Review -> Approved workflow and return helpers."""
    wf = WorkflowDefinitionFactory(created_by=user)
    s_draft = StateFactory(workflow_definition=wf, name="Draft", is_initial=True, position_order=1)
    s_review = StateFactory(workflow_definition=wf, name="Review", position_order=2)
    s_approved = StateFactory(
        workflow_definition=wf, name="Approved", is_terminal=True, position_order=3
    )
    t_submit = TransitionFactory(
        workflow_definition=wf, from_state=s_draft, to_state=s_review, name="Submit"
    )
    t_approve = TransitionFactory(
        workflow_definition=wf, from_state=s_review, to_state=s_approved, name="Approve"
    )
    return wf, s_draft, s_review, s_approved, t_submit, t_approve


# ---------------------------------------------------------------------------
# WorkflowDefinition CRUD
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWorkflowDefinitionEndpoints:
    def test_list_requires_auth(self):
        client = APIClient()
        resp = client.get("/api/workflows/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_returns_200_for_authenticated_user(self):
        client, user = _auth_client()
        WorkflowDefinitionFactory()
        resp = client.get("/api/workflows/")
        assert resp.status_code == status.HTTP_200_OK

    def test_create_workflow_with_states_and_transitions(self):
        client, user = _auth_client()
        payload = {
            "name": "Leave Request",
            "description": "Employee leave workflow",
            "states": [
                {"name": "Draft", "is_initial": True, "is_terminal": False, "position_order": 1},
                {"name": "Approved", "is_terminal": True, "is_initial": False, "position_order": 2},
            ],
            "transitions": [
                {"name": "Approve", "from_state": "Draft", "to_state": "Approved"}
            ],
        }
        resp = client.post("/api/workflows/", payload, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.data
        assert data["name"] == "Leave Request"

    def test_create_requires_exactly_one_initial_state(self):
        client, _ = _auth_client()
        payload = {
            "name": "Bad Workflow",
            "states": [
                {"name": "A", "is_initial": False, "is_terminal": False, "position_order": 1},
                {"name": "B", "is_terminal": True, "is_initial": False, "position_order": 2},
            ],
            "transitions": [],
        }
        resp = client.post("/api/workflows/", payload, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_retrieve_returns_states_and_transitions(self):
        client, user = _auth_client()
        wf, *_ = _simple_workflow(user)
        resp = client.get(f"/api/workflows/{wf.id}/")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data["states"]) == 3
        assert len(resp.data["transitions"]) == 2


# ---------------------------------------------------------------------------
# WorkflowInstance creation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWorkflowInstanceCreation:
    def test_create_instance_sets_initial_state(self):
        client, user = _auth_client()
        wf, s_draft, *_ = _simple_workflow(user)

        resp = client.post(
            "/api/instances/",
            {"workflow_definition": str(wf.id)},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["current_state_name"] == "Draft"

    def test_create_instance_generates_reference_number(self):
        client, user = _auth_client()
        wf, *_ = _simple_workflow(user)

        resp = client.post(
            "/api/instances/",
            {"workflow_definition": str(wf.id)},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        ref = resp.data["reference_number"]
        assert ref and len(ref) > 0

    def test_reference_numbers_are_unique(self):
        client, user = _auth_client()
        wf, *_ = _simple_workflow(user)

        refs = set()
        for _ in range(3):
            resp = client.post(
                "/api/instances/",
                {"workflow_definition": str(wf.id)},
                format="json",
            )
            assert resp.status_code == status.HTTP_201_CREATED
            refs.add(resp.data["reference_number"])
        assert len(refs) == 3


# ---------------------------------------------------------------------------
# Workflow transition endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTransitionEndpoint:
    def _create_instance(self, client, wf_id):
        resp = client.post("/api/instances/", {"workflow_definition": str(wf_id)}, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        return resp.data["id"]

    def test_valid_transition_advances_state(self):
        client, user = _auth_client()
        wf, s_draft, s_review, s_approved, t_submit, t_approve = _simple_workflow(user)
        instance_id = self._create_instance(client, wf.id)

        resp = client.post(
            f"/api/instances/{instance_id}/transition/",
            {"transition_id": str(t_submit.id)},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["current_state_name"] == "Review"

    def test_transition_response_includes_transition_info(self):
        client, user = _auth_client()
        wf, s_draft, s_review, *_, t_submit, _ = _simple_workflow(user)
        instance_id = self._create_instance(client, wf.id)

        resp = client.post(
            f"/api/instances/{instance_id}/transition/",
            {"transition_id": str(t_submit.id)},
            format="json",
        )
        assert "transition_applied" in resp.data
        assert resp.data["transition_applied"]["name"] == "Submit"

    def test_invalid_transition_from_wrong_state_returns_400(self):
        client, user = _auth_client()
        wf, s_draft, s_review, s_approved, t_submit, t_approve = _simple_workflow(user)
        instance_id = self._create_instance(client, wf.id)

        # t_approve goes from Review -> Approved; instance is at Draft
        resp = client.post(
            f"/api/instances/{instance_id}/transition/",
            {"transition_id": str(t_approve.id)},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_nonexistent_transition_id_returns_400(self):
        import uuid

        client, user = _auth_client()
        wf, *_ = _simple_workflow(user)
        instance_id = self._create_instance(client, wf.id)

        resp = client.post(
            f"/api/instances/{instance_id}/transition/",
            {"transition_id": str(uuid.uuid4())},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_full_workflow_lifecycle(self):
        """Draft -> Review -> Approved happy path."""
        client, user = _auth_client()
        wf, s_draft, s_review, s_approved, t_submit, t_approve = _simple_workflow(user)
        instance_id = self._create_instance(client, wf.id)

        # Submit
        resp = client.post(
            f"/api/instances/{instance_id}/transition/",
            {"transition_id": str(t_submit.id)},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["current_state_name"] == "Review"

        # Approve
        resp = client.post(
            f"/api/instances/{instance_id}/transition/",
            {"transition_id": str(t_approve.id)},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["current_state_name"] == "Approved"

    def test_unauthenticated_request_returns_401(self):
        import uuid

        client = APIClient()
        resp = client.post(
            f"/api/instances/{uuid.uuid4()}/transition/",
            {"transition_id": str(uuid.uuid4())},
            format="json",
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Audit trail written on transition
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBulkOperations:
    def _create_instances(self, client, wf_id, n):
        ids = []
        for _ in range(n):
            resp = client.post("/api/instances/", {"workflow_definition": str(wf_id)}, format="json")
            assert resp.status_code == status.HTTP_201_CREATED
            ids.append(resp.data["id"])
        return ids

    def test_bulk_transition_advances_all(self):
        client, user = _auth_client()
        wf, s_draft, s_review, *_ , t_submit, _ = _simple_workflow(user)
        ids = self._create_instances(client, wf.id, 3)

        resp = client.post(
            "/api/instances/bulk-transition/",
            {"instance_ids": ids, "transition_id": str(t_submit.id)},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["succeeded"] == 3
        assert resp.data["failed"] == 0
        assert all(r["status"] == "ok" for r in resp.data["results"])

        from apps.instances.models import WorkflowInstance

        assert (
            WorkflowInstance.objects.filter(id__in=ids, current_state=s_review).count() == 3
        )

    def test_bulk_transition_reports_partial_failures(self):
        client, user = _auth_client()
        wf, s_draft, s_review, s_approved, t_submit, t_approve = _simple_workflow(user)
        ids = self._create_instances(client, wf.id, 3)

        # Advance one instance to Review so t_submit is invalid for it
        client.post(
            f"/api/instances/{ids[0]}/transition/",
            {"transition_id": str(t_submit.id)},
            format="json",
        )

        resp = client.post(
            "/api/instances/bulk-transition/",
            {"instance_ids": ids, "transition_id": str(t_submit.id)},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["succeeded"] == 2
        assert resp.data["failed"] == 1
        by_id = {r["id"]: r for r in resp.data["results"]}
        assert by_id[ids[0]]["status"] == "blocked"

    def test_bulk_transition_validates_input(self):
        client, user = _auth_client()
        wf, *_ , t_submit, _ = _simple_workflow(user)

        resp = client.post(
            "/api/instances/bulk-transition/",
            {"instance_ids": [], "transition_id": str(t_submit.id)},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

        resp = client.post(
            "/api/instances/bulk-transition/",
            {"instance_ids": ["not-a-uuid"], "transition_id": str(t_submit.id)},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["results"][0]["status"] == "error"

    def test_direct_instance_update_and_delete_are_blocked(self):
        client, user = _auth_client()
        wf, *_ = _simple_workflow(user)
        iid = self._create_instances(client, wf.id, 1)[0]

        assert client.patch(f"/api/instances/{iid}/", {"metadata_json": {}}, format="json").status_code == 405
        assert client.delete(f"/api/instances/{iid}/").status_code == 405
        # ...while the metadata action endpoint accepts PATCH
        resp = client.patch(
            f"/api/instances/{iid}/metadata/", {"metadata_json": {"k": 1}}, format="json"
        )
        assert resp.status_code == 200

    def test_export_csv_includes_metadata_columns(self):
        client, user = _auth_client()
        wf, *_ = _simple_workflow(user)
        ids = self._create_instances(client, wf.id, 2)
        client.patch(
            f"/api/instances/{ids[0]}/metadata/",
            {"metadata_json": {"priority": "high"}},
            format="json",
        )

        resp = client.get(f"/api/instances/export/?ids={','.join(ids)}")
        assert resp.status_code == status.HTTP_200_OK
        assert resp["Content-Type"] == "text/csv"
        body = resp.content.decode()
        lines = [l for l in body.strip().splitlines() if l]
        assert len(lines) == 3  # header + 2 rows
        assert "metadata.priority" in lines[0]
        assert "high" in body


@pytest.mark.django_db
class TestAuditTrailOnTransition:
    def test_audit_log_created_after_transition(self):
        from apps.audit.models import AuditLog

        client, user = _auth_client()
        wf, s_draft, s_review, *_, t_submit, _ = _simple_workflow(user)
        resp = client.post("/api/instances/", {"workflow_definition": str(wf.id)}, format="json")
        instance_id = resp.data["id"]

        before = AuditLog.objects.filter(workflow_instance_id=instance_id).count()

        client.post(
            f"/api/instances/{instance_id}/transition/",
            {"transition_id": str(t_submit.id)},
            format="json",
        )

        after = AuditLog.objects.filter(workflow_instance_id=instance_id).count()
        assert after > before
