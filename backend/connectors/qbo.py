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

    async def find_deposit(self, amount: Decimal, date_from: datetime, date_to: datetime, target_account_type: str = None, payout_id: str = None) -> Optional[LedgerEntry]:
        """
        Find a deposit using a multi-tiered strategy:
        1. ID Match: Checks 'PrivateNote' for the payout_id (Winner).
        2. Exact Match: Matches exact amount (Runner-up).
        3. Fuzzy Match: Matches amount within tolerance (Fallback).
        """
        
        formatted_date_from = date_from.strftime("%Y-%m-%d")
        formatted_date_to = date_to.strftime("%Y-%m-%d")
        
        # Query generic Deposit
        query = f"SELECT * FROM Deposit WHERE TxnDate >= '{formatted_date_from}' AND TxnDate <= '{formatted_date_to}'"
        
        data = await self._query(query)
        deposits = data.get("QueryResponse", {}).get("Deposit", [])
        
        best_fuzzy_match = None
        exact_match = None
        
        # Tolerance for fuzzy matching (e.g. $10.00)
        # In the future, this could be configurable per tenant
        TOLERANCE = Decimal("10.00")
        
        for dep in deposits:
            # 1. Deterministic ID Match (Prioritize this over account filter)
            memo = dep.get("PrivateNote", "")
            if payout_id and payout_id in memo:
                logger.info(f"Deterministic ID Match found for {payout_id}")
                return self._parse_ledger_entry(dep)

            # Check Account Mapping if specified
            if target_account_type:
                account_ref = dep.get("DepositToAccountRef", {})
                acct_name = account_ref.get("name", "").lower()
                # Only filter if we HAVE a name and it doesn't match
                if acct_name and target_account_type.lower() not in acct_name:
                     continue

            dep_amount = Decimal(str(dep.get("TotalAmt", 0)))
            
            # 2. Exact Match
            if dep_amount == amount:
                # We store it but keep looking in case there is an ID match later (which we check first now, so this is just "unmatched ID exact match")
                if not exact_match:
                    exact_match = dep
                continue
            
            # 3. Fuzzy Match
            diff = abs(dep_amount - amount)
            if diff <= TOLERANCE:
                # Store the closest match
                if not best_fuzzy_match or diff < abs(Decimal(str(best_fuzzy_match.get("TotalAmt", 0))) - amount):
                    best_fuzzy_match = dep
        
        if exact_match:
            return self._parse_ledger_entry(exact_match)
            
        if best_fuzzy_match:
            logger.info(f"Fuzzy Match found for {amount} (Actual: {best_fuzzy_match.get('TotalAmt')})")
            return self._parse_ledger_entry(best_fuzzy_match)
        
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
        
        response = await self.client.post(endpoint, json=payload)
        response.raise_for_status()
        return response.json()

    async def create_deposit(self, amount: Decimal, date: datetime, target_account_id: str, source_account_id: str, memo: str):
        """
        Create a Deposit transaction in QBO.
        Target Account: The Bank Account (Checking).
        Source Account: Where the money comes from (Undeposited Funds).
        """
        endpoint = "/deposit"
        
        formatted_date = date.strftime("%Y-%m-%d")
        
        payload = {
            "TxnDate": formatted_date,
            "PrivateNote": memo, 
            "DepositToAccountRef": {
                "value": target_account_id
            },
            "Line": [
                {
                    "DetailType": "DepositLineDetail",
                    "Amount": float(amount),
                    "DepositLineDetail": {
                        "AccountRef": {
                            "value": source_account_id
                        }
                    }
                }
            ]
        }
        
        logger.info(f"Creating QBO Deposit: {amount} to {target_account_id} from {source_account_id}")
        response = await self.client.post(endpoint, json=payload)
        response.raise_for_status()
        return response.json()
