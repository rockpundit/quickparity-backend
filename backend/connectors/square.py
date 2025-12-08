import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

import httpx
from pydantic import ValidationError

from backend.models import Payout

logger = logging.getLogger(__name__)

class SquareClient:
    """
    Async client for Square API with rate limiting handling.
    """
    BASE_URL = "https://connect.squareup.com/v2"

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Square-Version": "2023-10-20", # Pin a recent API version
        }
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers=self.headers,
            timeout=30.0
        )

    async def close(self):
        await self.client.aclose()

    async def _request(self, method: str, endpoint: str, params: dict = None) -> dict:
        """
        Internal request method with exponential backoff for rate limits.
        """
        url = endpoint
        retries = 0
        max_retries = 5
        base_delay = 2

        while retries < max_retries:
            try:
                response = await self.client.request(method, url, params=params)
                
                if response.status_code == 429:
                    # Rate limited
                    logger.warning(f"Rate limited on {endpoint}. Retrying...")
                    # Respect retry-after if available, else exponential backoff
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        wait_time = int(retry_after)
                    else:
                        wait_time = base_delay * (2 ** retries)
                    
                    await asyncio.sleep(wait_time)
                    retries += 1
                    continue
                
                response.raise_for_status()
                return response.json()
            
            except httpx.HTTPError as e:
                logger.error(f"HTTP error on {endpoint}: {e}")
                raise

        raise Exception(f"Max retries exceeded for {endpoint}")

    async def get_payouts(self, status: str = "PAID", begin_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[Payout]:
        """
        Fetch payouts from Square.
        """
        endpoint = "/payouts"
        params = {"status": status}
        if begin_time:
            params["begin_time"] = begin_time.isoformat()
        if end_time:
            params["end_time"] = end_time.isoformat()

        if end_time:
            params["end_time"] = end_time.isoformat()

        # Simple pagination loop could be added here if needed, Square uses 'cursor'
        # For simplicity in this demo, fetching first page. 
        # TODO: Implement full pagination.

        data = await self._request("GET", endpoint, params=params)
        payouts_data = data.get("payouts", [])
        
        payouts = []
        for p_data in payouts_data:
            try:
                amount_money = Decimal(str(p_data["amount_money"]["amount"])) / 100
                
                # Fetch detailed fees
                payout_id = p_data["id"]
                fee_amount = await self.get_payout_fee(payout_id)
                
                created_at = datetime.fromisoformat(p_data["created_at"].replace("Z", "+00:00"))
                arrival_date = None
                if "arrival_date" in p_data:
                     # Square returns YYYY-MM-DD
                     arrival_date = datetime.strptime(p_data["arrival_date"], "%Y-%m-%d")

                payout = Payout(
                    id=p_data["id"],
                    status=p_data["status"],
                    amount_money=amount_money,
                    created_at=created_at,
                    arrival_date=arrival_date,
                    processing_fee=fee_amount
                )
                payouts.append(payout)
            except (ValidationError, KeyError) as e:
                logger.error(f"Error parsing payout {p_data.get('id')}: {e}")
                continue
                
        return payouts

    async def get_payout_fee(self, payout_id: str) -> Decimal:
        """
        Fetch payout entries to calculate total fees.
        """
        endpoint = f"/payouts/{payout_id}/payout-entries"
        
        # Similar simple fetching, assuming data fits in one page or just taking summary
        # Square payout entries can be many.
        
        data = await self._request("GET", endpoint)
        entries = data.get("payout_entries", [])
        
        total_fee_cents = 0
        
        for entry in entries:
            type_ = entry.get("type")
            if type_ in ["FEE", "PROCESSING_FEE", "ADJUSTMENT"]: 
                # Fees are usually negative in accounting terms, but Square might return them as distinct
                # We need the absolute magnitude of the fee to deduce Gross = Net + Fee
                # Square Net = Gross - Fee.
                # If entry amount is negative (deduction), we sum it up.
                
                amount_money = entry.get("gross_amount_money", {}) or entry.get("amount_money", {})
                amount = int(amount_money.get("amount", 0))
                
                # Square fees are negative in the payout entry often, or positive if it's a "Fee" object?
                # Usually: Sale +100, Fee -3. Net +97.
                # We want to know the total "Fee" part.
                
                if entry.get("type_payout_entry_uid"): # Example check, checking documentation mental model
                   pass

                # Assuming fee entries are negative amounts in the payout summary components
                if type_ in ["FEE", "PROCESSING_FEE"]:
                     # These are usually negative. We want the absolute sum to report "Fee".
                     total_fee_cents += abs(amount)

        return Decimal(total_fee_cents) / 100

    async def get_payout_entries_detailed(self, payout_id: str) -> List[dict]:

        """
        Fetch detailed entries for a payout.
        """
        endpoint = f"/payouts/{payout_id}/payout-entries"
        data = await self._request("GET", endpoint)
        entries = data.get("payout_entries", [])
        
        # We perform a pass to identify payment IDs if needed for tax lookup
        # For this implementation, we will assume the entry contains enough info
        # OR fetch payments if type is CHARGE.
        
        detailed = []
        for entry in entries:
            # If we need tax separation, we might need to fetch the payment object
            # if the payout entry doesn't have it.
            # Square Payout Entry has 'type', 'fee', 'gross', 'amount_money', 'source_payment_id'.
            
            if entry.get("type") in ["CHARGE", "PAYMENT"] and entry.get("source_payment_id"):
                 # Optional: fetch payment details for tax
                 # payment_details = await self.get_payment(entry["source_payment_id"])
                 # entry["tax_money"] = payment_details.get("tax_money")
                 pass

            detailed.append(entry)
            
        return detailed

