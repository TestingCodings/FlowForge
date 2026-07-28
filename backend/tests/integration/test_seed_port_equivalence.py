"""`load_app classic` must reproduce what `seed --testrail` produces.

This is the safety net for moving demo content out of Python
(docs/DEMO-PHASE1.md §3 step 1). If the YAML loader can rebuild the demo the
Python seed builds, it's trustworthy for new content. If it can't, the
difference is a loader bug — and better found here than in a client's app.

Compared structurally rather than field-by-field, because the two paths
legitimately differ on generated ids and timestamps.
"""
import pytest
from django.core.management import call_command
from io import StringIO

from apps.workflows.models import WorkflowDefinition

PORTED = [
    "Employee Leave Request", "Insurance Claim", "Test Run", "Bug Report", "Release",
]


def _shape(name):
    """A comparable description of a workflow definition."""
    wf = WorkflowDefinition.objects.get(name=name)
    return {
        "prefix": wf.reference_prefix,
        "ui_schema": wf.ui_schema or {},
        "states": sorted(
            (s.name, s.is_initial, s.is_terminal,
             (s.sla_config or {}).get("sla_hours"),
             (s.task_config or {}).get("default_role"))
            for s in wf.states.all()
        ),
        "transitions": sorted(
            (t.name, t.from_state.name, t.to_state.name, t.requires_approval)
            for t in wf.transitions.select_related("from_state", "to_state")
        ),
        "rules": sorted(
            (r.transition.name if r.transition else None,
             repr(r.condition), repr(r.action))
            for r in wf.rules.select_related("transition")
        ),
    }


def _quiet(command, *args):
    call_command(command, *args, stdout=StringIO(), no_color=True)


@pytest.mark.django_db
class TestSeedPortEquivalence:
    @pytest.mark.parametrize("name", PORTED)
    def test_load_app_matches_seed(self, name):
        _quiet("seed", "--reset", "--testrail", "--quiet")
        from_seed = _shape(name)

        # Clear and rebuild the same workflow from YAML.
        from apps.workflows.management.commands.seed import _delete_instances_leaves_first
        from apps.instances.models import WorkflowInstance

        _delete_instances_leaves_first(
            WorkflowInstance.objects.filter(workflow_definition__name__in=PORTED))
        WorkflowDefinition.objects.filter(name__in=PORTED).delete()

        _quiet("load_app", "classic", "--skip-identity")
        from_yaml = _shape(name)

        assert from_yaml == from_seed


@pytest.mark.django_db
def test_every_seeded_workflow_is_ported():
    """A workflow added to seed.py but not to the content directory would
    silently vanish from the ported demo."""
    _quiet("seed", "--reset", "--testrail", "--quiet")
    seeded = set(WorkflowDefinition.objects.values_list("name", flat=True))
    assert seeded == set(PORTED), f"seed produces {seeded - set(PORTED)} which is not ported"
