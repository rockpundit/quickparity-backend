import pytest
import time
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch
from backend.services.mock_generator import MockDataGenerator
from backend.connectors.simulated import SimulatedSquareClient, SimulatedQBOClient
from backend.services.reconciliation import ReconciliationEngine

@pytest.mark.performance
@pytest.mark.asyncio
async def test_high_volume_processing():
    """
    Generate 5,000 payouts and process them.
    We patch asyncio.sleep to avoid the 0.1s simulated latency per call, 
    measuring raw engine throughput.
    """
    # Patch sleep to speed up the loop
    with patch("asyncio.sleep", return_value=None):
        
        # 1. Setup
        generator = MockDataGenerator()
        
        # Instantiate Square Client (creates ~50 items by default)
        sq_client = SimulatedSquareClient(generator)
        
        # Instantiate QBO Client, linked to Square's ledger map
        qbo_client = SimulatedQBOClient(generator, universe_ledger_map=sq_client.ledger_map)
        
        # Clear pre-filled random data to ensure we control the count and source exactly
        sq_client.generated_payouts = {}
        sq_client.ledger_map = {}
        
        # 2. Boost volume to 5,000 items
        target_count = 5000
        
        print(f"Generating {target_count} mock Square items...")
        
        for _ in range(target_count):
            payout, ledger, scenario = generator.generate_payout(source="Square")
            sq_client.generated_payouts[payout.id] = payout
            sq_client.ledger_map[payout.id] = ledger
            
        assert len(sq_client.generated_payouts) == target_count
        
        # 3. Setup Engine
        engine = ReconciliationEngine(
            square_client=sq_client,
            stripe_client=None,
            shopify_client=None,
            paypal_client=None,
            qbo_client=qbo_client
        )
        
        # 4. Run Execution
        start_time = time.time()
        
        # Run for a broad period to catch all generated items (last 30 days)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=35)
        
        report = await engine.run_for_period(start_date, end_date)
        
        duration = time.time() - start_time
        
        # 5. Assertions
        processed_count = len(report)
        print(f"Processed {processed_count} payouts in {duration:.2f} seconds.")
        print(f"Throughput: {processed_count / duration:.2f} items/sec")
        
        assert processed_count >= target_count
        
        # Performance Goal: > 100 items/sec ? 
        # 5000 items in < 50 seconds (100 items/sec)
        # Note: If logging is heavy, it might be slower.
        assert duration < 60, f"Processing took too long: {duration:.2f}s"
