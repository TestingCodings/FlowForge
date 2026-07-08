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
