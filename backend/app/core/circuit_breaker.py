"""
Circuit Breaker Pattern Implementation for ASTA Memory Tiers.

Ensures <150ms voice loop remains uninterrupted by wrapping L2 (Vector) 
and L3 (Graph) operations in circuit breakers with strict timeouts.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Circuit tripped, requests bypass (fail-fast)
- HALF_OPEN: Testing if service recovered
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Callable, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("CircuitBreaker")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitStats:
    """Tracks circuit breaker statistics."""
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    total_requests: int = 0
    total_failures: int = 0
    total_timeouts: int = 0
    state_changed_at: float = field(default_factory=time.time)


class CircuitBreaker:
    """
    Circuit breaker for protecting the voice loop from slow/failing subsystems.
    
    Configuration:
    - failure_threshold: Consecutive failures before opening (default: 3)
    - recovery_timeout: Seconds to wait before attempting recovery (default: 60)
    - timeout_ms: Max time to wait for operation (default: 250ms)
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 60.0,
        timeout_seconds: float = 0.250,
        half_open_max_calls: int = 1
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        self.timeout_seconds = timeout_seconds
        self.half_open_max_calls = half_open_max_calls
        
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
        
    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (allowing traffic)."""
        return self._state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (bypassing traffic)."""
        return self._state == CircuitState.OPEN
    
    @property
    def stats(self) -> CircuitStats:
        """Get current statistics."""
        return self._stats
    
    def _should_allow_request(self) -> bool:
        """Determine if request should be allowed based on state."""
        if self._state == CircuitState.CLOSED:
            return True
            
        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            elapsed = time.time() - self._stats.state_changed_at
            if elapsed >= self.recovery_timeout:
                logger.info(f"[CB:{self.name}] Recovery timeout elapsed, transitioning to HALF_OPEN")
                self._transition_to(CircuitState.HALF_OPEN)
                return True
            return False
            
        if self._state == CircuitState.HALF_OPEN:
            # Allow limited requests in half-open state
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False
            
        return False
    
    def _transition_to(self, new_state: CircuitState):
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._stats.state_changed_at = time.time()
        
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            
        logger.warning(f"[CB:{self.name}] State transition: {old_state.value} → {new_state.value}")
    
    def _record_success(self):
        """Record a successful operation."""
        self._stats.success_count += 1
        self._stats.last_success_time = time.time()
        self._stats.total_requests += 1
        
        if self._state == CircuitState.HALF_OPEN:
            logger.info(f"[CB:{self.name}] Success in HALF_OPEN, closing circuit")
            self._transition_to(CircuitState.CLOSED)
            self._stats.failure_count = 0
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            self._stats.failure_count = 0
    
    def _record_failure(self, is_timeout: bool = False):
        """Record a failed operation."""
        self._stats.failure_count += 1
        self._stats.total_failures += 1
        self._stats.total_requests += 1
        self._stats.last_failure_time = time.time()
        
        if is_timeout:
            self._stats.total_timeouts += 1
        
        if self._state == CircuitState.HALF_OPEN:
            logger.warning(f"[CB:{self.name}] Failure in HALF_OPEN, reopening circuit")
            self._transition_to(CircuitState.OPEN)
        elif self._state == CircuitState.CLOSED:
            if self._stats.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[CB:{self.name}] Failure threshold reached ({self._stats.failure_count}/{self.failure_threshold}), "
                    f"opening circuit"
                )
                self._transition_to(CircuitState.OPEN)
    
    async def call(
        self,
        operation: Callable[[], Any],
        fallback: Any = None,
        timeout_override: Optional[float] = None
    ) -> tuple[Any, bool]:
        """
        Execute an operation through the circuit breaker.
        
        Args:
            operation: Async callable to execute
            fallback: Value to return if circuit is open or operation fails
            timeout_override: Override default timeout (seconds)
            
        Returns:
            tuple: (result, success_flag)
        """
        timeout = timeout_override or self.timeout_seconds
        
        # Check if we should allow the request
        if not self._should_allow_request():
            logger.debug(f"[CB:{self.name}] Circuit OPEN, returning fallback")
            return fallback, False
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                operation(),
                timeout=timeout
            )
            self._record_success()
            return result, True
            
        except asyncio.TimeoutError:
            logger.warning(f"[CB:{self.name}] Operation timed out after {timeout}s")
            self._record_failure(is_timeout=True)
            return fallback, False
            
        except Exception as e:
            logger.error(f"[CB:{self.name}] Operation failed: {type(e).__name__}: {e}")
            self._record_failure()
            return fallback, False
    
    def force_open(self):
        """Manually open the circuit (for health checks)."""
        self._transition_to(CircuitState.OPEN)
        
    def force_close(self):
        """Manually close the circuit (for testing/recovery)."""
        self._transition_to(CircuitState.CLOSED)
        self._stats.failure_count = 0
    
    def get_health_report(self) -> dict:
        """Generate a health report for observability."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._stats.failure_count,
            "success_count": self._stats.success_count,
            "total_requests": self._stats.total_requests,
            "total_failures": self._stats.total_failures,
            "total_timeouts": self._stats.total_timeouts,
            "last_failure_time": self._stats.last_failure_time,
            "last_success_time": self._stats.last_success_time,
            "is_healthy": self._state == CircuitState.CLOSED
        }


class StatusRegistry:
    """
    Centralized health status registry for all ASTA subsystems.
    Tracks health of Redis, MongoDB, Neo4j, Pinecone, and memory tiers.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._health = {}
            cls._instance._circuit_breakers = {}
            cls._instance._lock = asyncio.Lock()
        return cls._instance
    
    def register_circuit_breaker(self, name: str, circuit_breaker: CircuitBreaker):
        """Register a circuit breaker for health tracking."""
        self._circuit_breakers[name] = circuit_breaker
        
    def get_circuit_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Get a registered circuit breaker."""
        return self._circuit_breakers.get(name)
    
    async def update_health(self, service: str, is_healthy: bool, details: dict = None):
        """Update health status for a service."""
        async with self._lock:
            self._health[service] = {
                "is_healthy": is_healthy,
                "last_check": datetime.now(timezone.utc).isoformat(),
                "details": details or {}
            }
    
    def get_health(self, service: str) -> dict:
        """Get health status for a specific service."""
        return self._health.get(service, {"is_healthy": False, "last_check": None})
    
    def get_all_health(self) -> dict:
        """Get health status for all services."""
        health_report = dict(self._health)
        
        # Add circuit breaker states
        for name, cb in self._circuit_breakers.items():
            health_report[f"circuit_{name}"] = cb.get_health_report()
        
        return health_report
    
    def get_memory_mode(self) -> str:
        """
        Determine current memory operation mode based on subsystem health.
        
        Returns:
            - "full": All tiers operational (L1 + L2 + L3)
            - "degraded_l3": L3 unavailable, using L1 + L2
            - "degraded_l2_l3": L2 and L3 unavailable, L1 only
            - "local_only": L1 only (minimal mode)
        """
        l2_healthy = self._health.get("l2_vector", {}).get("is_healthy", False)
        l3_healthy = self._health.get("l3_graph", {}).get("is_healthy", False)
        
        # Check circuit breakers
        l2_cb = self._circuit_breakers.get("l2_vector")
        l3_cb = self._circuit_breakers.get("l3_graph")
        
        if l2_cb and l2_cb.is_open:
            l2_healthy = False
        if l3_cb and l3_cb.is_open:
            l3_healthy = False
        
        if l2_healthy and l3_healthy:
            return "full"
        elif l2_healthy and not l3_healthy:
            return "degraded_l3"
        elif not l2_healthy and not l3_healthy:
            return "local_only"
        else:
            return "degraded_l2_l3"
    
    def get_status_summary(self) -> dict:
        """Get a summary for LLM context injection."""
        mode = self.get_memory_mode()
        
        return {
            "mode": mode,
            "l1_status": "operational",  # L1 is always operational (RAM)
            "l2_status": "operational" if "l2" not in mode or mode == "degraded_l3" else "degraded",
            "l3_status": "operational" if mode == "full" else "degraded",
            "redis_status": self._health.get("redis", {}).get("is_healthy", False),
            "mongodb_status": self._health.get("mongodb", {}).get("is_healthy", False),
            "neo4j_status": self._health.get("neo4j", {}).get("is_healthy", False),
            "pinecone_status": self._health.get("pinecone", {}).get("is_healthy", False)
        }


# Global singleton
status_registry = StatusRegistry()


# Pre-configured circuit breakers for memory tiers
circuit_l2_vector = CircuitBreaker(
    name="l2_vector",
    failure_threshold=3,
    recovery_timeout_seconds=60.0,
    timeout_seconds=0.250  # 250ms strict timeout
)

circuit_l3_graph = CircuitBreaker(
    name="l3_graph",
    failure_threshold=3,
    recovery_timeout_seconds=60.0,
    timeout_seconds=0.250  # 250ms strict timeout
)

# Register with status registry
status_registry.register_circuit_breaker("l2_vector", circuit_l2_vector)
status_registry.register_circuit_breaker("l3_graph", circuit_l3_graph)
