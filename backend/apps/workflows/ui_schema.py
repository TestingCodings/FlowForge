"""
ui_schema validation (VISION Layer 2).

The ui_schema JSON on a WorkflowDefinition controls how the workflow is
presented. It travels inside export bundles, so this module is the single
source of truth for what a valid presentation config looks like — both the
API endpoint and bundle import validate through here.

Recognised keys:
    shell         "list" | "kanban" | "table" | "calendar"
    card_fields   [str]  metadata keys shown on kanban cards
    list_columns  [str]  table shell columns: built-ins or "metadata.<key>"
    date_field    str    calendar shell date source: "created_at" or a metadata key
    title_field   str    metadata key used as the card/row title
    state_display {state_name: {"colour": "#hex"}}  per-state display config
"""

VALID_SHELLS = ("list", "kanban", "table", "calendar")

TABLE_BUILTIN_COLUMNS = ("reference", "state", "sla", "status", "created")


def _is_str_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)


def validate_ui_schema(ui_schema) -> str | None:
    """Return an error message, or None if the schema is valid."""
    if not isinstance(ui_schema, dict):
        return "ui_schema must be an object."

    shell = ui_schema.get("shell", "list")
    if shell not in VALID_SHELLS:
        return f"Unknown shell '{shell}'. Valid: {', '.join(VALID_SHELLS)}."

    for key in ("card_fields", "list_columns"):
        if key in ui_schema and not _is_str_list(ui_schema[key]):
            return f"ui_schema.{key} must be a list of non-empty strings."

    for key in ("date_field", "title_field"):
        if key in ui_schema and (not isinstance(ui_schema[key], str) or not ui_schema[key].strip()):
            return f"ui_schema.{key} must be a non-empty string."

    state_display = ui_schema.get("state_display")
    if state_display is not None:
        if not isinstance(state_display, dict):
            return "ui_schema.state_display must be an object keyed by state name."
        for state_name, cfg in state_display.items():
            if not isinstance(cfg, dict):
                return f"ui_schema.state_display['{state_name}'] must be an object."
            colour = cfg.get("colour")
            if colour is not None and not isinstance(colour, str):
                return f"ui_schema.state_display['{state_name}'].colour must be a string."

    return None
