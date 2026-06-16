import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def registered_user(db):
    return User.objects.create_user(
        email="test@example.com",
        password="StrongPass123!",
        first_name="Test",
        last_name="User",
    )


@pytest.mark.django_db
class TestRegisterView:
    def test_register_creates_user(self, api_client):
        url = reverse("auth-register")
        payload = {
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "User",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        }
        response = api_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "new@example.com"
        assert User.objects.filter(email="new@example.com").exists()

    def test_register_password_mismatch(self, api_client):
        url = reverse("auth-register")
        payload = {
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "User",
            "password": "StrongPass123!",
            "password_confirm": "WrongPass123!",
        }
        response = api_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_duplicate_email(self, api_client, registered_user):
        url = reverse("auth-register")
        payload = {
            "email": registered_user.email,
            "first_name": "Dup",
            "last_name": "User",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        }
        response = api_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_does_not_return_password(self, api_client):
        url = reverse("auth-register")
        payload = {
            "email": "nopass@example.com",
            "first_name": "No",
            "last_name": "Pass",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        }
        response = api_client.post(url, payload, format="json")
        assert "password" not in response.data


@pytest.mark.django_db
class TestLoginView:
    def test_login_returns_tokens(self, api_client, registered_user):
        url = reverse("auth-login")
        response = api_client.post(
            url, {"email": registered_user.email, "password": "StrongPass123!"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data
        assert "user" in response.data

    def test_login_wrong_password(self, api_client, registered_user):
        url = reverse("auth-login")
        response = api_client.post(
            url, {"email": registered_user.email, "password": "WrongPass!"}, format="json"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_user(self, api_client):
        url = reverse("auth-login")
        response = api_client.post(
            url, {"email": "nobody@example.com", "password": "Whatever123!"}, format="json"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestProtectedEndpoint:
    def test_health_check_is_public(self, api_client):
        url = reverse("health-check")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "ok"

    def test_unauthenticated_request_returns_401(self, api_client):
        # Any protected endpoint — use DRF's built-in user list as a proxy,
        # or a simple protected view. We test via the JWT token refresh endpoint
        # with a bogus token to confirm 401 behaviour.
        url = reverse("auth-refresh")
        response = api_client.post(url, {"refresh": "not-a-real-token"}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
