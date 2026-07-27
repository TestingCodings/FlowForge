"""DSL rule actions must be in the shape the engine actually checks.

`then: {block_transition: true}` is the documented DSL syntax (it's in
dsl.py's own docstring and docs/BUILDER.md), but it compiled to
`{"block_transition": True}` while the engine tests `action["type"] ==
"block_transition"`. So every blocking rule authored through the YAML editor
silently did nothing — the workflow looked correctly configured and the rule
never fired.
"""
import pytest

from apps.workflows.dsl import parse_dsl

BASE = """
workflow: Gate
prefix: GAT

states:
  - name: Open
  - name: Closed
    terminal: true

transitions:
  - Open -> Closed:
      name: Shut
      rules:
        - if: {field: amount, op: gt, value: 10}
          then: %s
"""


def _action(then_clause: str) -> dict:
    return parse_dsl(BASE % then_clause)["rules"][0]["action"]


def test_block_transition_gets_the_engine_type():
    action = _action("{block_transition: true, reason: Too large}")
    assert action["type"] == "block_transition"
    assert action["reason"] == "Too large"


def test_message_is_accepted_as_an_alias_for_reason():
    """docs/BUILDER.md used `message:`; the engine reads `reason`."""
    assert _action("{block_transition: true, message: Nope}")["reason"] == "Nope"


def test_block_transition_without_a_reason_still_typed():
    assert _action("{block_transition: true}")["type"] == "block_transition"


def test_assign_role_gets_the_engine_type():
    action = _action("{assign_role: approver}")
    assert action["type"] == "assign_role"
    assert action["role"] == "approver"


def test_set_metadata_gets_the_engine_type():
    action = _action("{set_metadata: {escalated: true}}")
    assert action["type"] == "set_metadata"
    assert action["values"] == {"escalated": True}


def test_explicit_engine_form_passes_through_unchanged():
    """Authors may write the engine shape directly; don't mangle it."""
    action = _action('{type: block_transition, reason: Direct}')
    assert action == {"type": "block_transition", "reason": "Direct"}


def test_unknown_action_is_rejected_rather_than_silently_ignored():
    from apps.workflows.dsl import DslError

    with pytest.raises(DslError, match="unknown rule action"):
        parse_dsl(BASE % "{teleport: true}")
