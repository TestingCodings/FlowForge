"""Integration + unit tests for the secret store (docs/HOOKS.md Part 1)."""
import pytest
from cryptography.fernet import Fernet
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.secrets import crypto
from apps.secrets.models import Secret
from apps.workflows.models import WorkflowDefinition

# A fixed key so tests are deterministic; overrides the (empty) default.
TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
def keyed_settings(settings):
    settings.SECRETS_ENCRYPTION_KEYS = {1: TEST_KEY}
    settings.SECRETS_ENCRYPTION_KEY_CURRENT = 1
    return settings


@pytest.fixture
def designer_client(db):
    user = User.objects.create_user(
        email="d@example.com", password="StrongPass123!", first_name="D", last_name="Z",
    )
    UserRole.objects.create(user=user, role=Role.objects.create(name=RoleName.WORKFLOW_DESIGNER))
    client = APIClient()
    login = client.post("/api/auth/login/", {"email": user.email, "password": "StrongPass123!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return user, client


# ── crypto unit ──

def test_encrypt_decrypt_roundtrip(keyed_settings):
    ct, version = crypto.encrypt("hunter2")
    assert version == 1
    assert b"hunter2" not in ct  # actually encrypted
    assert crypto.decrypt(ct, version) == "hunter2"


def test_encrypt_fails_closed_without_key(settings):
    settings.SECRETS_ENCRYPTION_KEYS = {}
    with pytest.raises(crypto.SecretsNotConfigured):
        crypto.encrypt("x")


def test_key_versioning_decrypts_old_ciphertext(settings):
    k1, k2 = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    settings.SECRETS_ENCRYPTION_KEYS = {1: k1}
    settings.SECRETS_ENCRYPTION_KEY_CURRENT = 1
    ct, v = crypto.encrypt("old")
    # Rotate: add k2 as current, keep k1 for decrypting old rows
    settings.SECRETS_ENCRYPTION_KEYS = {1: k1, 2: k2}
    settings.SECRETS_ENCRYPTION_KEY_CURRENT = 2
    assert crypto.decrypt(ct, v) == "old"           # old key still works
    ct2, v2 = crypto.encrypt("new")
    assert v2 == 2 and crypto.decrypt(ct2, v2) == "new"


def test_redact_scrubs_known_values():
    assert crypto.redact("token=abc123 fine", ["abc123"]) == "token=«redacted» fine"


# ── model ──

@pytest.mark.django_db
def test_model_set_value_encrypts_and_reveals(keyed_settings):
    s = Secret(name="api_key")
    s.set_value("s3cr3t")
    s.save()
    s.refresh_from_db()
    assert bytes(s.ciphertext) != b"s3cr3t"
    assert s.reveal() == "s3cr3t"


@pytest.mark.django_db
def test_resolve_prefers_workflow_scope(keyed_settings):
    wf = WorkflowDefinition.objects.create(name="WF")
    g = Secret(name="tok"); g.set_value("global"); g.save()
    scoped = Secret(name="tok", scope=wf); scoped.set_value("scoped"); scoped.save()
    assert Secret.resolve("tok", wf.id).reveal() == "scoped"
    assert Secret.resolve("tok", None).reveal() == "global"


# ── API ──

@pytest.mark.django_db
def test_create_secret_never_returns_value(keyed_settings, designer_client):
    _, client = designer_client
    resp = client.post("/api/secrets/", {"name": "azure_token", "value": "abc123"}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    assert "value" not in resp.data
    assert resp.data["name"] == "azure_token"
    # And it's genuinely encrypted at rest
    assert Secret.objects.get(id=resp.data["id"]).reveal() == "abc123"


@pytest.mark.django_db
def test_list_never_exposes_values(keyed_settings, designer_client):
    _, client = designer_client
    client.post("/api/secrets/", {"name": "k1", "value": "v1"}, format="json")
    resp = client.get("/api/secrets/")
    rows = resp.data["results"] if "results" in resp.data else resp.data
    assert all("value" not in r for r in rows)


@pytest.mark.django_db
def test_rotate_replaces_value(keyed_settings, designer_client):
    _, client = designer_client
    created = client.post("/api/secrets/", {"name": "k", "value": "old"}, format="json").data
    resp = client.post(f"/api/secrets/{created['id']}/rotate/", {"value": "new"}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    assert Secret.objects.get(id=created["id"]).reveal() == "new"


@pytest.mark.django_db
def test_no_update_endpoint(keyed_settings, designer_client):
    _, client = designer_client
    created = client.post("/api/secrets/", {"name": "k", "value": "v"}, format="json").data
    # PATCH/PUT are not allowed — rotate is the only way to change a value
    assert client.patch(f"/api/secrets/{created['id']}/", {"name": "x"}, format="json").status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
def test_create_fails_closed_without_key(settings, designer_client):
    settings.SECRETS_ENCRYPTION_KEYS = {}
    _, client = designer_client
    resp = client.post("/api/secrets/", {"name": "k", "value": "v"}, format="json")
    assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.django_db
def test_viewer_cannot_create_secret(keyed_settings, db):
    viewer = User.objects.create_user(email="v@example.com", password="StrongPass123!", first_name="V", last_name="R")
    UserRole.objects.create(user=viewer, role=Role.objects.create(name=RoleName.VIEWER))
    client = APIClient()
    login = client.post("/api/auth/login/", {"email": viewer.email, "password": "StrongPass123!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    resp = client.post("/api/secrets/", {"name": "k", "value": "v"}, format="json")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
