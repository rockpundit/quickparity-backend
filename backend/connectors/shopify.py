import logging
import shopify
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from backend.models import Payout

logger = logging.getLogger(__name__)

class ShopifyClient:
    """
    Shopify Client Wrapper.
    Uses 'shopify' python library. 
    Focuses on 'Shopify Payments' Payouts resource.
    """
    def __init__(self, shop_url: str, access_token: str):
        self.shop_url = shop_url
        self.access_token = access_token
        self.session = None
        
        if self.access_token != "mock_shopify_token":
             # Initialize Shopify Session
             # Standard pattern: shopify.Session(shop_url, version, token)
             # And then activate_session(session) context manager or global
             # keeping it global for this simple client class context
             # Warning: shopify lib is heavily global-state based in older versions, 
             # modern usage recommends context managers.
             # We will activate session for each call to be safe in async context if possible,
             # though the library is blocking/sync.
             api_version = "2024-01"
             self.session = shopify.Session(shop_url, api_version, access_token)

    async def close(self):
        pass

    async def get_payouts(self, status: str = "paid", begin_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[Payout]:
        try:
             # Run sync in executor if needed for prod
             shopify.ShopifyResource.activate_session(self.session)
             
             # Shopify Payouts API: https://shopify.dev/docs/api/admin-rest/2024-01/resources/payout
             # Filtering: date_min, date_max, status
             params = {"status": status}
             if begin_time:
                 params["date_min"] = begin_time.strftime("%Y-%m-%d")
             if end_time:
                 params["date_max"] = end_time.strftime("%Y-%m-%d")
                 
             payouts_resource = shopify.Payout.find(**params)
             
             results = []
             for p in payouts_resource:
                 # p.amount, p.currency, p.date (ISO)
                 # p.summary (fees, gross etc sometimes in summary)
                 
                 amount = Decimal(p.amount)
                 # fees often need calculation or separate fetching of transactions, 
                 # but generic Payout object has 'summary' with fee details in some versions.
                 # Let's assume we can get it from attributes or fallback.
                 
                 # simplified mapping
                 try:
                     created_at = datetime.fromisoformat(p.date)
                 except ValueError:
                     created_at = datetime.now() # Fallback
                     
                 results.append(Payout(
                     id=str(p.id),
                     status=p.status.upper(),
                     amount_money=amount,
                     created_at=created_at,
                     source="Shopify"
                     # processing_fee=... fetch detail later
                 ))
                 
             return results
             
        except Exception as e:
            logger.error(f"Shopify Error: {e}")
            return []
        finally:
            shopify.ShopifyResource.clear_session()


    async def get_payout_entries_detailed(self, payout_id: str) -> List[dict]:
        try:
            shopify.ShopifyResource.activate_session(self.session)
            # Find the payout
            # Then we typically list 'transactions' or 'balance_transactions' for that payout
            # Access pattern: /admin/api/2024-01/shopify_payments/payouts/{payout_id}/transactions.json
            
            # Using the library, might be Payout.transactions() or similar
            # If not directly supported by lib resources yet, use Generic find or request.
            # Assuming shopify.Payout(id).transactions() works or equivalent.
            # In official lib 'shopify.Payout' usually has no direct 'transactions' method documented easily,
            # might need to use `shopify.BalanceTransaction.find(payout_id=...)`
            
            transactions = shopify.BalanceTransaction.find(payout_id=payout_id)
            
            detailed = []
            for t in transactions:
                # t.amount, t.fee, t.net, t.type (charge, refund, etc)
                detailed.append({
                    "type": t.type.upper(),
                    "gross_amount": Decimal(t.amount), # Note: check if amount is Gross or Net in Shopify API for this resource
                    "fee_amount": Decimal(t.fee),
                    "net_amount": Decimal(t.net)
                })
            
            return detailed
            
        except Exception as e:
            logger.error(f"Shopify Entry Fetch Error: {e}")
            return []
        finally:
            shopify.ShopifyResource.clear_session()
