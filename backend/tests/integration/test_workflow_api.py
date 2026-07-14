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


# ---------------------------------------------------------------------------
# VISION Layers: workspace theming, ui_schema, export/import
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWorkspaceTheming:
    def test_get_returns_default_workspace(self):
        client, _ = _auth_client()
        resp = client.get("/api/workspace/")
        assert resp.status_code == 200
        assert resp.data["name"] == "FlowForge"
        assert "theme" in resp.data["ui_config"]

    def test_put_updates_theme_for_admin(self):
        client, _ = _auth_client()  # platform_admin via helper
        resp = client.put(
            "/api/workspace/",
            {"name": "Acme Corp", "ui_config": {"theme": {"accent": "#0052cc"}}},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["name"] == "Acme Corp"
        assert resp.data["ui_config"]["theme"]["accent"] == "#0052cc"

    def test_put_denied_for_non_admin(self):
        from conftest import give_role
        from tests.factories import UserFactory
        from django.urls import reverse
        from rest_framework.test import APIClient

        user = UserFactory(password="StrongPass123!")
        give_role(user, "viewer")
        client = APIClient()
        login = client.post(
            reverse("auth-login"),
            {"email": user.email, "password": "StrongPass123!"},
            format="json",
        )
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        resp = client.put("/api/workspace/", {"name": "Hacked"}, format="json")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestUiSchema:
    def test_set_kanban_shell(self):
        client, user = _auth_client()
        wf, *_ = _simple_workflow(user)
        resp = client.patch(
            f"/api/workflows/{wf.id}/ui-schema/",
            {"ui_schema": {"shell": "kanban", "card_fields": ["priority"]}},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["ui_schema"]["shell"] == "kanban"

    def test_unknown_shell_rejected(self):
        client, user = _auth_client()
        wf, *_ = _simple_workflow(user)
        resp = client.patch(
            f"/api/workflows/{wf.id}/ui-schema/",
            {"ui_schema": {"shell": "hologram"}},
            format="json",
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestWorkflowPortability:
    def test_export_import_round_trip(self):
        from apps.workflows.models import Rule

        client, user = _auth_client()
        wf, s_draft, s_review, s_approved, t_submit, t_approve = _simple_workflow(user)
        Rule.objects.create(
            workflow_definition=wf,
            transition=t_approve,
            condition={"field": "value", "operator": "gt", "value": 100},
            action={"type": "block_transition", "reason": "Too big"},
            priority=1,
        )

        resp = client.get(f"/api/workflows/{wf.id}/export/")
        assert resp.status_code == 200
        import json as json_mod

        bundle = json_mod.loads(resp.content)
        assert bundle["kind"] == "flowforge.workflow"
        assert len(bundle["states"]) == 3
        assert len(bundle["transitions"]) == 2
        assert len(bundle["rules"]) == 1

        # Import under a new name
        resp = client.post(
            "/api/workflows/import/",
            {"bundle": bundle, "name": f"{wf.name} (copy)"},
            format="json",
        )
        assert resp.status_code == 201, resp.data
        new_id = resp.data["id"]
        assert new_id != str(wf.id)
        assert len(resp.data["states"]) == 3
        assert len(resp.data["transitions"]) == 2

        # The imported workflow is fully functional: create + transition an instance
        inst = client.post("/api/instances/", {"workflow_definition": new_id}, format="json")
        assert inst.status_code == 201

    def test_import_duplicate_name_rejected(self):
        client, user = _auth_client()
        wf, *_ = _simple_workflow(user)
        resp = client.get(f"/api/workflows/{wf.id}/export/")
        import json as json_mod

        bundle = json_mod.loads(resp.content)
        resp = client.post("/api/workflows/import/", bundle, format="json")
        assert resp.status_code == 400
        assert "already exists" in resp.data["detail"]


@pytest.mark.django_db
class TestUiSchemaValidation:
    def _patch(self, client, wf_id, ui_schema):
        return client.patch(f"/api/workflows/{wf_id}/ui-schema/", {"ui_schema": ui_schema}, format="json")

    def test_all_four_shells_accepted(self):
        client, user = _auth_client()
        wf, *_ = _simple_workflow(user)
        for shell in ("list", "kanban", "table", "calendar"):
            resp = self._patch(client, wf.id, {"shell": shell})
            assert resp.status_code == 200, (shell, resp.data)

    def test_config_shapes_validated(self):
        client, user = _auth_client()
        wf, *_ = _simple_workflow(user)
        assert self._patch(client, wf.id, {"shell": "table", "list_columns": "reference"}).status_code == 400
        assert self._patch(client, wf.id, {"shell": "kanban", "card_fields": [1, 2]}).status_code == 400
        assert self._patch(client, wf.id, {"shell": "calendar", "date_field": ""}).status_code == 400
        assert self._patch(client, wf.id, {"shell": "kanban", "state_display": "red"}).status_code == 400
        ok = self._patch(client, wf.id, {
            "shell": "table",
            "list_columns": ["reference", "state", "metadata.priority"],
            "title_field": "title",
            "state_display": {"Draft": {"colour": "#6b7280"}},
        })
        assert ok.status_code == 200

    def test_bundle_with_invalid_ui_schema_rejected(self):
        client, user = _auth_client()
        wf, *_ = _simple_workflow(user)
        import json as json_mod

        bundle = json_mod.loads(client.get(f"/api/workflows/{wf.id}/export/").content)
        bundle["workflow"]["ui_schema"] = {"shell": "hologram"}
        resp = client.post(
            "/api/workflows/import/", {"bundle": bundle, "name": "Broken import"}, format="json"
        )
        assert resp.status_code == 400
        assert "ui_schema" in resp.data["detail"]


# ---------------------------------------------------------------------------
# Instance containers (hierarchy)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestInstanceContainers:
    def _plan_and_run_workflows(self, client, user):
        """Parent 'Plan' workflow allowing 'Run' children."""
        plan_wf, *_ = _simple_workflow(user)
        run_wf = WorkflowDefinitionFactory(created_by=user, name=f"Run {plan_wf.id.hex[:6]}")
        StateFactory(workflow_definition=run_wf, name="Open", is_initial=True, position_order=1)
        s_done = StateFactory(workflow_definition=run_wf, name="Done", is_terminal=True, position_order=2)
        t_finish = TransitionFactory(
            workflow_definition=run_wf,
            from_state=run_wf.states.get(name="Open"),
            to_state=s_done,
            name="Finish",
        )
        resp = client.patch(
            f"/api/workflows/{plan_wf.id}/ui-schema/",
            {"ui_schema": {"shell": "list", "children": {"workflows": [run_wf.name], "shell": "table", "roll_up": True}}},
            format="json",
        )
        assert resp.status_code == 200
        return plan_wf, run_wf, t_finish

    def _create(self, client, wf_id, parent=None):
        payload = {"workflow_definition": str(wf_id)}
        if parent:
            payload["parent"] = str(parent)
        return client.post("/api/instances/", payload, format="json")

    def test_child_creation_respects_allow_list(self):
        client, user = _auth_client()
        plan_wf, run_wf, _ = self._plan_and_run_workflows(client, user)
        plan = self._create(client, plan_wf.id).data

        ok = self._create(client, run_wf.id, parent=plan["id"])
        assert ok.status_code == 201
        assert str(ok.data["parent"]) == str(plan["id"])
        assert ok.data["parent_reference"] == plan["reference_number"]

        # A Plan inside a Plan is not allowed
        denied = self._create(client, plan_wf.id, parent=plan["id"])
        assert denied.status_code == 400
        assert "does not allow" in str(denied.data)

    def test_children_endpoint_and_rollup_stats(self):
        client, user = _auth_client()
        plan_wf, run_wf, t_finish = self._plan_and_run_workflows(client, user)
        plan = self._create(client, plan_wf.id).data
        child_ids = [self._create(client, run_wf.id, parent=plan["id"]).data["id"] for _ in range(3)]

        children = client.get(f"/api/instances/{plan['id']}/children/")
        assert children.status_code == 200
        assert len(children.data) == 3

        # Complete one child; parent detail rolls up 1/3
        client.post(f"/api/instances/{child_ids[0]}/transition/", {"transition_id": str(t_finish.id)}, format="json")
        detail = client.get(f"/api/instances/{plan['id']}/")
        assert detail.data["children_stats"] == {"total": 3, "completed": 1, "open": 2}

    def test_rollup_rule_blocks_parent_until_children_complete(self):
        from apps.workflows.models import Rule

        client, user = _auth_client()
        plan_wf, run_wf, t_finish = self._plan_and_run_workflows(client, user)
        t_submit = plan_wf.transitions.get(name="Submit")
        Rule.objects.create(
            workflow_definition=plan_wf,
            transition=t_submit,
            condition={"field": "children_complete", "operator": "is_false"},
            action={"type": "block_transition", "reason": "All children must be complete first."},
            priority=1,
        )
        plan = self._create(client, plan_wf.id).data
        child = self._create(client, run_wf.id, parent=plan["id"]).data

        blocked = client.post(
            f"/api/instances/{plan['id']}/transition/", {"transition_id": str(t_submit.id)}, format="json"
        )
        assert blocked.status_code == 400
        assert "children must be complete" in str(blocked.data)

        client.post(f"/api/instances/{child['id']}/transition/", {"transition_id": str(t_finish.id)}, format="json")
        allowed = client.post(
            f"/api/instances/{plan['id']}/transition/", {"transition_id": str(t_submit.id)}, format="json"
        )
        assert allowed.status_code == 200

    def test_move_rejects_cycles_and_disallowed_parents(self):
        client, user = _auth_client()
        plan_wf, run_wf, _ = self._plan_and_run_workflows(client, user)
        plan = self._create(client, plan_wf.id).data
        child = self._create(client, run_wf.id, parent=plan["id"]).data

        # Parent cannot become a child of its own child (also fails allow-list here)
        cyc = client.patch(f"/api/instances/{plan['id']}/move/", {"parent": child["id"]}, format="json")
        assert cyc.status_code == 400

        # Detach works
        detached = client.patch(f"/api/instances/{child['id']}/move/", {"parent": None}, format="json")
        assert detached.status_code == 200
        assert detached.data["parent"] is None

    def test_top_level_filter(self):
        client, user = _auth_client()
        plan_wf, run_wf, _ = self._plan_and_run_workflows(client, user)
        plan = self._create(client, plan_wf.id).data
        self._create(client, run_wf.id, parent=plan["id"])

        top = client.get("/api/instances/?parent__isnull=true")
        assert top.status_code == 200
        refs = [r["reference_number"] for r in top.data["results"]]
        assert plan["reference_number"] in refs
        assert all(r["parent"] is None for r in top.data["results"])
