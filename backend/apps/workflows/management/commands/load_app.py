"""
python manage.py load_app <name>          — load demo content from YAML
python manage.py load_app <name> --reset  — replace it if already present

Demo content lives as YAML under apps/workflows/content/<name>/ rather than
as Python literals (docs/DEMO-PHASE1.md §1). Two reasons:

* **One code path.** The YAML compiles through `parse_dsl` into exactly the
  bundle `export_workflow` produces, then imports through `import_workflow` —
  the same route a client's delivered app takes. The demo therefore cannot
  drift from the export format, and an import bug shows up in our own demo
  before a client ever sees it.
* **Editable by someone other than the author.** A thousand-line seed module
  can't be diffed meaningfully or handed to anyone.

Instances are advanced by firing real transitions, never by writing
`current_state`. That is what gives them believable timelines and audit
trails, which is one of the strongest things the demo has to show.
"""
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User, Workspace
from apps.instances.models import InstanceRelationship, WorkflowInstance
from apps.workflows.dsl import DslError, parse_dsl
from apps.workflows.models import Transition, WorkflowDefinition
from apps.workflows.portability import BundleError, import_workflow

CONTENT_ROOT = Path(__file__).resolve().parents[2] / "content"


class Command(BaseCommand):
    help = "Load an app's workflows, identity and demo instances from YAML content."

    def add_arguments(self, parser):
        parser.add_argument("app", help="Content directory name, e.g. 'demo'.")
        parser.add_argument(
            "--reset", action="store_true",
            help="Delete the app's existing workflows and instances first.",
        )
        parser.add_argument(
            "--skip-identity", action="store_true",
            help="Load workflows without touching the workspace branding.",
        )

    def handle(self, *args, **options):
        app_dir = CONTENT_ROOT / options["app"]
        manifest_path = app_dir / "app.yaml"
        if not manifest_path.exists():
            raise CommandError(
                f"App content not found: {manifest_path}. "
                f"Available: {', '.join(self._available()) or '(none)'}"
            )

        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        bundles = [
            self._compile(app_dir / filename)
            for filename in manifest.get("workflows", [])
        ]
        names = [b["workflow"]["name"] for b in bundles]

        existing = WorkflowDefinition.objects.filter(name__in=names)
        if existing.exists():
            if not options["reset"]:
                self.stdout.write(self.style.WARNING(
                    f"'{options['app']}' is already loaded "
                    f"({existing.count()} of {len(names)} workflows present). "
                    "Re-run with --reset to replace it and delete its instances."
                ))
                return
            self._delete(names)

        with transaction.atomic():
            author = User.objects.order_by("date_joined").first()
            for bundle in bundles:
                import_workflow(bundle, created_by=author)
                self.stdout.write(f"  loaded {bundle['workflow']['name']}")

            if not options["skip_identity"]:
                self._apply_identity(manifest)

            instances_file = manifest.get("instances")
            if instances_file:
                self._load_instances(app_dir / instances_file)

        self.stdout.write(self.style.SUCCESS(f"Loaded app '{options['app']}'."))

    # ── helpers ────────────────────────────────────────────────────────────

    def _available(self):
        if not CONTENT_ROOT.exists():
            return []
        return sorted(p.name for p in CONTENT_ROOT.iterdir() if (p / "app.yaml").exists())

    def _compile(self, path: Path) -> dict:
        """YAML → bundle, with the filename in any error so it's findable."""
        if not path.exists():
            raise CommandError(f"Workflow file not found: {path}")
        try:
            return parse_dsl(path.read_text(encoding="utf-8"))
        except DslError as exc:
            raise CommandError(f"{path.name}: {exc}") from exc

    def _delete(self, names):
        """Remove the app's instances and definitions, children first.

        WorkflowInstance.parent is PROTECT, so a flat delete raises as soon as
        any instance has a child — and this content deliberately nests jobs
        under assets.
        """
        from apps.workflows.management.commands.seed import _delete_instances_leaves_first

        instances = WorkflowInstance.objects.filter(workflow_definition__name__in=names)
        count = instances.count()
        _delete_instances_leaves_first(instances)
        WorkflowDefinition.objects.filter(name__in=names).delete()
        self.stdout.write(f"  removed {len(names)} workflow(s) and {count} instance(s)")

    def _apply_identity(self, manifest):
        ws = Workspace.current()
        ws.name = manifest.get("name", ws.name)
        ws.tagline = manifest.get("tagline", ws.tagline)
        ws.logo_url = manifest.get("logo_url", ws.logo_url)
        if manifest.get("ui_config"):
            # Merge rather than replace: the workspace may carry settings the
            # app doesn't express, and losing them silently would be worse
            # than ignoring an unknown key.
            ws.ui_config = {**(ws.ui_config or {}), **manifest["ui_config"]}
        ws.save()
        self.stdout.write(f"  identity applied: {ws.name}")

    def _load_instances(self, path: Path):
        if not path.exists():
            raise CommandError(f"Instances file not found: {path}")
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        by_ref: dict[str, WorkflowInstance] = {}
        for spec in doc.get("instances", []):
            by_ref[spec["ref"]] = self._create_instance(spec, by_ref)

        for link in doc.get("relationships", []):
            src, dst = by_ref.get(link["from"]), by_ref.get(link["to"])
            if src is None or dst is None:
                raise CommandError(
                    f"Relationship references an unknown ref: {link}"
                )
            InstanceRelationship.objects.get_or_create(
                from_instance=src, to_instance=dst, rel_type=link["type"],
                defaults={"created_by": src.created_by},
            )

        self.stdout.write(
            f"  {len(by_ref)} instance(s), "
            f"{len(doc.get('relationships', []))} relationship(s)"
        )

    def _create_instance(self, spec, by_ref) -> WorkflowInstance:
        from apps.audit.services import instance_created, transition_applied
        from apps.workflows.engine import WorkflowTransitionError, perform_transition

        wf = WorkflowDefinition.objects.get(name=spec["workflow"])
        creator = User.objects.filter(email=spec.get("creator")).first()

        # `ref` is stored so relationships and tests can find this instance.
        metadata = {**(spec.get("metadata") or {}), "ref": spec["ref"]}

        instance = WorkflowInstance.objects.create(
            workflow_definition=wf,
            current_state=wf.states.get(is_initial=True),
            created_by=creator,
            metadata_json=metadata,
            parent=by_ref.get(spec.get("parent")) if spec.get("parent") else None,
        )
        instance_created(instance, actor=creator)

        for transition_name in spec.get("advance", []):
            transition = Transition.objects.filter(
                workflow_definition=wf, name=transition_name,
                from_state=instance.current_state,
            ).first()
            if transition is None:
                raise CommandError(
                    f"{spec['ref']}: no transition '{transition_name}' from "
                    f"'{instance.current_state.name}'"
                )
            from_name = instance.current_state.name
            try:
                perform_transition(instance, transition.id)
            except WorkflowTransitionError as exc:
                # A rule blocking a seeded advance means the content and the
                # rules disagree. Failing loudly beats a demo whose instances
                # are quietly in the wrong states.
                raise CommandError(
                    f"{spec['ref']}: '{transition_name}' was blocked — {exc}"
                ) from exc
            instance.refresh_from_db()
            transition_applied(
                instance, actor=creator,
                from_state=from_name,
                to_state=instance.current_state.name,
                payload={"transition_name": transition_name, "seeded": True},
            )

        return instance
