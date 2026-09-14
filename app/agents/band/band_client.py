"""Multi-Agent Orchestration Connector.

Provides backward-compatible connectors to the native in-house OrchestrationEngine.
Third-party band.ai / band-sdk dependencies have been completely removed in favor of
our own self-contained multi-agent collaboration architecture.
"""

from typing import Any, Dict, Optional
from app.agents.orchestrator import (
    AgentRoom,
    OrchestrationEngine,
    OrchestratorClient,
    get_orchestrator,
    _GLOBAL_ENGINE,
)

# Compatibility aliases for existing agent code
BandClient = OrchestratorClient


class _StubBackend(OrchestrationEngine):
    """In-process native orchestration engine backend."""
    pass


class _LiveBackend(OrchestrationEngine):
    """Native live orchestration backend (replaces third-party SDK)."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.config = config or {}


def get_band_client(backend: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> OrchestratorClient:
    """Return an OrchestratorClient instance for collaborative multi-agent workflows."""
    if backend and backend.lower() == "live":
        return OrchestratorClient(_LiveBackend(config=config))
    return get_orchestrator(backend=backend, config=config)


__all__ = [
    "BandClient",
    "OrchestratorClient",
    "get_band_client",
    "get_orchestrator",
    "AgentRoom",
    "OrchestrationEngine",
    "_StubBackend",
    "_LiveBackend",
]
