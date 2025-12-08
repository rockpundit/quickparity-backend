from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

class ReconciliationStatus(str, Enum):
    MATCHED = "MATCHED"
    VARIANCE_DETECTED = "VARIANCE_DETECTED"
    MISSING_DEPOSIT = "MISSING_DEPOSIT"
    ERROR = "ERROR"

class Payout(BaseModel):
    """
    Represents a payout from a payment processor (Square/Stripe).
    """
    id: str
    status: str
    amount_money: Decimal  # Net amount deposited
    created_at: datetime
    arrival_date: Optional[datetime] = None
    processing_fee: Decimal = Decimal("0.00") # Calculated or fetched fee
    currency: str = "USD"
    
    # Square specific fields can be optional or part of a detailed model if needed
    
    model_config = ConfigDict(arbitrary_types_allowed=True)


class LedgerEntry(BaseModel):
    """
    Represents a deposit or transaction in the accounting system (QBO).
    """
    id: str  # QBO Transaction ID
    txn_date: datetime
    total_amount: Decimal
    currency: str = "USD"
    has_fee_line_item: bool = False
    fee_amount: Decimal = Decimal("0.00")
    
    model_config = ConfigDict(arbitrary_types_allowed=True)


class ReconciliationResult(BaseModel):
    """
    Result of an audit for a single payout.
    """
    payout_id: str
    ledger_entry_id: Optional[str] = None
    status: ReconciliationStatus
    gross_sales: Decimal
    net_deposit: Decimal
    calculated_fee: Decimal
    ledger_fee: Decimal
    variance_amount: Decimal
    timestamp: datetime = datetime.now()

    def is_balanced(self) -> bool:
        return self.variance_amount == Decimal("0.00") and self.status == ReconciliationStatus.MATCHED

class Tenant(BaseModel):
    """
    Represents a customer/tenant with encrypted credentials.
    """
    id: str
    name: str
    encrypted_sq_token: str
    encrypted_qbo_token: str
    qbo_realm_id: str
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
