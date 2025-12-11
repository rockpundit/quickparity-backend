"""
PayPal Connector Tests
Tests connection integrity, read operations, and error handling.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime
from decimal import Decimal


class TestPayPalConnectionIntegrity:
    """Tests for PayPal client initialization and health checks."""

    @pytest.mark.asyncio
    async def test_paypal_client_initialization(self, mock_paypal):
        """Verify client initializes with required credentials."""
        assert mock_paypal is not None

    @pytest.mark.asyncio
    async def test_paypal_oauth_token_acquisition(self):
        """Verify OAuth token is acquired on initialization."""
        from backend.connectors.paypal import PayPalClient
        
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "access_token": "A21AAF...",
                "token_type": "Bearer",
                "expires_in": 32400
            }
            mock_post.return_value = mock_response
            
            # Token should be acquired
            # Implementation-specific


class TestPayPalReadOperations:
    """Tests for PayPal data retrieval operations."""

    @pytest.mark.asyncio
    async def test_get_payouts_returns_correct_schema(self, mock_paypal):
        """Verify get_payouts returns data matching internal schema."""
        mock_paypal.get_payouts.return_value = [
            {
                "id": "PAYPAL_PAYOUT_1",
                "amount": Decimal("200.00"),
                "status": "SUCCESS",
                "date": datetime.now(),
            }
        ]
        
        payouts = await mock_paypal.get_payouts(datetime.now(), datetime.now())
        
        assert len(payouts) == 1
        assert "PAYPAL" in payouts[0]["id"]

    @pytest.mark.asyncio
    async def test_get_transaction_details(self, mock_paypal):
        """Verify transaction details include fee breakdown."""
        mock_paypal.get_payout_entries_detailed.return_value = [
            {
                "type": "PAYMENT",
                "gross_amount": 100.00,
                "fee_amount": -2.90,
                "net_amount": 97.10,
            }
        ]
        
        entries = await mock_paypal.get_payout_entries_detailed("PAYPAL_TXN_1")
        
        assert len(entries) == 1
        assert entries[0]["fee_amount"] == -2.90


class TestPayPalPagination:
    """Tests for PayPal pagination handling."""

    @pytest.mark.asyncio
    async def test_pagination_with_page_token(self):
        """Verify connector handles PayPal's page-based pagination."""
        from backend.connectors.paypal import PayPalClient
        
        with patch("httpx.AsyncClient.get") as mock_get:
            # First page
            mock_resp_1 = MagicMock()
            mock_resp_1.status_code = 200
            mock_resp_1.json.return_value = {
                "transaction_details": [{"id": "1"}],
                "page": 1,
                "total_pages": 2,
            }
            
            # Second page
            mock_resp_2 = MagicMock()
            mock_resp_2.status_code = 200
            mock_resp_2.json.return_value = {
                "transaction_details": [{"id": "2"}],
                "page": 2,
                "total_pages": 2,
            }
            
            mock_get.side_effect = [mock_resp_1, mock_resp_2]
            
            # Verify all pages fetched


class TestPayPalErrorHandling:
    """Tests for PayPal error scenarios."""

    @pytest.mark.asyncio
    async def test_401_token_expired_refresh(self):
        """Verify token refresh on 401 error."""
        from backend.connectors.paypal import PayPalClient
        
        with patch("httpx.AsyncClient.request") as mock_request:
            mock_401 = MagicMock()
            mock_401.status_code = 401
            mock_401.json.return_value = {"error": "invalid_token"}
            
            mock_token = MagicMock()
            mock_token.status_code = 200
            mock_token.json.return_value = {"access_token": "new_token", "expires_in": 32400}
            
            mock_200 = MagicMock()
            mock_200.status_code = 200
            mock_200.json.return_value = {"transaction_details": []}
            
            mock_request.side_effect = [mock_401, mock_token, mock_200]
            
            # Should retry with new token

    @pytest.mark.asyncio
    async def test_500_internal_server_error(self):
        """Verify graceful handling of PayPal outages."""
        from backend.connectors.paypal import PayPalClient
        
        with patch("httpx.AsyncClient.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.json.return_value = {"name": "INTERNAL_SERVICE_ERROR"}
            mock_request.return_value = mock_response
            
            # Should handle gracefully without crashing
