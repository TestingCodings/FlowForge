"""
Workflow definition export/import (VISION Layer 3 foundation).

A bundle is a self-contained JSON document capturing everything needed to
recreate a workflow on another FlowForge install: definition, states,
transitions, rules, per-state forms, and the presentation ui_schema.
References between objects use names (not UUIDs) so bundles are portable.
"""

from django.db import transaction

from apps.forms.models import FormDefinition

from .models import Rule, State, Transition, WorkflowDefinition

BUNDLE_VERSION = 1


def export_workflow(workflow: WorkflowDefinition) -> dict:
    states = list(workflow.states.order_by("position_order"))
    transitions = list(
        workflow.transitions.select_related("from_state", "to_state").all()
    )
    rules = list(workflow.rules.select_related("transition").all())
    forms = list(
        FormDefinition.objects.filter(workflow_definition=workflow).select_related("state")
    )

    return {
        "bundle_version": BUNDLE_VERSION,
        "kind": "flowforge.workflow",
        "workflow": {
            "name": workflow.name,
            "description": workflow.description,
            "reference_prefix": workflow.reference_prefix,
            "version": workflow.version,
            "is_active": workflow.is_active,
            "ui_schema": workflow.ui_schema or {},
        },
        "states": [
            {
                "name": s.name,
                "display_name": s.display_name,
                "is_initial": s.is_initial,
                "is_terminal": s.is_terminal,
                "position_order": s.position_order,
                "sla_config": s.sla_config or {},
                "task_config": s.task_config or {},
            }
            for s in states
        ],
        "transitions": [
            {
                "name": t.name,
                "display_name": t.display_name,
                "from_state": t.from_state.name,
                "to_state": t.to_state.name,
                "requires_approval": t.requires_approval,
            }
            for t in transitions
        ],
        "rules": [
            {
                "transition": r.transition.name if r.transition else None,
                "condition": r.condition,
                "action": r.action,
                "priority": r.priority,
            }
            for r in rules
        ],
        "forms": [
            {
                "state": f.state.name,
                "name": f.name,
                "schema": f.schema or {},
                "version": f.version,
            }
            for f in forms
        ],
    }


class BundleError(ValueError):
    pass


@transaction.atomic
def import_workflow(bundle: dict, created_by=None, rename: str | None = None) -> WorkflowDefinition:
    """Create a new WorkflowDefinition from a bundle. Fails if the name is taken."""
    if bundle.get("kind") != "flowforge.workflow":
        raise BundleError("Not a FlowForge workflow bundle (missing kind).")
    if bundle.get("bundle_version") != BUNDLE_VERSION:
        raise BundleError(f"Unsupported bundle_version: {bundle.get('bundle_version')}")

    wf_data = bundle.get("workflow") or {}
    name = rename or wf_data.get("name")
    if not name:
        raise BundleError("Bundle has no workflow name.")
    if WorkflowDefinition.objects.filter(name=name).exists():
        raise BundleError(
            f"A workflow named '{name}' already exists. Pass a new name to import as a copy."
        )

    initial_states = [s for s in bundle.get("states", []) if s.get("is_initial")]
    if len(initial_states) != 1:
        raise BundleError("Bundle must contain exactly one initial state.")

    ui_schema = wf_data.get("ui_schema") or {}
    from .ui_schema import validate_ui_schema

    ui_error = validate_ui_schema(ui_schema)
    if ui_error:
        raise BundleError(f"Invalid ui_schema in bundle: {ui_error}")

    workflow = WorkflowDefinition.objects.create(
        name=name,
        description=wf_data.get("description", ""),
        reference_prefix=wf_data.get("reference_prefix", "WFF"),
        version=1,
        is_active=wf_data.get("is_active", False),
        ui_schema=ui_schema,
        created_by=created_by,
    )

    state_by_name = {}
    for s in bundle.get("states", []):
        state_by_name[s["name"]] = State.objects.create(
            workflow_definition=workflow,
            name=s["name"],
            display_name=s.get("display_name", s["name"]),
            is_initial=s.get("is_initial", False),
            is_terminal=s.get("is_terminal", False),
            position_order=s.get("position_order", 0),
            sla_config=s.get("sla_config") or {},
            task_config=s.get("task_config") or {},
        )

    transition_by_name = {}
    for t in bundle.get("transitions", []):
        try:
            from_state = state_by_name[t["from_state"]]
            to_state = state_by_name[t["to_state"]]
        except KeyError as exc:
            raise BundleError(f"Transition '{t.get('name')}' references unknown state {exc}.")
        transition_by_name[t["name"]] = Transition.objects.create(
            workflow_definition=workflow,
            name=t["name"],
            display_name=t.get("display_name", ""),
            from_state=from_state,
            to_state=to_state,
            requires_approval=t.get("requires_approval", False),
        )

    for r in bundle.get("rules", []):
        tr_name = r.get("transition")
        if tr_name is not None and tr_name not in transition_by_name:
            raise BundleError(f"Rule references unknown transition '{tr_name}'.")
        Rule.objects.create(
            workflow_definition=workflow,
            transition=transition_by_name.get(tr_name) if tr_name else None,
            condition=r.get("condition") or {},
            action=r.get("action") or {},
            priority=r.get("priority", 100),
        )

    for f in bundle.get("forms", []):
        st_name = f.get("state")
        if st_name not in state_by_name:
            raise BundleError(f"Form '{f.get('name')}' references unknown state '{st_name}'.")
        FormDefinition.objects.create(
            workflow_definition=workflow,
            state=state_by_name[st_name],
            name=f.get("name", "Form"),
            schema=f.get("schema") or {},
            version=f.get("version", 1),
        )

    return workflow


