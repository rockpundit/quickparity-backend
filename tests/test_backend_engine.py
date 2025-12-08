import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from datetime import datetime

from backend.services.reconciliation import ReconciliationEngine
from backend.models import Payout, LedgerEntry, ReconciliationStatus

@pytest.mark.asyncio
async def test_tax_splitter_logic(tmp_path):
    # Setup Mocks
    mock_sq = AsyncMock()
    mock_qbo = AsyncMock()
    
    # Use tmp file DB
    db_file = tmp_path / "test.db"
    engine = ReconciliationEngine(mock_sq, mock_qbo, db_path=str(db_file))
    
    # User Scenario:
    # Gross Sale: $100 (incl $10 tax).
    # Fee: $3.
    # Net Deposit: $97.
    
    payout = Payout(
        id="p1", status="PAID", amount_money=Decimal("97.00"), 
        created_at=datetime.now(), processing_fee=Decimal("3.00")
    )
    
    # Mock Payout Entries
    mock_sq.get_payout_entries_detailed.return_value = [
        {
            "type": "CHARGE",
            "gross_amount": 100.00,
            "fee_amount": -3.00,
            "tax_amount": 10.00,
            "source_payment_id": "pay_1"
        }
    ]
    
    # Mock QBO Finding Deposit (Matching)
    mock_qbo.find_deposit.return_value = LedgerEntry(
        id="d1", txn_date=datetime.now(), total_amount=Decimal("97.00"), fee_amount=Decimal("-3.00")
    )
    
    # Run
    result = await engine.process_payout(payout, auto_fix=False)
    
    # Verify Status
    assert result.status == ReconciliationStatus.MATCHED
    
    # Verify Tax Capture
    assert result.sales_tax_collected == 10.00
    
    # Verify Gross Sales (Total Charge Amount)
    assert result.gross_sales == 100.00
    
    # Verify Fees
    assert result.calculated_fees == 3.00

@pytest.mark.asyncio
async def test_refund_logic(tmp_path):
    mock_sq = AsyncMock()
    mock_qbo = AsyncMock()
    db_file = tmp_path / "test_refund.db"
    engine = ReconciliationEngine(mock_sq, mock_qbo, db_path=str(db_file))
    
    # Scenario: Refund of $100.
    # Net Deposit reduces by $100 (or if it's substantial, negative payout).
    # Let's say we have a Payout of -$100 (Refund only).
    
    payout = Payout(
        id="p2", status="PAID", amount_money=Decimal("-100.00"), 
        created_at=datetime.now(), processing_fee=Decimal("0.00")
    )
    
    mock_sq.get_payout_entries_detailed.return_value = [
        {
            "type": "REFUND",
            "gross_amount": -100.00, # Refund is negative flow
            "fee_amount": 0.00,
            "tax_amount": 0.00
        }
    ]
    
    # Mock QBO Deposit (Withdrawal in this case)
    mock_qbo.find_deposit.return_value = LedgerEntry(
        id="d2", txn_date=datetime.now(), total_amount=Decimal("-100.00"), fee_amount=Decimal("0.00")
    )

    result = await engine.process_payout(payout, auto_fix=False)
    
    assert result.status == ReconciliationStatus.MATCHED
    assert result.refund_amount == 100.00 # We store absolute value for reporting
    assert result.net_deposit == -100.00

@pytest.mark.asyncio
async def test_multi_connector_integration(tmp_path):
    # Setup Mocks for all connectors
    mock_sq = AsyncMock()
    mock_qbo = AsyncMock()
    mock_stripe = AsyncMock()
    mock_shopify = AsyncMock()
    mock_paypal = AsyncMock()
    
    db_file = tmp_path / "test_multi.db"
    
    # Init Engine with all connectors
    engine = ReconciliationEngine(
        mock_sq, mock_qbo, 
        stripe_client=mock_stripe, 
        shopify_client=mock_shopify, 
        paypal_client=mock_paypal,
        db_path=str(db_file)
    )
    
    # Mock data return from each
    mock_sq.get_payouts.return_value = []
    mock_stripe.get_payouts.return_value = [
        Payout(id="st_1", status="PAID", amount_money=Decimal("50.00"), created_at=datetime.now(), source="Stripe")
    ]
    mock_shopify.get_payouts.return_value = [
        Payout(id="sh_1", status="PAID", amount_money=Decimal("100.00"), created_at=datetime.now(), source="Shopify")
    ]
    mock_paypal.get_payouts.return_value = [
        Payout(id="pp_1", status="COMPLETED", amount_money=Decimal("75.00"), created_at=datetime.now(), source="PayPal")
    ]
    
    # Mock QBO to align with all (simplification: strict match found for all)
    mock_qbo.find_deposit.side_effect = lambda amount, d_from, d_to: LedgerEntry(
        id=f"dep_{amount}", txn_date=datetime.now(), total_amount=amount, fee_amount=Decimal("0.00")
    )

    # Run for period
    results = await engine.run_for_period(datetime.now(), datetime.now(), auto_fix=False)
    
    # Verify we got 3 results (1 from each non-empty source)
    assert len(results) == 3
    
    # Verify sources were preserved and processed
    sources = [r.payout_id for r in results]
    assert "st_1" in sources
    assert "sh_1" in sources
    assert "pp_1" in sources
    
    # Verify detailed entry fetch was called for specific sources
    mock_stripe.get_payout_entries_detailed.assert_called_once()
    mock_shopify.get_payout_entries_detailed.assert_called_once()
    mock_paypal.get_payout_entries_detailed.assert_called_once()
