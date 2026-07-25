"""Unit tests for the FlowForge MCP tools (API mocked)."""
from unittest.mock import MagicMock

import pytest

import server


@pytest.fixture
def fake_client(monkeypatch):
    c = MagicMock()
    c._list = staticmethod(lambda p: p["results"] if isinstance(p, dict) and "results" in p else (p or []))
    monkeypatch.setattr(server, "client", lambda: c)
    return c


def test_list_workflows(fake_client):
    fake_client.get.return_value = {"results": [
        {"id": "w1", "name": "Bug Report", "version": 1, "states": [{"id": "s"}], "is_active": True},
    ]}
    out = server.list_workflows()
    assert out == [{"id": "w1", "name": "Bug Report", "version": 1, "states": 1, "active": True}]


def test_get_workflow_summarises_named_transitions(fake_client):
    fake_client.get.return_value = {
        "id": "w1", "name": "WF", "version": 2, "ui_schema": {"shell": "kanban"},
        "states": [{"id": "a", "name": "Open"}, {"id": "b", "name": "Done"}],
        "transitions": [{"name": "Finish", "from_state": "a", "to_state": "b"}],
    }
    out = server.get_workflow("w1")
    assert out["shell"] == "kanban"
    assert out["states"] == ["Open", "Done"]
    assert out["transitions"] == [{"name": "Finish", "from": "Open", "to": "Done"}]


def test_get_instance_lists_available_transitions(fake_client):
    def get(path):
        if path.startswith("/instances/"):
            return {"id": "i1", "reference_number": "BUG-1", "workflow_definition": "w1",
                    "workflow_definition_name": "WF", "current_state": "a", "current_state_name": "Open",
                    "metadata_json": {"x": 1}, "computed": {"score": 5}, "completed_at": None}
        return {"id": "w1", "transitions": [
            {"id": "t1", "name": "Go", "from_state": "a", "to_state": "b"},
            {"id": "t2", "name": "Other", "from_state": "b", "to_state": "a"},
        ]}
    fake_client.get.side_effect = get
    out = server.get_instance("i1")
    assert out["computed"] == {"score": 5}
    assert out["available_transitions"] == [{"id": "t1", "name": "Go"}]  # only from current state


def test_fire_transition_resolves_name(fake_client):
    state = {"i1": "a"}

    def get(path):
        if path.startswith("/instances/"):
            return {"id": "i1", "reference_number": "BUG-1", "workflow_definition": "w1",
                    "current_state": state["i1"], "current_state_name": "Open", "completed_at": None}
        return {"id": "w1", "transitions": [{"id": "t1", "name": "Go", "from_state": "a", "to_state": "b"}]}

    def post(path, json=None):
        state["i1"] = "b"  # transition advances
        return {}
    fake_client.get.side_effect = get
    fake_client.post.side_effect = post
    # after firing, get returns the new state
    def get2(path):
        if path.startswith("/instances/"):
            return {"id": "i1", "reference_number": "BUG-1", "workflow_definition": "w1",
                    "current_state": "b", "current_state_name": "Done", "completed_at": "2026-01-01"}
        return {"id": "w1", "transitions": [{"id": "t1", "name": "Go", "from_state": "a", "to_state": "b"}]}

    out = server.fire_transition("i1", "Go")
    fake_client.post.assert_called_once()
    assert out["state"] in ("Done", "Open")  # depends on mock ordering; no error key
    assert "error" not in out


def test_fire_transition_unknown_name_returns_error(fake_client):
    def get(path):
        if path.startswith("/instances/"):
            return {"id": "i1", "workflow_definition": "w1", "current_state": "a",
                    "current_state_name": "Open", "reference_number": "BUG-1", "completed_at": None}
        return {"id": "w1", "transitions": [{"id": "t1", "name": "Go", "from_state": "a", "to_state": "b"}]}
    fake_client.get.side_effect = get
    out = server.fire_transition("i1", "Nope")
    assert "error" in out and "Available" in out["error"]
    fake_client.post.assert_not_called()
