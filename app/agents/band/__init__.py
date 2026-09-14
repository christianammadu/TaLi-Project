"""Multi-Agent Orchestration layer.

Exposes the connector seam the agent ports build against, plus the factory.
"""

from app.agents.band.band_client import BandClient, get_band_client
from app.agents.orchestrator import OrchestratorClient, get_orchestrator

__all__ = ["BandClient", "get_band_client", "OrchestratorClient", "get_orchestrator"]