# ── App bundles (docs/APPS.md) ──────────────────────────────────────────────
#
# A workflow bundle carries one workflow and no branding, so a client could be
# handed their processes but not their *system*. An app bundle adds identity
# and many workflows, which is the unit a client actually buys — and the same
# unit `manage.py load_app` builds from YAML.
#
# Versioned separately from BUNDLE_VERSION: the two formats evolve
# independently, and conflating them would mean bumping one to change the
# other. Workflow bundles nest inside unchanged, so there is one importer
# rather than two implementations that can drift.

APP_BUNDLE_VERSION = 1


def export_app(workflow_names: list[str], include_identity: bool = True) -> dict:
    """Bundle several workflows plus the workspace's identity into one file."""
    workflows = []
    for name in workflow_names:
        wf = WorkflowDefinition.objects.filter(name=name).first()
        if wf is None:
            raise BundleError(f"Workflow not found: {name}")
        workflows.append(export_workflow(wf))

    bundle = {
        "bundle_version": APP_BUNDLE_VERSION,
        "kind": "flowforge.app",
        "workflows": workflows,
    }

    if include_identity:
        from apps.accounts.models import Workspace

        ws = Workspace.current()
        bundle["identity"] = {
            "name": ws.name,
            "tagline": ws.tagline,
            "logo_url": ws.logo_url,
            "ui_config": ws.ui_config or {},
        }

    return bundle


def import_app(bundle: dict, created_by=None, apply_identity: bool = True) -> list:
    """Recreate every workflow in an app bundle, optionally applying identity.

    Atomic: a half-imported app — some workflows present, some not, branding
    changed — is worse than a failed one, because there's no obvious way back.

    `apply_identity=False` matters when importing a client's processes into an
    install that already has its own branding; the caller shouldn't have to
    strip the file by hand to avoid being rebranded.
    """
    if bundle.get("kind") != "flowforge.app":
        raise BundleError(
            f"Not a FlowForge app bundle (kind={bundle.get('kind')!r}). "
            "A single-workflow bundle imports through import_workflow."
        )
    if bundle.get("bundle_version") != APP_BUNDLE_VERSION:
        raise BundleError(
            f"Unsupported app bundle_version: {bundle.get('bundle_version')}"
        )

    created = []
    with transaction.atomic():
        for inner in bundle.get("workflows", []):
            created.append(import_workflow(inner, created_by=created_by))

        identity = bundle.get("identity")
        if identity and apply_identity:
            from apps.accounts.models import Workspace

            ws = Workspace.current()
            ws.name = identity.get("name", ws.name)
            ws.tagline = identity.get("tagline", ws.tagline)
            ws.logo_url = identity.get("logo_url", ws.logo_url)
            if identity.get("ui_config"):
                # Merge, so settings the bundle doesn't express survive.
                ws.ui_config = {**(ws.ui_config or {}), **identity["ui_config"]}
            ws.save()

    return created
