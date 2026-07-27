"""reset_demo: the public demo has to survive whatever visitors do to it.

The command runs nightly and must be safe to run at any time, from any
state — including twice in a row, and on a database a visitor has already
scribbled on.
"""
import pytest
from django.core.management import call_command
from io import StringIO

from apps.accounts.models import User
from apps.instances.models import WorkflowInstance
from apps.workflows.models import State, WorkflowDefinition


def _run(**kwargs):
    out = StringIO()
    call_command("reset_demo", stdout=out, no_color=True, **kwargs)
    return out.getvalue()


@pytest.mark.django_db
class TestResetDemo:
    def test_seeds_from_an_empty_database(self):
        assert not WorkflowDefinition.objects.exists()
        _run()
        assert WorkflowDefinition.objects.exists()
        assert User.objects.filter(email="admin@flowforge.dev").exists()

    def test_is_idempotent(self):
        """Running twice must not duplicate workflows — the nightly job would
        otherwise grow the database without bound."""
        _run()
        first = WorkflowDefinition.objects.count()
        _run()
        assert WorkflowDefinition.objects.count() == first

    def test_discards_instances_a_visitor_created(self):
        """The reset's whole purpose: visitor mess does not accumulate."""
        _run()
        wf = WorkflowDefinition.objects.first()
        admin = User.objects.get(email="admin@flowforge.dev")
        WorkflowInstance.objects.create(
            workflow_definition=wf,
            current_state=State.objects.filter(workflow_definition=wf, is_initial=True).first(),
            created_by=admin,
        )
        before = WorkflowInstance.objects.count()

        _run()

        assert WorkflowInstance.objects.count() < before or before == 0

    def test_restores_a_deleted_demo_user(self):
        """A visitor with admin rights can delete accounts; the reset must
        put them back or the demo becomes unusable."""
        _run()
        User.objects.filter(email="bob@flowforge.dev").delete()
        _run()
        assert User.objects.filter(email="bob@flowforge.dev").exists()

    def test_prints_no_credentials(self):
        """Output goes to container logs, which are not a secret store.
        The seed command prints passwords; reset_demo must not."""
        output = _run()
        assert "Admin1234!" not in output
        assert "password" not in output.lower()

    def test_survives_nested_instances(self):
        """Regression: WorkflowInstance.parent is PROTECT, so deleting a
        parent before its child raises ProtectedError. A visitor creating a
        sub-instance would otherwise wedge the nightly reset permanently —
        the demo would never recover on its own."""
        _run()
        wf = WorkflowDefinition.objects.first()
        admin = User.objects.get(email="admin@flowforge.dev")
        initial = State.objects.filter(workflow_definition=wf, is_initial=True).first()

        parent = WorkflowInstance.objects.create(
            workflow_definition=wf, current_state=initial, created_by=admin)
        child = WorkflowInstance.objects.create(
            workflow_definition=wf, current_state=initial, created_by=admin, parent=parent)
        WorkflowInstance.objects.create(
            workflow_definition=wf, current_state=initial, created_by=admin, parent=child)

        _run()  # must not raise ProtectedError

        assert not WorkflowInstance.objects.filter(pk=parent.pk).exists()


@pytest.mark.django_db
class TestScheduledResetGuard:
    """The task must refuse to run outside demo mode. This is the failure
    that would destroy a customer's data, so it gets its own coverage."""

    def test_refuses_when_demo_mode_is_absent(self):
        from apps.workflows.tasks import reset_demo_scheduled

        _run()
        wf = WorkflowDefinition.objects.first()
        admin = User.objects.get(email="admin@flowforge.dev")
        keeper = WorkflowInstance.objects.create(
            workflow_definition=wf,
            current_state=State.objects.filter(workflow_definition=wf, is_initial=True).first(),
            created_by=admin,
        )

        result = reset_demo_scheduled()

        assert "skipped" in result
        assert WorkflowInstance.objects.filter(pk=keeper.pk).exists(), \
            "the guard let a nightly wipe run against non-demo data"

    @pytest.mark.django_db
    def test_runs_when_demo_mode_is_on(self):
        from django.test import override_settings
        from apps.workflows.tasks import reset_demo_scheduled

        with override_settings(DEMO_MODE=True):
            assert reset_demo_scheduled() == "demo reset"
        assert WorkflowDefinition.objects.exists()


@pytest.mark.django_db
class TestDeployedPasswordsDifferFromSeed:
    """The seed's passwords are in a public file. A public demo must not use
    them, or the repo effectively publishes its own admin login."""

    def test_reset_applies_passwords_from_demo_accounts(self):
        from django.test import override_settings

        accounts = [{"email": "admin@flowforge.dev", "password": "Deployed-Only-9!", "role": "Admin"}]
        with override_settings(DEMO_ACCOUNTS=accounts):
            _run()

        user = User.objects.get(email="admin@flowforge.dev")
        assert user.check_password("Deployed-Only-9!")
        assert not user.check_password("Admin1234!"), "seed password still works"

    def test_seed_passwords_stand_when_nothing_is_configured(self):
        """Local dev has no DEMO_ACCOUNTS and must keep working unchanged."""
        _run()
        assert User.objects.get(email="admin@flowforge.dev").check_password("Admin1234!")

    def test_unknown_emails_are_ignored(self):
        from django.test import override_settings

        with override_settings(DEMO_ACCOUNTS=[{"email": "ghost@nowhere.dev", "password": "x"}]):
            _run()  # must not raise
        assert not User.objects.filter(email="ghost@nowhere.dev").exists()
