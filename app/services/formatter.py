from datetime import datetime

CURRENCY_SYMBOLS = {
    'NGN': '₦',
    'USD': '$',
    'EUR': '€',
    'GBP': '£',
    'KES': 'KSh',
    'GHS': 'GH₵',
}


def format_currency(amount, currency='NGN'):
    """Format a number with the appropriate currency symbol. e.g. 2000 -> ₦2,000"""
    symbol = CURRENCY_SYMBOLS.get(currency.upper(), currency)
    if amount < 0:
        return f"-{symbol}{abs(amount):,.0f}"
    return f"{symbol}{amount:,.0f}"


_TX_ACTION_LABELS = {
    'sale': 'Sale (income)', 'purchase': 'Purchase (expense)',
    'expense': 'Expense', 'income': 'Income',
    'payment': 'Payment', 'transfer': 'Transfer', 'other': 'Other',
}
_DEBT_TYPE_LABELS = {'customer_debt': 'Customer owes you', 'supplier_debt': 'You owe supplier'}
_DEBT_ACTION_LABELS = {'add_debt': 'New debt', 'repayment': 'Repayment', 'full_payment': 'Full payment'}


def _table(rows):
    """Render aligned label/value rows inside a WhatsApp monospace block."""
    if not rows:
        return ""
    width = max(len(label) for label, _ in rows)
    lines = [f"{label.ljust(width)}   {value}" for label, value in rows]
    return "```\n" + "\n".join(lines) + "\n```"


def _grid(headers, rows, right_align=(), footer_rows=()):
    """Render a columnar table inside a WhatsApp monospace block.

    ``right_align`` is a set of column indexes (money columns). ``footer_rows``
    are appended under a rule line (totals). Kept narrow so it doesn't wrap on
    a phone screen.
    """
    all_rows = [list(map(str, headers))] + [list(map(str, r)) for r in rows] \
               + [list(map(str, r)) for r in footer_rows]
    widths = [max(len(r[i]) for r in all_rows) for i in range(len(headers))]

    def fmt(r):
        cells = [
            (c.rjust(widths[i]) if i in right_align else c.ljust(widths[i]))
            for i, c in enumerate(r)
        ]
        return "  ".join(cells).rstrip()

    header_line = fmt(all_rows[0])
    rule = "─" * len(header_line)
    body = all_rows[1:len(rows) + 1]
    lines = [header_line, rule] + [fmt(r) for r in body]
    if footer_rows:
        lines.append(rule)
        lines.extend(fmt(r) for r in all_rows[len(rows) + 1:])
    return "```\n" + "\n".join(lines) + "\n```"


def _short_date(date_str):
    """'2026-06-02' -> 'Jun 02' (falls back to the raw string)."""
    try:
        return datetime.strptime(str(date_str), '%Y-%m-%d').strftime('%b %d')
    except (ValueError, TypeError):
        return str(date_str)


def format_statement_chat(rows, meta, max_rows=15):
    """Render a transactions statement as a refined in-chat message.

    Same data the PDF renderer receives (list of dicts with date/type/action/
    item/category/amount/currency). Shows the most recent ``max_rows`` per
    currency; totals always cover the full result set.
    """
    by_cur = {}
    for r in rows or []:
        by_cur.setdefault(r.get('currency') or 'NGN', []).append(r)

    parts = [f"📋 *{meta['title']}*", f"_{meta.get('subtitle', '')}_"]
    for currency, cur_rows in sorted(by_cur.items()):
        income = sum(r['amount'] for r in cur_rows if r['type'] == 'income')
        expense = sum(r['amount'] for r in cur_rows if r['type'] != 'income')
        hidden = len(cur_rows) - max_rows
        display = cur_rows[-max_rows:] if hidden > 0 else cur_rows

        table_rows = [
            (_short_date(r['date']),
             (r.get('item') or r.get('category') or r.get('action') or '—')[:12],
             format_currency(r['amount'], currency))
            for r in display
        ]
        footer = [
            ('', 'Income', format_currency(income, currency)),
            ('', 'Expenses', format_currency(expense, currency)),
            ('', 'Net', format_currency(income - expense, currency)),
        ]
        section = "" if len(by_cur) == 1 else f"\n*{currency}*"
        if section:
            parts.append(section.strip())
        parts.append(_grid(('Date', 'Item', 'Amount'), table_rows,
                           right_align={2}, footer_rows=footer))
        if hidden > 0:
            parts.append(f"_…plus {hidden} earlier entr{'y' if hidden == 1 else 'ies'} not shown._")

    parts.append("_Reply *pdf* or *excel* to get the full statement as a file._")
    return "\n".join(parts)


