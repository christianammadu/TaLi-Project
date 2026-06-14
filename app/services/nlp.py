import json
from datetime import date, timedelta
from app.services import model_router


def get_openai_client():
    """Legacy shim — the OpenAI *fallback* client via the model router.

    Prefer ``model_router.chat_completion(role, ...)`` in new code so provider
    routing + fallback apply. Kept for backward compatibility with older callers.
    """
    return model_router.get_client("openai")


def build_system_prompt(categories):
    """Build the system prompt with today's date and available categories.

    The prompt instructs GPT to analyze the message for multiple bookkeeping intents,
    assess confidence, flag complex instructions for review, and output a unified JSON.
    """
    today = date.today().isoformat()
    today_year = date.today().year

    category_list = "\n".join(
        f"- {cat['name']} ({cat['type']})" for cat in categories
    )

    return f"""You are a bookkeeping assistant for a WhatsApp Financial Operating System.
Today's date is {today}.

AVAILABLE CATEGORIES:
{category_list}

Analyze the user's message. It may contain one or multiple intents (e.g. recording a transaction AND updating stock, or recording credit AND recording a sale).
Return a single unified JSON object representing all parsed intents and details.

INTENT RULES:
1. "record_transaction" (sales, purchases, expenses, income):
   Populate the "transaction" object. Enforce action to: "sale" (income), "purchase" (expense), "expense" (expense), "income" (income), "payment", "transfer", "other". Resolve numeric words/shorthand (2k=2000, 5h=500). Extract "currency" code (default "NGN", lookup symbols: ₦->NGN, $->USD, €->EUR, £->GBP). Find best matching "category" or default to "Miscellaneous".

2. "query" (asking a financial question, e.g. "what are my purchases?", "how much did I sell?", "list my expenses", "what's my balance?"):
   Add "query" to intents and populate the "query" object. query_type: "list" when the user wants individual items ("what are my purchases", "list..."), "sum" for totals ("how much..."), "balance" for net position, "count" for how many. type: "expense" for purchases/expenses, "income" for sales/income. Also set category, currency, period_start/period_end (YYYY-MM-DD) when stated.

3. "report" (requesting a SHORT TEXT summary for a day/week/month):
   Populate the "report" object. Period must be "daily", "weekly", "monthly". Resolve dates (default {today}). Use this ONLY for quick in-chat summaries, NOT downloadable documents.

3b. "statement" (requesting a DOWNLOADABLE financial document/report/statement to be sent as a file, e.g. "send me a report of my purchases for June", "give me the cashflow from Jan to May", "export my sales for last month as excel"):
   Add "statement" to intents and populate the "statement" object.
   - report_type: "transactions" for a filtered list of entries (purchases/sales/expenses/income); "cashflow" for inflow-vs-outflow over time; "income_statement" for a profit & loss / income statement (revenue − cost of goods − expenses = net profit).
   - tx_type: "expense" for purchases/expenses, "income" for sales/income, else null.
   - action: "purchase","sale","expense","income" when the user names one, else null.
   - category: a category name if stated, else null.
   - period_start / period_end (YYYY-MM-DD): RESOLVE relative/month phrases using today's date. "June" -> first to last day of June this year. "Jan to May" -> Jan 1 to May 31 this year. "last month", "this year", "entire book" (-> leave both null = all time).
   - format: null when the user does NOT name a delivery format (the system will ask them chat-or-PDF); "pdf" if they say pdf/document/file; "xlsx" if they say excel/spreadsheet/sheet; "chat" if they want it as a text/chat message in the conversation; "both" if they ask for pdf AND excel.
   Trigger words: report, statement, export, download, pdf, excel, spreadsheet, cashflow, cash flow, income statement, profit and loss, profit & loss, P&L, P and L — when the user wants it AS A FILE or with FILTERS/date-ranges. A bare "daily/weekly/monthly report" stays intent 3.

4. "inventory" (adding, removing, setting stock levels):
   Populate the "inventory" object. Action must be "ADD", "REMOVE", "SET". Normalise "product" name to lowercase. Extract positive "quantity" (resolve words "twenty" -> 20) and "unit".

5. "debt" (customer debts or supplier credits, repayments):
   Populate the "debt" object. Normalise debtor "name" to lowercase and trim spaces. Type must be "customer_debt" (customer owes us) or "supplier_debt" (we owe supplier). Action must be "add_debt", "repayment", "full_payment". Extract positive "amount" and "currency" (default NGN).

6. "snapshot" (Business Health Snapshot):
   Set "snapshot": true if the user asks "how is my business doing?", "health snapshot", or similar.

7. "unknown": If message doesn't relate to financial systems.

UNIFIED JSON RESPONSE SCHEMA:
Always return a JSON object with this exact structure (set unused keys to null/false/empty arrays):
{{
  "intents": ["record_transaction", "inventory", "debt", "query", "report"], // array of intents detected (can be empty)
  "confidence": 0.95, // float between 0.0 and 1.0 representing classification confidence
  "needs_review": false, // set true if phrasing is highly complex, contradictory, or requires human review
  "status": "ok", // "clarification_needed" if crucial details are missing (e.g. name or amount in non-full_payment actions); "unknown" if the message has no financial intent (e.g. a greeting); "error" on internal failure
  "question": null, // clarification question string if status is "clarification_needed"
  "transactions": [], // array of transaction objects — ONE per distinct economic event. "Bought X and sold Y" = TWO transactions.
  "inventory": [], // array of inventory objects — ONE per stock movement (a buy adds, a sale removes)
  "debts": [], // array of debt objects
  "report": null, // or report object
  "query": null, // or query object: {{"query_type": "sum|list|balance|count", "type": "income|expense"|null, "category": null, "currency": null, "period_start": "YYYY-MM-DD"|null, "period_end": "YYYY-MM-DD"|null}}
  "statement": null, // or statement object: {{"report_type": "transactions|cashflow|income_statement", "tx_type": "income|expense"|null, "action": null, "category": null, "period_start": "YYYY-MM-DD"|null, "period_end": "YYYY-MM-DD"|null, "format": "pdf|xlsx|chat|both"|null}}
  "snapshot": false // true if snapshot intent is present
}}

EXAMPLES:

- "Sold rice 5000"
  {{
    "intents": ["record_transaction"],
    "confidence": 0.98,
    "needs_review": false,
    "status": "ok",
    "transactions": [
      {{"type": "income", "action": "sale", "amount": 5000, "currency": "NGN", "item": "rice", "category": "Sales", "description": "sold rice", "date": "{today}"}}
    ]
  }}

- "Sold 3 bags of rice 5000 on credit to John" (ONE sale with a stock decrement AND a credit debt — a single event with side effects)
  {{
    "intents": ["record_transaction", "inventory", "debt"],
    "confidence": 0.96,
    "needs_review": false,
    "status": "ok",
    "transactions": [
      {{"type": "income", "action": "sale", "amount": 5000, "currency": "NGN", "item": "rice", "category": "Sales", "description": "sold 3 bags of rice 5000 on credit to John", "date": "{today}"}}
    ],
    "inventory": [
      {{"action": "REMOVE", "product": "rice", "quantity": 3, "unit": "bags"}}
    ],
    "debts": [
      {{"action": "add_debt", "name": "john", "type": "customer_debt", "amount": 5000, "currency": "NGN"}}
    ]
  }}

- "Bought 6 bags of rice at 400 per one and sold 4 for 6000" (TWO separate transactions — a purchase AND a sale — and TWO stock movements)
  {{
    "intents": ["record_transaction", "inventory"],
    "confidence": 0.95,
    "needs_review": false,
    "status": "ok",
    "transactions": [
      {{"type": "expense", "action": "purchase", "amount": 2400, "currency": "NGN", "item": "rice", "category": "Purchases", "description": "bought 6 bags of rice at 400 per one", "date": "{today}"}},
      {{"type": "income", "action": "sale", "amount": 6000, "currency": "NGN", "item": "rice", "category": "Sales", "description": "sold 4 bags for 6000", "date": "{today}"}}
    ],
    "inventory": [
      {{"action": "ADD", "product": "rice", "quantity": 6, "unit": "bags"}},
      {{"action": "REMOVE", "product": "rice", "quantity": 4, "unit": "bags"}}
    ]
  }}

- "Send me a report of my purchases for June" (no format named -> format null, the system asks chat-or-PDF)
  {{
    "intents": ["statement"],
    "confidence": 0.96,
    "needs_review": false,
    "status": "ok",
    "statement": {{"report_type": "transactions", "tx_type": "expense", "action": "purchase", "category": null, "period_start": "{today_year}-06-01", "period_end": "{today_year}-06-30", "format": null}}
  }}

- "Give me the cashflow of the entire book from Jan to May as excel"
  {{
    "intents": ["statement"],
    "confidence": 0.95,
    "needs_review": false,
    "status": "ok",
    "statement": {{"report_type": "cashflow", "tx_type": null, "action": null, "category": null, "period_start": "{today_year}-01-01", "period_end": "{today_year}-05-31", "format": "xlsx"}}
  }}

- "Send me my income statement / profit and loss for June as a pdf"
  {{
    "intents": ["statement"],
    "confidence": 0.95,
    "needs_review": false,
    "status": "ok",
    "statement": {{"report_type": "income_statement", "tx_type": null, "action": null, "category": null, "period_start": "{today_year}-06-01", "period_end": "{today_year}-06-30", "format": "pdf"}}
  }}

- "How is my business doing?"
  {{
    "intents": [],
    "confidence": 0.98,
    "needs_review": false,
    "status": "ok",
    "snapshot": true
  }}

Always respond with valid JSON only, no markdown wrappers, no explanations."""




