"""
ui_schema validation (VISION Layer 2).

The ui_schema JSON on a WorkflowDefinition controls how the workflow is
presented. It travels inside export bundles, so this module is the single
source of truth for what a valid presentation config looks like — both the
API endpoint and bundle import validate through here.

Recognised keys:
    shell         "list" | "kanban" | "table" | "calendar" | "matrix" | "stepped_form"
    card_fields   [str]  metadata keys shown on kanban cards
    list_columns  [str]  table shell columns: built-ins or "metadata.<key>"
    date_field    str    calendar shell date source: "created_at" or a metadata key
    title_field   str    metadata key used as the card/row title
    swimlanes     str    kanban second-level grouping: "metadata.<key>" or "parent"
    state_display {state_name: {"colour": "#hex", "icon": "play"}}
    children      {workflows: [names], shell, columns, roll_up: bool}
                  which workflow definitions may nest inside instances of this
                  one, and how the children render on the parent detail page
    matrix        {rows, columns}  matrix shell axes; each is "current_state",
                  "parent", or "metadata.<key>"
    instance_view {title_field, panels: [...], layout: "sidebar"|"stacked"}
                  per-workflow detail-page configuration
"""

VALID_SHELLS = ("list", "kanban", "table", "calendar", "matrix", "stepped_form")

TABLE_BUILTIN_COLUMNS = ("reference", "state", "sla", "status", "created")

# Grouping vocabulary shared by matrix axes and kanban swimlanes.
GROUP_BUILTINS = ("current_state", "parent")

VALID_ICONS = (
    "circle", "dot-filled", "play", "pause", "check", "x", "alert",
    "clock", "star", "flag", "lock", "search", "edit", "inbox", "archive",
)

VALID_PANELS = (
    "description", "metadata", "comments", "state_graph", "timeline",
    "forms", "children", "relationships", "tasks",
)

VALID_LAYOUTS = ("sidebar", "stacked")


def _is_str_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)


def _is_group_field(value) -> bool:
    """A grouping field is a builtin or a "metadata.<key>" path."""
    if not isinstance(value, str) or not value.strip():
        return False
    return value in GROUP_BUILTINS or (value.startswith("metadata.") and len(value) > 9)


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

    children = ui_schema.get("children")
    if children is not None:
        if not isinstance(children, dict):
            return "ui_schema.children must be an object."
        if "workflows" in children and not _is_str_list(children["workflows"]):
            return "ui_schema.children.workflows must be a list of workflow names."
        child_shell = children.get("shell", "table")
        if child_shell not in VALID_SHELLS:
            return f"Unknown children shell '{child_shell}'. Valid: {', '.join(VALID_SHELLS)}."
        if "columns" in children and not _is_str_list(children["columns"]):
            return "ui_schema.children.columns must be a list of non-empty strings."
        if "roll_up" in children and not isinstance(children["roll_up"], bool):
            return "ui_schema.children.roll_up must be a boolean."

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
            icon = cfg.get("icon")
            if icon is not None:
                if not isinstance(icon, str) or not icon.strip():
                    return f"ui_schema.state_display['{state_name}'].icon must be a string."
                if icon not in VALID_ICONS:
                    return (
                        f"Unknown icon '{icon}' for state '{state_name}'. "
                        f"Valid: {', '.join(VALID_ICONS)}."
                    )

    swimlanes = ui_schema.get("swimlanes")
    if swimlanes is not None and not _is_group_field(swimlanes):
        return (
            "ui_schema.swimlanes must be 'current_state', 'parent', "
            "or 'metadata.<key>'."
        )

    matrix = ui_schema.get("matrix")
    if matrix is not None:
        if not isinstance(matrix, dict):
            return "ui_schema.matrix must be an object."
        for axis in ("rows", "columns"):
            if axis in matrix and not _is_group_field(matrix[axis]):
                return (
                    f"ui_schema.matrix.{axis} must be 'current_state', 'parent', "
                    "or 'metadata.<key>'."
                )

    instance_view = ui_schema.get("instance_view")
    if instance_view is not None:
        if not isinstance(instance_view, dict):
            return "ui_schema.instance_view must be an object."
        title_field = instance_view.get("title_field")
        if title_field is not None and (not isinstance(title_field, str) or not title_field.strip()):
            return "ui_schema.instance_view.title_field must be a non-empty string."
        panels = instance_view.get("panels")
        if panels is not None:
            if not _is_str_list(panels):
                return "ui_schema.instance_view.panels must be a list of non-empty strings."
            unknown = [p for p in panels if p not in VALID_PANELS]
            if unknown:
                return (
                    f"Unknown instance_view panel(s): {', '.join(unknown)}. "
                    f"Valid: {', '.join(VALID_PANELS)}."
                )
        layout = instance_view.get("layout")
        if layout is not None and layout not in VALID_LAYOUTS:
            return (
                f"Unknown instance_view layout '{layout}'. "
                f"Valid: {', '.join(VALID_LAYOUTS)}."
            )

    return None
