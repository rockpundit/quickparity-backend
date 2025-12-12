
import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from datetime import datetime

from backend.services.reconciliation import ReconciliationEngine
from backend.models import ReconciliationEntry, ReconciliationStatus, VarianceType, LedgerEntry

@pytest.mark.asyncio
async def test_apply_fix_missing_tax():
    # Setup
    mock_qbo = AsyncMock()
    # Mock find_deposit to return a ledger entry (required for apply_fix to proceed)
    mock_qbo.find_deposit.return_value = LedgerEntry(
        id="999",
        txn_date=datetime.now(),
        total_amount=Decimal("100.00"),
        has_fee_line_item=False,
        fee_amount=Decimal("0.00")
    )
    mock_qbo.create_journal_entry.return_value = {"id": "JE-123"}
    
    engine = ReconciliationEngine(square_client=AsyncMock(), qbo_client=mock_qbo)
    
    # Entry
    entry = ReconciliationEntry(
        date="2023-01-01",
        payout_id="PAY-1",
        status=ReconciliationStatus.VARIANCE_DETECTED,
        gross_sales=100.0,
        net_deposit=95.0,
        calculated_fees=0.0,
        ledger_fee=0.0,
        sales_tax_collected=5.0,
        refund_amount=0.0,
        refund_fee_reversal=0.0,
        variance_amount=5.0,
        variance_type=VarianceType.MISSING_TAX,
        variance_reason="Missing Tax"
    )
    
    # Settings
    settings = {
        "default_fee_account_id": "FEE-1",
        "default_undeposited_funds_account_id": "UNDEP-1",
        "default_tax_account_id": "TAX-1"
    }
    
    # Action
    success, msg = await engine.apply_fix(entry, settings)
    
    # Assert
    assert success is True
    assert entry.status == "FIXED"
    
    # Verify Call
    mock_qbo.create_journal_entry.assert_called_once()
    call_kwargs = mock_qbo.create_journal_entry.call_args.kwargs
    
    assert call_kwargs["deposit_id"] == "999"
    assert call_kwargs["expense_account_id"] == "TAX-1" # The Key Assertion
    assert "Tax Withholding Adjustment" in call_kwargs["description"]

@pytest.mark.asyncio
async def test_apply_fix_missing_tax_fallback():
    # Test fallback if no tax account is set
    mock_qbo = AsyncMock()
    mock_qbo.find_deposit.return_value = LedgerEntry(
        id="999", txn_date=datetime.now(), total_amount=Decimal("100.00")
    )
    mock_qbo.create_journal_entry.return_value = {"id": "JE-123"}
    
    engine = ReconciliationEngine(square_client=AsyncMock(), qbo_client=mock_qbo)
    
    entry = ReconciliationEntry(
        date="2023-01-01", payout_id="PAY-2", status=ReconciliationStatus.VARIANCE_DETECTED,
        gross_sales=100.0, net_deposit=95.0, calculated_fees=0.0, ledger_fee=0.0,
        sales_tax_collected=5.0, refund_amount=0.0, refund_fee_reversal=0.0,
        variance_amount=5.0, variance_type=VarianceType.MISSING_TAX
    )
    
    # No tax account in settings
    settings = {
        "default_fee_account_id": "FEE-1",
        "default_undeposited_funds_account_id": "UNDEP-1"
    }
    
    success, msg = await engine.apply_fix(entry, settings)
    
    assert success is True
    call_kwargs = mock_qbo.create_journal_entry.call_args.kwargs
    assert call_kwargs["expense_account_id"] == "FEE-1" # Fallback to fee
