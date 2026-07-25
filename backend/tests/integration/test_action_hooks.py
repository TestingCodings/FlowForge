"""Tests for outbound safety, templating, and `after` action hooks."""
import pytest
from cryptography.fernet import Fernet
from unittest.mock import MagicMock, patch

from apps.accounts.models import Role, RoleName, User, UserRole
from apps.notifications import outbound
from apps.notifications.hooks import _execute_hook_impl, run_after_hooks
from apps.notifications.models import HookExecutionLog, TransitionHook
from apps.instances.models import WorkflowInstance
from apps.secrets.models import Secret
from apps.workflows.models import State, Transition, WorkflowDefinition

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
def keyed(settings):
    settings.SECRETS_ENCRYPTION_KEYS = {1: TEST_KEY}
    settings.SECRETS_ENCRYPTION_KEY_CURRENT = 1
    settings.OUTBOUND_ALLOWED_HOSTS = []
    return settings


@pytest.fixture
def wf(db):
    user = User.objects.create_user(email="d@e.com", password="x", first_name="D", last_name="Z")
    w = WorkflowDefinition.objects.create(name="Deploys", created_by=user)
    building = State.objects.create(workflow_definition=w, name="Building", is_initial=True, position_order=1)
    done = State.objects.create(workflow_definition=w, name="Deployed", is_terminal=True, position_order=2)
    tr = Transition.objects.create(workflow_definition=w, from_state=building, to_state=done, name="Finish")
    inst = WorkflowInstance.objects.create(workflow_definition=w, created_by=user, metadata_json={"env": "prod"})
    return w, tr, inst, user


# ── SSRF guard ──

@pytest.mark.parametrize("url", [
    "http://localhost/x", "http://127.0.0.1/x", "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.5/x", "http://192.168.1.1/x", "ftp://example.com/x",
])
def test_ssrf_guard_blocks_unsafe_urls(url):
    with pytest.raises(outbound.UnsafeURLError):
        outbound.assert_safe_url(url)


def test_ssrf_guard_allows_public_host():
    # Resolves to a public IP; should not raise.
    outbound.assert_safe_url("https://example.com/webhook")


def test_ssrf_allow_list(settings):
    settings.OUTBOUND_ALLOWED_HOSTS = ["hooks.example.com"]
    with pytest.raises(outbound.UnsafeURLError):
        outbound.assert_safe_url("https://example.com/x")  # not in allow-list


# ── templating ──

def test_render_template_resolves_all_kinds(wf):
    _, _, inst, _ = wf
    out = outbound.render_template(
        "u={{instance.reference_number}} e={{metadata.env}} t={{secret.TOK}}",
        instance=inst, secret_values={"TOK": "abc"},
    )
    assert inst.reference_number in out
    assert "e=prod" in out and "t=abc" in out


def test_referenced_secret_names():
    assert outbound.referenced_secret_names("{{secret.A}} {{metadata.x}} {{secret.B}}") == {"A", "B"}


# ── after hooks ──

@pytest.mark.django_db
def test_after_hook_fires_and_writes_output(keyed, wf):
    w, tr, inst, user = wf
    s = Secret(name="TOK", scope=w); s.set_value("topsecret"); s.save()
    hook = TransitionHook.objects.create(
        transition=tr, trigger="after", action="http_request",
        config={"url": "https://api.example.com/deploy", "method": "POST",
                "headers": {"Authorization": "Bearer {{secret.TOK}}"},
                "body_template": '{"ref":"{{instance.reference_number}}"}'},
        output_to="metadata.deploy_id", created_by=user,
    )
    log = HookExecutionLog.objects.create(hook=hook, workflow_instance=inst)

    fake = MagicMock(status_code=200, text='{"id": "dep-42"}')
    fake.json.return_value = {"id": "dep-42"}
    fake.raise_for_status.return_value = None
    with patch("apps.notifications.hooks.httpx.request", return_value=fake) as m, \
         patch("apps.notifications.hooks.assert_safe_url"):
        _execute_hook_impl(str(log.id))

    log.refresh_from_db(); inst.refresh_from_db()
    assert log.status == HookExecutionLog.Status.SUCCEEDED
    # secret went out in the header…
    sent_headers = m.call_args.kwargs["headers"]
    assert sent_headers["Authorization"] == "Bearer topsecret"
    # …but is redacted from the log
    assert "topsecret" not in (log.request_summary + log.response_summary + log.error_message)
    # output_to wrote the response into metadata
    assert inst.metadata_json["deploy_id"] == {"id": "dep-42"}


@pytest.mark.django_db
def test_after_hook_failure_marks_failed(keyed, wf):
    w, tr, inst, user = wf
    hook = TransitionHook.objects.create(
        transition=tr, trigger="after", action="probe",
        config={"url": "https://api.example.com/health", "expect_status": 200}, created_by=user,
    )
    log = HookExecutionLog.objects.create(hook=hook, workflow_instance=inst)
    fake = MagicMock(status_code=503, text="down")
    fake.raise_for_status.return_value = None
    with patch("apps.notifications.hooks.httpx.request", return_value=fake), \
         patch("apps.notifications.hooks.assert_safe_url"), pytest.raises(Exception):
        _execute_hook_impl(str(log.id))
    log.refresh_from_db()
    assert log.status == HookExecutionLog.Status.FAILED  # expect_status mismatch → retry


