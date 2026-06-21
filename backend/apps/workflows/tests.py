import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.instances.models import WorkflowInstance
from apps.workflows.engine import WorkflowTransitionError, validate_transition
from apps.workflows.models import State, Transition, WorkflowDefinition


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(db, api_client):
    user = User.objects.create_user(
        email="phase2@example.com",
        password="StrongPass123!",
        first_name="Phase",
        last_name="Two",
    )
    login_response = api_client.post(
        reverse("auth-login"),
        {"email": user.email, "password": "StrongPass123!"},
        format="json",
    )
    token = login_response.data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client, user


@pytest.mark.django_db
class TestWorkflowEngineApi:
    def test_create_workflow_start_instance_and_transition(self, auth_client):
        client, _ = auth_client

        create_workflow_payload = {
            "name": "Claim Review",
            "description": "Simple three-step claim workflow",
            "reference_prefix": "CLA",
            "version": 1,
            "is_active": True,
            "states": [
                {
                    "name": "Draft",
                    "display_name": "Draft",
                    "is_initial": True,
                    "is_terminal": False,
                    "position_order": 1,
                },
                {
                    "name": "Submitted",
                    "display_name": "Submitted",
                    "is_initial": False,
                    "is_terminal": False,
                    "position_order": 2,
                },
                {
                    "name": "Approved",
                    "display_name": "Approved",
                    "is_initial": False,
                    "is_terminal": True,
                    "position_order": 3,
                },
            ],
            "transitions": [
                {
                    "name": "Submit",
                    "from_state": "Draft",
                    "to_state": "Submitted",
                    "requires_approval": False,
                },
                {
                    "name": "Approve",
                    "from_state": "Submitted",
                    "to_state": "Approved",
                    "requires_approval": True,
                },
            ],
        }

        workflow_create_response = client.post(
            "/api/workflows/", create_workflow_payload, format="json"
        )
        assert workflow_create_response.status_code == status.HTTP_201_CREATED
        workflow_id = workflow_create_response.data["id"]

        workflow_detail_response = client.get(f"/api/workflows/{workflow_id}/")
        assert workflow_detail_response.status_code == status.HTTP_200_OK
        assert len(workflow_detail_response.data["states"]) == 3
        assert len(workflow_detail_response.data["transitions"]) == 2

        submit_transition = next(
            t for t in workflow_detail_response.data["transitions"] if t["name"] == "Submit"
        )
        approve_transition = next(
            t for t in workflow_detail_response.data["transitions"] if t["name"] == "Approve"
        )

        instance_create_response = client.post(
            "/api/instances/",
            {
                "workflow_definition": workflow_id,
                "metadata_json": {"claim_value": 2500, "claimant": "Jane Doe"},
            },
            format="json",
        )
        assert instance_create_response.status_code == status.HTTP_201_CREATED
        assert instance_create_response.data["current_state_name"] == "Draft"
        assert instance_create_response.data["reference_number"].startswith("CLA-")
        instance_id = instance_create_response.data["id"]

        transition_response = client.post(
            f"/api/instances/{instance_id}/transition/",
            {"transition_id": submit_transition["id"]},
            format="json",
        )
        assert transition_response.status_code == status.HTTP_200_OK
        assert transition_response.data["current_state_name"] == "Submitted"

        invalid_transition_response = client.post(
            f"/api/instances/{instance_id}/transition/",
            {"transition_id": submit_transition["id"]},
            format="json",
        )
        assert invalid_transition_response.status_code == status.HTTP_400_BAD_REQUEST

        valid_second_transition = client.post(
            f"/api/instances/{instance_id}/transition/",
            {"transition_id": approve_transition["id"]},
            format="json",
        )
        assert valid_second_transition.status_code == status.HTTP_200_OK
        assert valid_second_transition.data["current_state_name"] == "Approved"


@pytest.mark.django_db
class TestStateMachineCore:
    def test_validate_transition_rejects_wrong_from_state(self):
        user = User.objects.create_user(
            email="engine@example.com",
            password="StrongPass123!",
            first_name="Engine",
            last_name="Test",
        )
        workflow = WorkflowDefinition.objects.create(
            name="Engine Workflow",
            description="Unit test workflow",
            version=1,
            is_active=True,
            created_by=user,
        )
        draft = State.objects.create(
            workflow_definition=workflow,
            name="Draft",
            display_name="Draft",
            is_initial=True,
            is_terminal=False,
            position_order=1,
        )
        submitted = State.objects.create(
            workflow_definition=workflow,
            name="Submitted",
            display_name="Submitted",
            is_initial=False,
            is_terminal=False,
            position_order=2,
        )
        approved = State.objects.create(
            workflow_definition=workflow,
            name="Approved",
            display_name="Approved",
            is_initial=False,
            is_terminal=True,
            position_order=3,
        )

        submit = Transition.objects.create(
            workflow_definition=workflow,
            from_state=draft,
            to_state=submitted,
            name="Submit",
            requires_approval=False,
        )
        approve = Transition.objects.create(
            workflow_definition=workflow,
            from_state=submitted,
            to_state=approved,
            name="Approve",
            requires_approval=True,
        )

        instance = WorkflowInstance.objects.create(
            workflow_definition=workflow,
            created_by=user,
            metadata_json={"unit_test": True},
        )
        assert instance.current_state_id == draft.id

        validate_transition(instance, submit.id)

        with pytest.raises(WorkflowTransitionError):
            validate_transition(instance, approve.id)
