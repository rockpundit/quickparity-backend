import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

import httpx

from backend.models import LedgerEntry

logger = logging.getLogger(__name__)

class QBOClient:
    """
    Async client for QuickBooks Online API.
    """
    def __init__(self, realm_id: str, access_token: str, is_sandbox: bool = True):
        self.realm_id = realm_id
        self.access_token = access_token
        self.base_url = "https://sandbox-quickbooks.api.intuit.com/v3/company" if is_sandbox else "https://quickbooks.api.intuit.com/v3/company"
        
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        self.client = httpx.AsyncClient(
            base_url=f"{self.base_url}/{self.realm_id}",
            headers=self.headers,
            timeout=30.0
        )

    async def close(self):
        await self.client.aclose()
        
    async def _query(self, query_sql: str) -> dict:
        """
        Execute a QBO SQL query.
        """
        endpoint = "/query"
        params = {"query": query_sql}
        
        # Simple retry logic similar to Square
        retries = 0
        max_retries = 3
        
        while retries < max_retries:
            try:
                response = await self.client.get(endpoint, params=params)
                
                if response.status_code == 429:
                    logger.warning("QBO Rate Limit hit. Retrying...")
                    await asyncio.sleep(2 * (retries + 1))
                    retries += 1
                    continue
                    
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"QBO Query Error: {e}")
                raise

        raise Exception("QBO Max Retries Exceeded")

    async def find_deposit(self, amount: Decimal, date_from: datetime, date_to: datetime, target_account_type: str = None) -> Optional[LedgerEntry]:
        """
        Find a deposit matching the net amount within a date range.
        Optional: Filter by target_account_type ('checking', 'undeposited')
        """
        
        formatted_date_from = date_from.strftime("%Y-%m-%d")
        formatted_date_to = date_to.strftime("%Y-%m-%d")
        
        # Query generic Deposit
        query = f"SELECT * FROM Deposit WHERE TxnDate >= '{formatted_date_from}' AND TxnDate <= '{formatted_date_to}'"
        
        data = await self._query(query)
        deposits = data.get("QueryResponse", {}).get("Deposit", [])
        
        for dep in deposits:
            dep_amount = Decimal(str(dep.get("TotalAmt", 0)))
            if dep_amount == amount:
                
                # Check Account Mapping if specified
                if target_account_type:
                    account_ref = dep.get("DepositToAccountRef", {})
                    acct_name = account_ref.get("name", "").lower()
                    
                    # Strict check against user configuration
                    if target_account_type.lower() not in acct_name:
                         continue
                
                return self._parse_ledger_entry(dep)
        
        return None

    def _parse_ledger_entry(self, data: dict) -> LedgerEntry:
        # Check for lines that look like fees
        has_fee = False
        fee_amt = Decimal("0.00")
        
        lines = data.get("Line", [])
        for line in lines:
            # Heuristic: Check if line is negative or linked to an expense account
            # In a real app, we'd check the AccountRef against known Fee accounts.
            amount = Decimal(str(line.get("Amount", 0)))
            if amount < 0:
                has_fee = True
                fee_amt += amount # Summing up negative amounts

        return LedgerEntry(
            id=data["Id"],
            txn_date=datetime.strptime(data["TxnDate"], "%Y-%m-%d"),
            total_amount=Decimal(str(data["TotalAmt"])),
            has_fee_line_item=has_fee,
            fee_amount=fee_amt
        )

    async def create_journal_entry(self, deposit_id: str, variance_amount: Decimal, idempotency_key: str, fee_account_id: str, undeposited_funds_account_id: str):
        """
        Create a Journal Entry to fix the variance.
        Uses explicit Account IDs provided by configuration.
        """
        
        endpoint = "/journalentry"
        # 1. Debit Merchant Fees (Expense)
        # 2. Credit Undeposited Funds (Asset)
        
        payload = {
            "Line": [
                {
                    "DetailType": "JournalEntryLineDetail",
                    "JournalEntryLineDetail": {
                        "PostingType": "Debit",
                        "AccountRef": {"value": fee_account_id}
                    },
                    "Amount": float(abs(variance_amount)),
                    "Description": f"Fee Adjustment for Deposit {deposit_id}"
                },
                {
                    "DetailType": "JournalEntryLineDetail",
                    "JournalEntryLineDetail": {
                        "PostingType": "Credit",
                        "AccountRef": {"value": undeposited_funds_account_id}
                    },
                    "Amount": float(abs(variance_amount))
                }
            ],
            "DocNumber": f"ADJ-{idempotency_key[:8]}"
        }
        
        # In a real implementation, we would pass 'requestid' query param for idempotency if QBO supports it,
        # or rely on DocNumber uniqueness.
        
        # or rely on DocNumber uniqueness.
        
        response = await self.client.post(endpoint, json=payload)
        response.raise_for_status()
        return response.json()
