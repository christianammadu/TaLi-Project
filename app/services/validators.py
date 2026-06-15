"""Validation logic for parsed transaction, inventory, debt, and query data.

Validates and normalizes structured output from the NLP layer using Pydantic V2 models.
"""

from datetime import date, datetime, timedelta
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

# Valid action types and their mapping to broad types
VALID_ACTIONS = {
    'sale': 'income',
    'purchase': 'expense',
    'expense': 'expense',
    'income': 'income',
    'payment': None,   # context-dependent, determined by 'type' field
    'transfer': None,  # context-dependent
    'other': None,
}

VALID_TYPES = {'income', 'expense'}

MAX_AMOUNT = 999_999_999.99  # ~1 billion Naira
MIN_AMOUNT = 0.01


class TransactionModel(BaseModel):
    type: Literal['income', 'expense']
    action: Literal['sale', 'purchase', 'expense', 'income', 'payment', 'transfer', 'other'] = 'other'
    # Optional so a parse with a stated item but NO price still validates — the
    # intake agent then asks the user for the missing price instead of failing
    # the whole message. A None amount is never recorded.
    amount: Optional[float] = None
    currency: str = 'NGN'
    item: Optional[str] = None
    category: str = 'Miscellaneous'
    description: Optional[str] = ''
    date: str

    @field_validator('type', mode='before')
    @classmethod
    def check_type(cls, v):
        t = str(v).lower().strip() if v is not None else v
        if t not in VALID_TYPES:
            raise ValueError(f"Invalid transaction type: '{v}'. Must be 'income' or 'expense'.")
        return t

    @field_validator('action', mode='before')
    @classmethod
    def coerce_action(cls, v):
        # Unknown/empty actions fall back to the declared default rather than
        # rejecting the whole transaction (LLM output varies).
        a = str(v).lower().strip() if v else ''
        return a if a in VALID_ACTIONS else 'other'

    @field_validator('amount')
    @classmethod
    def validate_amount_val(cls, v):
        if v is None:
            return None
        try:
            val = float(v)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid amount: '{v}'. Must be a number.")

        if val <= 0:
            raise ValueError(f"Amount must be positive, got {val}.")
        if val < MIN_AMOUNT:
            raise ValueError(f"Amount too small: {val}. Minimum is {MIN_AMOUNT}.")
        if val > MAX_AMOUNT:
            raise ValueError(f"Amount too large: {val:,.2f}. Maximum is {MAX_AMOUNT:,.2f}.")
        return round(val, 2)

    @field_validator('date')
    @classmethod
    def validate_date_val(cls, v):
        if not v:
            return date.today().isoformat()
        try:
            parsed_date = datetime.strptime(str(v), '%Y-%m-%d').date()
        except ValueError:
            raise ValueError(f"Invalid date format: '{v}'. Expected YYYY-MM-DD.")

        one_year_ago = date.today() - timedelta(days=365)
        if parsed_date < one_year_ago:
            raise ValueError(f"Date {v} is more than 1 year ago.")
        if parsed_date > date.today():
            raise ValueError(f"Date {v} is in the future.")
        return parsed_date.isoformat()

    @field_validator('item')
    @classmethod
    def clean_item(cls, v):
        if v:
            return str(v).strip()[:255]
        return None

    @field_validator('description')
    @classmethod
    def clean_description(cls, v):
        if v:
            return str(v).strip()[:255]
        return ''

    @field_validator('currency')
    @classmethod
    def clean_currency(cls, v):
        if not v or not str(v).strip():
            return 'NGN'
        return str(v).strip().upper()[:10]

    @field_validator('category', mode='before')
    @classmethod
    def clean_category(cls, v):
        # mode='before' so an explicit None/empty coerces to the default
        # (an 'after' validator never runs — None fails the str type first).
        if not v or not str(v).strip():
            return 'Miscellaneous'
        return str(v).strip()


