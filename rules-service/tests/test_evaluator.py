from evaluator import evaluate_rules


def test_evaluate_rules_prioritized_actions():
    rules = [
        {
            "priority": 20,
            "condition": {"field": "claim_value", "operator": "gt", "value": 5000},
            "action": {"type": "assign_role", "role": "director"},
        },
        {
            "priority": 10,
            "condition": {
                "operator": "and",
                "conditions": [
                    {"field": "claim_value", "operator": "gt", "value": 1000},
                    {"field": "category", "operator": "eq", "value": "Liability"},
                ],
            },
            "action": {"type": "notify", "channel": "email"},
        },
    ]

    actions = evaluate_rules(rules, {"claim_value": 7000, "category": "Liability"})
    assert actions == [
        {"type": "notify", "channel": "email"},
        {"type": "assign_role", "role": "director"},
    ]
