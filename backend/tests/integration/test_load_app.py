"""`manage.py load_app` — demo content as data (docs/DEMO-PHASE1.md §1).

Content lives as YAML files that compile, via the existing DSL and bundle
importer, to the same structures a client import produces. Seeding and
delivery share one code path, so the demo can't drift from the export format.
"""
import pytest
from django.core.management import call_command
from io import StringIO

from apps.accounts.models import User
from apps.instances.models import InstanceRelationship, WorkflowInstance
from apps.workflows.models import WorkflowDefinition


def _run(app="demo", **kwargs):
    out = StringIO()
    call_command("load_app", app, stdout=out, no_color=True, **kwargs)
    return out.getvalue()


@pytest.fixture
def users(db):
    for email in ("admin@flowforge.dev", "bob@flowforge.dev"):
        User.objects.create_user(
            email=email, password="StrongPass123!", first_name="T", last_name="U",
        )


@pytest.mark.django_db
class TestLoadApp:
    def test_creates_workflows_from_yaml(self, users):
        _run()
        assert WorkflowDefinition.objects.filter(name="Maintenance Request").exists()

    def test_applies_identity_to_the_workspace(self, users):
        from apps.accounts.models import Workspace

        _run()
        assert Workspace.current().name == "Northwind Facilities"

    def test_preserves_ui_schema_from_yaml(self, users):
        """The presentation layer is the point of the demo; if `ui:` doesn't
        survive, every workflow loads as an unconfigured list."""
        _run()
        wf = WorkflowDefinition.objects.get(name="Maintenance Request")
        assert wf.ui_schema.get("shell") == "kanban"

    def test_creates_instances(self, users):
        _run()
        assert WorkflowInstance.objects.filter(
            workflow_definition__name="Maintenance Request").exists()

    def test_instances_reach_their_target_state(self, users):
        _run()
        inst = WorkflowInstance.objects.get(reference_number__startswith="MNT-", 
                                            metadata_json__ref="in-progress-job")
        assert inst.current_state.name == "In Progress"

    def test_instances_are_advanced_by_firing_transitions(self, users):
        """Setting current_state directly would leave an empty timeline and
        make the audit trail a lie — and the audit trail is a headline
        feature. Each advance must produce audit entries."""
        from apps.audit.models import AuditLog

        _run()
        inst = WorkflowInstance.objects.get(metadata_json__ref="in-progress-job")
        transitions = AuditLog.objects.filter(
            workflow_instance=inst, action_type="transition")
        assert transitions.count() >= 2, "instance was not advanced through the engine"

    def test_creates_relationships(self, users):
        _run()
        assert InstanceRelationship.objects.exists()

    def test_refuses_to_clobber_without_reset(self, users):
        _run()
        output = _run()
        assert "already" in output.lower()
        assert WorkflowDefinition.objects.filter(name="Maintenance Request").count() == 1

    def test_reset_replaces_cleanly(self, users):
        _run()
        _run(reset=True)
        assert WorkflowDefinition.objects.filter(name="Maintenance Request").count() == 1

    def test_unknown_app_fails_clearly(self, users):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError, match="not found"):
            _run(app="nonexistent")
