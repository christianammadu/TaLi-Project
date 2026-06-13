"""Band SDK Event Schemas (Pydantic V2).
"""

from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from datetime import datetime
from typing import Dict, Any, Optional, List
from app.services.validators import UnifiedResponseModel, TransactionModel, InventoryModel, DebtModel, ReportModel


class BaseBandEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: UUID = Field(default_factory=uuid4)
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    business_id: Optional[int] = 1
    source_agent: str
    target_agent: Optional[str] = None
    event_type: str  # transaction, inventory, debt, report, error
    schema_version: str = "1.0"


class IntakeEventPayload(BaseModel):
    intent: str
    confidence_score: float
    raw_text: str
    is_fast_path: bool = False
    fast_path_transaction: Optional[TransactionModel] = None
    nlp_parsed: Optional[UnifiedResponseModel] = None


class IntakePayload(BaseBandEvent):
    payload: IntakeEventPayload


class TransactionResult(BaseModel):
    id: str
    type: str
    action: str
    amount: float
    currency: str
    item: Optional[str] = None
    category: str
    description: str
    date: str


class InventoryResult(BaseModel):
    product: str
    action: str
    quantity: float
    unit: Optional[str] = None
    new_stock: float
    status: Optional[str] = None
    question: Optional[str] = None


class DebtResult(BaseModel):
    name: str
    type: str
    action: str
    amount: float
    previous_balance: float
    new_balance: float
    status: str
    transaction_id: Optional[str] = None
    question: Optional[str] = None


class LedgerUpdateData(BaseModel):
    transactions: List[TransactionResult] = Field(default_factory=list)
    inventory: List[InventoryResult] = Field(default_factory=list)
    debts: List[DebtResult] = Field(default_factory=list)
    report: Optional[ReportModel] = None


class LedgerUpdateEventPayload(BaseModel):
    transaction_id: Optional[str] = None
    status: str  # 'success' or 'error'
    intent: str
    raw_text: str
    data: Optional[LedgerUpdateData] = None
    error_reason: Optional[str] = None


class LedgerUpdateEvent(BaseBandEvent):
    payload: LedgerUpdateEventPayload


class CFOEscalationEventPayload(BaseModel):
    status: str
    message: str
    raw_text: str
    parsed: Dict[str, Any] = Field(default_factory=dict)


class CFOEscalationEvent(BaseBandEvent):
    payload: CFOEscalationEventPayload
