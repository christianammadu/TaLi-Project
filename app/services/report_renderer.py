"""Render financial statements as PDF (ReportLab) or spreadsheet (openpyxl).

Pure rendering: takes already-queried data + metadata, writes a file into a temp
directory, and returns file descriptors. The caller is responsible for delivering
the files and deleting ``meta['tmpdir']`` afterwards.

Two report kinds are supported:
  * ``transactions`` — a filtered ledger (Date, Type, Action, Item, Category, Amount),
    grouped per currency with totals.
  * ``cashflow`` — monthly inflow/outflow/net/cumulative, grouped per currency.

Both are pure-Python deps (reportlab, openpyxl) so they install on the
PythonAnywhere free tier with no system libraries.
"""

import os
import re
import tempfile
from datetime import datetime

from app.services.formatter import format_currency

PDF_MIME = "application/pdf"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _slug(text):
    return re.sub(r'[^A-Za-z0-9]+', '_', text).strip('_') or 'statement'


def _tmpdir(meta):
    """Return (creating once) a temp dir stored on meta for the caller to clean up."""
    if not meta.get('tmpdir'):
        meta['tmpdir'] = tempfile.mkdtemp(prefix='tali_report_')
    return meta['tmpdir']


def render(kind, data, meta, fmt='pdf'):
    """Render the requested format(s) and return a list of file descriptors.

    Each descriptor is {'path', 'filename', 'mime'}. ``fmt`` is 'pdf' | 'xlsx' | 'both'.
    """
    formats = ['pdf', 'xlsx'] if fmt == 'both' else [fmt]
    files = []
    for f in formats:
        if f == 'xlsx':
            files.append(_render_xlsx(kind, data, meta))
        else:
            files.append(_render_pdf(kind, data, meta))
    return files


# --------------------------------------------------------------------------- PDF

