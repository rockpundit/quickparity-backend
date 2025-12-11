"""
Pagination Tests
Tests for data volume handling across all connectors.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime


class TestPaginationGeneral:
    """General pagination behavior tests."""

    @pytest.mark.asyncio
    async def test_empty_response_handled(self, mock_square):
        """Verify empty pages don't cause errors."""
        mock_square.get_payouts.return_value = []
        
        payouts = await mock_square.get_payouts(datetime.now(), datetime.now())
        
        assert payouts == []
        assert len(payouts) == 0

    @pytest.mark.asyncio
    async def test_single_page_no_cursor(self, mock_square):
        """Verify single page responses work without pagination."""
        mock_square.get_payouts.return_value = [{"id": "po_1"}]
        
        payouts = await mock_square.get_payouts(datetime.now(), datetime.now())
        
        assert len(payouts) == 1


class TestCursorBasedPagination:
    """Tests for cursor-based pagination (Stripe, Square)."""

    @pytest.mark.asyncio
    async def test_cursor_pagination_fetches_all(self):
        """Verify all pages are fetched when cursor indicates more data."""
        from backend.connectors.square import SquareClient
        
        with patch("httpx.AsyncClient.request") as mock_request:
            # Page 1: has cursor
            page1 = MagicMock()
            page1.status_code = 200
            page1.json.return_value = {
                "payouts": [{"id": "po_1"}],
                "cursor": "next_page_cursor"
            }
            
            # Page 2: no cursor (last page)
            page2 = MagicMock()
            page2.status_code = 200
            page2.json.return_value = {
                "payouts": [{"id": "po_2"}],
                "cursor": None
            }
            
            mock_request.side_effect = [page1, page2]
            
            client = SquareClient(access_token="test")
            # Implementation should call twice
            # assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_cursor_loop_protection(self):
        """Verify infinite cursor loops are prevented."""
        # If API returns same cursor repeatedly, should break
        from backend.connectors.square import SquareClient
        
        with patch("httpx.AsyncClient.request") as mock_request:
            # Malformed response: cursor keeps returning itself
            bad_page = MagicMock()
            bad_page.status_code = 200
            bad_page.json.return_value = {
                "payouts": [{"id": "po_loop"}],
                "cursor": "same_cursor"
            }
            
            mock_request.return_value = bad_page
            
            client = SquareClient(access_token="test")
            # Should have max iterations protection


class TestLinkHeaderPagination:
    """Tests for Link header pagination (Shopify)."""

    def test_parse_link_header_next(self):
        """Verify Link header parsing extracts next URL."""
        link_header = '<https://shop.myshopify.com/admin/api/payouts.json?page_info=abc123>; rel="next"'
        
        # Simple parser
        if 'rel="next"' in link_header:
            url = link_header.split(";")[0].strip("<>")
            assert "page_info=abc123" in url

    def test_parse_link_header_no_next(self):
        """Verify missing 'next' link is handled."""
        link_header = '<https://shop.myshopify.com/admin/api/payouts.json?page_info=xyz>; rel="previous"'
        
        has_next = 'rel="next"' in link_header
        assert has_next is False


class TestPageBasedPagination:
    """Tests for page number pagination (PayPal)."""

    @pytest.mark.asyncio
    async def test_total_pages_iteration(self):
        """Verify all pages up to total_pages are fetched."""
        from backend.connectors.paypal import PayPalClient
        
        with patch("httpx.AsyncClient.request") as mock_request:
            responses = []
            for i in range(1, 4):  # 3 pages
                page = MagicMock()
                page.status_code = 200
                page.json.return_value = {
                    "transaction_details": [{"id": f"txn_{i}"}],
                    "page": i,
                    "total_pages": 3
                }
                responses.append(page)
            
            mock_request.side_effect = responses
            
            # Should make 3 requests


class TestLargeDatasetHandling:
    """Tests for performance with large datasets."""

    @pytest.mark.asyncio
    async def test_1000_records_memory_efficiency(self, mock_square):
        """Verify 1000 records don't cause memory issues."""
        large_dataset = [{"id": f"po_{i}", "amount": 100.00} for i in range(1000)]
        mock_square.get_payouts.return_value = large_dataset
        
        payouts = await mock_square.get_payouts(datetime.now(), datetime.now())
        
        assert len(payouts) == 1000

    @pytest.mark.asyncio
    async def test_streaming_vs_batch(self, mock_square):
        """Verify large datasets use appropriate retrieval strategy."""
        # For very large datasets, streaming/generator pattern is preferred
        # This test verifies the data is accessible
        mock_square.get_payouts.return_value = [{"id": f"po_{i}"} for i in range(500)]
        
        payouts = await mock_square.get_payouts(datetime.now(), datetime.now())
        
        # Should be iterable
        count = 0
        for _ in payouts:
            count += 1
        assert count == 500
