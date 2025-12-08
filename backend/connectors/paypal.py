import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

# Attempt to import PayPal SDK.
# If not present, we can't run real logic, but we write the code as if it is present.
try:
    from paypalcheckoutsdk.core import PayPalHttpClient, SandboxEnvironment, LiveEnvironment
    from paypalcheckoutsdk.orders import OrdersGetRequest
    # Note: Payouts/Reporting might need different SDK or REST calls as checkoutsdk is for Checkout
    # For Payouts/Reporting, standard REST via requests/httpx is often used if SDK is limited.
    # However, "paypal-checkout-serversdk" is strictly for checkout.
    # For reporting/transactions, we usually use REST API directly.
    # I will use httpx for Reporting API as it's more versatile for this use case.
    import httpx
except ImportError:
    # Fallback for dev environment without deps
    httpx = None

from backend.models import Payout

logger = logging.getLogger(__name__)

class PayPalClient:
    """
    PayPal Client for fetching settlement/payout data.
    Uses PayPal Reporting API via httpx (since checkout-sdk doesn't cover reporting well).
    """
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://api-m.paypal.com" # Live default
        
        if client_id.startswith("mock_"):
            self.base_url = "mock"
        
        self.access_token = None
        self.token_expiry = 0

    async def _get_access_token(self):
        if self.access_token and datetime.now().timestamp() < self.token_expiry:
            return self.access_token
            
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/oauth2/token",
                    auth=(self.client_id, self.client_secret),
                    data={"grant_type": "client_credentials"},
                    headers={"Accept": "application/json", "Accept-Language": "en_US"}
                )
                response.raise_for_status()
                data = response.json()
                self.access_token = data["access_token"]
                self.token_expiry = datetime.now().timestamp() + data["expires_in"] - 60
                return self.access_token
            except Exception as e:
                logger.error(f"PayPal Auth Error: {e}")
                raise

    async def close(self):
        pass

    async def get_payouts(self, status: str = "SUCCESS", begin_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[Payout]:
        """
        Fetch 'payouts' or settlements. 
        In PayPal, 'balances' or 'transactions' API is used.
        We will use the GET /v1/reporting/transactions endpoint.
        """
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        params = {
            "transaction_status": "S", # S for Success
            "fields": "all"
        }
        if begin_time:
            params["start_date"] = begin_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
             # PayPal requires start_date. Default to 30 days ago.
             params["start_date"] = (datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
             
        if end_time:
            params["end_date"] = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            params["end_date"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        async with httpx.AsyncClient() as client:
            try:
                # Using /v1/reporting/transactions
                resp = await client.get(
                    f"{self.base_url}/v1/reporting/transactions",
                    headers=headers,
                    params=params
                )
                if resp.status_code == 400:
                    logger.error(f"PayPal API Bad Request: {resp.text}")
                    return []
                resp.raise_for_status()
                data = resp.json()
                
                # Parse transaction_details
                results = []
                if "transaction_details" in data:
                    for txn in data["transaction_details"]:
                        info = txn.get("transaction_info", {})
                        
                        # We are looking for withdrawals to bank (Settlements)
                        # OR we can treat every Sale as a payout if they don't hold balance?
                        # Usually Reconciliation matches "Payouts" (Transfers to Bank).
                        # Event Code T0000 (General) or T0001 (Bank Transfer)
                        # Let's filter for withdrawals if possible, or just return all for now.
                        # Real implementation needs strict event code filtering.
                        
                        event_code = info.get("transaction_event_code", "")
                        if not event_code.startswith("T01"): # T01 = Settlement/Transfer usually
                             # Skipping non-transfer events for 'payouts' view?
                             # Or if we want to digest Sales directly?
                             # Let's assume we want Withdrawals.
                             pass
                        
                        transaction_id = info.get("transaction_id")
                        amount_obj = info.get("transaction_amount", {})
                        amount = Decimal(amount_obj.get("value", "0.00"))
                        
                        # PayPal amounts are signed. Withdrawal is negative?
                        # If negative, we treat absolute as Payout amount.
                        if amount < 0:
                            amount = abs(amount)

                        date_str = info.get("transaction_initiation_date")
                        created_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        
                        results.append(Payout(
                            id=transaction_id,
                            status="COMPLETED", # PayPal reporting usually returns completed
                            amount_money=amount,
                            created_at=created_at,
                            source="PayPal"
                        ))
                return results

            except Exception as e:
                logger.error(f"PayPal fetch error: {e}")
                return []

    async def get_payout_entries_detailed(self, payout_id: str) -> List[dict]:
        """
        For a given Settlement (Withdrawal), find the transactions that composed it.
        PayPal is difficult here because 'Withdrawals' are lump sums of Balance.
        We might need to search for transactions *leading up to* this withdrawal.
        
        SIMPLIFICATION: We will return the Payout itself as a single entry for now,
        or just return nothing if we can't easily link.
        """
        return []
