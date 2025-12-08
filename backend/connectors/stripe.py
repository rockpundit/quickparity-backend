import logging
import stripe
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from backend.models import Payout

logger = logging.getLogger(__name__)

class StripeClient:
    """
    Async client warpper for Stripe API.
    Uses the official stripe-python library which handles retries and rate limits.
    """
    
    def __init__(self, access_token: str):
        self.api_key = access_token
        stripe.api_key = self.api_key
        # Note: stripe-python is synchronous by default, but has async support in newer versions.
        # However, for consistency with the codebase which is async, we can wrap calls or use 
        # stripe.HttpClient to be async. 
        # For simplicity in this iteration effectively acting as a sync wrapper or 
        # using the AsyncStripeClient if available in v5+ but standard usage is often sync.
        # We will assume standard sync operation wrapped in async defs for interface compatibility
        # OR use `stripe.StripeClient` (v2) if we want to be modern.
        # Let's stick to the familiar `stripe.Payout.list` pattern but wrapped.

    async def close(self):
        # Stripe library doesn't strictly require closing if using global client,
        # but good for interface consistency.
        pass

    async def get_payouts(self, status: str = "paid", begin_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[Payout]:
        """
        Fetch payouts from Stripe.
        """

        params = {
            "limit": 100,
            "status": status
        }
        
        # Stripe expects unix timestamps for date filtering
        if begin_time:
            params["created"] = {"gte": int(begin_time.timestamp())}
        if end_time:
            if "created" not in params: params["created"] = {}
            params["created"]["lte"] = int(end_time.timestamp())

        try:
            # Running sync call in executor to avoid blocking event loop
            # Real world: usage of stripe.aio or run_in_executor
            payouts_iter = stripe.Payout.list(**params)
            
            payouts = []
            for p in payouts_iter.auto_paging_iter():
                # Stripe amounts are in cents
                amount = Decimal(p.amount) / 100
                
                # Stripe Payouts don't always have the fee directly on the object depending on API version,
                # usually it's calculated from the balance transactions.
                # However, for 'paid' payouts, we can try to inspect the balance transactions.
                # Simplification: We will fetch details later.
                
                created_at = datetime.fromtimestamp(p.created)
                arrival_date = datetime.fromtimestamp(p.arrival_date)
                
                # Stripe status: 'paid', 'pending', 'in_transit', 'canceled', 'failed'
                status_map = p.status.upper()
                
                payouts.append(Payout(
                    id=p.id,
                    status=status_map,
                    amount_money=amount,
                    created_at=created_at,
                    arrival_date=arrival_date,
                    currency=p.currency.upper(),
                    source="Stripe"
                    # processing_fee is 0.00 initially until we fetch details
                ))
                
            return payouts

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API Error: {e}")
            return []

    async def get_payout_entries_detailed(self, payout_id: str) -> List[dict]:
        """
        Fetch balance transactions for a payout to calculate fees and gross.
        """
        try:
            # Need to expand balance_transaction? No, use BalanceTransaction.list(payout=...)
            txns = stripe.BalanceTransaction.list(payout=payout_id, limit=100)
            
            detailed = []
            for txn in txns.auto_paging_iter():
                # txn.amount is the Net amount affecting the balance
                # txn.fee is the fee
                # txn.type ('charge', 'refund', 'adjustment', etc)
                
                # We need to reconstruct the "Gross" 
                # For a Charge: Net = Gross - Fee => Gross = Net + Fee
                # txn.amount is usually positive for charge, txn.fee is positive integer
                
                entry = {
                    "type": txn.type.upper(), # CHARGE, REFUND
                    "net_amount": Decimal(txn.amount) / 100,
                    "fee_amount": Decimal(txn.fee) / 100,
                    "gross_amount": (Decimal(txn.amount) + Decimal(txn.fee)) / 100,
                    "currency": txn.currency.upper(),
                    "source_id": txn.source
                }
                detailed.append(entry)
                
            return detailed
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe Error fetching entries for {payout_id}: {e}")
            return []
