from typing import Any, Dict, Type, TypeVar

T = TypeVar('T')

class ServiceRegistry:
    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Any] = {}

    def register(self, name: str, instance: Any) -> None:
        """Register a singleton instance."""
        self._services[name] = instance

    def register_factory(self, name: str, factory_func: Any) -> None:
        """Register a factory for transient/scoped instances."""
        self._factories[name] = factory_func

    def get(self, name: str) -> Any:
        """Retrieve a service by name."""
        if name in self._services:
            return self._services[name]
        if name in self._factories:
            return self._factories[name]()
        raise KeyError(f"Service '{name}' not found in registry.")

    def clear(self) -> None:
        """Clear registry (mostly for testing)."""
        self._services.clear()
        self._factories.clear()

# Global registry instance
registry = ServiceRegistry()

def safe_get(service_name: str) -> Any:
    try:
        return registry.get(service_name)
    except KeyError:
        return None
