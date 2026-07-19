"""Integration tests for rules service circuit breaker and timeout resilience."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import httpx

from apps.workflows.rules import (
    CircuitBreaker,
    CircuitBreakerState,
    evaluate_rules_via_service,
    evaluate_rules_local,
    _rules_circuit_breaker,
)
from tests.factories import RuleFactory


class TestCircuitBreaker:
    """Unit tests for CircuitBreaker state machine."""

    def test_circuit_breaker_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    def test_circuit_breaker_closes_on_success(self):
        cb = CircuitBreaker(failure_threshold=3)

        def success_func():
            return "ok"

        result = cb.call(success_func)
        assert result == "ok"
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    def test_circuit_breaker_increments_failures(self):
        cb = CircuitBreaker(failure_threshold=3)

        def fail_func():
            raise Exception("failure")

        with pytest.raises(Exception):
            cb.call(fail_func)

        assert cb.failure_count == 1
        assert cb.state == CircuitBreakerState.CLOSED

    def test_circuit_breaker_opens_at_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)

        def fail_func():
            raise Exception("failure")

        for _ in range(3):
            with pytest.raises(Exception):
                cb.call(fail_func)

        assert cb.state == CircuitBreakerState.OPEN

    def test_circuit_breaker_prevents_calls_when_open(self):
        cb = CircuitBreaker(failure_threshold=1)

        def fail_func():
            raise Exception("failure")

        # Trigger open
        with pytest.raises(Exception):
            cb.call(fail_func)

        assert cb.state == CircuitBreakerState.OPEN

        # Next call should fail immediately with "Circuit breaker is OPEN"
        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            cb.call(fail_func)

    def test_circuit_breaker_half_open_recovery(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=0)

        def fail_func():
            raise Exception("failure")

        # Trigger open
        with pytest.raises(Exception):
            cb.call(fail_func)

        assert cb.state == CircuitBreakerState.OPEN

        # Simulate time passing (recovery_timeout_seconds=0 means immediate)
        # Next call should transition to HALF_OPEN and attempt recovery
        def success_func():
            return "recovered"

        result = cb.call(success_func)
        assert result == "recovered"
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    def test_circuit_breaker_resets_on_success_from_half_open(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=0)

        def fail_func():
            raise Exception("failure")

        # Cause 2 failures to open circuit
        with pytest.raises(Exception):
            cb.call(fail_func)
        with pytest.raises(Exception):
            cb.call(fail_func)

        assert cb.state == CircuitBreakerState.OPEN

        # Recovery attempt succeeds
        def success_func():
            return "ok"

        result = cb.call(success_func)
        assert result == "ok"
        assert cb.state == CircuitBreakerState.CLOSED


@pytest.mark.django_db
class TestRulesServiceTimeout:
    """Integration tests for rules service timeout handling."""

    def test_rules_service_timeout_falls_back_to_local(self):
        """Service timeout should fall back to local evaluation."""
        rule = RuleFactory(
            condition={"field": "status", "operator": "eq", "value": "urgent"},
            action={"block_transition": True},
        )

        data = {"status": "urgent"}

        # Mock httpx.post to timeout
        with patch("apps.workflows.rules.httpx.post") as mock_post:
            mock_post.side_effect = httpx.TimeoutException("timeout")

            with patch("apps.workflows.rules.config") as mock_config:
                def config_side_effect(key, default=None):
                    if key == "RULES_SERVICE_URL":
                        return "http://localhost:8001"
                    elif key == "RULES_SERVICE_TIMEOUT_SECONDS":
                        return 2.0
                    return default

                mock_config.side_effect = config_side_effect

                # Reset circuit breaker to closed state
                _rules_circuit_breaker.state = CircuitBreakerState.CLOSED
                _rules_circuit_breaker.failure_count = 0

                # Should fall back to local evaluation
                actions = evaluate_rules_via_service([rule], data)

                # Local evaluation should return the action
                assert len(actions) == 1
                assert actions[0]["block_transition"] is True

    def test_rules_service_connection_error_falls_back(self):
        """Service connection error should fall back to local evaluation."""
        rule = RuleFactory(
            condition={"field": "approved", "operator": "is_false"},
            action={"send_notification": True},
        )

        data = {"approved": False}

        with patch("apps.workflows.rules.httpx.post") as mock_post:
            mock_post.side_effect = httpx.ConnectError("cannot connect")

            with patch("apps.workflows.rules.config") as mock_config:
                def config_side_effect(key, default=None):
                    if key == "RULES_SERVICE_URL":
                        return "http://localhost:8001"
                    elif key == "RULES_SERVICE_TIMEOUT_SECONDS":
                        return 2.0
                    return default

                mock_config.side_effect = config_side_effect

                _rules_circuit_breaker.state = CircuitBreakerState.CLOSED
                _rules_circuit_breaker.failure_count = 0

                actions = evaluate_rules_via_service([rule], data)
                assert len(actions) == 1
                assert actions[0]["send_notification"] is True

    def test_rules_service_http_error_falls_back(self):
        """Service HTTP 5xx error should fall back to local evaluation."""
        rule = RuleFactory(
            condition={"field": "priority", "operator": "gt", "value": 5},
            action={"escalate": True},
        )

        data = {"priority": 8}

        with patch("apps.workflows.rules.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )
            mock_post.return_value = mock_response

            with patch("apps.workflows.rules.config") as mock_config:
                def config_side_effect(key, default=None):
                    if key == "RULES_SERVICE_URL":
                        return "http://localhost:8001"
                    elif key == "RULES_SERVICE_TIMEOUT_SECONDS":
                        return 2.0
                    return default

                mock_config.side_effect = config_side_effect

                _rules_circuit_breaker.state = CircuitBreakerState.CLOSED
                _rules_circuit_breaker.failure_count = 0

                actions = evaluate_rules_via_service([rule], data)
                assert len(actions) == 1
                assert actions[0]["escalate"] is True


@pytest.mark.django_db
class TestRulesServiceCircuitBreaker:
    """Integration tests for circuit breaker behavior."""

    def test_circuit_breaker_opens_after_threshold_failures(self):
        """Circuit breaker should open after configured failure threshold."""
        rule = RuleFactory()
        data = {"test": "data"}

        with patch("apps.workflows.rules.httpx.post") as mock_post:
            mock_post.side_effect = httpx.ConnectError("cannot connect")

            with patch("apps.workflows.rules.config") as mock_config:
                def config_side_effect(key, default=None):
                    if key == "RULES_SERVICE_URL":
                        return "http://localhost:8001"
                    elif key == "RULES_SERVICE_TIMEOUT_SECONDS":
                        return 2.0
                    elif key == "RULES_SERVICE_FAILURE_THRESHOLD":
                        return "2"  # Lower threshold for testing
                    elif key == "RULES_SERVICE_RECOVERY_TIMEOUT_SECONDS":
                        return "60"
                    return default

                mock_config.side_effect = config_side_effect

                _rules_circuit_breaker.state = CircuitBreakerState.CLOSED
                _rules_circuit_breaker.failure_count = 0
                _rules_circuit_breaker.failure_threshold = 2

                # First failure
                evaluate_rules_via_service([rule], data)
                assert _rules_circuit_breaker.state == CircuitBreakerState.CLOSED

                # Second failure opens circuit
                evaluate_rules_via_service([rule], data)
                assert _rules_circuit_breaker.state == CircuitBreakerState.OPEN

    def test_circuit_breaker_skips_service_when_open(self):
        """When circuit is open, should skip service calls entirely."""
        rule = RuleFactory()
        data = {"test": "data"}

        # Force circuit to OPEN
        _rules_circuit_breaker.state = CircuitBreakerState.OPEN
        _rules_circuit_breaker.failure_count = 10
        _rules_circuit_breaker.last_failure_time = datetime.now()

        with patch("apps.workflows.rules.httpx.post") as mock_post:
            with patch("apps.workflows.rules.config") as mock_config:
                def config_side_effect(key, default=None):
                    if key == "RULES_SERVICE_URL":
                        return "http://localhost:8001"
                    elif key == "RULES_SERVICE_TIMEOUT_SECONDS":
                        return 2.0
                    return default

                mock_config.side_effect = config_side_effect

                # Service should not be called
                actions = evaluate_rules_via_service([rule], data)

                # Should fall back to local evaluation instead
                assert mock_post.call_count == 0
                # Local evaluation is used as fallback
                assert isinstance(actions, list)

    def test_circuit_breaker_recovery_attempt_after_timeout(self):
        """Circuit breaker should attempt recovery after timeout period."""
        _rules_circuit_breaker.state = CircuitBreakerState.OPEN
        _rules_circuit_breaker.failure_count = 5
        _rules_circuit_breaker.last_failure_time = datetime.now() - timedelta(seconds=61)
        _rules_circuit_breaker.recovery_timeout_seconds = 60

        # Should be ready to attempt recovery
        assert _rules_circuit_breaker._should_attempt_reset() is True
