
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from decimal import Decimal
from backend.connectors.square import SquareClient
from backend.connectors.stripe import StripeClient
from backend.services.reconciliation import ReconciliationEngine

@pytest.mark.asyncio
async def test_square_pagination():
    """Verify Square connector fetches multiple pages of payouts."""
    
    # Mock Response Page 1
    page1 = {
        "payouts": [{"id": "p1", "status": "PAID", "amount_money": {"amount": 1000}, "created_at": "2023-01-01T12:00:00Z"}],
        "cursor": "abc_next_page"
    }
    # Mock Response Page 2
    page2 = {
        "payouts": [{"id": "p2", "status": "PAID", "amount_money": {"amount": 2000}, "created_at": "2023-01-02T12:00:00Z"}],
        "cursor": "" # End
    }
    
    # Mock fee response
    fee_resp = {"payout_entries": [{"type": "FEE", "amount_money": {"amount": 50}}]}

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        def side_effect(method, url, params=None):
            if "payouts" in url and "entries" not in url:
                if params and params.get("cursor") == "abc_next_page":
                    return MagicMock(json=lambda: page2, status_code=200)
                return MagicMock(json=lambda: page1, status_code=200)
            if "payout-entries" in url:
                 return MagicMock(json=lambda: {"payout_entries": []}, status_code=200) # Simplify fee fetching
            return MagicMock(json=lambda: {}, status_code=200)

        mock_req.side_effect = side_effect
        
        # We need to mock get_payout_fee as well or let it run. 
        # Since I replaced request side effect, it might handle it? 
        # But get_payout_fee calls request too.
        # Let's simple-mock get_payout_fee to avoid complexity in this test
        
        client = SquareClient(access_token="test")
        client.get_payout_fee = AsyncMock(return_value=Decimal("0.50"))
        
        payouts = await client.get_payouts()
        
        assert len(payouts) == 2
        assert payouts[0].id == "p1"
        assert payouts[1].id == "p2"


@pytest.mark.asyncio
async def test_stripe_pagination():
    """Verify Stripe connector uses manual loop for pagination."""
    # Patch stripe at the module level where it is used
    with patch("stripe.Payout.list") as mock_list:
        from backend.connectors.stripe import StripeClient
        
        page1_data = [MagicMock(id="p1", status="paid", amount=100, created=1672531200, arrival_date=1672531200, currency="usd")]
        page2_data = [MagicMock(id="p2", status="paid", amount=200, created=1672617600, arrival_date=1672617600, currency="usd")]
        
        mock_page1 = MagicMock()
        mock_page1.data = page1_data
        mock_page1.has_more = True
        
        mock_page2 = MagicMock()
        mock_page2.data = page2_data
        mock_page2.has_more = False
        
        mock_list.side_effect = [mock_page1, mock_page2]
        
        client = StripeClient(access_token="test")
        payouts = await client.get_payouts()
        
        assert len(payouts) == 2
        assert payouts[0].id == "p1"
        assert payouts[1].id == "p2"
        
        # Verify call args
        assert mock_list.call_count == 2
        
        # First call has no starting_after (or is None)
        args1, kwargs1 = mock_list.call_args_list[0]
        assert "starting_after" not in kwargs1 or kwargs1["starting_after"] is None
        
        # Second call has starting_after = p1
        args2, kwargs2 = mock_list.call_args_list[1]
        assert kwargs2["starting_after"] == "p1"
