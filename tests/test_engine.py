import pytest
import asyncio
from decimal import Decimal
from datetime import datetime
from backend.models import Payout, LedgerEntry, ReconciliationStatus, ReconciliationEntry

@pytest.mark.asyncio
async def test_reconciliation_variance_detected(engine, mock_square, mock_qbo):
    """
    Test that a variance is detected when Square fee != QBO fee.
    """
    payout = Payout(
        id="po_123",
        status="PAID",
        amount_money=Decimal("100.00"),
        created_at=datetime.now(),
        processing_fee=Decimal("3.00")
    )
    
    # Mock detailed entries for the engine's fetching step
    # The new engine calls get_payout_entries_detailed
    mock_square.get_payout_entries_detailed.return_value = [
        {"type": "CHARGE", "gross_amount": 10300, "fee_amount": -300, "tax_amount": 0} # 103.00 gross, 3.00 fee
    ]
    # Note: Connector mock needs to match what engine expects. 
    # Engine does: Decimal(str(entry.get("gross_amount", 0))) 
    # If connector returns raw cents (int) or Decimal, engine handles it.
    # Let's assume connector (and engine logic) handles specific format. 
    # In `backend/services/reconciliation.py`:
    # gross_amt = Decimal(str(entry.get("gross_amount", 0)))
    # If we pass 10300 (cents), Decimal("10300").
    # Wait, the engine logic in `reconciliation.py`:
    # 104: gross_amt = Decimal(str(entry.get("gross_amount", 0)))
    # This implies the values in detailed entries are ALREADY Decimals or floats representing Dollars, OR the engine logic is flawed for Cents.
    # Connectors usually normalize. 
    # Let's look at `backend/connectors/square.py` from Step 84:
    # It returns raw dictionary from Square or mock. 
    # Square API returns Money objects (amount, currency).
    # `get_payout_entries_detailed` in mock (lines 175+) returns `{"gross_amount": 100.00}` (floats).
    # So we should mock with floats/Decimals representing Major Units (Dollars).
    
    mock_square.get_payout_entries_detailed.return_value = [
         {"type": "CHARGE", "gross_amount": 103.00, "fee_amount": -3.00, "tax_amount": 0.00}
    ]

    # Ledger Fee is 0 (missing fee line)
    ledger = LedgerEntry(
        id="dep_456",
        txn_date=datetime.now(),
        total_amount=Decimal("100.00"),
        has_fee_line_item=False,
        fee_amount=Decimal("0.00")
    )
    mock_qbo.find_deposit.return_value = ledger
    
    result = await engine.process_payout(payout, auto_fix=True)
    
    assert result.status == ReconciliationStatus.VARIANCE_DETECTED
    assert result.variance_amount == Decimal("3.00")
    
    # Verify Journal Entry Created
    mock_qbo.create_journal_entry.assert_called_once()
    args = mock_qbo.create_journal_entry.call_args[1]
    assert args["deposit_id"] == "dep_456"
    assert args["variance_amount"] == Decimal("3.00")

@pytest.mark.asyncio
async def test_reconciliation_matched(engine, mock_square, mock_qbo):
    """
    Test that no action is taken when fees match.
    """
    payout = Payout(
        id="po_789",
        status="PAID",
        amount_money=Decimal("97.00"),
        created_at=datetime.now(),
        processing_fee=Decimal("3.00")
    )
    
    mock_square.get_payout_entries_detailed.return_value = [
         {"type": "CHARGE", "gross_amount": 100.00, "fee_amount": -3.00, "tax_amount": 0.00}
    ]

    # Ledger matches: Fee entry -3 present.
    ledger = LedgerEntry(
        id="dep_999",
        txn_date=datetime.now(),
        total_amount=Decimal("97.00"),
        has_fee_line_item=True,
        fee_amount=Decimal("-3.00")
    )
    mock_qbo.find_deposit.return_value = ledger
    
    result = await engine.process_payout(payout, auto_fix=True)
    
    assert result.status == ReconciliationStatus.MATCHED
    mock_qbo.create_journal_entry.assert_not_called()

@pytest.mark.asyncio
async def test_reconciliation_missing_deposit(engine, mock_square, mock_qbo):
    """
    Test result when no deposit is found.
    """
    payout = Payout(
        id="po_missing",
        status="PAID",
        amount_money=Decimal("50.00"),
        created_at=datetime.now(),
        processing_fee=Decimal("1.50")
    )
    
    mock_square.get_payout_entries_detailed.return_value = [
         {"type": "CHARGE", "gross_amount": 51.50, "fee_amount": -1.50, "tax_amount": 0.00}
    ]
    
    mock_qbo.find_deposit.return_value = None
    
    result = await engine.process_payout(payout, auto_fix=True)
    
    assert result.status == ReconciliationStatus.MISSING_DEPOSIT
    mock_qbo.create_journal_entry.assert_not_called()