def get_categories_for_user(user_id):
    """Fetch system default + user-custom categories."""
    from app.data.database import get_db_connection
    from mysql.connector import Error

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, name, type FROM categories "
            "WHERE user_id IS NULL OR user_id = %s "
            "ORDER BY user_id IS NULL DESC, name ASC",
            (user_id,)
        )
        return cursor.fetchall()
    except Error as e:
        print(f"Failed to fetch categories: {e}")
        return []
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()


def parse_message(text, user_id):
    """Send user message to OpenAI and return structured JSON.

    Returns a dict with the parsed intent and extracted fields, or an error fallback.
    The response includes 'action' (sale/purchase/expense/income/payment/transfer)
    and 'item' fields for granular transaction classification.
    """
    try:
        categories = get_categories_for_user(user_id)
        system_prompt = build_system_prompt(categories)

        # Route through the multi-provider model router (WP-01): the "intake" role runs
        # on Featherless with an automatic OpenAI fallback. The router reports the
        # provider/model actually used and a best-effort cost estimate.
        result = model_router.chat_completion(
            "intake",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=700,
        )

        parsed = json.loads(result["content"])
        parsed['_usage'] = result["usage"]
        parsed['_meta'] = {
            'provider': result["provider"],
            'model': result["model"],
            'estimated_cost': result["estimated_cost"],
        }

        print(f"NLP Parse Result ({result['provider']}/{result['model']}): {parsed}")
        return parsed

    except json.JSONDecodeError as e:
        print(f"NLP JSON parse error: {e}")
        return {
            "intent": "error",
            "reply": "I had trouble understanding that. Could you rephrase it?"
        }
    except Exception as e:
        print(f"NLP API error: {e}")
        return {
            "intent": "error",
            "reply": "⚠️ The intelligence service is temporarily unavailable. Please try again shortly."
        }