def _render_pdf(kind, data, meta):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    )

    tmpdir = _tmpdir(meta)
    path = os.path.join(tmpdir, _slug(meta['title']) + '.pdf')

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle('h1', parent=styles['Title'], fontSize=16, spaceAfter=2)
    sub = ParagraphStyle('sub', parent=styles['Normal'], fontSize=9, textColor=colors.grey)
    sect = ParagraphStyle('sect', parent=styles['Heading2'], fontSize=11, spaceBefore=10, spaceAfter=4)

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=14 * mm, rightMargin=14 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=meta['title'],
    )
    elems = [
        Paragraph(meta.get('business_name') or 'TaLi', h1),
        Paragraph(meta['title'], styles['Heading3']),
        Paragraph(meta.get('subtitle', ''), sub),
        Paragraph(f"Generated {datetime.now().strftime('%b %d, %Y %H:%M')}", sub),
        Spacer(1, 6),
    ]

    header_bg = colors.HexColor('#1f6f54')
    base_style = [
        ('BACKGROUND', (0, 0), (-1, 0), header_bg),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#eef5f2')]),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#cccccc')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]

    if kind == 'cashflow':
        for currency, rows in sorted(data.items()):
            elems.append(Paragraph(f"Cashflow — {currency}", sect))
            table_data = [['Month', 'Inflow', 'Outflow', 'Net', 'Cumulative']]
            tot_in = tot_out = 0.0
            for r in rows:
                tot_in += r['inflow']
                tot_out += r['outflow']
                table_data.append([
                    r['month'],
                    format_currency(r['inflow'], currency),
                    format_currency(r['outflow'], currency),
                    format_currency(r['net'], currency),
                    format_currency(r['cumulative'], currency),
                ])
            table_data.append([
                'TOTAL',
                format_currency(tot_in, currency),
                format_currency(tot_out, currency),
                format_currency(tot_in - tot_out, currency),
                '',
            ])
            elems.append(_money_table(table_data, base_style, colors, money_cols=(1, 2, 3, 4)))
            elems.append(Spacer(1, 6))
    else:  # transactions
        by_cur = _group_rows_by_currency(data)
        for currency, rows in sorted(by_cur.items()):
            elems.append(Paragraph(f"Transactions — {currency}", sect))
            table_data = [['Date', 'Type', 'Action', 'Item', 'Category', 'Amount']]
            income = expense = 0.0
            for r in rows:
                amt = r['amount']
                if r['type'] == 'income':
                    income += amt
                else:
                    expense += amt
                table_data.append([
                    r['date'], (r['type'] or '').title(), (r.get('action') or '').title(),
                    (r.get('item') or '—')[:24], (r.get('category') or '—')[:18],
                    format_currency(amt, currency),
                ])
            table_data.append(['', '', '', '', 'Income', format_currency(income, currency)])
            table_data.append(['', '', '', '', 'Expenses', format_currency(expense, currency)])
            table_data.append(['', '', '', '', 'Net', format_currency(income - expense, currency)])
            elems.append(_money_table(table_data, base_style, colors, money_cols=(5,), total_rows=3))
            elems.append(Spacer(1, 6))

        if not by_cur:
            elems.append(Paragraph("No records found for this period.", styles['Normal']))

    brand = meta.get('business_name') or 'TaLi'

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#cccccc'))
        canvas.setLineWidth(0.4)
        canvas.line(14 * mm, 13 * mm, A4[0] - 14 * mm, 13 * mm)
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(14 * mm, 9 * mm, f"{brand} · generated by TaLi")
        canvas.drawRightString(A4[0] - 14 * mm, 9 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(elems, onFirstPage=_footer, onLaterPages=_footer)
    return {'path': path, 'filename': os.path.basename(path), 'mime': PDF_MIME}


def _money_table(table_data, base_style, colors, money_cols=(), total_rows=1, repeat=True):
    from reportlab.platypus import Table, TableStyle
    t = Table(table_data, repeatRows=1 if repeat else 0)
    style = list(base_style)
    # right-align money columns
    for c in money_cols:
        style.append(('ALIGN', (c, 0), (c, -1), 'RIGHT'))
    # emphasise the trailing total row(s)
    for i in range(1, total_rows + 1):
        style.append(('FONTNAME', (0, -i), (-1, -i), 'Helvetica-Bold'))
        style.append(('LINEABOVE', (0, -i), (-1, -i), 0.5, colors.HexColor('#1f6f54')))
    t.setStyle(TableStyle(style))
    return t


# -------------------------------------------------------------------------- XLSX

def _render_xlsx(kind, data, meta):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    tmpdir = _tmpdir(meta)
    path = os.path.join(tmpdir, _slug(meta['title']) + '.xlsx')

    wb = Workbook()
    wb.remove(wb.active)

    header_fill = PatternFill('solid', fgColor='1F6F54')
    header_font = Font(color='FFFFFF', bold=True)
    bold = Font(bold=True)
    money_fmt = '#,##0.00'
    thin = Side(style='thin', color='CCCCCC')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def style_header(ws, ncols):
        for c in range(1, ncols + 1):
            cell = ws.cell(row=1, column=c)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')
            cell.border = border
        ws.freeze_panes = 'A2'

    if kind == 'cashflow':
        for currency, rows in sorted(data.items()):
            ws = wb.create_sheet(title=f"Cashflow {currency}"[:31])
            ws.append(['Month', 'Inflow', 'Outflow', 'Net', 'Cumulative'])
            style_header(ws, 5)
            tot_in = tot_out = 0.0
            for r in rows:
                tot_in += r['inflow']
                tot_out += r['outflow']
                ws.append([r['month'], r['inflow'], r['outflow'], r['net'], r['cumulative']])
            ws.append(['TOTAL', tot_in, tot_out, tot_in - tot_out, None])
            _finish_sheet(ws, money_cols=(2, 3, 4, 5), money_fmt=money_fmt, bold=bold)
    else:
        by_cur = _group_rows_by_currency(data)
        for currency, rows in sorted(by_cur.items()):
            ws = wb.create_sheet(title=f"Transactions {currency}"[:31])
            ws.append(['Date', 'Type', 'Action', 'Item', 'Category', f'Amount ({currency})'])
            style_header(ws, 6)
            income = expense = 0.0
            for r in rows:
                if r['type'] == 'income':
                    income += r['amount']
                else:
                    expense += r['amount']
                ws.append([
                    r['date'], (r['type'] or '').title(), (r.get('action') or '').title(),
                    r.get('item') or '', r.get('category') or '', r['amount'],
                ])
            ws.append([None, None, None, None, 'Income', income])
            ws.append([None, None, None, None, 'Expenses', expense])
            ws.append([None, None, None, None, 'Net', income - expense])
            _finish_sheet(ws, money_cols=(6,), money_fmt=money_fmt, bold=bold, total_rows=3)
        if not by_cur:
            ws = wb.create_sheet(title='Statement')
            ws.append(['No records found for this period.'])

    wb.save(path)
    return {'path': path, 'filename': os.path.basename(path), 'mime': XLSX_MIME}


def _finish_sheet(ws, money_cols, money_fmt, bold, total_rows=1):
    max_row = ws.max_row
    for col in money_cols:
        for row in range(2, max_row + 1):
            ws.cell(row=row, column=col).number_format = money_fmt
    for i in range(total_rows):
        for cell in ws[max_row - i]:
            cell.font = bold
    # auto-ish column widths
    for col_cells in ws.columns:
        width = max((len(str(c.value)) for c in col_cells if c.value is not None), default=8)
        ws.column_dimensions[col_cells[0].column_letter].width = min(max(width + 2, 10), 40)


# ------------------------------------------------------------------------- utils

def _group_rows_by_currency(rows):
    by_cur = {}
    for r in rows or []:
        by_cur.setdefault(r.get('currency') or 'NGN', []).append(r)
    return by_cur