class QueryModel(BaseModel):
    query_type: Literal['sum', 'list', 'balance', 'count', 'stock'] = 'sum'
    type: Optional[Literal['income', 'expense']] = None
    category: Optional[str] = None
    currency: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None

    @field_validator('query_type', mode='before')
    @classmethod
    def coerce_query_type(cls, v):
        # Unknown query types fall back to 'sum' rather than rejecting the query.
        q = str(v).lower().strip() if v else ''
        return q if q in ('sum', 'list', 'balance', 'count', 'stock') else 'sum'

    @field_validator('currency')
    @classmethod
    def clean_currency(cls, v):
        if v:
            return str(v).strip().upper()[:10]
        return None

    @field_validator('period_start', 'period_end')
    @classmethod
    def clean_date(cls, v):
        if v:
            try:
                datetime.strptime(str(v), '%Y-%m-%d')
                return str(v)
            except ValueError:
                return None
        return None


class InventoryModel(BaseModel):
    action: Literal['ADD', 'REMOVE', 'SET']
    product: str
    quantity: float
    unit: Optional[str] = None

    @field_validator('product')
    @classmethod
    def clean_product(cls, v):
        if not v or not str(v).strip():
            raise ValueError("Product name is missing.")
        return str(v).strip().lower()

    @field_validator('quantity')
    @classmethod
    def validate_qty(cls, v):
        try:
            val = float(v)
        except (ValueError, TypeError):
            raise ValueError("Quantity must be a valid number.")
        if val < 0:
            raise ValueError("Quantity must be non-negative.")
        return val


class DebtModel(BaseModel):
    action: Literal['add_debt', 'repayment', 'full_payment']
    name: str
    type: Literal['customer_debt', 'supplier_debt']
    amount: Optional[float] = None
    currency: str = 'NGN'

    @field_validator('currency', mode='before')
    @classmethod
    def clean_currency(cls, v):
        # normalise case, consistent with TransactionModel
        if not v or not str(v).strip():
            return 'NGN'
        return str(v).strip().upper()[:10]

    @field_validator('name')
    @classmethod
    def clean_name(cls, v):
        if not v or not str(v).strip():
            raise ValueError("Name is missing.")
        return str(v).strip().lower()

    @field_validator('amount')
    @classmethod
    def validate_amount(cls, v, info):
        # Allow None so a debt with a missing amount still validates; the intake
        # agent asks the user for it rather than failing the whole message.
        if v is None:
            return None
        try:
            val = float(v)
        except (ValueError, TypeError):
            raise ValueError("Amount must be a number.")
        if val <= 0:
            raise ValueError("Amount must be positive.")
        return val


class ReportModel(BaseModel):
    period: Literal['daily', 'weekly', 'monthly']
    date: Optional[str] = None


