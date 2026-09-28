"""Financial metrics, cashflow analytics, and ledger queries for the Merchant Web Portal (WP-08).

All queries are strictly isolated to the authenticated merchant's account (user_id / business_id).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from sqlalchemy import case, func, or_, select

from app.data.db import session_scope
from app.data.models import Category, DebtBalance, InventoryItem, Product, Transaction, User
from app.services.formatter import format_currency


def _get_scope(session, user_id):
    """Resolve (column, value) for multi-tenant query isolation."""
    try:
        biz_id = session.execute(
            select(User.business_id).where(User.id == user_id)
        ).scalar_one_or_none()
        if biz_id is not None:
            return Transaction.business_id, biz_id
    except Exception:
        pass
    return Transaction.user_id, user_id


def get_merchant_financial_summary(user_id: str) -> dict:
    """Compute aggregate financial health indicators for a merchant.

    Returns:
        Dictionary containing gross revenue, expenses, net cashflow, MTD/today metrics,
        receivables/payables, and SKU counts.
    """
    summary = {
        "total_revenue": 0.0,
        "total_revenue_fmt": "₦0.00",
        "total_expense": 0.0,
        "total_expense_fmt": "₦0.00",
        "net_cashflow": 0.0,
        "net_cashflow_fmt": "₦0.00",
        "month_revenue": 0.0,
        "month_revenue_fmt": "₦0.00",
        "month_expense": 0.0,
        "month_expense_fmt": "₦0.00",
        "month_net": 0.0,
        "month_net_fmt": "₦0.00",
        "today_revenue": 0.0,
        "today_revenue_fmt": "₦0.00",
        "total_receivables": 0.0,
        "total_receivables_fmt": "₦0.00",
        "total_payables": 0.0,
        "total_payables_fmt": "₦0.00",
        "active_skus": 0,
        "transaction_count": 0,
    }

    today = date.today()
    month_start = today.replace(day=1)

    try:
        with session_scope() as s:
            scope_col, scope_val = _get_scope(s, user_id)

            # 1. Lifetime & MTD & Today Transaction Aggregates
            inflow_expr = case((Transaction.type == "income", Transaction.amount), else_=0)
            outflow_expr = case((Transaction.type == "expense", Transaction.amount), else_=0)

            month_inflow_expr = case(
                ((Transaction.type == "income") & (Transaction.transaction_date >= month_start), Transaction.amount),
                else_=0,
            )
            month_outflow_expr = case(
                ((Transaction.type == "expense") & (Transaction.transaction_date >= month_start), Transaction.amount),
                else_=0,
            )

            today_inflow_expr = case(
                ((Transaction.type == "income") & (Transaction.transaction_date == today), Transaction.amount),
                else_=0,
            )

            tx_query = select(
                func.coalesce(func.sum(inflow_expr), 0).label("total_in"),
                func.coalesce(func.sum(outflow_expr), 0).label("total_out"),
                func.coalesce(func.sum(month_inflow_expr), 0).label("month_in"),
                func.coalesce(func.sum(month_outflow_expr), 0).label("month_out"),
                func.coalesce(func.sum(today_inflow_expr), 0).label("today_in"),
                func.count(Transaction.id).label("tx_count"),
            ).where(scope_col == scope_val)

            row = s.execute(tx_query).first()
            if row:
                tot_in = float(row.total_in or 0)
                tot_out = float(row.total_out or 0)
                m_in = float(row.month_in or 0)
                m_out = float(row.month_out or 0)
                t_in = float(row.today_in or 0)

                summary["total_revenue"] = tot_in
                summary["total_revenue_fmt"] = format_currency(tot_in)
                summary["total_expense"] = tot_out
                summary["total_expense_fmt"] = format_currency(tot_out)
                summary["net_cashflow"] = tot_in - tot_out
                summary["net_cashflow_fmt"] = format_currency(tot_in - tot_out)

                summary["month_revenue"] = m_in
                summary["month_revenue_fmt"] = format_currency(m_in)
                summary["month_expense"] = m_out
                summary["month_expense_fmt"] = format_currency(m_out)
                summary["month_net"] = m_in - m_out
                summary["month_net_fmt"] = format_currency(m_in - m_out)

                summary["today_revenue"] = t_in
                summary["today_revenue_fmt"] = format_currency(t_in)
                summary["transaction_count"] = int(row.tx_count or 0)

            # 2. Debt Balances (Receivables & Payables)
            debt_query = select(
                func.coalesce(
                    func.sum(
                        case(
                            (DebtBalance.debt_type == "receivable", DebtBalance.outstanding_balance),
                            else_=0,
                        )
                    ),
                    0,
                ).label("receivables"),
                func.coalesce(
                    func.sum(
                        case(
                            (DebtBalance.debt_type == "payable", DebtBalance.outstanding_balance),
                            else_=0,
                        )
                    ),
                    0,
                ).label("payables"),
            ).where(DebtBalance.user_id == user_id)

            debt_row = s.execute(debt_query).first()
            if debt_row:
                rec = float(debt_row.receivables or 0)
                pay = float(debt_row.payables or 0)
                summary["total_receivables"] = rec
                summary["total_receivables_fmt"] = format_currency(rec)
                summary["total_payables"] = pay
                summary["total_payables_fmt"] = format_currency(pay)

            # 3. Active SKUs Count
            inv_count = s.execute(
                select(func.count(InventoryItem.id)).where(InventoryItem.user_id == user_id)
            ).scalar() or 0

            prod_count = s.execute(
                select(func.count(Product.id)).where(Product.user_id == user_id)
            ).scalar() or 0

            summary["active_skus"] = max(inv_count, prod_count)

    except Exception as e:
        print(f"Error compiling merchant summary: {e}")

    return summary


def get_merchant_cashflow_trends(user_id: str, days: int = 30) -> dict:
    """Return daily revenue vs expense series for Chart.js visualization.

    Returns:
        {
            "labels": ["Sep 01", "Sep 02", ...],
            "dates": ["2026-09-01", ...],
            "revenue": [10000.0, 0.0, ...],
            "expense": [2500.0, 1000.0, ...],
            "net": [7500.0, -1000.0, ...]
        }
    """
    days = min(max(days, 7), 90)
    today = date.today()
    start_date = today - timedelta(days=days - 1)

    # Initialize daily bins
    date_bins = {}
    curr = start_date
    while curr <= today:
        date_bins[curr.strftime("%Y-%m-%d")] = {
            "label": curr.strftime("%b %d"),
            "revenue": 0.0,
            "expense": 0.0,
        }
        curr += timedelta(days=1)

    try:
        with session_scope() as s:
            scope_col, scope_val = _get_scope(s, user_id)

            stmt = select(
                Transaction.transaction_date,
                func.coalesce(
                    func.sum(case((Transaction.type == "income", Transaction.amount), else_=0)), 0
                ).label("day_income"),
                func.coalesce(
                    func.sum(case((Transaction.type == "expense", Transaction.amount), else_=0)), 0
                ).label("day_expense"),
            ).where(
                scope_col == scope_val,
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= today,
            ).group_by(Transaction.transaction_date)

            for row in s.execute(stmt).all():
                d_str = str(row.transaction_date)
                if d_str in date_bins:
                    date_bins[d_str]["revenue"] = float(row.day_income or 0)
                    date_bins[d_str]["expense"] = float(row.day_expense or 0)

    except Exception as e:
        print(f"Error compiling cashflow trends: {e}")

    dates = list(date_bins.keys())
    labels = [b["label"] for b in date_bins.values()]
    revenue = [b["revenue"] for b in date_bins.values()]
    expense = [b["expense"] for b in date_bins.values()]
    net = [rev - exp for rev, exp in zip(revenue, expense)]

    return {
        "labels": labels,
        "dates": dates,
        "revenue": revenue,
        "expense": expense,
        "net": net,
    }


def get_merchant_transactions(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    tx_type: str = None,
    search: str = None,
    start_date: str = None,
    end_date: str = None,
) -> tuple[list[dict], int]:
    """Retrieve filtered, paginated ledger entries for the merchant."""
    items = []
    total_count = 0

    try:
        with session_scope() as s:
            scope_col, scope_val = _get_scope(s, user_id)

            base_stmt = select(
                Transaction.id,
                Transaction.type,
                Transaction.action,
                Transaction.amount,
                Transaction.currency,
                Transaction.item,
                Transaction.description,
                Transaction.raw_text,
                Transaction.transaction_date,
                Transaction.created_at,
                func.coalesce(Category.name, "General").label("category_name"),
            ).select_from(Transaction).outerjoin(
                Category, Transaction.category_id == Category.id
            ).where(scope_col == scope_val)

            # Apply filters
            if tx_type in ("income", "expense"):
                base_stmt = base_stmt.where(Transaction.type == tx_type)

            if search:
                search_term = f"%{search.strip()}%"
                base_stmt = base_stmt.where(
                    or_(
                        Transaction.item.ilike(search_term),
                        Transaction.description.ilike(search_term),
                        Transaction.raw_text.ilike(search_term),
                        Category.name.ilike(search_term),
                    )
                )

            if start_date:
                base_stmt = base_stmt.where(Transaction.transaction_date >= start_date)
            if end_date:
                base_stmt = base_stmt.where(Transaction.transaction_date <= end_date)

            # Count total matching rows
            count_stmt = select(func.count()).select_from(base_stmt.subquery())
            total_count = s.execute(count_stmt).scalar() or 0

            # Fetch paginated rows ordered by latest date and created_at
            rows = s.execute(
                base_stmt.order_by(
                    Transaction.transaction_date.desc(),
                    Transaction.created_at.desc(),
                )
                .limit(limit)
                .offset(offset)
            ).all()

            for r in rows:
                amt = float(r.amount or 0)
                items.append({
                    "id": str(r.id),
                    "type": r.type,
                    "action": r.action or "other",
                    "amount": amt,
                    "amount_formatted": format_currency(amt, r.currency or "NGN"),
                    "currency": r.currency or "NGN",
                    "item": r.item or "",
                    "description": r.description or r.raw_text or "",
                    "category": r.category_name,
                    "transaction_date": str(r.transaction_date),
                    "created_at": r.created_at.strftime("%b %d, %H:%M") if r.created_at else str(r.transaction_date),
                })

    except Exception as e:
        print(f"Error querying merchant transactions: {e}")

    return items, total_count


def get_recent_merchant_transactions(user_id: str, limit: int = 5) -> list[dict]:
    """Retrieve the most recent N transactions for dashboard preview."""
    txs, _ = get_merchant_transactions(user_id, limit=limit, offset=0)
    return txs
