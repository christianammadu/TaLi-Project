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
  * ``"live"`` — the real band.ai platform through ``band-sdk``'s generated REST client.
    Gated behind credentials; the synchronous Flask webhook still owns the local agent
    execution, while Band owns the room, participants, messages, and audit trail.
"""

import json
import threading
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
            # A terminal reply is a point-to-point answer for collect_reply — the END of a
            # chain, NOT a new inbound event. Capture it and STOP: it must not also be
            # dispatched to @mentioned handlers. Re-dispatching re-enters a handler with
            # reply data (e.g. the Compliance verdict reaching the Ledger), which corrupts
            # that handler's per-message state (the Ledger's _user_cid → wrong reply key →
            # "Transaction failed") and trips schema validation on the reply body.
            self._replies[correlation_id] = body
            return msg["id"]
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
        if correlation_id in self._replies:
            return self._replies.pop(correlation_id)
        return None


# --- Live backend: in-process orchestration + a real Band-room mirror ---
#
# The agents are LOCAL (the Ledger writes our MySQL), so Band is the coordination/
# audit surface, not an autonomous runtime — band-sdk's persistent-WebSocket runtime
# needs a long-running process the sync Flask webhook doesn't have (registration.md).
# So _LiveBackend keeps the stub's reliable synchronous in-process @mention dispatch +
# reply collection, and MIRRORS each handoff into the real Band room through
# ``band.client.rest.RestClient`` from band-sdk:
#   create room  agent_api_chats.create_agent_chat(ChatRoomRequest())
#   add member   agent_api_participants.add_agent_chat_participant(ParticipantRequest(...))
#   message      agent_api_messages.create_agent_chat_message(ChatMessageRequest(...))
#   event        agent_api_events.create_agent_chat_event(ChatEventRequest(...))
# A message may only @mention agents already in the room, so the gateway uses the
# configured room when its agents are members, else AUTO-PROVISIONS an agent-owned room
# and adds the peers. The resolved room is cached per-process (get_band_client is called
# per request — without the cache we'd create a room per message). Best-effort: a room
# failure only logs; bookkeeping always proceeds in-process.

# process-wide cache of the resolved room id (keyed by tenant + configured room + agents)
_LIVE_ROOM_CACHE = {}
_LIVE_LOCK = threading.Lock()


class _LiveBackend(_StubBackend):
    REST_DEFAULT = "https://app.band.ai"
    MESSAGES_DEFAULT = "/api/v1/agent/chats/{chat_id}/messages"

    def __init__(self, config=None):
        super().__init__()
        cfg = config or {}
        self.rest_url = (cfg.get("rest_url") or self.REST_DEFAULT).rstrip("/")
        self.configured_room = cfg.get("room_id") or ""
        self.messages_path = cfg.get("message_path") or self.MESSAGES_DEFAULT
        self.shared_api_key = cfg.get("api_key") or ""
        # internal handle -> {"agent_id", "api_key", "remote_handle"}
        self.agents = cfg.get("agents", {})
        if not self.agents:
            raise RuntimeError(
                "BAND_BACKEND=live but no agent credentials configured — set "
                "BAND_*_AGENT_ID / BAND_*_API_KEY (see app/agents/band/registration.md)."
            )
        injected_sdk = cfg.get("sdk")
        if injected_sdk is not None:
            self._sdk = injected_sdk
        else:
            try:
                from band.client.rest import (  # local import; only live mode needs band-sdk
                    DEFAULT_REQUEST_OPTIONS,
                    ChatEventRequest,
                    ChatMessageRequest,
                    ChatMessageRequestMentionsItem,
                    ChatRoomRequest,
                    ParticipantRequest,
                    RestClient,
                )
                self._sdk = {
                    "RestClient": RestClient,
                    "ChatEventRequest": ChatEventRequest,
                    "ChatMessageRequest": ChatMessageRequest,
                    "ChatMessageRequestMentionsItem": ChatMessageRequestMentionsItem,
                    "ChatRoomRequest": ChatRoomRequest,
                    "ParticipantRequest": ParticipantRequest,
                    "request_options": DEFAULT_REQUEST_OPTIONS,
                }
            except Exception as e:  # pragma: no cover
                raise RuntimeError(
                    "BAND_BACKEND=live requires band-sdk and its dependencies. "
                    "Install requirements.txt before starting live Band orchestration."
                ) from e
        self._clients = {}
        self._mirror_on = self._sdk is not None

    # --- small SDK helpers (X-API-Key auth handled by RestClient) ---
    def _client(self, api_key):
        if api_key not in self._clients:
            self._clients[api_key] = self._sdk["RestClient"](
                api_key=api_key,
                base_url=self.rest_url,
                timeout=12,
            )
        return self._clients[api_key]

    def _request_options(self):
        return self._sdk["request_options"]

    def _owner(self):
        """The provisioning/owner agent — prefer Intake, else any configured agent."""
        return self.agents.get("@tali-intake") or next(iter(self.agents.values()))

    def _api_key_for(self, internal=None):
        """Return an agent-auth key for Band's ``agent_api_*`` endpoints.

        Tenant REST keys can exist in the Band UI, but these generated SDK calls reject
        them with "This endpoint requires agent authentication". Prefer the sender or
        owner agent key; keep the shared key only as a last-resort fallback.
        """
        if internal:
            key = (self.agents.get(internal) or {}).get("api_key")
            if key:
                return key
        return self._owner().get("api_key") or self.shared_api_key

    def _agent_id(self, internal):
        return (self.agents.get(internal) or {}).get("agent_id")

    def _handle(self, internal):
        """Remote handle without the leading '@' (the mentions API stores owner/slug)."""
        return ((self.agents.get(internal) or {}).get("remote_handle") or internal).lstrip("@")

    def _cache_key(self):
        ids = tuple(sorted((c.get("agent_id") or "") for c in self.agents.values()))
        auth = "shared" if self.shared_api_key else "per-agent"
        return (self.rest_url, self.configured_room, ids, auth)

    def _resolve_room(self):
        """Return a real room the agents can post to (cached per process). Prefer the
        configured room if the owner agent is a member; otherwise provision one + add peers."""
        key = self._cache_key()
        with _LIVE_LOCK:
            if key in _LIVE_ROOM_CACHE:
                return _LIVE_ROOM_CACHE[key]
            room = self._provision_locked()
            _LIVE_ROOM_CACHE[key] = room   # cache even None so we don't retry every message
            return room

    def _provision_locked(self):
        owner = self._owner()
        okey = self._api_key_for()
        if not okey:
            return None
        # 1) Use the configured room if the owner agent is already a participant of it.
        if self.configured_room:
            try:
                self._client(okey).agent_api_chats.get_agent_chat(
                    self.configured_room,
                    request_options=self._request_options(),
                )
                print(f"[Band live] using configured room {self.configured_room}")
                return self.configured_room
            except Exception as e:
                print(f"[Band live] configured room {self.configured_room} not joinable by the "
                      f"agents ({e}); provisioning an agent-owned room instead. "
                      f"(Add the 4 agents to that room in the Band UI to use it directly.)")
        # 2) Provision an agent-owned coordination room and add the other agents.
        try:
            client = self._client(okey)
            response = client.agent_api_chats.create_agent_chat(
                chat=self._sdk["ChatRoomRequest"](),
                request_options=self._request_options(),
            )
            room = response.data.id
            for internal, creds in self.agents.items():
                if creds is owner or not creds.get("agent_id"):
                    continue
                try:
                    client.agent_api_participants.add_agent_chat_participant(
                        room,
                        participant=self._sdk["ParticipantRequest"](
                            participant_id=creds["agent_id"],
                            role="member",
                        ),
                        request_options=self._request_options(),
                    )
                except Exception as e:
                    print(f"[Band live] add participant {internal} failed: {e}")
            print(f"[Band live] provisioned coordination room — watch it at {self.rest_url}/chat/{room}")
            return room
        except Exception as e:
            print(f"[Band live] provisioning error ({e}); mirror off.")
            return None

    def send(self, room_id, mentions, body, correlation_id=None, sender=None, terminal=False):
        # 1) Authoritative: synchronous in-process dispatch + reply capture (inherited).
        mid = super().send(room_id, mentions, body, correlation_id=correlation_id,
                           sender=sender, terminal=terminal)
        # 2) Best-effort: mirror the handoff into the real Band room asynchronously.
        if self._mirror_on:
            try:
                t = threading.Thread(
                    target=self._mirror_safe,
                    args=(mentions, body, sender),
                    name=f"band-mirror-{mid[:8]}"
                )
                t.daemon = True
                t.start()
            except Exception as e:
                print(f"[Band live] failed to start mirror thread: {e}")
        return mid

    def _mirror_safe(self, mentions, body, sender):
        try:
            self._mirror(mentions, body, sender)
        except Exception as e:
            print(f"[Band live] room mirror error (continuing in-process): {e}")

    def _mirror(self, mentions, body, sender):
        room = self._resolve_room()
        if not room:
            return
        api_key = self._api_key_for(sender)
        if not api_key:
            return
        text = body if isinstance(body, str) else json.dumps(body, default=str, ensure_ascii=False)
        # only @mention targets that are participant agents (you can't mention non-members)
        targets = [(self._agent_id(m), self._handle(m)) for m in (mentions or []) if self._agent_id(m)]
        
        client = self._client(api_key)
        if targets:
            content = " ".join(f"@{h}" for _, h in targets) + "\n" + text
            mention_items = [
                self._sdk["ChatMessageRequestMentionsItem"](id=aid, handle=h)
                for aid, h in targets
            ]
            client.agent_api_messages.create_agent_chat_message(
                room,
                message=self._sdk["ChatMessageRequest"](
                    content=content,
                    mentions=mention_items,
                ),
                request_options=self._request_options(),
            )
        else:
            # no participant target (e.g. -> gateway/human terminal reply): record as an event.
            content = ""
            if mentions:
                content += " ".join(f"@{m.lstrip('@')}" for m in mentions) + "\n"
            content += text
            client.agent_api_events.create_agent_chat_event(
                room,
                event=self._sdk["ChatEventRequest"](
                    content=content[:6000],
                    message_type="task",
                ),
                request_options=self._request_options(),
            )



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
        "api_key": get("BAND_API_KEY", "") or "",
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
