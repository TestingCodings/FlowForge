"""Unit tests for ui_schema validation (VISION Layer 2)."""
import pytest

from apps.workflows.ui_schema import validate_ui_schema


def test_matrix_shell_is_valid():
    assert validate_ui_schema({"shell": "matrix"}) is None


def test_stepped_form_shell_is_valid():
    assert validate_ui_schema({"shell": "stepped_form"}) is None


def test_unknown_shell_rejected():
    err = validate_ui_schema({"shell": "gantt"})
    assert err and "gantt" in err and "matrix" in err


@pytest.mark.parametrize("axes", [
    {"rows": "parent", "columns": "current_state"},
    {"rows": "metadata.suite", "columns": "metadata.run"},
    {"rows": "current_state"},
    {},
])
def test_valid_matrix_axes(axes):
    assert validate_ui_schema({"shell": "matrix", "matrix": axes}) is None


@pytest.mark.parametrize("axes", [
    {"rows": "metadata."},        # empty metadata key
    {"columns": "assignee"},      # bare key without the metadata. prefix
    {"rows": ""},
    {"columns": 7},
])
def test_invalid_matrix_axes_rejected(axes):
    err = validate_ui_schema({"shell": "matrix", "matrix": axes})
    assert err and "metadata.<key>" in err


def test_matrix_must_be_object():
    assert "must be an object" in validate_ui_schema({"matrix": ["rows"]})


@pytest.mark.parametrize("value", ["metadata.epic", "parent", "current_state"])
def test_valid_swimlanes(value):
    assert validate_ui_schema({"shell": "kanban", "swimlanes": value}) is None


def test_invalid_swimlanes_rejected():
    err = validate_ui_schema({"shell": "kanban", "swimlanes": "epic"})
    assert err and "swimlanes" in err


def test_state_display_icon_accepted():
    schema = {"state_display": {"Open": {"colour": "#fff", "icon": "play"}}}
    assert validate_ui_schema(schema) is None


def test_unknown_state_display_icon_rejected():
    err = validate_ui_schema({"state_display": {"Open": {"icon": "rocket"}}})
    assert err and "rocket" in err and "Open" in err


def test_instance_view_accepted():
    schema = {
        "instance_view": {
            "title_field": "summary",
            "panels": ["description", "metadata", "state_graph"],
            "layout": "stacked",
        }
    }
    assert validate_ui_schema(schema) is None


def test_instance_view_unknown_panel_rejected():
    err = validate_ui_schema({"instance_view": {"panels": ["description", "gantt"]}})
    assert err and "gantt" in err


def test_instance_view_unknown_layout_rejected():
    err = validate_ui_schema({"instance_view": {"layout": "grid"}})
    assert err and "grid" in err


def test_instance_view_must_be_object():
    assert "must be an object" in validate_ui_schema({"instance_view": "sidebar"})


def test_existing_schema_still_valid():
    """Regression: previously-valid schemas must keep validating."""
    schema = {
        "shell": "kanban",
        "card_fields": ["assignee", "priority"],
        "list_columns": ["reference", "metadata.priority"],
        "title_field": "summary",
        "state_display": {"Open": {"colour": "#6366f1"}},
        "children": {"workflows": ["Sub Task"], "shell": "table", "roll_up": True},
    }
    assert validate_ui_schema(schema) is None
