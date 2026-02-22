"""
Circuit Breaker Pattern for DriveGuard API resilience.

Prevents cascading failures by stopping calls to failing services
and using fallbacks instead of blocking on timeouts.

States:
    CLOSED  — Normal operation, requests flow through
    OPEN    — Service is down, requests short-circuit to fallback
    HALF_OPEN — Testing recovery, one request allowed through
"""

import time
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger("dg.circuit_breaker")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Generic circuit breaker for external service calls.

    Usage:
        cb = CircuitBreaker("dz_module", failure_threshold=3, recovery_timeout=30)

        if cb.can_execute():
            try:
                result = await call_service()
                cb.record_success()
            except Exception:
                cb.record_failure()
                result = fallback()
        else:
            result = fallback()  # Skip call entirely
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ):
        """
        Args:
            name: Identifier for logging (e.g. 'dz_module', 'weather_api')
            failure_threshold: Consecutive failures before opening circuit
            recovery_timeout: Seconds to wait before trying again (half-open)
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._success_count_since_half_open = 0

    @property
    def state(self) -> CircuitState:
        """Current state, with automatic OPEN → HALF_OPEN transition."""
        if self._state == CircuitState.OPEN and self._last_failure_time:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info(
                    f"CircuitBreaker[{self.name}]: OPEN → HALF_OPEN "
                    f"(after {elapsed:.0f}s recovery timeout)"
                )
        return self._state

    def can_execute(self) -> bool:
        """Check if a request should be attempted."""
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            return True  # Allow one test request
        return False  # OPEN — skip

    def record_success(self) -> None:
        """Record a successful call — close circuit if half-open."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count_since_half_open += 1
            if self._success_count_since_half_open >= 2:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count_since_half_open = 0
                logger.info(f"CircuitBreaker[{self.name}]: HALF_OPEN → CLOSED (recovered)")
        else:
            # Reset failure count on success in closed state
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call — open circuit if threshold reached."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # Failed during test — go back to open
            self._state = CircuitState.OPEN
            self._success_count_since_half_open = 0
            logger.warning(
                f"CircuitBreaker[{self.name}]: HALF_OPEN → OPEN (recovery test failed)"
            )
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                f"CircuitBreaker[{self.name}]: CLOSED → OPEN "
                f"({self._failure_count} consecutive failures)"
            )

    def get_status(self) -> dict:
        """Return status dict for health/debug endpoints."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_s": self.recovery_timeout,
            "last_failure": self._last_failure_time,
        }
