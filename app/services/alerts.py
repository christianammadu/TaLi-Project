"""Observability and alerting service.
Logs warnings and alerts for latency spikes, DB saturation, and delivery errors.
"""

import logging

logger = logging.getLogger("tali.alerts")

def alert_slow_request(operation_name, duration_ms):
    """Trigger alert when request/operation exceeds threshold."""
    if duration_ms > 5000:
        print(f"[ALERT] [CRITICAL_LATENCY] {operation_name} took {duration_ms}ms (exceeded 5s threshold)")
        logger.error(f"CRITICAL_LATENCY: {operation_name} took {duration_ms}ms")
    elif duration_ms > 3000:
        print(f"[ALERT] [WARNING_LATENCY] {operation_name} took {duration_ms}ms (exceeded 3s threshold)")
        logger.warning(f"WARNING_LATENCY: {operation_name} took {duration_ms}ms")

def alert_db_pool_saturation():
    """Trigger alert when MySQL connection pool saturation is detected."""
    print("[ALERT] [CRITICAL_DB] Database Connection Pool Saturation Alert! Direct connection fallback triggered.")
    logger.critical("DB_POOL_SATURATION: Connection pool exhausted")

def alert_failed_confirmation_delivery(sender_id, text, error_reason):
    """Trigger alert when a critical message cannot be delivered to a channel."""
    print(f"[ALERT] [CRITICAL_DELIVERY] Message delivery to {sender_id} failed: '{text[:50]}...'. Error: {error_reason}")
    logger.critical(f"DELIVERY_FAILED: to={sender_id} error={error_reason}")

def alert_job_failed(job_id, error_reason):
    """Trigger alert when a background queued job fails."""
    print(f"[ALERT] [CRITICAL_JOB] Background job {job_id} failed: {error_reason}")
    logger.error(f"JOB_FAILED: job_id={job_id} error={error_reason}")
