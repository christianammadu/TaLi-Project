"""Agent Router — the central traffic controller for the financial intelligence system.

Registers Band SDK subscriptions and passes execution flow through the Intake, Ledger,
and CFO agents.
"""

import json
from mysql.connector import Error
from app.agents.band_sdk import BandSDK
from app.agents.agent_1_intake import IntakeAgent
from app.agents.agent_2_ledger import LedgerAgent
from app.agents.agent_3_cfo import CFOAgent
from app.auth import get_active_session
from app.data.database import get_db_connection


class AgentRouter:
    """Core intelligence router that configures Band SDK links and dispatches incoming messages."""

    def __init__(self, user_id, sender_id):
        self.user_id = user_id
        self.sender_id = sender_id

    def route(self, text, message_id=None):
        """Builds Agent 1, Agent 2, and Agent 3 connections via Band SDK, and starts the processing loop.

        Args:
            text: str, the raw message from WhatsApp.
            message_id: str, unique WhatsApp message ID for idempotency protection.

        Returns:
            str: Response string from the CFO Agent.
        """
        # 1. Verify active session at the router entry point
        session = get_active_session(self.sender_id)
        if not session:
            from app.auth import get_user_by_sender, get_user_by_phone
            user = get_user_by_sender(self.sender_id) or get_user_by_phone(self.sender_id)
            if user:
                return "🔒 Session expired or not found. Type *login* to authenticate."
            else:
                return ("👋 *Welcome to TaLi!*\n\n"
                        "Your number isn't registered yet. Type *register* to get your sign-up link.")

        # Clean active channels to prevent multiple calls
        BandSDK.clear_subscriptions()

        # 2. Instantiate the three definitive agents
        intake = IntakeAgent(self.user_id, self.sender_id)
        ledger = LedgerAgent(self.user_id, self.sender_id)
        cfo = CFOAgent(self.user_id, self.sender_id)

        # 3. Configure pub-sub bindings via Band SDK channels
        BandSDK.subscribe("intake_to_ledger", ledger.handle_intake_payload)
        BandSDK.subscribe("ledger_updates", cfo.handle_ledger_update)
        BandSDK.subscribe("cfo_escalation", cfo.handle_escalation)
        BandSDK.subscribe("ledger_errors", cfo.handle_ledger_error)

        # 4. Webhook Deduplication and Processing State check
        if message_id:
            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                # Attempt atomic transition from received/failed to processing
                cursor.execute(
                    "UPDATE webhook_events SET status = 'processing', processed_at = NULL "
                    "WHERE whatsapp_message_id = %s AND status IN ('received', 'failed')",
                    (message_id,)
                )
                conn.commit()
                
                if cursor.rowcount == 0:
                    # Either it is already processing/processed, OR it doesn't exist yet (fallback).
                    cursor.execute(
                        "SELECT status FROM webhook_events WHERE whatsapp_message_id = %s LIMIT 1",
                        (message_id,)
                    )
                    row = cursor.fetchone()
                    if row:
                        # It exists and is already processing or processed
                        return "__DUPLICATE_DROP__"
                    else:
                        # Fallback if no pre-registered event exists: insert under 'processing' state.
                        payload_json = json.dumps({"text": text})
                        try:
                            cursor.execute(
                                "INSERT INTO webhook_events (whatsapp_message_id, sender_id, payload, status) "
                                "VALUES (%s, %s, %s, 'processing')",
                                (message_id, self.sender_id, payload_json)
                            )
                            conn.commit()
                        except Error:
                            # Drop if there was a parallel insert race
                            return "__DUPLICATE_DROP__"
            except Error as e:
                print(f"[AgentRouter Deduplication Error] {e}")
            finally:
                if 'conn' in locals() and conn.is_connected():
                    cursor.close()
                    conn.close()

        # 5. Execute processing loop via Agent 1
        try:
            response = intake.process(text)
            if response == {"status": "error_handled_via_pubsub"}:
                response = "__ERROR_HANDLED_SAGA__"

            # Mark as successfully processed
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
            # Mark processing as failed on exception
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
