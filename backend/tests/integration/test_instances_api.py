"""Integration tests for the Instances API."""
import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.instances.models import WorkflowInstance
from apps.workflows.models import State, WorkflowDefinition


@pytest.fixture
def setup_context(db):
    """Create a test user, workflow, and instance."""
    user = User.objects.create_user(
        email="test@example.com",
        password="StrongPass123!",
        first_name="Test",
        last_name="User",
    )
    role = Role.objects.create(name=RoleName.PARTICIPANT)
    UserRole.objects.create(user=user, role=role)

    wf = WorkflowDefinition.objects.create(name="Test WF", created_by=user)
    State.objects.create(
        workflow_definition=wf,
        name="Draft",
        is_initial=True,
        is_terminal=False,
        position_order=1,
    )
    instance = WorkflowInstance.objects.create(workflow_definition=wf, created_by=user)
    return user, wf, instance


@pytest.mark.django_db
def test_metadata_update_without_if_match(setup_context):
    """Metadata update should succeed without If-Match header (backwards compatible)."""
    user, wf, instance = setup_context

    client = APIClient()
    client.post(
        "/api/auth/login/",
        {"email": user.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {client.post('/api/auth/login/', {'email': user.email, 'password': 'StrongPass123!'}, format='json').data['access']}")

    new_meta = {"key1": "value1", "priority": 5}
    response = client.patch(
        f"/api/instances/{instance.id}/metadata/",
        {"metadata_json": new_meta},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["metadata_json"] == new_meta

    instance.refresh_from_db()
    assert instance.metadata_json == new_meta


@pytest.mark.django_db
def test_metadata_update_with_matching_if_match(setup_context):
    """Metadata update with matching If-Match should succeed."""
    user, wf, instance = setup_context

    client = APIClient()
    login_resp = client.post(
        "/api/auth/login/",
        {"email": user.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_resp.data['access']}")

    # Get current updated_at
    resp = client.get(f"/api/instances/{instance.id}/")
    current_updated_at = resp.data["updated_at"]

    new_meta = {"priority": 10}
    response = client.patch(
        f"/api/instances/{instance.id}/metadata/",
        {"metadata_json": new_meta},
        format="json",
        HTTP_IF_MATCH=current_updated_at,
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["metadata_json"] == new_meta


@pytest.mark.django_db
def test_metadata_update_with_stale_if_match_returns_409(setup_context):
    """Metadata update with stale If-Match should return 409 Conflict."""
    user, wf, instance = setup_context

    client = APIClient()
    login_resp = client.post(
        "/api/auth/login/",
        {"email": user.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_resp.data['access']}")

    # First update to change updated_at
    new_meta_1 = {"priority": 5}
    client.patch(
        f"/api/instances/{instance.id}/metadata/",
        {"metadata_json": new_meta_1},
        format="json",
    )

    # Try to update with old If-Match (before first update)
    old_updated_at = instance.updated_at.isoformat()

    # Make another update to change updated_at again
    newer_meta = {"priority": 10}
    client.patch(
        f"/api/instances/{instance.id}/metadata/",
        {"metadata_json": newer_meta},
        format="json",
    )

    # Now try with the old timestamp
    response = client.patch(
        f"/api/instances/{instance.id}/metadata/",
        {"metadata_json": {"priority": 15}},
        format="json",
        HTTP_IF_MATCH=old_updated_at,
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert "Conflict" in response.data["detail"]
    assert "current_instance" in response.data

    # Verify the instance was NOT updated
    instance.refresh_from_db()
    assert instance.metadata_json == newer_meta


@pytest.mark.django_db
def test_metadata_update_409_response_includes_current_state(setup_context):
    """409 Conflict response should include current instance state for merge."""
    user, wf, instance = setup_context

    client = APIClient()
    login_resp = client.post(
        "/api/auth/login/",
        {"email": user.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_resp.data['access']}")

    # Update metadata
    new_meta = {"conflict_key": "server_value"}
    client.patch(
        f"/api/instances/{instance.id}/metadata/",
        {"metadata_json": new_meta},
        format="json",
    )

    # Try to update with old timestamp
    response = client.patch(
        f"/api/instances/{instance.id}/metadata/",
        {"metadata_json": {"other_key": "client_value"}},
        format="json",
        HTTP_IF_MATCH="2000-01-01T00:00:00Z",  # Definitely old
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    current = response.data["current_instance"]
    assert current["metadata_json"] == new_meta
    assert current["updated_at"] is not None


@pytest.mark.django_db
def test_concurrent_metadata_edits_last_writer_wins_without_if_match(setup_context):
    """Without If-Match, last write wins (backwards compatible)."""
    user, wf, instance = setup_context

    client = APIClient()
    login_resp = client.post(
        "/api/auth/login/",
        {"email": user.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_resp.data['access']}")

    # User A writes
    client.patch(
        f"/api/instances/{instance.id}/metadata/",
        {"metadata_json": {"key": "value_a"}},
        format="json",
    )

    # User B writes (overwrites A's change)
    response = client.patch(
        f"/api/instances/{instance.id}/metadata/",
        {"metadata_json": {"key": "value_b"}},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["metadata_json"]["key"] == "value_b"


@pytest.mark.django_db
def test_metadata_update_invalid_if_match_format(setup_context):
    """Invalid If-Match format should return 400 Bad Request."""
    user, wf, instance = setup_context

    client = APIClient()
    login_resp = client.post(
        "/api/auth/login/",
        {"email": user.email, "password": "StrongPass123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_resp.data['access']}")

    response = client.patch(
        f"/api/instances/{instance.id}/metadata/",
        {"metadata_json": {"key": "value"}},
        format="json",
        HTTP_IF_MATCH="not-a-valid-timestamp",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid If-Match format" in response.data["detail"]
