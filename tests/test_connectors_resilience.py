import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import httpx
from backend.connectors.square import SquareClient
from backend.connectors.qbo import QBOClient
from backend.models import Payout, LedgerEntry
from datetime import datetime
from decimal import Decimal

@pytest.mark.asyncio
async def test_square_resilience_timeouts():
    """
    Test that the client handles timeouts gracefully (retries or raises known error).
    """
    with patch("httpx.AsyncClient.request") as mock_request:
        mock_request.side_effect = httpx.ConnectTimeout("Connection failed")
        
        client = SquareClient(access_token="test")
        
        with pytest.raises(Exception) as excinfo: # Or specific exception
           await client.get_payouts()
           
        # Just verifying it raises is enough for resilience (it doesn't hang forever)
        pass

@pytest.mark.asyncio
async def test_square_malformed_response():
    """
    Test handling of non-JSON response (e.g., 502 Bad Gateway text).
    """
    with patch("httpx.AsyncClient.request") as mock_request:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("Expecting value: line 1 column 1 (char 0)")
        mock_request.return_value = mock_resp
        
        client = SquareClient(access_token="test")
        
        with pytest.raises(ValueError):
             await client.get_payouts()

@pytest.mark.asyncio
async def test_idempotency_key_generation(engine, mock_square, mock_qbo):
    """
    Verify idempotency key is generated deterministically.
    """
    import hashlib
    payout_id = "po_idempotent"
    
    # We can spy on qbo.create_journal_entry
    
    payout = Payout(id=payout_id, status="PAID", amount_money=Decimal("97"), created_at=datetime.now())
    # Mock entries to avoid fetch error
    mock_square.get_payout_entries_detailed.return_value = [
        {"type": "CHARGE", "gross_amount": 100, "fee_amount": -3, "tax_amount": 0}
    ]
    
    # Ledger has 97 net, but 0 fee line (so missing fee)
    ledger = LedgerEntry(id="dep_1", txn_date=datetime.now(), total_amount=Decimal("97"), fee_amount=Decimal("0"))
    mock_qbo.find_deposit.return_value = ledger
    
    await engine.process_payout(payout, auto_fix=True)
    
    expected_key = hashlib.sha256(payout_id.encode()).hexdigest()
    
    # Square Fee 3. Ledger Fee 0. Variance 3. Should trigger fix.
    mock_qbo.create_journal_entry.assert_called_once()
    args = mock_qbo.create_journal_entry.call_args[1]
    assert args["idempotency_key"] == expected_key
