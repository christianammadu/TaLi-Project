"""Centralized user-facing UX response copy constants.
"""

RESPONSE_PROCESSING = "⏳ Processing..."
RESPONSE_CANCELLED = "❌ Cancelled — nothing was recorded. Send it again to retry."
RESPONSE_TIMEOUT = "⚠️ Connection timed out while recording. Your transaction was not saved. Please try again."
RESPONSE_FAILED = "❌ Ledger processing failed."
RESPONSE_PENDING = "Do you want to record this? Please reply YES or NO."
RESPONSE_TOO_MANY_REQUESTS = "⚠️ Too many requests. Please wait for your previous transactions to finish."
RESPONSE_INVALID_FORMAT = (
    "Which format would you like?\n\n"
    "1️⃣ Chat summary\n2️⃣ PDF document\n3️⃣ Excel spreadsheet\n\n"
    "Reply *1*, *2* or *3*."
)
RESPONSE_STATEMENT_CANCELLED = "❌ Okay — report cancelled."
RESPONSE_SYSTEM_OVERLOAD = "⚠️ System is currently experiencing high load. Please try again shortly."
