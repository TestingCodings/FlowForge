"""Integration tests for form schema versioning."""
import pytest
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.forms.models import FormDefinition, FormSubmission
from apps.instances.models import WorkflowInstance
from apps.workflows.models import State, WorkflowDefinition


@pytest.fixture
def setup_context(db):
    """Create a test user, workflow, and instance."""
    designer = User.objects.create_user(
        email="designer@example.com",
        password="StrongPass123!",
        first_name="Designer",
        last_name="User",
    )
    participant = User.objects.create_user(
        email="participant@example.com",
        password="StrongPass123!",
        first_name="Participant",
        last_name="User",
    )

    role_designer = Role.objects.create(name=RoleName.WORKFLOW_DESIGNER)
    role_participant = Role.objects.create(name=RoleName.PARTICIPANT)
    UserRole.objects.create(user=designer, role=role_designer)
    UserRole.objects.create(user=participant, role=role_participant)

    wf = WorkflowDefinition.objects.create(name="Test WF", created_by=designer)
    state = State.objects.create(
        workflow_definition=wf,
        name="Draft",
        is_initial=True,
        is_terminal=False,
        position_order=1,
    )
    instance = WorkflowInstance.objects.create(workflow_definition=wf, created_by=designer)

    return designer, participant, wf, state, instance


@pytest.mark.django_db
def test_can_create_form_without_submissions(setup_context):
    """Creating a new form should work."""
    designer, _, wf, state, _ = setup_context

    client = APIClient()
    login_resp = client.post(
        "/api/auth/login/",
        {"email": designer.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_resp.data['access']}")

    form_data = {
        "workflow_definition": str(wf.id),
        "state": str(state.id),
        "name": "My Form",
        "schema": {
            "required_to_transition": True,
            "fields": [
                {"key": "email", "type": "text", "label": "Email", "required": True}
            ],
        },
    }

    response = client.post("/api/forms/", form_data, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["version"] == 1
    assert response.data["name"] == "My Form"


@pytest.mark.django_db
def test_can_edit_form_without_submissions(setup_context):
    """Editing a form without submissions should work."""
    designer, _, wf, state, _ = setup_context

    # Create a form
    form = FormDefinition.objects.create(
        workflow_definition=wf,
        state=state,
        name="Original Form",
        schema={"fields": [{"key": "name", "type": "text"}]},
        created_by=designer,
    )

    client = APIClient()
    login_resp = client.post(
        "/api/auth/login/",
        {"email": designer.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_resp.data['access']}")

    # Edit the form
    new_schema = {"fields": [{"key": "email", "type": "text"}]}
    response = client.patch(
        f"/api/forms/{form.id}/",
        {"name": "Updated Form", "schema": new_schema},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["version"] == 1
    assert response.data["name"] == "Updated Form"


@pytest.mark.django_db
def test_editing_form_with_submissions_creates_new_version(setup_context):
    """Editing a form with submissions should create a new version instead."""
    designer, participant, wf, state, instance = setup_context

    # Create a form
    form = FormDefinition.objects.create(
        workflow_definition=wf,
        state=state,
        name="Original Form",
        schema={"fields": [{"key": "name", "type": "text"}]},
        version=1,
        created_by=designer,
    )

    # Submit the form
    FormSubmission.objects.create(
        workflow_instance=instance,
        form_definition=form,
        form_definition_version=1,
        data={"name": "John"},
        submitted_by=participant,
    )

    client = APIClient()
    login_resp = client.post(
        "/api/auth/login/",
        {"email": designer.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_resp.data['access']}")

    # Try to edit the form
    new_schema = {"fields": [{"key": "email", "type": "text"}]}
    response = client.patch(
        f"/api/forms/{form.id}/",
        {"name": "Updated Form", "schema": new_schema},
        format="json",
    )

    # Should create new version (201 Created) not update (200 OK)
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["form"]["version"] == 2
    assert response.data["form"]["name"] == "Updated Form"
    assert "Form has submissions" in response.data["detail"]

    # Original form should still exist unchanged
    form.refresh_from_db()
    assert form.version == 1
    assert form.name == "Original Form"

    # New form should be v2
    new_form = FormDefinition.objects.get(version=2, state=state)
    assert new_form.name == "Updated Form"


@pytest.mark.django_db
def test_form_submission_captures_version(setup_context):
    """Form submission should capture the form version at submission time."""
    designer, participant, wf, state, instance = setup_context

    # Create form v1
    form_v1 = FormDefinition.objects.create(
        workflow_definition=wf,
        state=state,
        name="Test Form",
        schema={"fields": [{"key": "field1", "type": "text"}]},
        version=1,
        created_by=designer,
    )

    # Submit against v1
    client = APIClient()
    login_resp = client.post(
        "/api/auth/login/",
        {"email": participant.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_resp.data['access']}")

    response = client.post(
        "/api/submissions/",
        {
            "workflow_instance": str(instance.id),
            "form_definition": str(form_v1.id),
            "data": {"field1": "value1"},
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["form_definition_version"] == 1

    # Verify in database
    submission = FormSubmission.objects.get(id=response.data["id"])
    assert submission.form_definition_version == 1


@pytest.mark.django_db
def test_multiple_form_versions_per_state(setup_context):
    """Multiple versions of a form should be allowed per state."""
    designer, _, wf, state, _ = setup_context

    client = APIClient()
    login_resp = client.post(
        "/api/auth/login/",
        {"email": designer.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_resp.data['access']}")

    # Create v1
    form_v1_response = client.post(
        "/api/forms/",
        {
            "workflow_definition": str(wf.id),
            "state": str(state.id),
            "name": "Test Form",
            "schema": {"fields": [{"key": "v1", "type": "text"}]},
        },
        format="json",
    )
    v1_id = form_v1_response.data["id"]
    assert form_v1_response.data["version"] == 1

    # Add submission to v1
    instance = WorkflowInstance.objects.create(workflow_definition=wf, created_by=designer)
    FormSubmission.objects.create(
        workflow_instance=instance,
        form_definition_id=v1_id,
        form_definition_version=1,
        data={"v1": "test"},
    )

    # Edit v1 → creates v2
    response = client.patch(
        f"/api/forms/{v1_id}/",
        {
            "name": "Test Form",
            "schema": {"fields": [{"key": "v2", "type": "text"}]},
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    v2_id = response.data["form"]["id"]
    assert response.data["form"]["version"] == 2

    # Both versions should exist
    v1 = FormDefinition.objects.get(id=v1_id)
    v2 = FormDefinition.objects.get(id=v2_id)
    assert v1.version == 1
    assert v2.version == 2
    assert v1.state_id == v2.state_id == state.id
