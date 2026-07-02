import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.forms.models import FormSubmission
from conftest import give_role
from apps.instances.models import WorkflowInstance
from apps.workflows.models import State, Transition, WorkflowDefinition


@pytest.fixture
def auth_client(db):
    client = APIClient()
    user = User.objects.create_user(
        email="forms@example.com",
        password="StrongPass123!",
        first_name="Form",
        last_name="Tester",
    )
    give_role(user, "platform_admin")
    login = client.post(
        reverse("auth-login"),
        {"email": user.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client, user


@pytest.fixture
def workflow_instance(auth_client):
    _, user = auth_client
    wf = WorkflowDefinition.objects.create(
        name="Forms Workflow",
        description="Form validation workflow",
        version=1,
        is_active=True,
        created_by=user,
    )
    s1 = State.objects.create(
        workflow_definition=wf,
        name="Draft",
        is_initial=True,
        is_terminal=False,
        position_order=1,
    )
    s2 = State.objects.create(
        workflow_definition=wf,
        name="Submitted",
        is_initial=False,
        is_terminal=True,
        position_order=2,
    )
    Transition.objects.create(
        workflow_definition=wf,
        from_state=s1,
        to_state=s2,
        name="Submit",
    )
    instance = WorkflowInstance.objects.create(workflow_definition=wf, created_by=user)
    return wf, s1, instance


@pytest.mark.django_db
class TestFormsApi:
    def test_form_definition_and_submission_validation(self, auth_client, workflow_instance):
        client, _ = auth_client
        wf, state, instance = workflow_instance

        form_payload = {
            "workflow_definition": str(wf.id),
            "state": str(state.id),
            "name": "Claim Intake",
            "schema": {
                "fields": [
                    {"name": "claim_value", "type": "number", "required": True, "min": 0},
                    {"name": "description", "type": "text", "required": True},
                    {"name": "category", "type": "dropdown", "required": True},
                ]
            },
            "version": 1,
        }
        form_response = client.post("/api/forms/", form_payload, format="json")
        assert form_response.status_code == status.HTTP_201_CREATED
        form_id = form_response.data["id"]

        valid_submission = client.post(
            "/api/submissions/",
            {
                "workflow_instance": str(instance.id),
                "form_definition": form_id,
                "data": {
                    "claim_value": 1500,
                    "description": "Water damage",
                    "category": "Property",
                },
            },
            format="json",
        )
        assert valid_submission.status_code == status.HTTP_201_CREATED
        submission_id = valid_submission.data["id"]
        assert FormSubmission.objects.filter(id=submission_id).exists()

        invalid_submission = client.post(
            "/api/submissions/",
            {
                "workflow_instance": str(instance.id),
                "form_definition": form_id,
                "data": {
                    "claim_value": 1500,
                    "category": "Property",
                },
            },
            format="json",
        )
        assert invalid_submission.status_code == status.HTTP_400_BAD_REQUEST
        assert "description" in str(invalid_submission.data)

        patch_submission = client.patch(
            f"/api/submissions/{submission_id}/",
            {"data": {"description": "updated"}},
            format="json",
        )
        assert patch_submission.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
