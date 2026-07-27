"""The YAML DSL must round-trip ui_schema.

`parse_dsl` has always read a top-level `ui:` key into ui_schema, but
`export_dsl` never emitted one. So "View as YAML", copy, re-import silently
dropped the shell, per-role panels, computed fields and scene config — every
presentation choice — and the workflow came back looking unconfigured.

That asymmetry also blocks storing demo content as YAML, since the demo's
whole point is the presentation layer.
"""
import yaml

from apps.workflows.dsl import export_dsl, parse_dsl

UI = {
    "shell": "kanban",
    "card_fields": ["priority", "assignee"],
    "state_display": {"Reported": {"colour": "#f59e0b", "icon": "alert"}},
    "computed": {"days_open": {"expr": "age_days"}},
    "instance_view": {
        "panels": ["state_graph", "timeline"],
        "panels_by_role": {"participant": ["forms", "attachments"]},
    },
}

BUNDLE = {
    "bundle_version": 1,
    "kind": "flowforge.workflow",
    "workflow": {
        "name": "Maintenance Request", "description": "", "reference_prefix": "MNT",
        "version": 1, "is_active": True, "ui_schema": UI,
    },
    "states": [
        {"name": "Reported", "is_initial": True, "is_terminal": False,
         "position_order": 1, "sla_config": {}, "task_config": {}},
        {"name": "Complete", "is_initial": False, "is_terminal": True,
         "position_order": 2, "sla_config": {}, "task_config": {}},
    ],
    "transitions": [{"name": "Finish", "from_state": "Reported", "to_state": "Complete",
                     "requires_approval": False}],
    "rules": [],
    "forms": [],
}


def test_export_emits_a_ui_block():
    assert "ui:" in export_dsl(BUNDLE)


def test_exported_yaml_is_valid_yaml():
    yaml.safe_load(export_dsl(BUNDLE))


def test_ui_schema_survives_a_round_trip():
    back = parse_dsl(export_dsl(BUNDLE))
    assert back["workflow"]["ui_schema"] == UI


def test_nested_structures_survive():
    """state_display, computed and panels_by_role are nested dicts — the
    parts most likely to be flattened by a naive serialiser."""
    ui = parse_dsl(export_dsl(BUNDLE))["workflow"]["ui_schema"]
    assert ui["state_display"]["Reported"]["icon"] == "alert"
    assert ui["computed"]["days_open"]["expr"] == "age_days"
    assert ui["instance_view"]["panels_by_role"]["participant"] == ["forms", "attachments"]


def test_no_ui_block_when_schema_is_empty():
    """An unconfigured workflow shouldn't gain noise in its YAML."""
    bundle = {**BUNDLE, "workflow": {**BUNDLE["workflow"], "ui_schema": {}}}
    assert "ui:" not in export_dsl(bundle)


def test_states_and_transitions_still_round_trip():
    back = parse_dsl(export_dsl(BUNDLE))
    assert [s["name"] for s in back["states"]] == ["Reported", "Complete"]
    assert back["transitions"][0]["name"] == "Finish"


# ── Scalars needing quoting ────────────────────────────────────────────────
# export_dsl built its header with f-strings, so any value containing a colon
# (or starting with a YAML indicator) produced text that failed to re-import.
# "View as YAML" showed it happily; pasting it back raised a scanner error.

def _bundle_with(**workflow_overrides):
    return {**BUNDLE, "workflow": {**BUNDLE["workflow"], **workflow_overrides}}


def test_description_containing_a_colon_round_trips():
    text = export_dsl(_bundle_with(description="A story: told in scenes"))
    assert parse_dsl(text)["workflow"]["description"] == "A story: told in scenes"


def test_name_containing_a_colon_round_trips():
    text = export_dsl(_bundle_with(name="Release: Q4"))
    assert parse_dsl(text)["workflow"]["name"] == "Release: Q4"


def test_state_name_containing_a_colon_round_trips():
    bundle = {**BUNDLE, "states": [
        {"name": "Blocked: waiting", "is_initial": True, "is_terminal": False,
         "position_order": 1, "sla_config": {}, "task_config": {}},
        {"name": "Done", "is_initial": False, "is_terminal": True,
         "position_order": 2, "sla_config": {}, "task_config": {}},
    ], "transitions": [{"name": "Finish", "from_state": "Blocked: waiting",
                        "to_state": "Done", "requires_approval": False}]}
    back = parse_dsl(export_dsl(bundle))
    assert [s["name"] for s in back["states"]] == ["Blocked: waiting", "Done"]


def test_value_starting_with_a_yaml_indicator_round_trips():
    text = export_dsl(_bundle_with(description="- not a list"))
    assert parse_dsl(text)["workflow"]["description"] == "- not a list"
