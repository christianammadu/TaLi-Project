"""Band gateway (WP-06) — the webhook→room entry point.

Replaces the retired in-memory ``BandSDK`` broker. Creates ONE shared Band connector,
wires the agents into the room as ``@mention`` handlers, then drives an inbound WhatsApp
message through Intake. Intake → Ledger → (Compliance review) → CFO coordinate in the
room; CFO posts the terminal reply, which bubbles back as Intake's collected reply.

Keeps the ``AgentRouter`` name + ``route(text, message_id)`` signature so
``app/web/routes.py`` is unchanged.
"""

import json
from mysql.connector import Error
from app.agents.band import get_band_client
from app.agents.agent_1_intake import IntakeAgent, LEDGER_HANDLE, CFO_HANDLE
from app.agents.agent_2_ledger import LedgerAgent
from app.agents.agent_3_cfo import CFOAgent
from app.auth import get_active_session, get_user_by_sender, get_user_by_phone
from app.data.database import get_db_connection


class AgentRouter:
    """Webhook→Band-room gateway. One shared connector; agents wired as room handlers.

    The Compliance agent (WP-07) is wired in separately so its absence degrades to the
    Ledger's default-allow review path rather than breaking the gateway.
    """

    def __init__(self, user_id, sender_id):
        self.user_id = user_id
        self.sender_id = sender_id
        # ONE connector shared by every agent so in-process @mention routing reaches them.
        self.band = get_band_client()
        self.intake = IntakeAgent(user_id, sender_id, band=self.band)
        self.ledger = LedgerAgent(user_id, sender_id, band=self.band)
        self.cfo = CFOAgent(user_id, sender_id, band=self.band)
        # Wire the room: each agent handles messages that @mention its handle.
        self.band.on_message(LEDGER_HANDLE, self.ledger.on_room_message)
        self.band.on_message(CFO_HANDLE, self.cfo.on_room_message)
        self._wire_optional_agents()

    def _wire_optional_agents(self):
        """Register the Compliance reviewer if present (WP-07). Kept optional so WP-06
        stands alone: with no reviewer, the Ledger's _review_gate default-allows."""
        try:
            from app.agents.compliance_agent import ComplianceAgent, COMPLIANCE_HANDLE
        except Exception:
            return
        self.compliance = ComplianceAgent(self.user_id, self.sender_id, band=self.band)
        self.band.on_message(COMPLIANCE_HANDLE, self.compliance.on_room_message)

    def route(self, text, message_id=None):
        """Authenticate, dedupe the webhook event, run Intake (which drives the room),
        and return the collected reply. Same contract as the pre-Band router."""
        # 1. Verify active session at the gateway entry point.
        session = get_active_session(self.sender_id)
        if not session:
            user = get_user_by_sender(self.sender_id) or get_user_by_phone(self.sender_id)
            if user:
                return "🔒 Your session's timed out. Type *login* to pick up where you left off."
            return ("👋 Hi, I'm TaLi — your pocket bookkeeper.\n\n"
                    "You're not set up yet. Type *register* to get your sign-up link.")

        # 2. Webhook deduplication + processing-state check (atomic transition).
        if message_id:
            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    "UPDATE webhook_events SET status = 'processing', processed_at = NULL "
                    "WHERE whatsapp_message_id = %s AND status IN ('received', 'failed')",
                    (message_id,)
                )
                conn.commit()
                if cursor.rowcount == 0:
                    cursor.execute(
                        "SELECT status FROM webhook_events WHERE whatsapp_message_id = %s LIMIT 1",
                        (message_id,)
                    )
                    row = cursor.fetchone()
                    if row:
                        return "__DUPLICATE_DROP__"
                    payload_json = json.dumps({"text": text})
                    try:
                        cursor.execute(
                            "INSERT INTO webhook_events (whatsapp_message_id, sender_id, payload, status) "
                            "VALUES (%s, %s, %s, 'processing')",
                            (message_id, self.sender_id, payload_json)
                        )
                        conn.commit()
                    except Error:
                        return "__DUPLICATE_DROP__"
            except Error as e:
                print(f"[AgentRouter Deduplication Error] {e}")
            finally:
                if 'conn' in locals() and conn.is_connected():
                    cursor.close()
                    conn.close()

        # 3. Drive the flow through Intake (which sends into the room + collects the reply).
        try:
            response = self.intake.process(text)
            if message_id:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE webhook_events SET status = 'processed', processed_at = CURRENT_TIMESTAMP "
                        "WHERE whatsapp_message_id = %s",
                        (message_id,)
                    )
                    conn.commit()
                except Error as e:
                    print(f"[AgentRouter Update Status Error] {e}")
                finally:
                    if 'conn' in locals() and conn.is_connected():
                        cursor.close()
                        conn.close()
            return response
        except Exception as err:
            if message_id:
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE webhook_events SET status = 'failed', processed_at = CURRENT_TIMESTAMP "
                        "WHERE whatsapp_message_id = %s",
                        (message_id,)
                    )
                    conn.commit()
                except Error as e:
                    print(f"[AgentRouter Failure Update Error] {e}")
                finally:
                    if 'conn' in locals() and conn.is_connected():
                        cursor.close()
                        conn.close()
            raise err
