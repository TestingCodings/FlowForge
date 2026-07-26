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


def test_attachments_panel_is_valid():
    """The frontend advertises an `attachments` panel (WS-B); the backend
    allow-list must accept it or the panel can never be explicitly ordered."""
    assert validate_ui_schema({"instance_view": {"panels": ["state_graph", "attachments"]}}) is None


# ---------------------------------------------------------------------------
# scene shell (WS-I / docs/MEDIA.md Part 2)
# ---------------------------------------------------------------------------


def test_scene_shell_is_valid():
    assert validate_ui_schema({"shell": "scene"}) is None


def test_scene_config_accepted():
    schema = {
        "shell": "scene",
        "scene_config": {
            "Awakening": {
                "background": "https://example.test/room.png",
                "speaker": "Narrator",
                "dialogue": "You wake on a cold floor.",
                "music": "https://example.test/theme.mp3",
                "sprites": [
                    {"asset": "1f1c6e2a-0000-4000-8000-000000000001", "position": "left"},
                    {"asset": "https://example.test/ghost.png"},  # position defaults
                ],
            }
        },
    }
    assert validate_ui_schema(schema) is None


def test_scene_config_must_be_an_object():
    assert "keyed by state name" in validate_ui_schema({"scene_config": ["Awakening"]})


def test_scene_must_be_an_object():
    err = validate_ui_schema({"scene_config": {"Awakening": "You wake up."}})
    assert err and "Awakening" in err and "must be an object" in err


@pytest.mark.parametrize("key", ["background", "speaker", "dialogue", "music"])
def test_scene_text_fields_must_be_strings(key):
    err = validate_ui_schema({"scene_config": {"Awakening": {key: 42}}})
    assert err and key in err and "must be a string" in err


def test_sprites_must_be_a_list():
    err = validate_ui_schema({"scene_config": {"Awakening": {"sprites": {"asset": "x"}}}})
    assert err and "sprites must be a list" in err


def test_sprite_requires_an_asset():
    err = validate_ui_schema({"scene_config": {"Awakening": {"sprites": [{"position": "left"}]}}})
    assert err and "requires an 'asset'" in err and "[0]" in err


def test_sprite_position_must_be_known():
    """British spelling is deliberate ('centre'); guard against 'center' drift."""
    err = validate_ui_schema(
        {"scene_config": {"Awakening": {"sprites": [{"asset": "x", "position": "center"}]}}}
    )
    assert err and "left, centre, right" in err
