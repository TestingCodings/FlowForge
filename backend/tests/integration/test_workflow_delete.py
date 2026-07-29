"""Deleting a workflow that is in use must fail cleanly.

`destroy` called straight through to Django, so a workflow with instances
raised ProtectedError as an unhandled exception — HTTP 500 with a stack
trace, on an action any designer might attempt. A foreseeable refusal should
be a clear 409, not a crash.

(States cascade; it is instances and their tasks that protect.)
"""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.instances.models import WorkflowInstance
from apps.workflows.models import State, WorkflowDefinition


@pytest.fixture
def designer(db):
    user = User.objects.create_user(
        email="deleter@example.com", password="StrongPass123!", first_name="D", last_name="L",
    )
    role, _ = Role.objects.get_or_create(name=RoleName.WORKFLOW_DESIGNER)
    UserRole.objects.create(user=user, role=role)
    client = APIClient()
    client.force_authenticate(user)
    return client, user


@pytest.mark.django_db
class TestWorkflowDelete:
    def test_bare_workflow_deletes(self, designer):
        client, user = designer
        wf = WorkflowDefinition.objects.create(name="Disposable", reference_prefix="DIS", created_by=user)
        assert client.delete(f"/api/workflows/{wf.id}/").status_code == 204

    def _in_use(self, user, name, prefix):
        wf = WorkflowDefinition.objects.create(name=name, reference_prefix=prefix, created_by=user)
        state = State.objects.create(
            workflow_definition=wf, name="Open", is_initial=True, position_order=1)
        WorkflowInstance.objects.create(
            workflow_definition=wf, current_state=state, created_by=user)
        return wf

    def test_workflow_with_instances_refuses_cleanly(self, designer):
        client, user = designer
        wf = self._in_use(user, "Has Instances", "HIN")

        resp = client.delete(f"/api/workflows/{wf.id}/")
        assert resp.status_code == 409, f"expected a clean refusal, got {resp.status_code}"
        assert "detail" in resp.data

    def test_refusal_explains_why(self, designer):
        client, user = designer
        wf = self._in_use(user, "Has Instances 2", "HI2")

        detail = str(client.delete(f"/api/workflows/{wf.id}/").data["detail"]).lower()
        assert "in use" in detail and "instances" in detail

    def test_workflow_survives_a_refused_delete(self, designer):
        client, user = designer
        wf = self._in_use(user, "Survivor", "SUR")

        client.delete(f"/api/workflows/{wf.id}/")
        assert WorkflowDefinition.objects.filter(pk=wf.pk).exists()
