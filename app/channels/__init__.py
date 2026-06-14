"""Messaging channels (WP-01 / G-CHANNEL-CONTRACT).

The channel-agnostic seam between messaging platforms and TaLi's Band gateway.
"""
from app.channels.base import (
    Channel, InboundMessage, WHATSAPP, TELEGRAM, make_address, split_address,
)

__all__ = ["Channel", "InboundMessage", "WHATSAPP", "TELEGRAM", "make_address", "split_address"]
