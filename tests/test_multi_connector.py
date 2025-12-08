import pytest
import asyncio
from datetime import datetime
from decimal import Decimal
from backend.models import Payout, ReconciliationStatus

@pytest.mark.asyncio
async def test_aggregation_logic(engine, mock_square, mock_stripe, mock_shopify, mock_paypal, mock_qbo):
    """
    Verify run_for_period fetches from all configured clients.
    """
    # Setup Date
    start = datetime.now()
    end = datetime.now()
    
    # Mock Results
    mock_square.get_payouts.return_value = [Payout(id="sq_1", source="Square", status="PAID", amount_money=Decimal("100"), created_at=start)]
    mock_stripe.get_payouts.return_value = [Payout(id="st_1", source="Stripe", status="PAID", amount_money=Decimal("200"), created_at=start)]
    mock_shopify.get_payouts.return_value = [Payout(id="sh_1", source="Shopify", status="PAID", amount_money=Decimal("300"), created_at=start)]
    mock_paypal.get_payouts.return_value = [Payout(id="pp_1", source="PayPal", status="PAID", amount_money=Decimal("400"), created_at=start)]
    
    # Mock processing to avoid needing full db/qbo setup for this specific test
    # We can patch process_payout or just let it run if we mock dependencies enough.
    # But process_payout calls get_payout_entries_detailed and qbo.find_deposit.
    # Let's mock the engine.process_payout method to isolate aggregation test?
    # Or just mock the dependencies.
    
    # Mocking Dependencies for process_payout to succeed quickly
    # Square routing
    mock_square.get_payout_entries_detailed.return_value = []
    mock_stripe.get_payout_entries_detailed.return_value = []
    mock_shopify.get_payout_entries_detailed.return_value = []
    mock_paypal.get_payout_entries_detailed.return_value = []
    
    # QBO mock from conftest is already there, return None (MISSING_DEPOSIT) to simplify flow
    mock_qbo.find_deposit.return_value = None
    
    results = await engine.run_for_period(start, end)
    
    assert len(results) == 4
    assert mock_square.get_payouts.called
    assert mock_stripe.get_payouts.called
    assert mock_shopify.get_payouts.called
    assert mock_paypal.get_payouts.called

@pytest.mark.asyncio
async def test_routing_logic(engine, mock_square, mock_stripe, mock_shopify, mock_paypal, mock_qbo):
    """
    Verify process_payout calls the correct connector for entries based on source.
    """
    # Ensure QBO doesn't return a Mock which causes math errors later
    mock_qbo.find_deposit.return_value = None
    
    # 1. Stripe Payout
    p1 = Payout(id="st_test", source="Stripe", status="PAID", amount_money=Decimal("50"), created_at=datetime.now())
    mock_stripe.get_payout_entries_detailed.return_value = []
    
    await engine.process_payout(p1, auto_fix=False)
    mock_stripe.get_payout_entries_detailed.assert_called_with("st_test")
    mock_square.get_payout_entries_detailed.assert_not_called()
    
    # Reset
    mock_stripe.reset_mock()
    
    # 2. Shopify Payout
    p2 = Payout(id="sh_test", source="Shopify", status="PAID", amount_money=Decimal("50"), created_at=datetime.now())
    mock_shopify.get_payout_entries_detailed.return_value = []
    
    await engine.process_payout(p2, auto_fix=False)
    mock_shopify.get_payout_entries_detailed.assert_called_with("sh_test")
