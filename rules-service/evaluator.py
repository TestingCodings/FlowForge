def _compare(lhs, operator, rhs):
    if operator == "eq":
        return lhs == rhs
    if operator == "ne":
        return lhs != rhs
    if operator == "gt":
        return lhs > rhs
    if operator == "gte":
        return lhs >= rhs
    if operator == "lt":
        return lhs < rhs
    if operator == "lte":
        return lhs <= rhs
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
        children = condition.get("conditions", [])
        if operator == "and":
            return all(evaluate_condition(child, data) for child in children)
        return any(evaluate_condition(child, data) for child in children)

    field = condition.get("field")
    value = condition.get("value")
    lhs = data.get(field)
    return _compare(lhs, operator, value)


def evaluate_rules(rules, data):
    matched_actions = []
    for rule in sorted(rules, key=lambda r: r.get("priority", 100)):
        if evaluate_condition(rule.get("condition", {}), data):
            matched_actions.append(rule.get("action", {}))
    return matched_actions
