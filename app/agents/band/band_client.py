"""Band connector — WP-02 / freeze gate G-BAND-CONTRACT.

The seam the agent ports (WP-03/04/05) build against. FOUR operations:

  1. ``send(room_id, mentions, body, correlation_id=None)`` → deliver a message to the
     @mentioned agents. **Fire-and-forget: returns the message id, never a reply.**
     (Band's `thenvoi_send_message` has no return value — regular text is an internal
     thought; only @mentioned participants receive a message.)
  2. ``on_message(handle, callback)`` → register an inbound handler for an agent handle.
  3. ``read_context(room_id, limit=50)`` → the shared room message log (Band's
     ``GET /api/v1/agent/chats/{id}/context``). This is our shared blackboard — Memory
     API is Enterprise-only and we are on Pro.
  4. ``collect_reply(correlation_id, timeout=...)`` → block until the terminal reply for
     a correlation id is posted, then return it. This is the **reply-collection seam**
     (Round 2, G-05): it is how the synchronous WhatsApp webhook gets its answer back
     out of an async room. An agent marks its message terminal via ``send(..., terminal=True)``.

Two backends, chosen by ``BAND_BACKEND``:

  * ``"stub"`` (default) — in-process and **fire-and-forget** (G-06): ``send`` returns a
    message id and dispatches to handlers, but discards their return value, so callers
    *cannot* rely on a synchronous return the way the retired ``BandSDK`` broker allowed.
    Replies arrive out-of-band via ``collect_reply``. Lets WP-03/04/05 be built/tested
    offline against the real async + reply-collection semantics.
  * ``"live"`` — the real band.ai / Thenvoi platform over REST (and optionally the
    `band-sdk` WebSocket runtime). Gated behind credentials; endpoints per docs.band.ai.
    **Not exercised here** — WP-02's live round-trip is pending the user's Band creds +
    identity confirmation (open question #1).
"""

import time
import uuid


# --- Stub backend (default) ------------------------------------------------

class _StubBackend:
    """In-process, fire-and-forget. Models the async contract without a network."""

    def __init__(self):
        self._handlers = {}     # handle -> callback(message: dict)
        self._log = []          # room_id -> ordered messages (flat list with room_id)
        self._replies = {}      # correlation_id -> terminal reply content

    def on_message(self, handle, callback):
        self._handlers[handle] = callback

    def send(self, room_id, mentions, body, correlation_id=None, sender=None, terminal=False):
        msg = {
            "id": uuid.uuid4().hex,
            "room_id": room_id,
            "sender": sender,
            "mentions": list(mentions or []),
            "body": body,
            "correlation_id": correlation_id,
            "terminal": terminal,
        }
        self._log.append(msg)
        if terminal and correlation_id is not None:
            self._replies[correlation_id] = body
        # Fire-and-forget: deliver to each @mentioned handler, DISCARD return values.
        for handle in msg["mentions"]:
            cb = self._handlers.get(handle)
            if cb is not None:
                try:
                    cb(dict(msg))
                except Exception as e:  # a handler crash must not kill the sender
                    print(f"[Band stub] handler {handle!r} raised: {e}")
        return msg["id"]

    def read_context(self, room_id, limit=50):
        msgs = [m for m in self._log if m["room_id"] == room_id]
        return msgs[-limit:]

    def collect_reply(self, correlation_id, timeout=10.0, poll=0.05):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if correlation_id in self._replies:
                return self._replies.pop(correlation_id)
            time.sleep(poll)
        return None


# --- Live backend (scaffold — pending creds + identity confirmation) -------

class _LiveBackend:
    """Real band.ai / Thenvoi over REST. Endpoints per docs.band.ai — confirm before use.

    Reply collection polls ``read_context`` for the terminal message tagged with the
    correlation id (carried in message metadata). The `band-sdk` package is imported
    lazily so the stub path never requires it to be installed.
    """

    REST_DEFAULT = "https://app.band.ai/"

    def __init__(self, config=None):
        cfg = config or {}
        self.rest_url = (cfg.get("BAND_REST_URL") or self.REST_DEFAULT).rstrip("/")
        self.agents = cfg.get("agents", {})   # handle -> {"agent_id":..., "api_key":...}
        if not self.agents:
            raise RuntimeError(
                "BAND_BACKEND=live but no agent credentials configured "
                "(register agents on app.band.ai and set BAND_*_AGENT_ID / BAND_*_API_KEY)."
            )
        import requests  # local import; only the live path needs it
        self._requests = requests

    def _api_key(self, sender):
        return (self.agents.get(sender) or {}).get("api_key", "")

    def read_context(self, room_id, limit=50, as_agent=None):
        # GET /api/v1/agent/chats/{chat_id}/context  (X-API-Key)
        url = f"{self.rest_url}/api/v1/agent/chats/{room_id}/context"
        r = self._requests.get(url, headers={"X-API-Key": self._api_key(as_agent)},
                               params={"limit": str(limit)}, timeout=15)
        r.raise_for_status()
        return r.json()

    def send(self, room_id, mentions, body, correlation_id=None, sender=None, terminal=False):
        # POST the message as `sender`, @mentioning `mentions`. Exact path per docs.band.ai
        # (the SDK's thenvoi_send_message tool dispatches to REST under the hood).
        raise NotImplementedError(
            "Live send is pending Band credentials + endpoint confirmation (open question #1). "
            "Use BAND_BACKEND=stub until WP-02's live spike is signed off."
        )

    def collect_reply(self, correlation_id, timeout=30.0, poll=1.0, room_id=None, as_agent=None):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for m in self.read_context(room_id, as_agent=as_agent):
                meta = m.get("metadata") or {}
                if meta.get("correlation_id") == correlation_id and meta.get("terminal"):
                    return m.get("content")
            time.sleep(poll)
        return None


# --- Facade + factory ------------------------------------------------------

class BandClient:
    """Thin facade over a backend. The agent ports depend only on this surface."""

    def __init__(self, backend):
        self._backend = backend

    def on_message(self, handle, callback):
        return self._backend.on_message(handle, callback)

    def send(self, room_id, mentions, body, correlation_id=None, sender=None, terminal=False):
        return self._backend.send(room_id, mentions, body,
                                  correlation_id=correlation_id, sender=sender, terminal=terminal)

    def read_context(self, room_id, limit=50):
        return self._backend.read_context(room_id, limit=limit)

    def collect_reply(self, correlation_id, timeout=10.0):
        return self._backend.collect_reply(correlation_id, timeout=timeout)


def get_band_client(backend=None, config=None):
    """Build a BandClient for the configured backend (``stub`` default, or ``live``)."""
    if backend is None:
        try:
            from flask import current_app
            backend = current_app.config.get("BAND_BACKEND", "stub") if current_app else "stub"
        except Exception:
            import os
            backend = os.getenv("BAND_BACKEND", "stub")
    backend = (backend or "stub").lower()
    if backend == "live":
        return BandClient(_LiveBackend(config=config))
    return BandClient(_StubBackend())