def format_cashflow_chat(buckets, meta):
    """Render monthly cashflow ({currency: [{month, inflow, outflow, net}, …]})
    as a refined in-chat message."""
    parts = [f"💸 *{meta['title']}*", f"_{meta.get('subtitle', '')}_"]
    for currency, rows in sorted((buckets or {}).items()):
        tot_in = sum(r['inflow'] for r in rows)
        tot_out = sum(r['outflow'] for r in rows)
        table_rows = [
            (r['month'],
             format_currency(r['inflow'], currency),
             format_currency(r['outflow'], currency),
             format_currency(r['net'], currency))
            for r in rows
        ]
        footer = [(
            'TOTAL',
            format_currency(tot_in, currency),
            format_currency(tot_out, currency),
            format_currency(tot_in - tot_out, currency),
        )]
        if len(buckets) > 1:
            parts.append(f"*{currency}*")
        parts.append(_grid(('Month', 'In', 'Out', 'Net'), table_rows,
                           right_align={1, 2, 3}, footer_rows=footer))

    parts.append("_Reply *pdf* or *excel* to get this as a file._")
    return "\n".join(parts)


def format_period_report(data):
    """Render the quick daily/weekly/monthly summary as refined chat text
    (replaces the old raw-JSON dump).

    ``data``: {'period_label', 'per_currency': {cur: {'income','expenses'}},
               'customer_debt', 'supplier_debt', 'top_selling_product'}
    """
    parts = [f"📊 *{data['period_label']}*"]
    per_currency = data.get('per_currency') or {'NGN': {'income': 0.0, 'expenses': 0.0}}
    for currency, v in sorted(per_currency.items()):
        income = v.get('income', 0.0)
        expenses = v.get('expenses', 0.0)
        rows = [
            ("Income", format_currency(income, currency)),
            ("Expenses", format_currency(expenses, currency)),
            ("Profit", format_currency(income - expenses, currency)),
        ]
        if len(per_currency) > 1:
            parts.append(f"*{currency}*")
        parts.append(_table(rows))

    extras = []
    if data.get('customer_debt'):
        extras.append(f"👥 Customers owe you: {format_currency(data['customer_debt'])}")
    if data.get('supplier_debt'):
        extras.append(f"🏭 You owe suppliers: {format_currency(data['supplier_debt'])}")
    top = data.get('top_selling_product')
    if top and top != 'None':
        extras.append(f"🏆 Top product: {top}")
    if extras:
        parts.append("\n".join(extras))

    parts.append("_Want details? Try \"statement for this month\" for a full breakdown._")
    return "\n\n".join(parts)


def format_confirmation(parsed):
    """Build a confirm-before-record breakdown of a parsed message.

    Shows one aligned section per write item. A message may carry several
    transactions / inventory movements / debts (e.g. a purchase AND a sale);
    each gets its own numbered section so the user can verify every entry
    before it commits.
    """
    sections = []

    transactions = parsed.get('transactions') or []
    inventory = parsed.get('inventory') or []
    debts = parsed.get('debts') or []

    multi_tx = len(transactions) > 1
    for i, tx in enumerate(transactions, 1):
        rows = [("Action", _TX_ACTION_LABELS.get(tx.get('action'), tx.get('action', '-')))]
        if tx.get('item'):
            rows.append(("Item", tx['item']))
        rows.append(("Amount", format_currency(float(tx.get('amount', 0)), tx.get('currency', 'NGN'))))
        rows.append(("Category", tx.get('category', 'Miscellaneous')))
        if tx.get('date'):
            rows.append(("Date", tx['date']))
        title = f"💰 *Transaction {i}*" if multi_tx else "💰 *Transaction*"
        sections.append(title + "\n" + _table(rows))

    multi_inv = len(inventory) > 1
    for i, inv in enumerate(inventory, 1):
        action = str(inv.get('action', '')).upper()
        sign = '−' if action == 'REMOVE' else ('=' if action == 'SET' else '+')
        unit = f" {inv['unit']}" if inv.get('unit') else ""
        qty = inv.get('quantity')
        qty_str = f"{int(qty)}" if isinstance(qty, (int, float)) and float(qty).is_integer() else f"{qty}"
        rows = [
            ("Action", str(inv.get('action', '-')).title()),
            ("Product", inv.get('product', '-')),
            ("Quantity", f"{sign}{qty_str}{unit}"),
        ]
        title = f"📦 *Inventory {i}*" if multi_inv else "📦 *Inventory*"
        sections.append(title + "\n" + _table(rows))

    multi_debt = len(debts) > 1
    for i, debt in enumerate(debts, 1):
        rows = [
            ("Person", str(debt.get('name', '-')).title()),
            ("Type", _DEBT_TYPE_LABELS.get(debt.get('type'), debt.get('type', '-'))),
            ("Action", _DEBT_ACTION_LABELS.get(debt.get('action'), debt.get('action', '-'))),
        ]
        if debt.get('amount') is not None:
            rows.append(("Amount", format_currency(float(debt['amount']), debt.get('currency', 'NGN'))))
        title = f"👥 *Debt {i}*" if multi_debt else "👥 *Debt*"
        sections.append(title + "\n" + _table(rows))

    if not sections:
        return None

    body = "\n\n".join(sections)
    return (
        "📝 *Please confirm this entry:*\n\n"
        f"{body}\n\n"
        "Reply *YES* to record or *NO* to cancel."
    )


