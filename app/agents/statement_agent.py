"""Statement Agent — turns a parsed `statement` request into a delivered document.

Read-only: queries the ledger, renders a PDF and/or spreadsheet, and sends it to
the user as a WhatsApp document (side effect). Returns a short text ack for the
normal send_reply path. No YES/NO confirmation — statements never mutate data.
"""

import shutil
from datetime import date

from app.data.queries import query_statement, query_cashflow
from app.services.report_renderer import render
from app.services.formatter import _format_period, format_statement_chat, format_cashflow_chat
from app.channels.registry import send_document   # routes to the originating channel (WP-05)


_ACTION_LABELS = {'purchase': 'Purchases', 'sale': 'Sales', 'expense': 'Expenses', 'income': 'Income'}
_TYPE_LABELS = {'expense': 'Expenses', 'income': 'Income'}


def _income_chat(rows, meta):
    """Compact in-chat Income Statement (revenue → gross → net) per currency."""
    from app.services.report_renderer import compute_income_statement, format_money
    lines = [f"📊 *{meta['title']}* — {meta['subtitle']}"]
    for cur, p in sorted(compute_income_statement(rows).items()):
        lines += [
            "",
            f"Total revenue: *{format_money(p['total_revenue'], cur)}*",
            f"Less cost of goods sold: {format_money(p['cogs'], cur)}",
            f"*Gross profit: {format_money(p['gross_profit'], cur)}*",
            f"Less operating expenses: {format_money(p['total_expenses'], cur)}",
            f"*Net profit: {format_money(p['net_profit'], cur)}*",
        ]
    return "\n".join(lines)


def describe(statement):
    """(title, range_label) for a parsed statement dict — used both for the
    document header and for the chat-or-PDF question before generation."""
    report_type = statement.get('report_type', 'transactions')
    if report_type == 'cashflow':
        title = 'Cashflow Statement'
    elif report_type == 'income_statement':
        title = 'Income Statement'
    else:
        label = (_ACTION_LABELS.get(statement.get('action'))
                 or _TYPE_LABELS.get(statement.get('tx_type'))
                 or 'Transactions')
        title = 'Statement of Account' if label == 'Transactions' else f"{label} Statement"
    start, end = _resolve_range(statement, report_type)
    return title, (_format_period(start, end) or 'all time')


def _resolve_range(statement, report_type):
    """Use NLP-provided dates; otherwise default sensibly (stated in the caption)."""
    start = statement.get('period_start')
    end = statement.get('period_end')
    if start or end:
        return start, end
    today = date.today()
    if report_type == 'cashflow':
        # last 6 months including the current one
        month = today.month - 5
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        return date(year, month, 1).isoformat(), today.isoformat()
    # transactions: current month to date
    return date(today.year, today.month, 1).isoformat(), today.isoformat()


class StatementAgent:
    def __init__(self, user_id, sender_id):
        self.user_id = user_id
        self.sender_id = sender_id

    def generate_and_send(self, statement):
        """statement: dict from the parsed StatementModel. Returns an ack string
        (or, for format 'chat', the rendered in-chat report itself)."""
        report_type = statement.get('report_type', 'transactions')
        fmt = statement.get('format', 'pdf') or 'pdf'
        start, end = _resolve_range(statement, report_type)

        meta = {
            'business_name': self._business_name(),
            'subtitle': self._range_label(start, end),
        }

        if report_type == 'cashflow':
            meta['title'] = 'Cashflow Statement'
            data = query_cashflow(self.user_id, start, end)
            is_empty = not data
        elif report_type == 'income_statement':
            meta['title'] = 'Income Statement'
            # P&L is derived from the full period's rows (no type/action filter).
            data = query_statement(self.user_id, {'period_start': start, 'period_end': end})
            is_empty = not data
        else:
            label = self._tx_label(statement)
            meta['title'] = 'Statement of Account' if label == 'Transactions' else f"{label} Statement"
            filters = {
                'tx_type': statement.get('tx_type'),
                'action': statement.get('action'),
                'category': statement.get('category'),
                'period_start': start,
                'period_end': end,
            }
            data = query_statement(self.user_id, filters)
            is_empty = not data

        if data is None:
            return "❌ Couldn't build that report right now. Please try again shortly."
        if is_empty:
            return f"📋 No {meta['title'].replace(' Statement','').lower()} found for {meta['subtitle']}."

        # In-chat delivery: render refined text tables, no file involved.
        if fmt == 'chat':
            if report_type == 'cashflow':
                return format_cashflow_chat(data, meta)
            if report_type == 'income_statement':
                return _income_chat(data, meta)
            return format_statement_chat(data, meta)

        files = []
        try:
            files = render(report_type, data, meta, fmt)
            caption = f"📎 {meta['title']} — {meta['subtitle']}"
            sent_labels = []
            for f in files:
                ok, detail = send_document(self.sender_id, f['path'], f['filename'], caption)
                if ok:
                    sent_labels.append('Excel' if f['filename'].endswith('.xlsx') else 'PDF')
                else:
                    print(f"[StatementAgent] send_document failed: {detail}")
            if not sent_labels:
                return "⚠️ I built your report but couldn't deliver the file. Please try again."
            return f"📎 Sent your *{meta['title']}* ({meta['subtitle']}) as {' + '.join(sent_labels)}."
        finally:
            tmpdir = meta.get('tmpdir')
            if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)

    # ---------------------------------------------------------------- helpers

    def _tx_label(self, statement):
        return (_ACTION_LABELS.get(statement.get('action'))
                or _TYPE_LABELS.get(statement.get('tx_type'))
                or 'Transactions')

    def _range_label(self, start, end):
        return _format_period(start, end) or 'all time'

    def _business_name(self):
        from app.data.database import get_db_connection
        from app.services.uuid_utils import uuid_to_bin
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT display_name, business_profile FROM users WHERE id = %s LIMIT 1",
                (uuid_to_bin(self.user_id),)
            )
            row = cursor.fetchone()
            if row:
                profile = row.get('business_profile')
                if isinstance(profile, str):
                    import json
                    try:
                        profile = json.loads(profile)
                    except Exception:
                        profile = None
                if isinstance(profile, dict):
                    name = profile.get('name') or profile.get('business_name')
                    if name:
                        return name
                if row.get('display_name'):
                    return row['display_name']
        except Exception as e:
            print(f"[StatementAgent business_name] {e}")
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
        return 'TaLi'
