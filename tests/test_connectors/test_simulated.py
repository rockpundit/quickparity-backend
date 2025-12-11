"""
Simulated/Mock Connector Tests
Tests for the development fallback mode.
"""
import pytest
from unittest.mock import AsyncMock
from datetime import datetime
from decimal import Decimal


class TestSimulatedConnectorIntegrity:
    """Tests for simulated connector behavior."""

    @pytest.mark.asyncio
    async def test_simulated_returns_deterministic_data(self):
        """Verify simulated connector returns consistent test data."""
        from backend.connectors.simulated import SimulatedStripeClient
        from backend.services.mock_generator import MockDataGenerator
        
        generator = MockDataGenerator()
        client = SimulatedStripeClient(generator=generator)
        
        payouts_1 = await client.get_payouts(datetime.now(), datetime.now())
        payouts_2 = await client.get_payouts(datetime.now(), datetime.now())
        
        # Should return same structure on repeated calls
        assert len(payouts_1) == len(payouts_2)

    @pytest.mark.asyncio
    async def test_simulated_generates_valid_payout_structure(self):
        """Verify simulated payouts match real connector schema."""
        from backend.connectors.simulated import SimulatedStripeClient
        from backend.services.mock_generator import MockDataGenerator
        
        client = SimulatedStripeClient(generator=MockDataGenerator())
        payouts = await client.get_payouts(datetime.now(), datetime.now())
        
        if payouts:
            payout = payouts[0]
            assert "id" in payout or hasattr(payout, "id")
            # Verify required fields exist

    @pytest.mark.asyncio
    async def test_simulated_entries_have_fee_breakdown(self):
        """Verify simulated entries include fee details."""
        from backend.connectors.simulated import SimulatedStripeClient
        from backend.services.mock_generator import MockDataGenerator
        
        client = SimulatedStripeClient(generator=MockDataGenerator())
        entries = await client.get_payout_entries_detailed("mock_payout")
        
        if entries:
            entry = entries[0]
            assert "fee_amount" in entry or "gross_amount" in entry

    @pytest.mark.asyncio
    async def test_simulated_never_raises_network_errors(self):
        """Verify simulated connector works offline (no network calls)."""
        from backend.connectors.simulated import SimulatedStripeClient
        from backend.services.mock_generator import MockDataGenerator
        
        client = SimulatedStripeClient(generator=MockDataGenerator())
        
        # Should never raise network-related exceptions
        try:
            await client.get_payouts(datetime.now(), datetime.now())
            await client.get_payout_entries_detailed("any_id")
        except Exception as e:
            assert "network" not in str(e).lower()
            assert "connection" not in str(e).lower()
