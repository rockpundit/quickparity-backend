import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict

from backend.models import Payout, LedgerEntry
from backend.services.mock_generator import MockDataGenerator

logger = logging.getLogger(__name__)

class SimulatedBaseClient:
    def __init__(self, generator: MockDataGenerator):
        self.generator = generator
        self.generated_payouts: Dict[str, Payout] = {}
        # Map Payout ID to potential Ledger Entry (for QBO simulation)
        self.ledger_map: Dict[str, Optional[LedgerEntry]] = {} 
        self._prefill_data()

    def _prefill_data(self, count=50):
        # Generate initial batch of data
        for _ in range(count):
            payout, ledger, scenario = self.generator.generate_payout()
            self.generated_payouts[payout.id] = payout
            self.ledger_map[payout.id] = ledger

    async def close(self):
        pass


class SimulatedStripeClient(SimulatedBaseClient):
    """
    Simulates Stripe API.
    """
    async def get_payouts(self, status: str = "paid", begin_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[Payout]:
        # Filter generated payouts by date and source
        results = []
        for p in self.generated_payouts.values():
            if p.source != "Stripe":
                continue
            
            # Simple date filtering
            if begin_time and p.created_at < begin_time:
                continue
            if end_time and p.created_at > end_time:
                continue
                
            results.append(p)
            
        # Simulate network latency
        await asyncio.sleep(0.1)
        return results

    async def get_payout_entries_detailed(self, payout_id: str) -> List[dict]:
        payout = self.generated_payouts.get(payout_id)
        if not payout:
            return []
            
        # Reverse engineer entries from the Payout object
        # Gross = Net + Fee (approximation for simulation)
        # We constructed Net = Charge - Fee.
        # So Charge = Net + Fee.
        
        net = payout.amount_money
        fee = payout.processing_fee
        gross = net + fee
        
        # Determine if it's a refund scenario (hacky detection from generator logic?)
        # For simplicty, just return one big CHARGE entry matching the totals
        
        return [{
            "type": "CHARGE",
            "gross_amount": float(gross),
            "fee_amount": float(fee),
            "net_amount": float(net),
            "currency": payout.currency,
            "source_id": "sim_charge_123"
        }]


class SimulatedSquareClient(SimulatedBaseClient):
    """
    Simulates Square API.
    """
    async def get_payouts(self, status: str = "PAID", begin_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[Payout]:
        results = []
        for p in self.generated_payouts.values():
            if p.source != "Square":
                continue
            if begin_time and p.created_at < begin_time: continue
            if end_time and p.created_at > end_time: continue
            results.append(p)
            
        await asyncio.sleep(0.1)
        return results

    async def get_payout_entries_detailed(self, payout_id: str) -> List[dict]:
        payout = self.generated_payouts.get(payout_id)
        if not payout: return []
        
        net = payout.amount_money
        fee = payout.processing_fee
        gross = net + fee
        
        return [{
            "type": "CHARGE", 
            "gross_amount": float(gross),
            "fee_amount": float(fee),
            "net_amount": float(net),
             "source_payment_id": "sim_pay_sq"
        }]


class SimulatedShopifyClient(SimulatedBaseClient):
    async def get_payouts(self, status: str = "paid", begin_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[Payout]:
        results = []
        for p in self.generated_payouts.values():
            if p.source != "Shopify": continue
            if begin_time and p.created_at < begin_time: continue
            if end_time and p.created_at > end_time: continue
            results.append(p)
        await asyncio.sleep(0.1)
        return results

    async def get_payout_entries_detailed(self, payout_id: str) -> List[dict]:
        payout = self.generated_payouts.get(payout_id)
        if not payout: return []
        net = payout.amount_money
        fee = payout.processing_fee
        gross = net + fee
        return [{
            "type": "ORDER", 
            "gross_amount": float(gross),
            "fee_amount": float(fee), 
            "net_amount": float(net)
        }]

class SimulatedPayPalClient(SimulatedBaseClient):
    async def get_payouts(self, status: str = "SUCCESS", begin_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[Payout]:
        results = []
        for p in self.generated_payouts.values():
            if p.source != "PayPal": continue
            if begin_time and p.created_at < begin_time: continue
            if end_time and p.created_at > end_time: continue
            results.append(p)
        await asyncio.sleep(0.1)
        return results

    async def get_payout_entries_detailed(self, payout_id: str) -> List[dict]:
        # PayPal is simple in our mock
        return []


class SimulatedQBOClient(SimulatedBaseClient):
    """
    Simulates QBO API.
    Shares state with other clients via the shared 'generator' 
    BUT needs access to the SAME dataset of payouts to find matches.
    
    The 'SimulatedBaseClient' creates its OWN data on init. 
    Ideally, we should pass a shared 'SimulationContext' or 'DataStore'.
    
    Refactor: We'll pass the *same* instance of a 'SimulationStore' to all clients.
    For this 'SimulatedBaseClient', we will just assume we can search the "Universe" of generated data.
    
    Workaround: QBO Client will hold a reference to the universe of ledger entries.
    """
    def __init__(self, generator: MockDataGenerator, universe_ledger_map: Dict[str, Optional[LedgerEntry]]):
        self.generator = generator
        self.ledger_map = universe_ledger_map
        self.journal_entries = [] # Store created JEs
        
    async def close(self):
        pass

    async def find_deposit(self, amount: Decimal, date_from: datetime, date_to: datetime, target_account_type: str = None) -> Optional[LedgerEntry]:
        # Scan the universe of Ledger Entries
        # Inefficnet O(N) but fine for simulation
        
        await asyncio.sleep(0.05)
        
        for ledger in self.ledger_map.values():
            if not ledger:
                continue
            
            # Match Amount
            # Note: Ledger Amount might not be exactly equal to Payout Net if there is a variance scenario
            # But the 'find_deposit' logic usually looks for exact match or potential partial match?
            # Standard logic: Exact Match on Amount.
            
            if ledger.total_amount == amount:
                 # Date check (loose)
                 if date_from <= ledger.txn_date <= date_to:
                     return ledger
                     
        return None

    async def create_journal_entry(self, deposit_id: str, variance_amount: Decimal, idempotency_key: str):
        logger.info(f"SIMULATION: Creating Journal Entry for Deposit {deposit_id}, Variance: {variance_amount}")
        self.journal_entries.append({
            "deposit_id": deposit_id,
            "variance": variance_amount,
            "key": idempotency_key,
            "created_at": datetime.now()
        })
        return {"Id": f"je_sim_{len(self.journal_entries)}"}

