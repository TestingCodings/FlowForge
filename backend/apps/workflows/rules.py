import logging
import time
from datetime import datetime, timedelta
from enum import Enum

import httpx
from decouple import config

from apps.workflows.models import Rule

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker for rules service to prevent cascading failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: int = 60,
        expected_exception: type = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED

    def call(self, func, *args, **kwargs):
        """Execute func with circuit breaker protection."""
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info("Circuit breaker transitioning to HALF_OPEN, attempting recovery")
            else:
                raise Exception("Circuit breaker is OPEN; rules service unavailable")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as exc:
            self._on_failure()
            raise

    def _on_success(self):
        """Reset failure count on successful call."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            logger.info("Circuit breaker CLOSED; rules service recovered")
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED

    def _on_failure(self):
        """Increment failure count and open circuit if threshold reached."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(
                f"Circuit breaker OPEN after {self.failure_count} failures; "
                f"rules service unavailable"
            )

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if not self.last_failure_time:
            return False
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout_seconds


_rules_circuit_breaker = CircuitBreaker(
    failure_threshold=int(config("RULES_SERVICE_FAILURE_THRESHOLD", default=5)),
    recovery_timeout_seconds=int(config("RULES_SERVICE_RECOVERY_TIMEOUT_SECONDS", default=60)),
    expected_exception=Exception,
)


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


def _call_rules_service(rules_service_url: str, payload: dict) -> dict:
    """Call rules service with timeout. Raises Exception on failure."""
    timeout = float(config("RULES_SERVICE_TIMEOUT_SECONDS", default=2.0))
    response = httpx.post(
        f"{rules_service_url}/evaluate",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def evaluate_rules_via_service(rules, data):
    """Evaluate rules via remote service with circuit breaker and timeout.

    Falls back to local evaluation if:
    - RULES_SERVICE_URL not configured
    - Service call times out (default 2s)
    - Service returns error (HTTP 5xx, connection error, etc.)
    - Circuit breaker is open (after 5 consecutive failures)

    Circuit breaker recovers after 60 seconds of no attempts.
    """
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
        result = _rules_circuit_breaker.call(_call_rules_service, rules_service_url, payload)
        return result.get("actions", [])
    except Exception as exc:
        logger.warning(f"Rules service call failed: {exc}. Falling back to local evaluation.")
        return evaluate_rules_local(rules, data)


def _hierarchy_facts(instance):
    """Computed children facts injected into rule data.

    Lets rules express roll-up gating with existing operators — e.g.
    {"field": "children_complete", "operator": "is_false"} blocks a parent
    transition while children are open — and works identically in the local
    evaluator and the rules microservice, since it's just data.
    """
    total = instance.children.count()
    if total == 0:
        return {"children_total": 0, "children_open": 0, "children_complete": True}
    open_count = instance.children.filter(completed_at__isnull=True).count()
    return {
        "children_total": total,
        "children_open": open_count,
        "children_complete": open_count == 0,
    }


def evaluate_for_transition(instance, transition):
    scoped_rules = Rule.objects.filter(workflow_definition=instance.workflow_definition).filter(
        transition__isnull=True
    )
    transition_rules = Rule.objects.filter(
        workflow_definition=instance.workflow_definition,
        transition=transition,
    )
    rules = list(scoped_rules) + list(transition_rules)
    data = {**(instance.metadata_json or {}), **_hierarchy_facts(instance)}
    return evaluate_rules_via_service(rules, data)
