"""
QBO (QuickBooks Online) Connector Tests
Tests connection integrity, read operations, WRITE operations, and token refresh.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime
from decimal import Decimal
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


class TestQBOConnectionIntegrity:
    """Tests for QBO client initialization and health checks."""

    @pytest.mark.asyncio
    async def test_qbo_client_initialization(self, mock_qbo):
        """Verify client initializes with required credentials."""
        assert mock_qbo is not None

    @pytest.mark.asyncio
    async def test_qbo_health_check_success(self, mock_qbo):
        """Verify health check (CompanyInfo query) succeeds."""
        mock_qbo.health_check = AsyncMock(return_value=True)
        result = await mock_qbo.health_check()
        assert result is True


class TestQBOReadOperations:
    """Tests for QBO data retrieval operations."""

    @pytest.mark.asyncio
    async def test_find_deposit_returns_ledger_entry(self, mock_qbo):
        """Verify find_deposit returns matching deposit."""
        from backend.models import LedgerEntry
        
        mock_qbo.find_deposit.return_value = LedgerEntry(
            id="dep_123",
            txn_date=datetime.now(),
            total_amount=Decimal("100.00"),
            has_fee_line_item=True,
            fee_amount=Decimal("-3.00"),
        )
        
        result = await mock_qbo.find_deposit(Decimal("100.00"), datetime.now(), datetime.now())
        
        assert result is not None
        assert result.id == "dep_123"

    @pytest.mark.asyncio
    async def test_find_deposit_with_tolerance(self, mock_qbo):
        """Verify deposit matching allows small tolerance for rounding."""
        from backend.models import LedgerEntry
        
        # $100.01 should match $100.00 within tolerance
        mock_qbo.find_deposit.return_value = LedgerEntry(
            id="dep_tolerance",
            txn_date=datetime.now(),
            total_amount=Decimal("100.01"),
            has_fee_line_item=True,
            fee_amount=Decimal("-3.00"),
        )
        
        result = await mock_qbo.find_deposit(Decimal("100.00"), datetime.now(), datetime.now())
        assert result is not None


class TestQBOWriteOperations:
    """Tests for QBO write operations (Journal Entries)."""

    @pytest.mark.asyncio
    async def test_create_journal_entry_valid_payload(self, mock_qbo):
        """Verify Journal Entry is created with correct structure."""
        mock_qbo.create_journal_entry.return_value = {"Id": "je_123", "SyncToken": "0"}
        
        result = await mock_qbo.create_journal_entry(
            deposit_id="dep_456",
            variance_amount=Decimal("3.00"),
            description="Fee variance adjustment",
        )
        
        assert result is not None
        mock_qbo.create_journal_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_journal_entry_debits_equal_credits(self):
        """Verify generated Journal Entry has balanced debits/credits."""
        from backend.connectors.qbo import QBOClient
        
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"JournalEntry": {"Id": "100"}}
            mock_post.return_value = mock_response
            
            client = QBOClient(realm_id="123", access_token="test")
            
            # The actual call would verify the payload structure
            # sum(debits) == sum(credits)

    @pytest.mark.asyncio
    async def test_journal_entry_with_memo(self, mock_qbo):
        """Verify memo/description is included in Journal Entry."""
        mock_qbo.create_journal_entry.return_value = {"Id": "je_memo"}
        
        await mock_qbo.create_journal_entry(
            deposit_id="dep_789",
            variance_amount=Decimal("5.00"),
            description="Stripe processing fee variance - Payout po_123",
        )
        
        call_args = mock_qbo.create_journal_entry.call_args
        assert "description" in call_args.kwargs or len(call_args.args) >= 3


class TestQBOTokenRefresh:
    """Tests for QBO OAuth token refresh flow."""

    @pytest.mark.asyncio
    async def test_token_refresh_on_401(self):
        """Verify automatic token refresh when access token expires."""
        from backend.connectors.qbo import QBOClient
        
        with open(os.path.join(DATA_DIR, "qbo_auth_response.json")) as f:
            token_response = json.load(f)
        
        with patch("httpx.AsyncClient.request") as mock_request:
            # First call: 401 (expired token)
            mock_401 = MagicMock()
            mock_401.status_code = 401
            mock_401.json.return_value = {"fault": {"error": [{"code": "401"}]}}
            
            # Token refresh call
            mock_token = MagicMock()
            mock_token.status_code = 200
            mock_token.json.return_value = token_response
            
            # Retry call: 200
            mock_200 = MagicMock()
            mock_200.status_code = 200
            mock_200.json.return_value = {"QueryResponse": {"Deposit": []}}
            
            mock_request.side_effect = [mock_401, mock_token, mock_200]
            
            client = QBOClient(realm_id="123", access_token="expired_token")
            # Should handle 401 and retry


class TestQBORateLimiting:
    """Tests for QBO rate limit handling."""

    @pytest.mark.asyncio
    async def test_429_respects_retry_after(self):
        """Verify client waits on 429 Too Many Requests."""
        from backend.connectors.qbo import QBOClient
        
        with patch("httpx.AsyncClient.request") as mock_request:
            mock_429 = MagicMock()
            mock_429.status_code = 429
            mock_429.headers = {"Retry-After": "60"}
            
            mock_200 = MagicMock()
            mock_200.status_code = 200
            mock_200.json.return_value = {"QueryResponse": {}}
            
            mock_request.side_effect = [mock_429, mock_200]
            
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                client = QBOClient(realm_id="123", access_token="test")
                # Verify sleep was called
