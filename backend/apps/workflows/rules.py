import httpx
from decouple import config

from apps.workflows.models import Rule


def _compare(lhs, operator, rhs):
    if operator == "eq":
        return lhs == rhs
    if operator == "ne":
        return lhs != rhs
    if operator == "gt":
        return lhs is not None and lhs > rhs
    if operator == "gte":
        return lhs is not None and lhs >= rhs
    if operator == "lt":
        return lhs is not None and lhs < rhs
    if operator == "lte":
        return lhs is not None and lhs <= rhs
    if operator == "contains":
        return str(rhs) in str(lhs)
    if operator == "starts_with":
        return str(lhs).startswith(str(rhs))
    if operator == "is_true":
        return bool(lhs) is True
    if operator == "is_false":
        return bool(lhs) is False
    return False


def evaluate_condition(condition, data):
    operator = condition.get("operator")
    if operator in {"and", "or"}:
        conditions = condition.get("conditions", [])
        if operator == "and":
            return all(evaluate_condition(c, data) for c in conditions)
        return any(evaluate_condition(c, data) for c in conditions)

    field = condition.get("field")
    value = condition.get("value")
    lhs = data.get(field)
    return _compare(lhs, operator, value)


def evaluate_rules_local(rules, data):
    actions = []
    for rule in sorted(rules, key=lambda r: r.priority):
        if evaluate_condition(rule.condition, data):
            actions.append({"rule_id": str(rule.id), **rule.action})
    return actions


def evaluate_rules_via_service(rules, data):
    rules_service_url = config("RULES_SERVICE_URL", default="").rstrip("/")
    if not rules_service_url:
        return evaluate_rules_local(rules, data)

    payload = {
        "rules": [
            {
                "id": str(rule.id),
                "priority": rule.priority,
                "condition": rule.condition,
                "action": rule.action,
            }
            for rule in rules
        ],
        "data": data,
    }

    try:
        response = httpx.post(f"{rules_service_url}/evaluate", json=payload, timeout=2.0)
        response.raise_for_status()
        return response.json().get("actions", [])
    except Exception:
        return evaluate_rules_local(rules, data)


def evaluate_for_transition(instance, transition):
    scoped_rules = Rule.objects.filter(workflow_definition=instance.workflow_definition).filter(
        transition__isnull=True
    )
    transition_rules = Rule.objects.filter(
        workflow_definition=instance.workflow_definition,
        transition=transition,
    )
    rules = list(scoped_rules) + list(transition_rules)
    return evaluate_rules_via_service(rules, instance.metadata or {})