def format_transaction_saved(result):
    """Format a saved transaction confirmation for WhatsApp.

    Args:
        result: dict with type, action, amount, currency, item, category, description, date.
    """
    currency = result.get('currency', 'NGN')
    amount = format_currency(result['amount'], currency)
    category = result.get('category', 'Miscellaneous')
    description = result.get('description', '')
    item = result.get('item')
    action = result.get('action', result['type'])
    tx_date = result.get('date', '')

    # Format date nicely
    try:
        dt = datetime.strptime(tx_date, '%Y-%m-%d')
        date_str = dt.strftime('%b %d, %Y')
    except (ValueError, TypeError):
        date_str = tx_date

    # Action-specific emoji and label
    action_display = {
        'sale': ('🏷️', 'Sale'),
        'purchase': ('🛒', 'Purchase'),
        'expense': ('💸', 'Expense'),
        'income': ('💰', 'Income'),
        'payment': ('💳', 'Payment'),
        'transfer': ('🔄', 'Transfer'),
    }
    emoji, action_label = action_display.get(action, ('📝', action.capitalize()))

    lines = [
        f"✅ *Transaction Recorded* {emoji}",
        "",
        f"*Action:* {action_label}",
        f"*Amount:* {amount}",
    ]

    if item:
        lines.append(f"*Item:* {item}")

    lines.append(f"*Category:* {category}")

    if description:
        lines.append(f"*Description:* {description}")

    lines.append(f"*Date:* {date_str}")

    return "\n".join(lines)


def format_sum_query(result):
    """Format a sum query result for WhatsApp.

    Args:
        result: dict with totals, type, category, period_start, period_end.
    """
    tx_type = result.get('type', 'all')
    category = result.get('category')

    # Build description
    desc_parts = []
    if tx_type and tx_type != 'all':
        desc_parts.append(tx_type)
    if category and category != 'all':
        desc_parts.append(f"on {category}")

    desc = " ".join(desc_parts) if desc_parts else "transactions"

    # Format period
    period = _format_period(result.get('period_start'), result.get('period_end'))

    lines = [
        "📊 *Summary*",
        "",
        f"*Total {desc}:*",
    ]

    totals = result.get('totals', {})
    if not totals:
        lines.append("• No transactions found.")
    else:
        for currency, info in totals.items():
            total_formatted = format_currency(info['total'], currency)
            lines.append(f"• *{currency}*: {total_formatted} ({info['count']} transactions)")

    if period:
        lines.append("")
        lines.append(f"*Period:* {period}")

    return "\n".join(lines)


def format_list_query(items, parsed):
    """Format a list of transactions for WhatsApp.

    Args:
        items: list of transaction dicts.
        parsed: the original parsed query for context.
    """
    if not items:
        return "📋 No transactions found for your query."

    tx_type = parsed.get('type', '')
    category = parsed.get('category', '')

    header_parts = []
    if tx_type:
        header_parts.append(tx_type.capitalize())
    if category and category != 'all':
        header_parts.append(category)
    header = " — ".join(header_parts) if header_parts else "Transactions"

    period = _format_period(parsed.get('period_start'), parsed.get('period_end'))

    lines = [f"📋 *{header}*"]
    if period:
        lines.append(f"_{period}_")
    lines.append("")

    for item in items:
        currency = item.get('currency', 'NGN')
        amount = format_currency(item['amount'], currency)
        emoji = "📈" if item['type'] == 'income' else "📉"
        desc = item.get('description', item.get('category', ''))
        try:
            dt = datetime.strptime(item['date'], '%Y-%m-%d')
            date_str = dt.strftime('%b %d')
        except (ValueError, TypeError):
            date_str = item['date']

        lines.append(f"{emoji} {desc} — {amount} ({date_str})")

    return "\n".join(lines)


def format_balance(result):
    """Format a balance query result for WhatsApp.

    Args:
        result: list of dicts with currency, income, expenses, net.
    """
    lines = [
        "💰 *Your Balance*",
        ""
    ]
    for balance in result:
        currency = balance['currency']
        income = format_currency(balance['income'], currency)
        expenses = format_currency(balance['expenses'], currency)
        net = balance['net']
        net_str = format_currency(net, currency)
        net_emoji = "📈" if net >= 0 else "📉"
        
        lines.extend([
            f"*{currency} Balance:*",
            f"• *Income:* {income}",
            f"• *Expenses:* {expenses}",
            f"• *Net:* {net_str} {net_emoji}",
            ""
        ])
    
    if lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def _format_period(start, end):
    """Format a date range into a readable string."""
    if not start and not end:
        return None

    try:
        parts = []
        if start:
            dt = datetime.strptime(start, '%Y-%m-%d')
            parts.append(dt.strftime('%b %d, %Y'))
        if end:
            dt = datetime.strptime(end, '%Y-%m-%d')
            parts.append(dt.strftime('%b %d, %Y'))
        return " → ".join(parts) if len(parts) == 2 else parts[0]
    except (ValueError, TypeError):
        return f"{start or ''} → {end or ''}"
