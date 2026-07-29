"""App bundles: identity + many workflows in one file (docs/APPS.md).

A workflow bundle carries one workflow and no branding, so a client could be
handed their processes but not their *system*. An app bundle adds identity
and multiple workflows, which is the unit a client actually buys.

Backwards compatibility is the constraint that matters: v1 workflow bundles
already exist in the wild (the export button has shipped for months), so
import must keep accepting them.
"""
import pytest

from apps.accounts.models import Workspace
from apps.workflows.models import WorkflowDefinition
from apps.workflows.portability import (
    APP_BUNDLE_VERSION, BundleError, export_app, export_workflow,
    import_app, import_workflow,
)


@pytest.fixture
def two_workflows(db):
    from tests.factories import StateFactory, TransitionFactory, WorkflowDefinitionFactory

    made = []
    for name, prefix in (("Alpha Flow", "ALF"), ("Beta Flow", "BEF")):
        wf = WorkflowDefinitionFactory(name=name, reference_prefix=prefix)
        s1 = StateFactory(workflow_definition=wf, name="Open", is_initial=True, position_order=1)
        s2 = StateFactory(workflow_definition=wf, name="Done", is_terminal=True, position_order=2)
        TransitionFactory(workflow_definition=wf, from_state=s1, to_state=s2, name="Finish")
        wf.ui_schema = {"shell": "kanban"}
        wf.save()
        made.append(wf)
    return made


@pytest.mark.django_db
class TestExportApp:
    def test_carries_every_named_workflow(self, two_workflows):
        bundle = export_app(["Alpha Flow", "Beta Flow"])
        assert len(bundle["workflows"]) == 2

    def test_is_distinguishable_from_a_workflow_bundle(self, two_workflows):
        """Import dispatches on `kind`; the two must not be confusable."""
        assert export_app(["Alpha Flow"])["kind"] == "flowforge.app"
        assert export_workflow(two_workflows[0])["kind"] == "flowforge.workflow"

    def test_carries_workspace_identity(self, two_workflows):
        ws = Workspace.current()
        ws.name = "Northwind Facilities"
        ws.tagline = "Facilities Management"
        ws.ui_config = {"locale": "en-GB", "density": "comfortable"}
        ws.save()

        identity = export_app(["Alpha Flow"])["identity"]
        assert identity["name"] == "Northwind Facilities"
        assert identity["ui_config"]["locale"] == "en-GB"

    def test_nested_workflows_are_full_bundles(self, two_workflows):
        """Reusing the workflow bundle shape means one importer, not two."""
        inner = export_app(["Alpha Flow"])["workflows"][0]
        assert inner["kind"] == "flowforge.workflow"
        assert inner["workflow"]["ui_schema"]["shell"] == "kanban"

    def test_unknown_workflow_name_is_rejected(self, two_workflows):
        with pytest.raises(BundleError, match="not found"):
            export_app(["Alpha Flow", "Nonexistent"])


@pytest.mark.django_db
class TestImportApp:
    def _round_trip(self, names):
        bundle = export_app(names)
        WorkflowDefinition.objects.filter(name__in=names).delete()
        return bundle

    def test_recreates_every_workflow(self, two_workflows):
        bundle = self._round_trip(["Alpha Flow", "Beta Flow"])
        import_app(bundle)
        assert WorkflowDefinition.objects.filter(name__in=["Alpha Flow", "Beta Flow"]).count() == 2

    def test_preserves_ui_schema(self, two_workflows):
        bundle = self._round_trip(["Alpha Flow"])
        import_app(bundle)
        assert WorkflowDefinition.objects.get(name="Alpha Flow").ui_schema["shell"] == "kanban"

    def test_applies_identity(self, two_workflows):
        ws = Workspace.current()
        ws.name = "Northwind Facilities"
        ws.save()
        bundle = self._round_trip(["Alpha Flow"])

        ws.name = "Something Else"
        ws.save()
        import_app(bundle)
        assert Workspace.current().name == "Northwind Facilities"

    def test_identity_can_be_skipped(self, two_workflows):
        """Importing a client's processes shouldn't force their branding on
        an install that already has its own."""
        bundle = self._round_trip(["Alpha Flow"])
        ws = Workspace.current()
        ws.name = "Keep Me"
        ws.save()

        import_app(bundle, apply_identity=False)
        assert Workspace.current().name == "Keep Me"

    def test_rejects_a_workflow_bundle(self, two_workflows):
        with pytest.raises(BundleError, match="kind"):
            import_app(export_workflow(two_workflows[0]))

    def test_rejects_an_unsupported_version(self, two_workflows):
        bundle = self._round_trip(["Alpha Flow"])
        bundle["bundle_version"] = APP_BUNDLE_VERSION + 99
        with pytest.raises(BundleError, match="version"):
            import_app(bundle)

    def test_is_atomic(self, two_workflows):
        """A half-imported app is worse than a failed one: the second
        workflow colliding must not leave the first behind."""
        bundle = export_app(["Alpha Flow", "Beta Flow"])
        WorkflowDefinition.objects.filter(name="Alpha Flow").delete()
        # "Beta Flow" still exists, so its import will collide.
        with pytest.raises(BundleError):
            import_app(bundle)
        assert not WorkflowDefinition.objects.filter(name="Alpha Flow").exists()


