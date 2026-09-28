"""Native Multi-Agent Orchestration Engine.

Replaces the external Band.ai / band-sdk dependency with an in-house, zero-dependency,
thread-safe collaborative agent orchestration system.

Features:
  1. Room Isolation: Each merchant session/sender operates in an isolated AgentRoom.
  2. Targeted @Mention Routing: Delivers structured messages to specific registered agent handles
     (@tali-intake, @tali-ledger, @tali-compliance, @tali-human, @tali-cfo, @tali-gateway).
  3. Fire-and-Forget Dispatch: Senders deliver envelopes asynchronously without blocking on handler return values.
  4. Event-Driven Reply Collection: Uses threading.Event for instantaneous, non-polling reply collection
     by correlation_id, bridging synchronous webhooks with asynchronous agent handoffs.
  5. Terminal Message Semantics: Terminal replies conclude the chain and fulfill collect_reply without
     re-entering handlers.
  6. Shared Room Blackboard: read_context provides an immutable chronological audit trail of handoffs.
"""

import json
import logging
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentRoom:
    """Thread-safe blackboard and message log for a collaborative room."""

    def __init__(self, room_id: str):
        self.room_id = room_id
        self._lock = threading.RLock()
        self._log: List[Dict[str, Any]] = []

    def append(self, message: Dict[str, Any]) -> None:
        with self._lock:
            self._log.append(message)

    def read_context(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._log[-limit:])

    def clear(self) -> None:
        with self._lock:
            self._log.clear()


class OrchestrationEngine:
    """Core native orchestration broker.

    Manages agent handle registrations, message dispatching, room contexts,
    and event-driven reply collection.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._rooms: Dict[str, AgentRoom] = {}
        self._replies: Dict[str, Any] = {}
        self._reply_events: Dict[str, threading.Event] = {}

    def _get_room(self, room_id: str) -> AgentRoom:
        with self._lock:
            if room_id not in self._rooms:
                self._rooms[room_id] = AgentRoom(room_id)
            return self._rooms[room_id]

    def _get_event(self, correlation_id: str) -> threading.Event:
        with self._lock:
            if correlation_id not in self._reply_events:
                self._reply_events[correlation_id] = threading.Event()
            return self._reply_events[correlation_id]

    def on_message(self, handle: str, callback: Callable[[Dict[str, Any]], Any]) -> None:
        """Register an inbound message handler callback for an agent handle."""
        with self._lock:
            self._handlers[handle] = callback

    def send(
        self,
        room_id: str,
        mentions: Optional[List[str]],
        body: Any,
        correlation_id: Optional[str] = None,
        sender: Optional[str] = None,
        terminal: bool = False,
    ) -> str:
        """Deliver a message to @mentioned agents in a room.

        Fire-and-forget: returns the unique message id immediately.
        If terminal=True and correlation_id is present, signals any waiting collect_reply.
        """
        msg_id = uuid.uuid4().hex
        msg: Dict[str, Any] = {
            "id": msg_id,
            "room_id": room_id,
            "sender": sender,
            "mentions": list(mentions or []),
            "body": body,
            "correlation_id": correlation_id,
            "terminal": terminal,
            "timestamp": time.time(),
        }

        # 1. Record message in room blackboard
        room = self._get_room(room_id)
        room.append(msg)

        # 2. Terminal reply completion: capture reply and wake up waiting collector immediately
        if terminal and correlation_id is not None:
            with self._lock:
                self._replies[correlation_id] = body
                if correlation_id in self._reply_events:
                    self._reply_events[correlation_id].set()
            return msg_id

        # 3. Fire-and-forget dispatch to @mentioned agent handlers
        for handle in msg["mentions"]:
            cb = None
            with self._lock:
                cb = self._handlers.get(handle)
            if cb is not None:
                try:
                    cb(dict(msg))
                except Exception as e:
                    logger.warning("[Orchestrator] Handler %r raised an exception: %s", handle, e)

        return msg_id

    def read_context(self, room_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the shared chronological room message log."""
        return self._get_room(room_id).read_context(limit=limit)

    def collect_reply(
        self,
        correlation_id: str,
        timeout: float = 10.0,
        poll: float = 0.05,
    ) -> Optional[Any]:
        """Wait for the terminal reply for a correlation id.

        Uses threading.Event for instantaneous wakeup when the terminal reply arrives,
        avoiding sleep polling loops.
        """
        event = self._get_event(correlation_id)

        # Check if reply already arrived
        with self._lock:
            if correlation_id in self._replies:
                val = self._replies.pop(correlation_id)
                self._reply_events.pop(correlation_id, None)
                return val

        # Wait on event until timeout
        signaled = event.wait(timeout=timeout)

        with self._lock:
            self._reply_events.pop(correlation_id, None)
            if correlation_id in self._replies:
                return self._replies.pop(correlation_id)

        return None


# Global process-wide orchestrator instance
_GLOBAL_ENGINE = OrchestrationEngine()


class OrchestratorClient:
    """Client facade for interacting with the native orchestration engine."""

    def __init__(self, engine: Optional[OrchestrationEngine] = None):
        self._backend = engine if engine is not None else OrchestrationEngine()
        self._engine = self._backend

    def on_message(self, handle: str, callback: Callable[[Dict[str, Any]], Any]) -> None:
        self._engine.on_message(handle, callback)

    def send(
        self,
        room_id: str,
        mentions: Optional[List[str]],
        body: Any,
        correlation_id: Optional[str] = None,
        sender: Optional[str] = None,
        terminal: bool = False,
    ) -> str:
        return self._engine.send(
            room_id,
            mentions,
            body,
            correlation_id=correlation_id,
            sender=sender,
            terminal=terminal,
        )

    def read_context(self, room_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return self._engine.read_context(room_id, limit=limit)

    def collect_reply(self, correlation_id: str, timeout: float = 10.0) -> Optional[Any]:
        return self._engine.collect_reply(correlation_id, timeout=timeout)


def get_orchestrator(backend: Optional[Any] = None, config: Optional[Dict[str, Any]] = None) -> OrchestratorClient:
    """Return an OrchestratorClient connected to a native engine backend."""
    if isinstance(backend, OrchestrationEngine):
        return OrchestratorClient(backend)
    return OrchestratorClient(OrchestrationEngine())


# Backward-compatible aliases for existing agent code
BandClient = OrchestratorClient
get_band_client = get_orchestrator


def post_human_decision(
    room_id: str,
    review_id: str,
    decision: str,
    reason: Optional[str] = None,
    orchestrator: Optional[OrchestratorClient] = None,
) -> str:
    """Post human-in-the-loop compliance decision into the agent room.

    Surfaces human decisions (@tali-human) to resume pending transactions or
    formalize audit vetoes across @tali-ledger and @tali-cfo.
    """
    client = orchestrator or get_orchestrator(_GLOBAL_ENGINE)
    payload = {
        "type": "human_decision",
        "review_id": review_id,
        "decision": decision,
        "reason": reason,
        "timestamp": time.time(),
    }
    return client.send(
        room_id=room_id,
        mentions=["@tali-ledger", "@tali-cfo"],
        body=payload,
        sender="@tali-human",
        correlation_id=review_id,
        terminal=False,
    )