@pytest.mark.django_db
def test_run_after_hooks_queues_only_active_after(keyed, wf):
    w, tr, inst, user = wf
    TransitionHook.objects.create(transition=tr, trigger="after", action="probe",
                                  config={"url": "https://x.example.com"}, is_active=True, created_by=user)
    TransitionHook.objects.create(transition=tr, trigger="after", action="probe",
                                  config={"url": "https://y.example.com"}, is_active=False, created_by=user)
    with patch("apps.notifications.hooks.execute_hook_task") as task:
        run_after_hooks(inst, tr)
    assert task.delay.call_count == 1  # only the active hook
    assert HookExecutionLog.objects.filter(workflow_instance=inst).count() == 1


# ── management API ──

@pytest.mark.django_db
def test_hook_api_validation(db):
    designer = User.objects.create_user(email="w@e.com", password="StrongPass123!", first_name="W", last_name="D")
    UserRole.objects.create(user=designer, role=Role.objects.create(name=RoleName.WORKFLOW_DESIGNER))
    w = WorkflowDefinition.objects.create(name="W", created_by=designer)
    b = State.objects.create(workflow_definition=w, name="B", is_initial=True, position_order=1)
    d = State.objects.create(workflow_definition=w, name="D", is_terminal=True, position_order=2)
    tr = Transition.objects.create(workflow_definition=w, from_state=b, to_state=d, name="Go")

    from rest_framework.test import APIClient
    client = APIClient()
    login = client.post("/api/auth/login/", {"email": designer.email, "password": "StrongPass123!"}, format="json")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    # before hooks are valid now
    r1 = client.post("/api/hooks/", {"transition": str(tr.id), "trigger": "before", "on_failure": "block",
                                     "action": "probe", "config": {"url": "https://x.example.com"}}, format="json")
    assert r1.status_code == 201
    # block only makes sense on a before hook
    r2 = client.post("/api/hooks/", {"transition": str(tr.id), "trigger": "after", "on_failure": "block",
                                     "action": "http_request", "config": {"url": "https://x.example.com"}}, format="json")
    assert r2.status_code == 400
    # missing url
    r3 = client.post("/api/hooks/", {"transition": str(tr.id), "trigger": "after",
                                     "action": "http_request", "config": {}}, format="json")
    assert r3.status_code == 400


# ── before hooks (gating, via the engine) ──

@pytest.mark.django_db
def test_before_hook_block_aborts_transition(keyed, wf):
    from apps.workflows.engine import perform_transition, WorkflowTransitionError
    w, tr, inst, user = wf
    TransitionHook.objects.create(
        transition=tr, trigger="before", action="probe", on_failure="block",
        config={"url": "https://health.example.com", "expect_status": 200}, created_by=user,
    )
    fake = MagicMock(status_code=503, text="down")
    fake.raise_for_status.return_value = None
    with patch("apps.notifications.hooks.httpx.request", return_value=fake), \
         patch("apps.notifications.hooks.assert_safe_url"):
        with pytest.raises(WorkflowTransitionError, match="Blocked by hook"):
            perform_transition(inst, tr.id)
    inst.refresh_from_db()
    assert inst.current_state_id == tr.from_state_id  # unchanged


@pytest.mark.django_db
def test_before_hook_warn_proceeds(keyed, wf):
    from apps.workflows.engine import perform_transition
    w, tr, inst, user = wf
    TransitionHook.objects.create(
        transition=tr, trigger="before", action="probe", on_failure="warn",
        config={"url": "https://health.example.com", "expect_status": 200}, created_by=user,
    )
    fake = MagicMock(status_code=503, text="down")
    fake.raise_for_status.return_value = None
    with patch("apps.notifications.hooks.httpx.request", return_value=fake), \
         patch("apps.notifications.hooks.assert_safe_url"):
        perform_transition(inst, tr.id)  # does not raise
    inst.refresh_from_db()
    assert inst.current_state_id == tr.to_state_id  # advanced despite the failure
    assert HookExecutionLog.objects.filter(hook__transition=tr, status="failed").exists()


@pytest.mark.django_db
def test_before_hook_success_writes_output_and_advances(keyed, wf):
    from apps.workflows.engine import perform_transition
    w, tr, inst, user = wf
    TransitionHook.objects.create(
        transition=tr, trigger="before", action="http_request", on_failure="block",
        config={"url": "https://provision.example.com"}, output_to="metadata.device_id", created_by=user,
    )
    fake = MagicMock(status_code=200, text='{"device_id": "dev-9"}')
    fake.json.return_value = {"device_id": "dev-9"}
    fake.raise_for_status.return_value = None
    with patch("apps.notifications.hooks.httpx.request", return_value=fake), \
         patch("apps.notifications.hooks.assert_safe_url"):
        perform_transition(inst, tr.id)
    inst.refresh_from_db()
    assert inst.current_state_id == tr.to_state_id
    assert inst.metadata_json["device_id"] == {"device_id": "dev-9"}


@pytest.mark.django_db
def test_transition_rechecks_state_under_lock(keyed, wf):
    """If the instance moves between pre-flight and commit, the transition aborts."""
    from apps.workflows.engine import perform_transition, WorkflowTransitionError
    w, tr, inst, user = wf

    # A before-hook whose side effect is to advance the instance out from under
    # the transition — simulating a concurrent move during pre-flight.
    def sneaky(*a, **k):
        WorkflowInstance.objects.filter(pk=inst.pk).update(current_state=tr.to_state_id)
        m = MagicMock(status_code=200, text="{}")
        m.json.return_value = {}
        m.raise_for_status.return_value = None
        return m

    TransitionHook.objects.create(
        transition=tr, trigger="before", action="probe", on_failure="block",
        config={"url": "https://x.example.com"}, created_by=user,
    )
    with patch("apps.notifications.hooks.httpx.request", side_effect=sneaky), \
         patch("apps.notifications.hooks.assert_safe_url"):
        with pytest.raises(WorkflowTransitionError, match="changed state during processing"):
            perform_transition(inst, tr.id)
