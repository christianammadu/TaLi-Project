"""Merchant Statement Exporter & Generator (WP-10).

Provides query scoping, period resolution, preview calculations, and multi-format
export (Branded PDF, Excel XLSX, and CSV) for merchant transaction records.
"""

from calendar import monthrange
import csv
from datetime import date, datetime, timedelta
import io
import json
import os
import re
import shutil
from typing import Any, Dict, List, Optional, Tuple

from app.data.models import User
from app.data.queries import query_opening_balance, query_statement
from app.services.formatter import format_currency
from app.services.report_renderer import render


def resolve_period_dates(
    period: str = "this_month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], str]:
    """Resolve start_date, end_date (ISO format YYYY-MM-DD or None) and human label.

    Supported period values:
    - 'this_month': 1st of current month to current day.
    - 'last_month': 1st of previous month to last day of previous month.
    - 'last_90_days' / '90d': 90 days ago to current day.
    - 'all_time': None, None ("All Time").
    - 'custom': parsed custom_start to custom_end.
    """
    today = date.today()
    p = (period or "this_month").lower().strip()

    if p == "this_month":
        start = date(today.year, today.month, 1)
        end = today
        label = f"This Month ({today.strftime('%B %Y')})"
        return start.isoformat(), end.isoformat(), label

    elif p == "last_month":
        first_of_this_month = date(today.year, today.month, 1)
        last_of_prev_month = first_of_this_month - timedelta(days=1)
        start_of_prev_month = date(last_of_prev_month.year, last_of_prev_month.month, 1)
        label = f"Last Month ({last_of_prev_month.strftime('%B %Y')})"
        return start_of_prev_month.isoformat(), last_of_prev_month.isoformat(), label

    elif p in ("last_90_days", "90d"):
        start = today - timedelta(days=90)
        end = today
        label = f"Last 90 Days ({start.strftime('%d %b')} – {end.strftime('%d %b %Y')})"
        return start.isoformat(), end.isoformat(), label

    elif p == "all_time":
        return None, None, "All Time"

    elif p == "custom":
        try:
            d_start = date.fromisoformat(str(custom_start).strip())
            d_end = date.fromisoformat(str(custom_end).strip())
            if d_start > d_end:
                d_start, d_end = d_end, d_start
            label = f"{d_start.strftime('%d %b %Y')} – {d_end.strftime('%d %b %Y')}"
            return d_start.isoformat(), d_end.isoformat(), label
        except (ValueError, TypeError, AttributeError):
            return resolve_period_dates("this_month")

    # Default fallback
    start = date(today.year, today.month, 1)
    end = today
    return start.isoformat(), end.isoformat(), f"This Month ({today.strftime('%B %Y')})"


def get_merchant_business_name(user_id: str, default_name: str = "TaLi Merchant") -> str:
    """Retrieve the business or display name for a merchant user."""
    from app.data.db import session_scope
    try:
        with session_scope() as s:
            user = s.get(User, user_id)
            if user:
                if user.business_profile:
                    profile = user.business_profile
                    if isinstance(profile, str):
                        try:
                            profile = json.loads(profile)
                        except Exception:
                            profile = {}
                    if isinstance(profile, dict):
                        bname = profile.get("name") or profile.get("business_name")
                        if bname:
                            return str(bname).strip()
                if user.display_name:
                    return str(user.display_name).strip()
    except Exception as e:
        print(f"[get_merchant_business_name] Error: {e}")
    return default_name


def get_statement_transactions(
    user_id: str,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    tx_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve filtered transaction rows for statement generation."""
    filters = {}
    if period_start:
        filters["period_start"] = period_start
    if period_end:
        filters["period_end"] = period_end
    if tx_type and tx_type != "all":
        filters["tx_type"] = tx_type

    rows = query_statement(user_id, filters)
    return rows if rows is not None else []


def get_statement_summary(
    user_id: str,
    period: str = "this_month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    tx_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate summary statistics and return preview rows for the statement view."""
    start_date, end_date, period_label = resolve_period_dates(period, custom_start, custom_end)
    raw_rows = get_statement_transactions(user_id, start_date, end_date, tx_type)

    total_inflow = 0.0
    total_outflow = 0.0
    currency = "NGN"

    for r in raw_rows:
        amt = float(r.get("amount") or 0)
        c = r.get("currency") or "NGN"
        if c:
            currency = c
        if r.get("type") == "income":
            total_inflow += amt
        else:
            total_outflow += amt

    net_movement = total_inflow - total_outflow

    # Opening balance if start_date is set
    opening_balances = query_opening_balance(user_id, start_date) if start_date else {}
    opening_bal = (
        float(opening_balances.get(currency, 0.0))
        if isinstance(opening_balances, dict)
        else 0.0
    )
    closing_bal = opening_bal + net_movement

    # Format rows for preview presentation
    formatted_rows = []
    for r in raw_rows:
        amt = float(r.get("amount") or 0)
        c = r.get("currency") or currency
        is_in = r.get("type") == "income"
        formatted_rows.append({
            "date": str(r.get("date", ""))[:10],
            "type": r.get("type", ""),
            "action": r.get("action", ""),
            "item": r.get("item") or "",
            "category": r.get("category") or "Miscellaneous",
            "amount": amt,
            "currency": c,
            "amount_formatted": format_currency(amt, c),
            "is_income": is_in,
            "description": r.get("item") or (r.get("action") or "").title() or "Transaction",
        })

    return {
        "period": period,
        "start_date": start_date or "",
        "end_date": end_date or "",
        "custom_start": custom_start or (start_date if period == "custom" else ""),
        "custom_end": custom_end or (end_date if period == "custom" else ""),
        "period_label": period_label,
        "total_inflow": total_inflow,
        "total_inflow_fmt": format_currency(total_inflow, currency),
        "total_outflow": total_outflow,
        "total_outflow_fmt": format_currency(total_outflow, currency),
        "net_movement": net_movement,
        "net_movement_fmt": format_currency(net_movement, currency),
        "opening_balance": opening_bal,
        "opening_balance_fmt": format_currency(opening_bal, currency),
        "closing_balance": closing_bal,
        "closing_balance_fmt": format_currency(closing_bal, currency),
        "transaction_count": len(raw_rows),
        "currency": currency,
        "rows": formatted_rows,
        "has_rows": len(raw_rows) > 0,
    }


def _safe_slug(text: str) -> str:
    """Create a URL/filename-safe string."""
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_") or "report"


def export_statement_csv(
    user_id: str,
    period: str = "this_month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    business_name: str = "Merchant",
) -> Tuple[str, str]:
    """Generate a clean CSV export for merchant transactions.

    Returns:
        (csv_string_content, suggested_filename)
    """
    start_date, end_date, period_label = resolve_period_dates(period, custom_start, custom_end)
    rows = get_statement_transactions(user_id, start_date, end_date)

    output = io.StringIO()
    writer = csv.writer(output)

    # Standard ledger header
    writer.writerow([
        "Date",
        "Description",
        "Category",
        "Type",
        "Action",
        "Money In",
        "Money Out",
        "Amount",
        "Currency",
    ])

    for r in rows:
        amt = float(r.get("amount") or 0)
        is_in = r.get("type") == "income"
        desc = r.get("item") or (r.get("action") or "").title() or "Transaction"
        writer.writerow([
            str(r.get("date", ""))[:10],
            desc,
            r.get("category", "Miscellaneous"),
            (r.get("type") or "").title(),
            r.get("action", ""),
            f"{amt:.2f}" if is_in else "",
            f"{amt:.2f}" if not is_in else "",
            f"{amt:.2f}",
            r.get("currency", "NGN"),
        ])

    csv_content = output.getvalue()
    slug_biz = _safe_slug(business_name)
    slug_period = _safe_slug(period if period != "custom" else f"{start_date}_to_{end_date}")
    filename = f"tali_statement_{slug_biz}_{slug_period}.csv"
    return csv_content, filename


def export_statement_pdf(
    user_id: str,
    period: str = "this_month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    business_name: str = "Merchant",
) -> Tuple[bytes, str]:
    """Generate a branded PDF statement using ReportLab renderer.

    Returns:
        (pdf_bytes, suggested_filename)
    """
    start_date, end_date, period_label = resolve_period_dates(period, custom_start, custom_end)
    rows = get_statement_transactions(user_id, start_date, end_date)
    opening = query_opening_balance(user_id, start_date) if start_date else {}

    meta = {
        "title": "Statement of Account",
        "business_name": business_name,
        "subtitle": period_label,
        "opening_balance": opening,
    }

    try:
        files = render("transactions", rows, meta, fmt="pdf")
        if not files or not os.path.exists(files[0]["path"]):
            raise RuntimeError("PDF rendering produced no output file.")

        pdf_path = files[0]["path"]
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        slug_biz = _safe_slug(business_name)
        slug_period = _safe_slug(period if period != "custom" else f"{start_date}_to_{end_date}")
        filename = f"tali_statement_{slug_biz}_{slug_period}.pdf"
        return pdf_bytes, filename
    finally:
        tmpdir = meta.get("tmpdir")
        if tmpdir and os.path.isdir(tmpdir):
            shutil.rmtree(tmpdir, ignore_errors=True)


def export_statement_excel(
    user_id: str,
    period: str = "this_month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    business_name: str = "Merchant",
) -> Tuple[bytes, str]:
    """Generate a branded Excel workbook statement using openpyxl renderer.

    Returns:
        (xlsx_bytes, suggested_filename)
    """
    start_date, end_date, period_label = resolve_period_dates(period, custom_start, custom_end)
    rows = get_statement_transactions(user_id, start_date, end_date)
    opening = query_opening_balance(user_id, start_date) if start_date else {}

    meta = {
        "title": "Statement of Account",
        "business_name": business_name,
        "subtitle": period_label,
        "opening_balance": opening,
    }

    try:
        files = render("transactions", rows, meta, fmt="xlsx")
        if not files or not os.path.exists(files[0]["path"]):
            raise RuntimeError("Excel rendering produced no output file.")

        xlsx_path = files[0]["path"]
        with open(xlsx_path, "rb") as f:
            xlsx_bytes = f.read()

        slug_biz = _safe_slug(business_name)
        slug_period = _safe_slug(period if period != "custom" else f"{start_date}_to_{end_date}")
        filename = f"tali_statement_{slug_biz}_{slug_period}.xlsx"
        return xlsx_bytes, filename
    finally:
        tmpdir = meta.get("tmpdir")
        if tmpdir and os.path.isdir(tmpdir):
            shutil.rmtree(tmpdir, ignore_errors=True)
