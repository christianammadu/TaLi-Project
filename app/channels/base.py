"""Channel abstraction — WP-01 / freeze gate G-CHANNEL-CONTRACT.

A ``Channel`` is the thin translation layer between a messaging platform (WhatsApp,
Telegram, …) and TaLi's channel-agnostic gateway/agents. Every platform implements the
same four jobs; the gateway depends only on this surface, so adding a channel never
touches the agents.

Identity is **channel-namespaced**: a ``sender`` is ``wa:<phone>`` / ``tg:<chat_id>`` so
one account can link multiple channels (see WP-02 ``channel_accounts``).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

WHATSAPP = "whatsapp"
TELEGRAM = "telegram"
PREFIX = {WHATSAPP: "wa", TELEGRAM: "tg"}
_BY_PREFIX = {v: k for k, v in PREFIX.items()}


def make_address(channel, native_id):
    """Namespaced sender, e.g. ``make_address('whatsapp', '2348012345678') -> 'wa:2348012345678'``."""
    try:
        return f"{PREFIX[channel]}:{native_id}"
    except KeyError:
        raise ValueError(f"unknown channel: {channel!r}")


def split_address(address):
    """Inverse of ``make_address`` → ``(channel, native_id)``.

    Tolerates a bare native id (legacy WhatsApp rows stored the raw phone, no prefix):
    returns ``(None, address)`` so callers can fall back to the legacy lookup.
    """
    if address and ":" in address:
        pre, native = address.split(":", 1)
        if pre in _BY_PREFIX:
            return _BY_PREFIX[pre], native
    return None, address


@dataclass
class InboundMessage:
    """A platform message normalized to the shape the gateway understands."""
    channel: str
    sender: str                         # namespaced: wa:<phone> / tg:<chat_id>
    text: str
    message_id: str
    command: Optional[str] = None       # bot command if present, e.g. "start", "link"
    command_arg: Optional[str] = None   # its argument, e.g. a binding token / "telegram"
    raw: dict = field(default_factory=dict)

    @property
    def native_id(self):
        """The platform-native id (phone / chat_id) without the channel prefix."""
        return split_address(self.sender)[1]


class Channel(ABC):
    """The seam every messaging platform implements (frozen contract — G-CHANNEL-CONTRACT)."""

    name: str = ""

    @abstractmethod
    def parse_inbound(self, request) -> Optional[InboundMessage]:
        """Turn a raw inbound webhook request into an ``InboundMessage`` — or ``None`` if the
        payload carries no user message (e.g. a delivery/status callback)."""

    @abstractmethod
    def verify(self, request) -> bool:
        """Confirm the request genuinely came from the platform (signature / secret token)."""

    @abstractmethod
    def send_text(self, sender, text):
        """Send a text reply to a (namespaced) sender."""

    @abstractmethod
    def send_document(self, sender, file_path, filename, caption=None):
        """Send a document (PDF/Excel) to a (namespaced) sender. Returns ``(success, detail)``."""
