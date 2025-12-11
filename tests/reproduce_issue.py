
import sys
import os
import asyncio
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.getcwd())

from backend.services.mock_generator import MockDataGenerator
from backend.connectors.simulated import SimulatedSquareClient, SimulatedQBOClient, SimulatedStripeClient
from backend.services.reconciliation import ReconciliationEngine

async def run_integration_test():
    print("Running Integration Test...")
    
    # Mirroring logic from routes.py
    generator = MockDataGenerator()
    shared_ledger_map = {}
    
    sq_client = SimulatedSquareClient(generator)
    # Stripe client just to populate ledger map potentially?
    stripe_client = SimulatedStripeClient(generator)
    
    shared_ledger_map.update(sq_client.ledger_map)
    shared_ledger_map.update(stripe_client.ledger_map)
    
    qbo_client = SimulatedQBOClient(generator, shared_ledger_map)
    
    # Engine
    engine = ReconciliationEngine(sq_client, qbo_client, stripe_client=stripe_client)
    
    # Run
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    print(f"Aggregated Ledger Map Size: {len(shared_ledger_map)}")
    
    results = await engine.run_for_period(start_date, end_date)
    
    stats = {}
    for r in results:
        stats[r.status] = stats.get(r.status, 0) + 1
        if r.status == "MISSING_DEPOSIT":
             print(f"MISSING: Payout {r.payout_id} Amt: {r.net_deposit}")
             
    print("\nIntegration Results:")
    print(stats)

if __name__ == "__main__":
    asyncio.run(run_integration_test())
