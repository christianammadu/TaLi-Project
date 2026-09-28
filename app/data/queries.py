"""Transaction reads/writes — ported to the SQLAlchemy ORM (app/db + app/models).

Reads are scoped to the user's business only when they are actually provisioned
into one (``business_id`` is set); otherwise strictly to ``user_id`` so unrelated
users can't read each other's records.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, or_, select

from app.data.db import session_scope
from app.data.models import Category, InventoryItem, InventoryMovement, Product, Record, Transaction, User
from app.services.uuid_utils import uuid7


def _scope(session, user_id):
    """Return (column, value) for scoping a transactions query.

    Business-scoped when the user has a real business_id, else user-scoped.
    """
    business_id = session.execute(
        select(User.business_id).where(User.id == user_id)
    ).scalar_one_or_none()
    if business_id is not None:
        return Transaction.business_id, business_id
    return Transaction.user_id, user_id


def record_transaction(user_id, sender_id, raw_text, parsed):
    """Insert a transaction (and a legacy records row) from NLP-parsed data.

    Returns a dict of the saved transaction on success, None on failure.
    """
    category_name = parsed.get('category', 'Miscellaneous')
    transaction_date = parsed.get('date', date.today().isoformat())
    amount = Decimal(str(parsed.get('amount', 0)))
    currency = parsed.get('currency', 'NGN')
    tx_type = parsed.get('type', 'expense')
    action = parsed.get('action', 'other')
    item = parsed.get('item')
    description = parsed.get('description', '')

    try:
        with session_scope() as s:
            # Resolve category (user-owned or system default), falling back to Miscellaneous.
            category_id = s.execute(
                select(Category.id).where(
                    Category.name == category_name,
                    or_(Category.user_id.is_(None), Category.user_id == user_id),
                ).limit(1)
            ).scalar_one_or_none()
            if category_id is None:
                category_id = s.execute(
                    select(Category.id).where(
                        Category.name == 'Miscellaneous', Category.user_id.is_(None)
                    ).limit(1)
                ).scalar_one_or_none()

            user = s.get(User, user_id)
            business_id = user.business_id if user else None

            tx_uuid = uuid7()
            rec_uuid = uuid7()

            s.add(Transaction(
                id=tx_uuid,
                user_id=user_id, business_id=business_id, category_id=category_id,
                type=tx_type, action=action, amount=amount, currency=currency,
                currency_code=currency, item=item, description=description,
                raw_text=raw_text, transaction_date=transaction_date,
            ))
            # Legacy records table (preserved for backward compatibility).
            s.add(Record(id=rec_uuid, sender_id=sender_id, raw_text=raw_text, amount=int(amount)))

        return {
            'type': tx_type,
            'action': action,
            'amount': float(amount),
            'currency': currency,
            'item': item,
            'category': category_name,
            'description': description,
            'date': transaction_date,
        }
    except Exception as e:
        print(f"Failed to record transaction: {e}")
        return None


def query_sum(user_id, parsed):
    """Total amount matching filters, grouped by currency (with counts)."""
    tx_type = parsed.get('type')
    category = parsed.get('category')
    period_start = parsed.get('period_start')
    period_end = parsed.get('period_end')
    currency_filter = parsed.get('currency')
    try:
        with session_scope() as s:
            scope_col, scope_val = _scope(s, user_id)
            stmt = select(
                Transaction.currency,
                func.coalesce(func.sum(Transaction.amount), 0).label('total'),
                func.count().label('count'),
            ).where(scope_col == scope_val)

            if tx_type:
                stmt = stmt.where(Transaction.type == tx_type)
            if category and category != 'all':
                stmt = stmt.join(Category, Transaction.category_id == Category.id).where(
                    Category.name == category
                )
            if currency_filter:
                stmt = stmt.where(Transaction.currency == currency_filter)
            if period_start:
                stmt = stmt.where(Transaction.transaction_date >= period_start)
            if period_end:
                stmt = stmt.where(Transaction.transaction_date <= period_end)

            stmt = stmt.group_by(Transaction.currency)
            rows = s.execute(stmt).all()
            totals = {
                r.currency: {'total': float(r.total), 'count': r.count} for r in rows
            }
        return {
            'totals': totals,
            'type': tx_type,
            'category': category,
            'period_start': period_start,
            'period_end': period_end,
        }
    except Exception as e:
        print(f"Failed to query sum: {e}")
        return None


def query_list(user_id, parsed, limit=10):
    """List recent transactions matching filters."""
    tx_type = parsed.get('type')
    category = parsed.get('category')
    period_start = parsed.get('period_start')
    period_end = parsed.get('period_end')
    currency_filter = parsed.get('currency')
    try:
        with session_scope() as s:
            scope_col, scope_val = _scope(s, user_id)
            stmt = select(
                Transaction.type,
                Transaction.amount,
                Transaction.currency,
                Transaction.description,
                Transaction.transaction_date,
                func.coalesce(Category.name, 'Miscellaneous').label('category'),
            ).select_from(Transaction).outerjoin(
                Category, Transaction.category_id == Category.id
            ).where(scope_col == scope_val)

            if tx_type:
                stmt = stmt.where(Transaction.type == tx_type)
            if category and category != 'all':
                stmt = stmt.where(Category.name == category)
            if currency_filter:
                stmt = stmt.where(Transaction.currency == currency_filter)
            if period_start:
                stmt = stmt.where(Transaction.transaction_date >= period_start)
            if period_end:
                stmt = stmt.where(Transaction.transaction_date <= period_end)

            stmt = stmt.order_by(
                Transaction.transaction_date.desc(), Transaction.created_at.desc()
            ).limit(limit)
            rows = s.execute(stmt).all()
            return [
                {
                    'type': r.type,
                    'amount': float(r.amount),
                    'currency': r.currency,
                    'description': r.description,
                    'date': str(r.transaction_date),
                    'category': r.category,
                }
                for r in rows
            ]
    except Exception as e:
        print(f"Failed to query list: {e}")
        return None


def query_statement(user_id, filters, limit=5000):
    """Full filtered transaction rows for a downloadable statement.

    Like ``query_list`` but unbounded (capped at ``limit`` for the free tier),
    ordered ascending by date, and including action/item for a proper ledger.
    ``filters`` keys: tx_type, action, category, currency, period_start, period_end.
    Returns a list of dicts, or None on failure.
    """
    tx_type = filters.get('tx_type') or filters.get('type')
    action = filters.get('action')
    category = filters.get('category')
    period_start = filters.get('period_start')
    period_end = filters.get('period_end')
    currency_filter = filters.get('currency')
    try:
        with session_scope() as s:
            scope_col, scope_val = _scope(s, user_id)
            stmt = select(
                Transaction.transaction_date,
                Transaction.type,
                Transaction.action,
                Transaction.item,
                Transaction.amount,
                Transaction.currency,
                func.coalesce(Category.name, 'Miscellaneous').label('category'),
            ).select_from(Transaction).outerjoin(
                Category, Transaction.category_id == Category.id
            ).where(scope_col == scope_val)

            if tx_type:
                stmt = stmt.where(Transaction.type == tx_type)
            if action and action != 'all':
                stmt = stmt.where(Transaction.action == action)
            if category and category != 'all':
                stmt = stmt.where(Category.name == category)
            if currency_filter:
                stmt = stmt.where(Transaction.currency == currency_filter)
            if period_start:
                stmt = stmt.where(Transaction.transaction_date >= period_start)
            if period_end:
                stmt = stmt.where(Transaction.transaction_date <= period_end)

            stmt = stmt.order_by(
                Transaction.transaction_date.asc(), Transaction.created_at.asc()
            ).limit(limit)
            rows = s.execute(stmt).all()
            return [
                {
                    'date': str(r.transaction_date),
                    'type': r.type,
                    'action': r.action,
                    'item': r.item,
                    'amount': float(r.amount),
                    'currency': r.currency,
                    'category': r.category,
                }
                for r in rows
            ]
    except Exception as e:
        print(f"Failed to query statement: {e}")
        return None


def query_cashflow(user_id, period_start=None, period_end=None):
    """Monthly inflow/outflow/net (+ running cumulative) per currency.

    Returns a dict: {currency: [ {month, inflow, outflow, net, cumulative}, ... ]}
    ordered by month ascending, or None on failure.
    """
    try:
        with session_scope() as s:
            scope_col, scope_val = _scope(s, user_id)
            month = func.date_format(Transaction.transaction_date, '%Y-%m').label('month')
            inflow = func.coalesce(
                func.sum(case((Transaction.type == 'income', Transaction.amount), else_=0)), 0
            ).label('inflow')
            outflow = func.coalesce(
                func.sum(case((Transaction.type == 'expense', Transaction.amount), else_=0)), 0
            ).label('outflow')
            stmt = (
                select(Transaction.currency, month, inflow, outflow)
                .where(scope_col == scope_val)
            )
            if period_start:
                stmt = stmt.where(Transaction.transaction_date >= period_start)
            if period_end:
                stmt = stmt.where(Transaction.transaction_date <= period_end)
            stmt = stmt.group_by(Transaction.currency, month).order_by(
                Transaction.currency.asc(), month.asc()
            )
            rows = s.execute(stmt).all()

        buckets = {}
        cumulative = {}
        for r in rows:
            cur = r.currency
            inf = float(r.inflow)
            outf = float(r.outflow)
            net = inf - outf
            cumulative[cur] = cumulative.get(cur, 0.0) + net
            buckets.setdefault(cur, []).append({
                'month': r.month,
                'inflow': inf,
                'outflow': outf,
                'net': net,
                'cumulative': cumulative[cur],
            })
        return buckets
    except Exception as e:
        print(f"Failed to query cashflow: {e}")
        return None


def query_balance(user_id):
    """Income, expenses and net per currency."""
    try:
        with session_scope() as s:
            scope_col, scope_val = _scope(s, user_id)
            income = func.coalesce(
                func.sum(case((Transaction.type == 'income', Transaction.amount), else_=0)), 0
            ).label('income')
            expenses = func.coalesce(
                func.sum(case((Transaction.type == 'expense', Transaction.amount), else_=0)), 0
            ).label('expenses')
            stmt = (
                select(Transaction.currency, income, expenses)
                .where(scope_col == scope_val)
                .group_by(Transaction.currency)
            )
            rows = s.execute(stmt).all()
            balances = [
                {
                    'currency': r.currency,
                    'income': float(r.income),
                    'expenses': float(r.expenses),
                    'net': float(r.income) - float(r.expenses),
                }
                for r in rows
            ]
        if not balances:
            balances.append({'currency': 'NGN', 'income': 0.0, 'expenses': 0.0, 'net': 0.0})
        return balances
    except Exception as e:
        print(f"Failed to query balance: {e}")
        return None


def query_opening_balance(user_id, before_date):
    """Net cash position (income − expenses) per currency for all transactions strictly
    before ``before_date`` — i.e. the opening balance for a statement starting that day.

    Returns ``{currency: net_float}`` (empty when there's no prior history or on failure),
    so a statement's running/closing balance is a true balance, not period-only.
    """
    if not before_date:
        return {}
    try:
        with session_scope() as s:
            scope_col, scope_val = _scope(s, user_id)
            income = func.coalesce(
                func.sum(case((Transaction.type == 'income', Transaction.amount), else_=0)), 0)
            expenses = func.coalesce(
                func.sum(case((Transaction.type == 'expense', Transaction.amount), else_=0)), 0)
            stmt = (
                select(Transaction.currency, (income - expenses).label('net'))
                .where(scope_col == scope_val)
                .where(Transaction.transaction_date < before_date)
                .group_by(Transaction.currency)
            )
            return {r.currency: float(r.net) for r in s.execute(stmt).all()}
    except Exception as e:
        print(f"Failed to query opening balance: {e}")
        return {}


def _stem_token(word: str) -> str:
    """Normalize plural forms to singular."""
    w = word.strip().lower()
    if len(w) <= 3:
        return w
    if w.endswith('ies') and len(w) > 4:
        return w[:-3] + 'y'
    if w.endswith('toes') or w.endswith('does'):
        return w[:-2]
    if w.endswith(('ches', 'shes', 'xes')):
        return w[:-2]
    if w.endswith('sses'):
        return w[:-2]
    if w.endswith('s') and not w.endswith('ss'):
        return w[:-1]
    return w


def get_user_product_names(user_id):
    """Fetch distinct product/item names owned by user across inventory_items and products.

    Used for injecting known canonical product names into the NLP prompt (WP-03).
    """
    if not user_id:
        return []
    names = set()
    try:
        with session_scope() as s:
            inv_names = s.execute(
                select(InventoryItem.item_name).where(InventoryItem.user_id == user_id)
            ).scalars().all()
            prod_names = s.execute(
                select(Product.name).where(Product.user_id == user_id)
            ).scalars().all()
            for n in inv_names:
                if n and n.strip():
                    names.add(n.strip())
            for n in prod_names:
                if n and n.strip():
                    names.add(n.strip())
        return sorted(list(names))
    except Exception as e:
        print(f"Failed to fetch user product names: {e}")
        return []


def resolve_inventory_item(user_id, product_name):
    """Multi-tier fuzzy resolution for inventory products (WP-03 / G-03 & G-07).

    Resolves merchant queries (e.g. 'rice', 'eggs') against stored inventory items
    (e.g. '50kg bag of rice', 'egg') across 3 tiers:
    1. Exact match (case-insensitive)
    2. Stemmed match (singular/plural normalization)
    3. Token / Substring containment (e.g. 'rice' in '50kg bag of rice')

    If multiple items tie with equal confidence in Tier 3 (e.g. 'Golden Penny Flour'
    and 'Golden Penny Semovita' for input 'Golden Penny'), returns:
      {
        "status": "clarification_needed",
        "matches": [item1, item2],
        "question": "🤔 I found multiple items matching 'Golden Penny'..."
      }
    Otherwise on unique match returns:
      {
        "status": "matched",
        "id": item_id,
        "item_id": item_id,
        "name": canonical_name,
        "item_name": canonical_name,
        "unit": unit,
        "stock": float(current_stock),
        "quantity": float(current_stock),
        "source": "inventory_items" | "products"
      }
    Returns None if no matching items are found.
    """
    if not user_id or not product_name:
        return None

    q = str(product_name).strip().lower()
    if not q:
        return None

    # Fetch user inventory items and products
    candidates = []
    seen_names = set()

    try:
        with session_scope() as s:
            # 1. Standard inventory_items with calculated movement stock
            level = func.coalesce(func.sum(case(
                (InventoryMovement.movement_type == 'stock_in', InventoryMovement.quantity),
                (InventoryMovement.movement_type == 'stock_out', -InventoryMovement.quantity),
                (InventoryMovement.movement_type == 'adjustment', InventoryMovement.quantity),
                else_=0,
            )), 0).label('stock')
            inv_stmt = (
                select(InventoryItem.id, InventoryItem.item_name, InventoryItem.unit, level)
                .select_from(InventoryItem)
                .outerjoin(InventoryMovement, InventoryItem.id == InventoryMovement.inventory_item_id)
                .where(InventoryItem.user_id == user_id)
                .group_by(InventoryItem.id, InventoryItem.item_name, InventoryItem.unit)
            )
            for r in s.execute(inv_stmt).all():
                name = r.item_name
                candidates.append({
                    "id": str(r.id),
                    "item_id": str(r.id),
                    "name": name,
                    "item_name": name,
                    "unit": r.unit or "units",
                    "stock": float(r.stock or 0),
                    "quantity": float(r.stock or 0),
                    "source": "inventory_items"
                })
                seen_names.add(name.lower().strip())

            # 2. Legacy products table (if not already represented in inventory_items)
            prod_stmt = select(Product.id, Product.name, Product.unit, Product.quantity).where(Product.user_id == user_id)
            for r in s.execute(prod_stmt).all():
                name = r.name
                if name.lower().strip() not in seen_names:
                    candidates.append({
                        "id": str(r.id),
                        "item_id": str(r.id),
                        "name": name,
                        "item_name": name,
                        "unit": r.unit or "units",
                        "stock": float(r.quantity or 0),
                        "quantity": float(r.quantity or 0),
                        "source": "products"
                    })
                    seen_names.add(name.lower().strip())
    except Exception as e:
        print(f"Error fetching inventory candidates: {e}")
        return None

    if not candidates:
        return None

    # Tier 1: Exact match (case-insensitive)
    exact_matches = [c for c in candidates if c["name"].strip().lower() == q]
    if len(exact_matches) == 1:
        return {"status": "matched", **exact_matches[0]}

    # Tier 2: Stemmed match (singular / plural normalization)
    q_stem = " ".join(_stem_token(w) for w in q.split())
    stemmed_matches = [
        c for c in candidates
        if " ".join(_stem_token(w) for w in c["name"].split()) == q_stem
    ]
    if len(stemmed_matches) == 1:
        return {"status": "matched", **stemmed_matches[0]}
    elif len(stemmed_matches) > 1:
        bullets = "\n".join(f"{i+1}. {m['name']}" for i, m in enumerate(stemmed_matches))
        return {
            "status": "clarification_needed",
            "matches": stemmed_matches,
            "question": (
                f"🤔 I found multiple items matching *\"{product_name}\"*. Which one did you mean?\n\n"
                f"{bullets}\n\n"
                "Please reply with the number or exact item name."
            )
        }

    # Tier 3: Token containment & Substring match
    q_tokens = set(q.split())
    q_stem_tokens = set(_stem_token(w) for w in q.split())
    tier3_matches = []
    for c in candidates:
        c_stem_tokens = set(_stem_token(w) for w in c["name"].split())
        c_name_lower = c["name"].lower()
        if q_stem_tokens.issubset(c_stem_tokens) or q in c_name_lower or c_name_lower in q:
            tier3_matches.append(c)

    if len(tier3_matches) == 1:
        return {"status": "matched", **tier3_matches[0]}
    elif len(tier3_matches) > 1:
        bullets = "\n".join(f"{i+1}. {m['name']}" for i, m in enumerate(tier3_matches))
        return {
            "status": "clarification_needed",
            "matches": tier3_matches,
            "question": (
                f"🤔 I found multiple items matching *\"{product_name}\"*. Which one did you mean?\n\n"
                f"{bullets}\n\n"
                "Please reply with the number or exact item name."
            )
        }

    return None


def query_stock_levels(user_id, limit=50):
    """Current stock level per item, computed from ``inventory_movements`` and ``products``.

    Scoped strictly by ``user_id`` regardless of business_id NULL status (G-03).
    Returns a list of ``{item, unit, stock}`` ordered by name, or ``None`` on failure.
    """
    try:
        with session_scope() as s:
            level = func.coalesce(func.sum(case(
                (InventoryMovement.movement_type == 'stock_in', InventoryMovement.quantity),
                (InventoryMovement.movement_type == 'stock_out', -InventoryMovement.quantity),
                (InventoryMovement.movement_type == 'adjustment', InventoryMovement.quantity),
                else_=0,
            )), 0).label('stock')
            stmt = (
                select(InventoryItem.item_name, InventoryItem.unit, level)
                .select_from(InventoryItem)
                .outerjoin(InventoryMovement, InventoryItem.id == InventoryMovement.inventory_item_id)
                .where(InventoryItem.user_id == user_id)
                .group_by(InventoryItem.id, InventoryItem.item_name, InventoryItem.unit)
                .order_by(InventoryItem.item_name)
                .limit(limit)
            )
            rows = [
                {'item': r.item_name, 'unit': r.unit or 'units', 'stock': float(r.stock or 0)}
                for r in s.execute(stmt).all()
            ]
            seen_items = {r['item'].lower().strip() for r in rows}
            # Also include legacy products if not already tracked in inventory_items
            prod_stmt = (
                select(Product.name, Product.unit, Product.quantity)
                .where(Product.user_id == user_id)
                .order_by(Product.name)
                .limit(limit)
            )
            for p in s.execute(prod_stmt).all():
                if p.name.lower().strip() not in seen_items:
                    rows.append({'item': p.name, 'unit': p.unit or 'units', 'stock': float(p.quantity or 0)})
                    seen_items.add(p.name.lower().strip())
            return rows
    except Exception as e:
        print(f"Failed to query stock levels: {e}")
        return None
