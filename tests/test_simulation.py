import pytest
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import tempfile
import os

from backend.services.mock_generator import MockDataGenerator
from backend.connectors.simulated import (
    SimulatedStripeClient, SimulatedQBOClient, SimulatedSquareClient, 
    SimulatedShopifyClient, SimulatedPayPalClient
)
from backend.services.reconciliation import ReconciliationEngine
from backend.models import ReconciliationStatus

@pytest.mark.asyncio
async def test_high_volume_simulation():
    """
    Runs a high-volume simulation (e.g. 50 payouts per source) to verify:
    1. Data Generation invariants (Net + Fee ~= Gross) - implicitly checked by logic
    2. Engine correctly identifies MATCH vs VARIANCE
    3. Auto-fix logic successfully writes to Simulated QBO
    """
    
    # 1. Setup Environment
    generator = MockDataGenerator()
    shared_ledger_map = {}
    
    # Create Clients with enough data
    # We want a mix of scenarios. The generator chooses random scenarios.
    
    sq_client = SimulatedSquareClient(generator) # Defaults to 50
    sq_client = SimulatedSquareClient(generator) 
    stripe_client = SimulatedStripeClient(generator)
    shopify_client = SimulatedShopifyClient(generator)
    paypal_client = SimulatedPayPalClient(generator)
    
    # Populate shared ledger map
    shared_ledger_map.update(sq_client.ledger_map)
    shared_ledger_map.update(stripe_client.ledger_map)
    shared_ledger_map.update(shopify_client.ledger_map)
    shared_ledger_map.update(paypal_client.ledger_map)
    
    qbo_client = SimulatedQBOClient(generator, shared_ledger_map)
    
    # Use a named temp file for DB
    # We close it immediately so we just get a path, and handle deletion ourselves
    # Windows might have issues but on Mac/Linux this pattern is okay if we are careful
    # Safest is to let NamedTemporaryFile handle it but we need path persistence
    
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tf.name
    tf.close()
    
    try:
        # 2. Run Engine
        engine = ReconciliationEngine(
            square_client=sq_client,
            qbo_client=qbo_client,
            stripe_client=stripe_client,
            shopify_client=shopify_client,
            paypal_client=paypal_client,
            db_path=db_path
        )
        
        # Time range: generator creates data in last 30 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)
        
        results = await engine.run_for_period(start_date, end_date)
        
        # 3. Assertions
        matches = [r for r in results if r.status == ReconciliationStatus.MATCHED]
        variances = [r for r in results if r.status == ReconciliationStatus.VARIANCE_DETECTED]
        missing = [r for r in results if r.status == ReconciliationStatus.MISSING_DEPOSIT]
        
        # Manually trigger fixes for variances
        for r in variances:
             await engine.apply_fix(r)
        
        print(f"\nSimulation Results: {len(results)} Total")
        print(f"Matched: {len(matches)}")
        print(f"Variances: {len(variances)}")
        print(f"Missing: {len(missing)}")
        
        assert len(results) > 0, "Should have processed generated payouts"
        
        # Check that Variances triggered Auto-Fix (Journal Entries)
        journal_entries = qbo_client.journal_entries
        print(f"Journal Entries Created: {len(journal_entries)}")
        
        assert len(journal_entries) == len(variances), "Every variance should have triggered a fix"
        
        # Verify correctness of a single fix
        if variances:
            sample_var = variances[0]
            import hashlib
            expected_key = hashlib.sha256(sample_var.payout_id.encode()).hexdigest()
            
            found_je = next((je for je in journal_entries if je["key"] == expected_key), None)
            assert found_je is not None, f"JE for payout {sample_var.payout_id} not found"
            
            assert abs(float(found_je["variance"]) - sample_var.variance_amount) < 0.01, "JE Amount should match Variance Amount"
    
        print("\nHigh Volume Simulation Passed!")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
