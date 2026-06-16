import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from tests.factories import StateFactory, UserFactory, WorkflowDefinitionFactory


@pytest.mark.django_db
def test_core_api_endpoints_are_reachable_with_auth():
    client = APIClient()
    user = UserFactory(password="StrongPass123!")

    login = client.post(
        reverse("auth-login"),
        {"email": user.email, "password": "StrongPass123!"},
        format="json",
    )
    assert login.status_code == 200

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    workflow = WorkflowDefinitionFactory(created_by=user)
    StateFactory(
        workflow_definition=workflow,
        name="Draft",
        display_name="Draft",
        is_initial=True,
        is_terminal=False,
        position_order=1,
    )

    authenticated_get_endpoints = [
        "/api/workflows/",
        "/api/states/",
        "/api/transitions/",
        "/api/rules/",
        "/api/instances/",
        "/api/forms/",
        "/api/submissions/",
        "/api/tasks/",
    ]

    for endpoint in authenticated_get_endpoints:
        response = client.get(endpoint)
        assert response.status_code == 200

    assert client.get(f"/api/audit/{workflow.id}/").status_code == 200

    admin_only_endpoints = [
        "/api/audit/",
        "/api/notification-templates/",
        "/api/notification-logs/",
    ]
    for endpoint in admin_only_endpoints:
        response = client.get(endpoint)
        assert response.status_code == 403
