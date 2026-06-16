import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.anyio
async def test_evaluate_endpoint_returns_actions_in_priority_order():
    payload = {
        "rules": [
            {
                "priority": 20,
                "condition": {"field": "claim_value", "operator": "gt", "value": 5000},
                "action": {"type": "assign_role", "role": "director"},
            },
            {
                "priority": 10,
                "condition": {"field": "category", "operator": "eq", "value": "Liability"},
                "action": {"type": "notify", "channel": "email"},
            },
        ],
        "data": {"claim_value": 7500, "category": "Liability"},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/evaluate", json=payload)

    assert response.status_code == 200
    assert response.json()["actions"] == [
        {"type": "notify", "channel": "email"},
        {"type": "assign_role", "role": "director"},
    ]


@pytest.mark.parametrize(
    ("operator", "value", "expected_actions"),
    [
        ("eq", "Liability", 1),
        ("ne", "Property", 1),
        ("gt", 1000, 1),
        ("gte", 5000, 1),
        ("lt", 9000, 1),
        ("lte", 7000, 1),
        ("contains", "Liab", 1),
        ("starts_with", "Lia", 1),
        ("is_true", None, 1),
        ("is_false", None, 0),
    ],
)
@pytest.mark.anyio
async def test_evaluate_endpoint_operator_matrix(operator, value, expected_actions):
    condition = {"field": "category", "operator": operator}
    if operator in {"gt", "gte", "lt", "lte"}:
        condition = {"field": "claim_value", "operator": operator, "value": value}
    elif operator in {"is_true", "is_false"}:
        condition = {"field": "urgent", "operator": operator}
    else:
        condition["value"] = value

    payload = {
        "rules": [
            {
                "priority": 10,
                "condition": condition,
                "action": {"type": "notify", "channel": "email"},
            }
        ],
        "data": {"claim_value": 7000, "category": "Liability", "urgent": True},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/evaluate", json=payload)

    assert response.status_code == 200
    assert len(response.json()["actions"]) == expected_actions
