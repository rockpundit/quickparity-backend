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

    async def find_deposit(self, amount: Decimal, date_from: datetime, date_to: datetime) -> Optional[LedgerEntry]:
        """
        Find a deposit matching the net amount within a date range.
        QBO Query: SELECT * FROM Deposit WHERE TxnDate >= '...' AND TxnDate <= '...'
        """
        # QBO amounts are numerical.
        # Note: QBO might not allow filtering by Amount directly in all endpoints or it might be inefficient.
        # But 'Deposit' entity supports filtering.
        
        formatted_date_from = date_from.strftime("%Y-%m-%d")
        formatted_date_to = date_to.strftime("%Y-%m-%d")
        
        query = f"SELECT * FROM Deposit WHERE TxnDate >= '{formatted_date_from}' AND TxnDate <= '{formatted_date_to}'"
        
        query = f"SELECT * FROM Deposit WHERE TxnDate >= '{formatted_date_from}' AND TxnDate <= '{formatted_date_to}'"
        
        data = await self._query(query)
        deposits = data.get("QueryResponse", {}).get("Deposit", [])
        
        # Filter in memory for exact amount match to avoid float issues in query string if any
        # QBO amount is often string in JSON "100.00"
        
        for dep in deposits:
            dep_amount = Decimal(str(dep.get("TotalAmt", 0)))
            if dep_amount == amount:
                # Found a candidate
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

    async def create_journal_entry(self, deposit_id: str, variance_amount: Decimal, idempotency_key: str):
        """
        Create a Journal Entry to fix the variance.
        OR update the Deposit if that's the preferred method (DepositMod).
        User requested: "Use DepositAdd (or DepositMod if it exists)."
        Actually user said: "The Fix (Write Action): Use DepositAdd (or DepositMod if it exists)."
        
        However, modifying an existing Linked Txn (Deposit) can be complex if it was created by a feed.
        Adding a Journal Entry is safer often, but the user specifically mentioned modifying the deposit:
        "Line 1 (The Gross Sale): Positive Amount... Line 2 (The Fee): Negative Amount..."
        
        This implies modifying the Deposit to include the Fee line so the net matches.
        
        But wait, the problem is: "Payment processors deposit funds on a Net basis... but accounting ledgers record sales on a Gross basis."
        Mismatched 'Undeposited Funds'.
        
        If we have a Deposit of $97 (Net) from Bank Feed, and Sales of $100 (Gross).
        The Deposit should probably be split:
        Source: Undeposited Funds $100
        Deduction: Merchant Fees -$3
        Net: $97.
        
        If the deposit exists as just $97 to Undeposited Funds, it leaves $3 in Undeposited Funds forever.
        
        So we need to mod the deposit to be:
        Line 1: Undeposited Funds $100 (replacing the $97 line?)
        Line 2: Fees -$3.
        
        Implementing DepositMod is tricky without full object.
        For this simplified version, I will implement a `create_journal_entry` as a "Zero-Sum" plug if `DepositMod` is too risky given we don't have the full object state.
        
        BUT, the user prompt says: "Generate a 'Zero-Sum' reconciliation artifact (Journal Entry or Deposit Adjustment)".
        And logic: "If auto_fix=True, create the Journal Entry to 'plug' the gap."
        
        So I will stick to creating a Journal Entry that debits "Merchant Fees" and Credits "Undeposited Funds" (to clear the remaining balance)?
        
        If Sales recorded $100 into Undeposited Funds.
        Bank Deposit matched $97 from Undeposited Funds to Checking.
        Remaining in Undeposited Funds: $3.
        We need to move $3 from Undeposited Funds to Fees.
        Credit Undeposited Funds $3.
        Debit Merchant Fees $3.
        
        So this Journal Entry fixes it without touching the deposit!
        This is much safer.
        """
        
        endpoint = "/journalentry"
        # 1. Debit Merchant Fees (Expense)
        # 2. Credit Undeposited Funds (Asset)
        
        # We need Account IDs. For this demo, using placeholders.
        FEE_ACCOUNT_ID = "123" # Merchant Service Fees
        UNDEP_FUNDS_ACCOUNT_ID = "456" # Undeposited Funds
        
        payload = {
            "Line": [
                {
                    "DetailType": "JournalEntryLineDetail",
                    "JournalEntryLineDetail": {
                        "PostingType": "Debit",
                        "AccountRef": {"value": FEE_ACCOUNT_ID}
                    },
                    "Amount": float(abs(variance_amount)),
                    "Description": f"Fee Adjustment for Deposit {deposit_id}"
                },
                {
                    "DetailType": "JournalEntryLineDetail",
                    "JournalEntryLineDetail": {
                        "PostingType": "Credit",
                        "AccountRef": {"value": UNDEP_FUNDS_ACCOUNT_ID}
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
