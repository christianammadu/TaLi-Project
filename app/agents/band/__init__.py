"""Band coordination layer (WP-02 / freeze gate G-BAND-CONTRACT).

Exposes the connector seam the agent ports (WP-03/04/05) build against, plus the
backend factory. See `band_client.py` for the contract and `registration.md` for
agent handles + the WS-vs-REST decision.
"""

from app.agents.band.band_client import BandClient, get_band_client

__all__ = ["BandClient", "get_band_client"]
