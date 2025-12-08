import pytest
import asyncio
from decimal import Decimal
from datetime import datetime
from backend.models import Payout, LedgerEntry, ReconciliationStatus

@pytest.mark.asyncio
@pytest.mark.parametrize("entries, ledger_fee, expected_status, expected_variance", [
    # Case 1: Perfect Match
    (
        [{"type": "CHARGE", "gross_amount": 103, "fee_amount": -3, "tax_amount": 0}], # Square says Fee is 3 (abs)
        Decimal("-3.00"), # QBO says Fee is -3
        ReconciliationStatus.MATCHED,
        Decimal("0.00")
    ),
    # Case 2: Fee Mismatch (Square 3, QBO 2.50) -> Variance 0.50
    (
        [{"type": "CHARGE", "gross_amount": 103, "fee_amount": -3, "tax_amount": 0}], 
        Decimal("-2.50"), 
        ReconciliationStatus.VARIANCE_DETECTED,
        Decimal("0.50") # 3.00 - 2.50 = 0.50
    ),
    # Case 3: Refund Scenario
    # Charge 100, Fee -3. Refund -100, FeeReversal +3? Or FeeReversal +2?
    # Let's say Net Payout is 0.
    # Entries: Charge(100, -3), Refund(-100, +3). Total Fees = 0.
    # Ledger Fee = 0.
    (
        [
            {"type": "CHARGE", "gross_amount": 100, "fee_amount": -3, "tax_amount": 0},
            {"type": "REFUND", "gross_amount": -100, "fee_amount": 3, "tax_amount": 0}
        ],
        Decimal("0.00"),
        ReconciliationStatus.MATCHED,
        Decimal("0.00")
    ),
    # Case 4: Rounding / Precision
    # Fee is 3.3333? Square usually gives ints.
    # What if QBO has -3.33 and Square has 3.34? Variance 0.01 (Allowed).
    # Logic allows > 0.01 variance.
    (
        [{"type": "CHARGE", "gross_amount": 100, "fee_amount": -3.34, "tax_amount": 0}], 
        Decimal("-3.33"), 
        ReconciliationStatus.MATCHED, # 0.01 difference is within check of > 0.01 (Wait, logic is > 0.01, so 0.01 is okay)
        Decimal("0.00") # Variance amount calculated reported as 0 if matched
    ),
     # Case 5: Variance > 0.01
    (
        [{"type": "CHARGE", "gross_amount": 100, "fee_amount": -3.35, "tax_amount": 0}], 
        Decimal("-3.33"), 
        ReconciliationStatus.VARIANCE_DETECTED, # 0.02 diff
        Decimal("0.02") 
    ),
])
async def test_calculation_parameterized(engine, mock_square, mock_qbo, entries, ledger_fee, expected_status, expected_variance):
    # Setup Payout
    net_amount = Decimal("0.00")
    # Calculate approximate net from entries for the Payout object (not crucial for this calc logic test but good for consistency)
    # The engine uses payout.amount_money mostly for initial matching.
    
    payout = Payout(
        id="po_calc",
        status="PAID",
        amount_money=Decimal("100.00"), # Dummy
        created_at=datetime.now(),
        processing_fee=Decimal("0.00") # Engine calculates this from detailed entries
    )

    mock_square.get_payout_entries_detailed.return_value = entries
    
    ledger = LedgerEntry(
        id="dep_calc",
        txn_date=datetime.now(),
        total_amount=Decimal("100.00"),
        has_fee_line_item=True,
        fee_amount=ledger_fee
    )
    mock_qbo.find_deposit.return_value = ledger
    
    result = await engine.process_payout(payout, auto_fix=False)
    
    assert result.status == expected_status
    # Check variance with precision
    # Using float in result model might cause small issues if not careful, but Decimal comparison in check was robust.
    # The result.variance_amount is float in the new model.
    # So we compare float to float approx or Decimal.
    assert abs(Decimal(str(result.variance_amount)) - expected_variance) < Decimal("0.001")
