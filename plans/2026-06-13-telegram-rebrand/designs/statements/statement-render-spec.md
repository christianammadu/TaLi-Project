# TaLi statement render spec — PDF + Excel (for `report_renderer.py`)

How the agent should render branded, accounting-correct documents. Targets the existing
**`app/services/report_renderer.py`** (ReportLab for PDF, openpyxl for Excel) +
**`app/agents/statement_agent.py`**. Mockups: `statement-pdf-design.html`,
`statement-excel-design.html`. Brand tokens: `../brand-spec.md` (D-01, `G-BRAND`).

Three statement types, one engine:
1. **Income Statement (P&L)** — the "accounting statement".
2. **Statement of Account** — the transactions ledger (Money in / Money out / running Balance).
3. **Cashflow Statement** — direct method (opening → in → out → closing).

---

## Brand → print adaptation (important)

The web brand uses warm paper `#FBF7EF`; **documents use WHITE paper** for legibility, ink
saving, and scan/print fidelity. Terracotta is kept only for the **header rule, section
underlines, total rules, and the wordmark dot**. So the document palette is:

```
ink        #241F1A   body text
soft       #6B6258   labels / captions
accent     #C2562F   header rule · section heads · total rules · wordmark dot
line       #D9D2C6   table rules
line_soft  #ECE6DB   row separators / zebra (#FCFAF6)
pos/in     #1E7A45   net-positive figures (sparingly)
neg/out    #B23A2E   negatives / money-out (sparingly)
band       #FBF7EF   table header fill only
```

## Fonts (ReportLab)

Embed the brand fonts as TTFs (download to `app/static/fonts/`):
```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
pdfmetrics.registerFont(TTFont("Fraunces", "app/static/fonts/Fraunces-SemiBold.ttf"))   # display/headers
pdfmetrics.registerFont(TTFont("Hanken",   "app/static/fonts/HankenGrotesk-Regular.ttf"))# body
pdfmetrics.registerFont(TTFont("Hanken-SB","app/static/fonts/HankenGrotesk-SemiBold.ttf"))
```
**Fallback (no TTFs bundled):** `Times-Bold` for headers, `Helvetica`/`Helvetica-Bold` for body.
Numbers always use tabular figures (Hanken/Helvetica are fine; right-align money columns).

## PDF layout (ReportLab)

- **Page:** A4 portrait (`A4`), margins 18mm (≈ 51pt) all sides.
- **Letterhead** (every page): wordmark `TaLi.` (Fraunces 30pt, terracotta dot) + tagline
  "Bookkeeping in your chat" (Hanken 9pt, uppercase, soft) top-left; doc title (Fraunces 18pt) +
  period + "Generated <date>" top-right. A **2pt terracotta rule** under the letterhead.
- **Business strip:** business name (Fraunces 14pt) + address (soft) left; currency + "Prepared by
  TaLi" right.
- **Section:** heading in Fraunces 14pt, terracotta, uppercase, with a 1px bottom rule. Line items
  in a 2-col layout (label left, amount right-aligned); indented sub-items in soft grey.
- **Subtotal:** top hairline + bold. **Total:** 1.5pt ink top rule + bold 15pt. **Grand total**
  (Net profit / Closing balance): 2pt terracotta top rule + 2px double-rule bottom, Fraunces 17pt,
  value in `pos` green.
- **Statement of Account table:** columns `Date · Description · Cat. · Money in · Money out ·
  Balance`. Header row: uppercase 10.5pt soft on `band` fill, 1.5pt ink bottom rule. Zebra rows
  `#FCFAF6`. `tfoot` totals row with 1.5pt top rule. Money columns right-aligned, tabular.
- **Footer** (every page, fixed bottom): left = "TaLi · <doc> · <business>", center = terracotta
  "Every entry validated & auditable", right = "Page X of Y". 1px top rule.
- **Number format:** `₦` + thousands sep + 2dp; negatives in parentheses (and `neg` red in tables):
  `format_money(-98000) -> "(₦98,000.00)"`.

### Accounting rules (compute, don't hand-wave)
- **COGS** = opening stock + purchases − closing stock.
- **Gross profit** = total revenue − COGS.
- **Net profit** = gross profit − total operating expenses.
- **Cashflow (direct):** closing = opening + total cash in − total cash out; running balance per row.
- **Statement of Account:** balance carries forward row to row (opening balance is row 1).

## Excel layout (openpyxl)

Workbook `<business>_<period>.xlsx`. Sheets: **Summary** (P&L), **Transactions** (ledger);
optional **Debtors**, **Stock**.

- **Header row** (Transactions): `Date · Description · Category · Type · Money in · Money out ·
  Balance`. Bold white on fill `#1E6E43`; `ws.freeze_panes = "A2"`; `ws.auto_filter.ref = "A1:G1"`.
- **Number format:** money cells `'"₦"#,##0.00'`; negatives `'"₦"#,##0.00;[Red]("₦"#,##0.00)'`.
  Dates `yyyy-mm-dd`. Right-align money columns.
- **Column widths:** Date 12 · Description 40 · Category 16 · Type 10 · money columns ≥ 14.
- **Totals row:** real formulas, not pasted values — `=SUM(E2:E<n>)`, `=SUM(F2:F<n>)`; bold, top
  border (`Border(top=Side(style="thin"))`).
- **Summary sheet:** the Income Statement in cells (col A labels, col B amounts). Section headers
  (`Revenue`, `Cost of goods sold`, `Operating expenses`) bold; `Total revenue` / `Gross profit` /
  `Net profit` bold with top border; `Net profit` gets the accent fill `#EAF3EC`. Indent detail
  rows with a leading two spaces or `alignment=Alignment(indent=1)`.
- **Type colouring (optional):** income green `#1E7A45`, expense red `#B23A2E` font on the Type cell.

## Data sources (reuse existing queries)

- Transactions / Money in/out / running balance → `transactions` (+ `records`), by `user_id` + period.
- Revenue / purchases / expenses split → `transactions.type` + `category`.
- Opening/closing stock → `inventory_movements` valuation (or flagged "stock not valued" if absent).
- Debtors → `debt_balances`. The `statement_agent` already resolves period + filters; this spec
  only changes **rendering**, not the data layer.

## Plug-in points
- `report_renderer.py`: add `render_income_statement(...)`, `render_statement_of_account(...)`,
  `render_cashflow(...)` (PDF) + `build_workbook(...)` (Excel) using the styles above; centralise
  `format_money()` + a `Brand` constants block (mirror the tokens here).
- `statement_agent.py`: route `report_type` (`transactions` | `cashflow` | `income_statement`) +
  `format` (`pdf` | `xlsx` | `both`) to the right renderer. (Income-statement is a **new**
  `report_type` to add to the NLP schema in `nlp.py`.)

## Maps to plan
Becomes **WP-10** (brand the generated statements) on the rebrand track — depends on **WP-06**
(brand tokens) for the shared `Brand` constants + fonts. Caveat: bundle the two TTFs, or ship the
Helvetica/Times fallback.
