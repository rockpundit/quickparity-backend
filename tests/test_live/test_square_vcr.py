import pytest
from datetime import datetime, timedelta

@pytest.mark.vcr
@pytest.mark.asyncio
async def test_square_live_fetch_payouts(square_live_client):
    """
    Fetch real payouts from Square Sandbox.
    """
    end = datetime.now()
    start = end - timedelta(days=90)
    
    payouts = await square_live_client.get_payouts(begin_time=start, end_time=end)
    
    assert isinstance(payouts, list)
    # Note: Sandbox might be empty unless we manually trigger transactions.
    # We assert the call succeeded (returned a list, empty or not).
    
    if len(payouts) > 0:
        p = payouts[0]
        assert p.source == "Square"
        assert p.amount_money is not None

@pytest.mark.vcr
@pytest.mark.asyncio
async def test_square_live_fetch_entries(square_live_client):
    """
    Fetch detailed entries for a Square payout.
    """
    end = datetime.now()
    start = end - timedelta(days=90)
    payouts = await square_live_client.get_payouts(begin_time=start, end_time=end)
    
    if len(payouts) == 0:
        pytest.skip("No Square Sandbox payouts found.")
        
    payout_id = payouts[0].id
    entries = await square_live_client.get_payout_entries_detailed(payout_id)
    
    assert isinstance(entries, list)
    if len(entries) > 0:
        e = entries[0]
        assert "gross_amount" in e
