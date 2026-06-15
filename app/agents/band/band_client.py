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

import json
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


# --- Live backend: in-process orchestration + a best-effort Band-room mirror ---
#
# The agents are LOCAL (the Ledger writes our MySQL), so Band is the coordination/
# audit surface, not an autonomous runtime. We therefore keep the stub's reliable,
# synchronous in-process @mention dispatch + reply collection (the REST-over-sync-Flask
# decision in registration.md) and additionally MIRROR each handoff into the real Band
# room via REST — under the sending agent's API key, translating the internal @tali-*
# handles to each agent's real handle on the tenant. The mirror is best-effort: a room
# post failure never breaks bookkeeping. (band-sdk's persistent-WebSocket runtime is
# deliberately not used — it needs a long-running process the sync webhook doesn't have.)

class _LiveBackend(_StubBackend):
    REST_DEFAULT = "https://app.band.ai"
    PATH_DEFAULT = "/api/v1/agent/chats/{chat_id}/messages"

    def __init__(self, config=None):
        super().__init__()
        cfg = config or {}
        self.rest_url = (cfg.get("rest_url") or self.REST_DEFAULT).rstrip("/")
        self.room_id = cfg.get("room_id") or ""
        self.message_path = cfg.get("message_path") or self.PATH_DEFAULT
        # internal handle -> {"agent_id", "api_key", "remote_handle"}
        self.agents = cfg.get("agents", {})
        if not self.agents:
            raise RuntimeError(
                "BAND_BACKEND=live but no agent credentials configured — set "
                "BAND_*_AGENT_ID / BAND_*_API_KEY (see app/agents/band/registration.md)."
            )
        try:
            import requests  # local import; only the live path needs it
            self._requests = requests
        except Exception as e:  # pragma: no cover
            self._requests = None
            print(f"[Band live] 'requests' unavailable ({e}); room mirror disabled.")
        self._mirror_on = bool(self.room_id) and self._requests is not None
        if not self.room_id:
            print("[Band live] BAND_ROOM_ID unset — agents run in-process only "
                  "(set BAND_ROOM_ID to mirror handoffs into the Band room).")

    def _remote_handle(self, internal):
        """internal @tali-* handle -> the agent's real @handle on the tenant."""
        return (self.agents.get(internal) or {}).get("remote_handle") or internal

    def _post_creds(self, sender):
        """Creds of the posting agent. The gateway/human aren't registered Band agents,
        so fall back to any registered agent's key so the message still appears."""
        return self.agents.get(sender) or next(iter(self.agents.values()), {})

    def send(self, room_id, mentions, body, correlation_id=None, sender=None, terminal=False):
        # 1) Authoritative: synchronous in-process dispatch + reply capture (inherited).
        mid = super().send(room_id, mentions, body, correlation_id=correlation_id,
                           sender=sender, terminal=terminal)
        # 2) Best-effort: mirror the handoff into the real Band room for visibility/audit.
        if self._mirror_on:
            try:
                self._mirror(room_id or self.room_id, mentions, body, sender)
            except Exception as e:
                print(f"[Band live] room mirror error (continuing in-process): {e}")
        return mid

    def _mirror(self, room_id, mentions, body, sender):
        creds = self._post_creds(sender)
        api_key = creds.get("api_key")
        if not (room_id and api_key):
            return
        mention_str = " ".join(self._remote_handle(m) for m in (mentions or []))
        text = body if isinstance(body, str) else json.dumps(body, default=str, ensure_ascii=False)
        content = (mention_str + ("\n" if mention_str else "") + text).strip()
        url = self.rest_url + self.message_path.format(chat_id=room_id)
        r = self._requests.post(
            url,
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            json={"content": content},
            timeout=10,
        )
        if r.status_code == 404:
            self._mirror_on = False  # wrong endpoint for this tenant — stop retrying, stay functional
            print(f"[Band live] room mirror disabled — POST {self.message_path} returned 404. "
                  f"Set BAND_MESSAGE_PATH to your tenant's send endpoint (see registration.md).")
        elif r.status_code >= 400:
            print(f"[Band live] room mirror POST {r.status_code} for {sender} (continuing in-process).")


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


# Internal contract handles (must match the agent modules + registration.md) -> env prefix.
_ROLES = (
    ("@tali-intake", "BAND_INTAKE"),
    ("@tali-ledger", "BAND_LEDGER"),
    ("@tali-cfo", "BAND_CFO"),
    ("@tali-compliance", "BAND_COMPLIANCE"),
)


def _live_config_from_app():
    """Assemble the live backend config (handle→creds + room + path) from app config,
    falling back to environment variables outside an app context."""
    try:
        from flask import current_app
        get = current_app.config.get
    except Exception:
        import os
        get = lambda k, d=None: os.getenv(k, d)
    agents = {}
    for internal, prefix in _ROLES:
        agent_id = get(f"{prefix}_AGENT_ID", "") or ""
        api_key = get(f"{prefix}_API_KEY", "") or ""
        if agent_id or api_key:
            agents[internal] = {
                "agent_id": agent_id,
                "api_key": api_key,
                "remote_handle": get(f"{prefix}_HANDLE", internal) or internal,
            }
    return {
        "rest_url": get("BAND_REST_URL", None) or get("THENVOI_REST_URL", None),
        "room_id": get("BAND_ROOM_ID", "") or "",
        "message_path": get("BAND_MESSAGE_PATH", None),
        "agents": agents,
    }


def get_band_client(backend=None, config=None):
    """Build a BandClient for the configured backend (``stub`` default, or ``live``).

    In ``live`` mode the handle→credentials config is assembled from app config when not
    supplied, so every call site gets the live mirror without threading config through.
    """
    if backend is None:
        try:
            from flask import current_app
            backend = current_app.config.get("BAND_BACKEND", "stub") if current_app else "stub"
        except Exception:
            import os
            backend = os.getenv("BAND_BACKEND", "stub")
    backend = (backend or "stub").lower()
    if backend == "live":
        if config is None:
            config = _live_config_from_app()
        return BandClient(_LiveBackend(config=config))
    return BandClient(_StubBackend())
