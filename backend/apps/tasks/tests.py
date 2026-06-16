import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.instances.models import WorkflowInstance
from apps.tasks.models import Task, TaskStatus
from apps.workflows.models import State, Transition, WorkflowDefinition


@pytest.fixture
def setup_task_workflow(db):
    user = User.objects.create_user(
        email="tasker@example.com",
        password="StrongPass123!",
        first_name="Task",
        last_name="Owner",
    )
    role = Role.objects.create(name=RoleName.PARTICIPANT)
    UserRole.objects.create(user=user, role=role)

    wf = WorkflowDefinition.objects.create(
        name="Task Workflow",
        description="Task assignment workflow",
        version=1,
        is_active=True,
        created_by=user,
    )
    draft = State.objects.create(
        workflow_definition=wf,
        name="Draft",
        is_initial=True,
        is_terminal=False,
        position_order=1,
        requires_task=True,
        task_assigned_role=RoleName.PARTICIPANT,
        task_sla_hours=24,
    )
    review = State.objects.create(
        workflow_definition=wf,
        name="Review",
        is_initial=False,
        is_terminal=False,
        position_order=2,
        requires_task=False,
    )
    Transition.objects.create(
        workflow_definition=wf,
        from_state=draft,
        to_state=review,
        name="Submit",
    )

    return user, wf, draft, review


@pytest.fixture
def auth_client(setup_task_workflow):
    user, _, _, _ = setup_task_workflow
    client = APIClient()
    login = client.post(
        reverse("auth-login"),
        {"email": user.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client, user


@pytest.mark.django_db
class TestTasksApi:
    def test_task_creation_listing_and_completion(self, auth_client, setup_task_workflow):
        client, _ = auth_client
        _, wf, _, review = setup_task_workflow

        create_instance = client.post(
            "/api/instances/",
            {"workflow_definition": str(wf.id), "metadata": {"claim": "A-123"}},
            format="json",
        )
        assert create_instance.status_code == status.HTTP_201_CREATED
        instance_id = create_instance.data["id"]

        task_list = client.get("/api/tasks/")
        assert task_list.status_code == status.HTTP_200_OK
        assert task_list.data["count"] == 1

        task_id = task_list.data["results"][0]["id"]
        complete = client.post(f"/api/tasks/{task_id}/complete/")
        assert complete.status_code == status.HTTP_200_OK
        assert complete.data["status"] == TaskStatus.COMPLETE

        instance = WorkflowInstance.objects.get(id=instance_id)
        assert instance.current_state_id == review.id

        task = Task.objects.get(id=task_id)
        assert task.completed_by_id is not None
