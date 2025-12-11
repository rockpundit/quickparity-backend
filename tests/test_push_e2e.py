
import sys
import os
import asyncio
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.getcwd())

from backend.services.mock_generator import MockDataGenerator
from backend.connectors.simulated import SimulatedSquareClient, SimulatedQBOClient, SimulatedStripeClient
from backend.services.reconciliation import ReconciliationEngine

async def run_push_test():
    print("Running Push Model E2E Test...")
    
    generator = MockDataGenerator()
    shared_ledger_map = {}
    
    sq_client = SimulatedSquareClient(generator)
    stripe_client = SimulatedStripeClient(generator)
    
    # We DO NOT populate shared_ledger_map initially from clients 
    # to force MISSING_DEPOSIT scenarios.
    # shared_ledger_map.update(sq_client.ledger_map) 
    
    # Actually, let's keep it empty to simulate 100% missing.
    
    qbo_client = SimulatedQBOClient(generator, shared_ledger_map)
    
    engine = ReconciliationEngine(sq_client, qbo_client, stripe_client=stripe_client)
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    # Configure Settings for Push
    tenant_settings = {
        "enable_deposit_push": True,
        "default_undeposited_funds_account_id": "123_undep",
        "deposit_account_mapping": {
            "square": "456_checking",
            "stripe": "456_checking"
        }
    }
    
    print(f"Initial Ledger Map Size: {len(shared_ledger_map)} (Should be 0)")
    
    results = await engine.run_for_period(start_date, end_date, tenant_settings=tenant_settings)
    
    stats = {}
    created_count = 0
    for r in results:
        stats[r.status] = stats.get(r.status, 0) + 1
        if r.variance_reason == "Auto-Created via Push Model":
            created_count += 1
            
    print("\nPush Test Results:")
    print(stats)
    print(f"Auto-Created Deposits: {created_count}")
    
    # Verify Ledger Map grew
    print(f"Final Ledger Map Size: {len(qbo_client.ledger_map)}")
    
    if created_count > 0 and stats.get("MATCHED", 0) > 0:
        print("SUCCESS: Push Model active.")
    else:
        print("FAILURE: Push Model did not create deposits.")

if __name__ == "__main__":
    asyncio.run(run_push_test())