class StatementModel(BaseModel):
    """A request for a downloadable financial document (PDF/spreadsheet).

    Distinct from ReportModel (text snapshot summaries): a statement is a
    filterable, document-rendered export delivered as a WhatsApp attachment.
    """
    report_type: Literal['transactions', 'cashflow'] = 'transactions'
    tx_type: Optional[Literal['income', 'expense']] = None
    action: Optional[str] = None
    category: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    # None = the user didn't specify → intake asks "chat or PDF?". An explicit
    # word skips the question.
    format: Optional[Literal['pdf', 'xlsx', 'both', 'chat']] = None

    @field_validator('format', mode='before')
    @classmethod
    def normalise_format(cls, v):
        if not v:
            return None
        v = str(v).strip().lower()
        if v in ('excel', 'spreadsheet', 'sheet', 'xls', 'xlsx'):
            return 'xlsx'
        if v in ('chat', 'text', 'message', 'summary'):
            return 'chat'
        if v in ('both', 'all'):
            return 'both'
        if v in ('pdf', 'document', 'doc'):
            return 'pdf'
        return None

    @field_validator('period_start', 'period_end')
    @classmethod
    def clean_date(cls, v):
        if v:
            try:
                datetime.strptime(str(v), '%Y-%m-%d')
                return str(v)
            except ValueError:
                return None
        return None

    @field_validator('action', 'category', 'tx_type', mode='before')
    @classmethod
    def clean_str(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None


class UnifiedResponseModel(BaseModel):
    intents: List[str] = Field(default_factory=list)
    confidence: float
    needs_review: bool = False
    status: Literal['ok', 'clarification_needed', 'error', 'unknown'] = 'ok'
    question: Optional[str] = None
    # Mutating events are lists — one message may contain several (e.g. a purchase
    # AND a sale). Read-only intents (report/query/snapshot) stay singular.
    transactions: List[TransactionModel] = Field(default_factory=list)
    inventory: List[InventoryModel] = Field(default_factory=list)
    debts: List[DebtModel] = Field(default_factory=list)
    report: Optional[ReportModel] = None
    query: Optional[QueryModel] = None
    statement: Optional[StatementModel] = None
    snapshot: bool = False

    @model_validator(mode='before')
    @classmethod
    def _fold_singular(cls, data):
        """Back-compat: fold legacy singular transaction/debt and a single
        inventory object into their lists, so regex fast-paths and any cached
        pending payloads (which emit singular) keep working."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        tx = data.pop('transaction', None)
        if tx is not None and not data.get('transactions'):
            data['transactions'] = [tx]
        debt = data.pop('debt', None)
        if debt is not None and not data.get('debts'):
            data['debts'] = [debt]
        inv = data.get('inventory')
        if inv is not None and not isinstance(inv, list):
            data['inventory'] = [inv]
        return data


def dump_model(model):
    """Helper to dump Pydantic model compatible with V1 and V2."""
    if hasattr(model, 'model_dump'):
        return model.model_dump()
    return model.dict()


def validate_transaction(parsed):
    """Validate a parsed transaction dict using Pydantic TransactionModel.

    Args:
        parsed: dict with transaction keys.

    Returns:
        (True, cleaned_parsed) on success.
        (False, error_message) on failure.
    """
    try:
        tx_type = parsed.get('type', '').lower().strip()
        action = parsed.get('action', 'other').lower().strip()
        if action in VALID_ACTIONS:
            expected_type = VALID_ACTIONS[action]
            if expected_type and tx_type != expected_type:
                parsed['type'] = expected_type

        model = TransactionModel(**parsed)
        return True, dump_model(model)
    except Exception as e:
        if hasattr(e, 'errors'):
            errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
            return False, "; ".join(errors)
        return False, str(e)


def validate_query(parsed):
    """Validate a parsed query dict using Pydantic QueryModel.

    Args:
        parsed: dict with query parameters.

    Returns:
        (True, cleaned_parsed) on success.
        (False, error_message) on failure.
    """
    try:
        model = QueryModel(**parsed)
        return True, dump_model(model)
    except Exception as e:
        return False, str(e)


def validate_amount(amount):
    """Helper for legacy support to validate individual amount."""
    if amount is None:
        return False, "Amount is missing."
    try:
        val = float(amount)
        if val <= 0:
            return False, f"Amount must be positive, got {val}."
        if val < MIN_AMOUNT:
            return False, f"Amount too small: {val}. Minimum is {MIN_AMOUNT}."
        if val > MAX_AMOUNT:
            return False, f"Amount too large: {val:,.2f}. Maximum is {MAX_AMOUNT:,.2f}."
        return True, round(val, 2)
    except (ValueError, TypeError):
        return False, f"Invalid amount: '{amount}'. Must be a number."


def validate_date(tx_date):
    """Helper for legacy support to validate individual date."""
    if not tx_date:
        return True, date.today().isoformat()
    try:
        parsed_date = datetime.strptime(str(tx_date), '%Y-%m-%d').date()
        one_year_ago = date.today() - timedelta(days=365)
        if parsed_date < one_year_ago:
            return False, f"Date {tx_date} is more than 1 year ago."
        if parsed_date > date.today():
            return False, f"Date {tx_date} is in the future."
        return True, parsed_date.isoformat()
    except ValueError:
        return False, f"Invalid date format: '{tx_date}'. Expected YYYY-MM-DD."


def validate_inventory(parsed):
    """Validate parsed inventory dict using Pydantic InventoryModel."""
    try:
        model = InventoryModel(**parsed)
        return True, dump_model(model)
    except Exception as e:
        if hasattr(e, 'errors'):
            errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
            return False, "; ".join(errors)
        return False, str(e)


def validate_debt(parsed):
    """Validate parsed debt dict using Pydantic DebtModel."""
    try:
        model = DebtModel(**parsed)
        return True, dump_model(model)
    except Exception as e:
        if hasattr(e, 'errors'):
            errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
            return False, "; ".join(errors)
        return False, str(e)
