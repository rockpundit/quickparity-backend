import pytest
from datetime import datetime, timedelta

# VCR decorator automatically records HTTP interactions to cassettes/test_stripe_live.yaml
@pytest.mark.vcr
@pytest.mark.asyncio
async def test_stripe_live_fetch_payouts(stripe_live_client):
    """
    Fetch real payouts from Stripe Sandbox.
    """
    # Use a wide range to ensure we get something if the sandbox has data
    end = datetime.now()
    start = end - timedelta(days=90)
    
    payouts = await stripe_live_client.get_payouts(begin_time=start, end_time=end)
    
    # We verify the schema and typing, not necessarily the count (depends on sandbox state)
    assert isinstance(payouts, list)
    if len(payouts) > 0:
        p = payouts[0]
        assert hasattr(p, "id")
        assert hasattr(p, "amount_money")
        assert p.source == "Stripe"

@pytest.mark.vcr
@pytest.mark.asyncio
async def test_stripe_live_fetch_entries(stripe_live_client):
    """
    Fetch detailed entries for a known payout ID (or first available).
    """
    # 1. Fetch payouts first to get a valid ID
    end = datetime.now()
    start = end - timedelta(days=90)
    payouts = await stripe_live_client.get_payouts(begin_time=start, end_time=end)
    
    if len(payouts) == 0:
        pytest.skip("No payouts found in Stripe Sandbox to test entries.")
        
    payout_id = payouts[0].id
    entries = await stripe_live_client.get_payout_entries_detailed(payout_id)
    
    assert isinstance(entries, list)
    if len(entries) > 0:
        e = entries[0]
        assert "gross_amount" in e
        assert "fee_amount" in e
        assert "type" in e