@pytest.mark.django_db
class TestBackwardsCompatibility:
    def test_v1_workflow_bundles_still_import(self, two_workflows):
        """Exports already in the wild must keep working."""
        bundle = export_workflow(two_workflows[0])
        WorkflowDefinition.objects.filter(name="Alpha Flow").delete()
        wf = import_workflow(bundle)
        assert wf.name == "Alpha Flow"


# ── API surface ────────────────────────────────────────────────────────────

@pytest.fixture
def designer(db):
    from rest_framework.test import APIClient

    from apps.accounts.models import Role, RoleName, User, UserRole

    user = User.objects.create_user(
        email="appdesigner@example.com", password="StrongPass123!",
        first_name="A", last_name="D",
    )
    role, _ = Role.objects.get_or_create(name=RoleName.WORKFLOW_DESIGNER)
    UserRole.objects.create(user=user, role=role)
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def viewer(db):
    from rest_framework.test import APIClient

    from apps.accounts.models import Role, RoleName, User, UserRole

    user = User.objects.create_user(
        email="appviewer@example.com", password="StrongPass123!",
        first_name="A", last_name="V",
    )
    role, _ = Role.objects.get_or_create(name=RoleName.VIEWER)
    UserRole.objects.create(user=user, role=role)
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.mark.django_db
class TestAppBundleApi:
    def test_export_returns_a_downloadable_app_bundle(self, designer, two_workflows):
        resp = designer.post("/api/workflows/export-app/",
                             {"workflows": ["Alpha Flow", "Beta Flow"]}, format="json")
        assert resp.status_code == 200
        assert "attachment" in resp["Content-Disposition"]
        import json
        body = json.loads(resp.content)
        assert body["kind"] == "flowforge.app"
        assert len(body["workflows"]) == 2

    def test_export_requires_a_workflow_list(self, designer, two_workflows):
        assert designer.post("/api/workflows/export-app/", {}, format="json").status_code == 400

    def test_export_rejects_an_unknown_name(self, designer, two_workflows):
        resp = designer.post("/api/workflows/export-app/",
                             {"workflows": ["Nope"]}, format="json")
        assert resp.status_code == 400

    def test_export_denied_to_a_viewer(self, viewer, two_workflows):
        """The bundle contains every workflow's full definition."""
        resp = viewer.post("/api/workflows/export-app/",
                           {"workflows": ["Alpha Flow"]}, format="json")
        assert resp.status_code in (403, 400)

    def test_round_trip_through_the_api(self, designer, two_workflows):
        import json

        resp = designer.post("/api/workflows/export-app/",
                             {"workflows": ["Alpha Flow"]}, format="json")
        bundle = json.loads(resp.content)
        WorkflowDefinition.objects.filter(name="Alpha Flow").delete()

        created = designer.post("/api/workflows/import-app/", bundle, format="json")
        assert created.status_code == 201, created.data
        assert created.data["imported"] == 1
        assert WorkflowDefinition.objects.filter(name="Alpha Flow").exists()

    def test_import_can_decline_the_identity(self, designer, two_workflows):
        import json

        ws = Workspace.current()
        ws.name = "Their Brand"
        ws.save()
        bundle = json.loads(
            designer.post("/api/workflows/export-app/",
                          {"workflows": ["Alpha Flow"]}, format="json").content
        )
        WorkflowDefinition.objects.filter(name="Alpha Flow").delete()
        ws.name = "Our Brand"
        ws.save()

        resp = designer.post("/api/workflows/import-app/",
                             {"bundle": bundle, "apply_identity": False}, format="json")
        assert resp.status_code == 201
        assert Workspace.current().name == "Our Brand"

    def test_import_denied_to_a_viewer(self, viewer, two_workflows):
        resp = viewer.post("/api/workflows/import-app/", {"kind": "flowforge.app"}, format="json")
        assert resp.status_code in (403, 400)
