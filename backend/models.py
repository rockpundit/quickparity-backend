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

class VarianceType(str, Enum):
    FEE_MISMATCH = "fee_mismatch"
    MISSING_TAX = "missing_tax"
    REFUND_DRIFT = "refund_drift"
    OTHER = "other"

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
    currency: str = "USD"
    type: str = "CHARGE" # CHARGE, REFUND, ADJUSTMENT
    source: str = "Square" # Square, Stripe, Shopify, PayPal
    
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


class ReconciliationEntry(BaseModel):
    """
    Detailed audit entry for a single payout, including tax and refund breakdowns.
    """
    date: str # YYYY-MM-DD
    payout_id: str
    status: ReconciliationStatus
    
    # Core Reconciliation Data
    gross_sales: float
    net_deposit: float
    calculated_fees: float
    ledger_fee: float
    
    # New Fields for Features 1 & 2
    sales_tax_collected: float
    refund_amount: float
    refund_fee_reversal: float
    
    variance_amount: float
    variance_type: Optional[VarianceType] = None
    
    # Metadata for UI
    source: str = "Square" # or Stripe
    
    model_config = ConfigDict(arbitrary_types_allowed=True)

class AuditReport(BaseModel):
    total_variance: float
    entries: List[ReconciliationEntry]
    action_required: bool

class Tenant(BaseModel):
    """
    Represents a customer/tenant with encrypted credentials.
    """
    id: str
    name: str
    encrypted_sq_token: str
    encrypted_stripe_token: Optional[str] = None
    encrypted_shopify_token: Optional[str] = None
    encrypted_paypal_token: Optional[str] = None
    encrypted_qbo_token: str
    qbo_realm_id: str
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
