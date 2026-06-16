"""Band gateway (WP-06) — the webhook→room entry point.

Replaces the retired in-memory ``BandSDK`` broker. Creates ONE shared Band connector,
wires the agents into the room as ``@mention`` handlers, then drives an inbound WhatsApp
message through Intake. Intake → Ledger → (Compliance review) → CFO coordinate in the
room; CFO posts the terminal reply, which bubbles back as Intake's collected reply.

Keeps the ``AgentRouter`` name + ``route(text, message_id)`` signature so
``app/web/routes.py`` is unchanged.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from mysql.connector import Error
from app.agents.band import get_band_client
from app.agents.agent_1_intake import IntakeAgent, LEDGER_HANDLE, CFO_HANDLE
from app.agents.agent_2_ledger import LedgerAgent
from app.agents.agent_3_cfo import CFOAgent
from app.auth import get_active_session, get_user_by_sender, get_user_by_phone
from app.data.database import get_db_connection

# ThreadPoolExecutor for backpressure control and thread worker reuse (max 10 concurrent tasks)
_EXECUTOR = ThreadPoolExecutor(max_workers=10)


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

    def route(self, text, message_id=None, sync=False):
        """Authenticate, dedupe the webhook event, run Intake (which drives the room),
        and return the collected reply. Same contract as the pre-Band router.
        """
        import hashlib
        import time
        import uuid
        from app.services.uuid_utils import uuid_to_bin
        from app.services.constants import RESPONSE_TOO_MANY_REQUESTS, RESPONSE_TIMEOUT, RESPONSE_FAILED

        # 1. Verify active session at the gateway entry point.
        session = get_active_session(self.sender_id)
        if not session:
            user = get_user_by_sender(self.sender_id) or get_user_by_phone(self.sender_id)
            if user:
                return "🔒 Your session's timed out. Type *login* to pick up where you left off."
            return ("👋 Hi, I'm TaLi — your pocket bookkeeper.\n\n"
                    "You're not set up yet. Type *register* to get your sign-up link.")

        # 1b. Enforce Request-Level Idempotency Key System
        # Hashing window: 1-minute bucket to prevent YES spam / duplicate webhook repeats
        time_bucket = int(time.time()) // 60
        raw_key = f"{self.user_id}:{message_id or ''}:{time_bucket}"
        idempotency_key = hashlib.sha256(raw_key.encode()).hexdigest()

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO processed_requests (idempotency_key) VALUES (%s)",
                (idempotency_key,)
            )
            conn.commit()
        except Error:
            # Idempotency key already exists. Skip execution entirely.
            if 'conn' in locals() and conn.is_connected():
                conn.rollback()
            print(f"[AgentRouter] Duplicate request drop: key={idempotency_key}")
            return "__DUPLICATE_DROP__"
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

        user_id_bin = uuid_to_bin(self.user_id)

        # 1c. Load Safety & Backpressure Control (Cap active jobs per user at 3)
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM background_jobs WHERE user_id = %s AND status IN ('pending', 'processing')",
                (user_id_bin,)
            )
            active_jobs = cursor.fetchone()[0]
            if active_jobs >= 3:
                print(f"[AgentRouter Backpressure] Throttling user {self.user_id}: {active_jobs} active requests.")
                return RESPONSE_TOO_MANY_REQUESTS
        except Error as e:
            print(f"[AgentRouter Throttling Check Error] {e}")
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

        # 2. Webhook deduplication + processing-state check (atomic transition).
        if message_id:
            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                # Claim the event atomically: a brand-new ('received'/'failed') row, OR a
                # STALE 'processing' row whose previous attempt crashed before reaching
                # processed/failed. Without the stale clause such an event would be dropped
                # as a duplicate forever. stale_secs is a config int (>> sync processing time),
                # embedded directly (sanitised via int(), injection-safe).
                stale_secs = int(os.getenv("WEBHOOK_PROCESSING_STALE_SECONDS", "120"))
                cursor.execute(
                    "UPDATE webhook_events SET status = 'processing', processed_at = NULL "
                    "WHERE whatsapp_message_id = %s AND ("
                    "status IN ('received', 'failed') "
                    f"OR (status = 'processing' AND created_at < (NOW() - INTERVAL {stale_secs} SECOND)))",
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

        # 2b. Durable SQL Job queue insertion
        job_id = uuid.uuid4().hex
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO background_jobs (id, user_id, sender_id, text, message_id, status) "
                "VALUES (%s, %s, %s, %s, %s, 'pending')",
                (job_id, user_id_bin, self.sender_id, text, message_id)
            )
            conn.commit()
        except Error as e:
            print(f"[AgentRouter Queue Error] Failed to write job to DB: {e}")
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

        # Check Flask app context and testing flag to determine synchronous execution
        sync_execution = False
        try:
            from flask import current_app
            if current_app:
                if current_app.config.get('TESTING', False) or current_app.testing:
                    sync_execution = True
            else:
                sync_execution = True
        except RuntimeError:
            sync_execution = True

        if sync or sync_execution:
            # 3. Drive the flow through Intake synchronously
            try:
                # Update job status
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE background_jobs SET status = 'processing' WHERE id = %s", (job_id,))
                    conn.commit()
                except Error:
                    pass
                finally:
                    if 'conn' in locals() and conn.is_connected():
                        cursor.close()
                        conn.close()

                response = self.intake.process(text)

                # Update job status
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE background_jobs SET status = 'completed' WHERE id = %s", (job_id,))
                    conn.commit()
                except Error:
                    pass
                finally:
                    if 'conn' in locals() and conn.is_connected():
                        cursor.close()
                        conn.close()

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
                # Update job status to failed
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE background_jobs SET status = 'failed' WHERE id = %s", (job_id,))
                    conn.commit()
                except Error:
                    pass
                finally:
                    if 'conn' in locals() and conn.is_connected():
                        cursor.close()
                        conn.close()

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
        else:
            # 3. Drive the flow through Intake asynchronously in the background thread pool
            from flask import current_app
            app = current_app._get_current_object()

            def async_worker(app_obj, text_val, msg_id, job_key):
                with app_obj.app_context():
                    import concurrent.futures
                    from app.services.alerts import alert_slow_request, alert_job_failed

                    # Update job status
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE background_jobs SET status = 'processing' WHERE id = %s", (job_key,))
                        conn.commit()
                    except Error as e:
                        print(f"Error marking job processing: {e}")
                    finally:
                        if 'conn' in locals() and conn.is_connected():
                            cursor.close()
                            conn.close()

                    # Enforce system-wide timeout wrapper (8-10 seconds limit). The nested
                    # worker thread does NOT inherit this thread's Flask app context (it is
                    # thread-local), so intake.process() must re-push it — otherwise its first
                    # current_app use (DB config, Band backend, session lookup) raises "Working
                    # outside of application context", the [Pipeline Failure] seen in prod.
                    response = None

                    def _process_with_context():
                        with app_obj.app_context():
                            return self.intake.process(text_val)

                    try:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as local_executor:
                            future = local_executor.submit(_process_with_context)
                            response = future.result(timeout=8.0)
                    except concurrent.futures.TimeoutError:
                        print(f"[AgentRouter] Pipeline Timeout: Job {job_key} exceeded MAX_REQUEST_LIFETIME (8.0s)")
                        alert_slow_request(f"job_{job_key}", 8000)
                        response = RESPONSE_TIMEOUT
                    except Exception as exc:
                        print(f"[AgentRouter] Pipeline Failure: Job {job_key} crashed: {exc}")
                        alert_job_failed(job_key, str(exc))
                        response = RESPONSE_FAILED

                    try:
                        if response:
                            from app.channels.registry import send_text
                            send_text(self.sender_id, response)
                        
                        status = 'completed' if response != RESPONSE_FAILED and response != RESPONSE_TIMEOUT else 'failed'
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE background_jobs SET status = %s WHERE id = %s", (status, job_key))
                        conn.commit()

                        if msg_id:
                            status_val = 'processed' if status == 'completed' else 'failed'
                            cursor.execute(
                                "UPDATE webhook_events SET status = %s, processed_at = CURRENT_TIMESTAMP "
                                "WHERE whatsapp_message_id = %s",
                                (status_val, msg_id)
                            )
                            conn.commit()
                    except Exception as post_err:
                        print(f"Error executing final status updates for job {job_key}: {post_err}")
                    finally:
                        if 'conn' in locals() and conn.is_connected():
                            cursor.close()
                            conn.close()

            _EXECUTOR.submit(async_worker, app, text, message_id, job_id)
            return "__ASYNC_STARTED__"
