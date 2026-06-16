import pytest

from apps.workflows.rules import _compare, evaluate_condition, evaluate_rules_local
from tests.factories import RuleFactory


@pytest.mark.parametrize(
    ("lhs", "operator", "rhs", "expected"),
    [
        (1, "eq", 1, True),
        (1, "ne", 2, True),
        (5, "gt", 4, True),
        (5, "gte", 5, True),
        (4, "lt", 5, True),
        (4, "lte", 4, True),
        ("Liability Claim", "contains", "Liability", True),
        ("CLA-2026-00001", "starts_with", "CLA", True),
        (True, "is_true", None, True),
        (False, "is_false", None, True),
        ("x", "unknown", "y", False),
    ],
)
def test_compare_operators(lhs, operator, rhs, expected):
    assert _compare(lhs, operator, rhs) is expected


def test_evaluate_condition_compound_logic():
    payload = {"claim_value": 7000, "category": "Liability", "urgent": True}

    condition = {
        "operator": "and",
        "conditions": [
            {"field": "claim_value", "operator": "gt", "value": 1000},
            {
                "operator": "or",
                "conditions": [
                    {"field": "category", "operator": "eq", "value": "Liability"},
                    {"field": "urgent", "operator": "is_true"},
                ],
            },
        ],
    }

    assert evaluate_condition(condition, payload) is True


@pytest.mark.django_db
def test_evaluate_rules_local_applies_priority_order():
    low_priority = RuleFactory(
        priority=20,
        condition={"field": "claim_value", "operator": "gt", "value": 5000},
        action={"type": "assign_role", "role": "director"},
    )
    high_priority = RuleFactory(
        workflow_definition=low_priority.workflow_definition,
        priority=10,
        condition={"field": "category", "operator": "eq", "value": "Liability"},
        action={"type": "notify", "channel": "email"},
    )

    actions = evaluate_rules_local(
        [low_priority, high_priority],
        {"claim_value": 6000, "category": "Liability"},
    )

    assert len(actions) == 2
    assert actions[0]["type"] == "notify"
    assert actions[1]["type"] == "assign_role"
