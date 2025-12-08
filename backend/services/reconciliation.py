import logging
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List

from backend.models import (
    Payout, ReconciliationEntry, ReconciliationStatus, VarianceType, LedgerEntry
)
# Note: Connector imports will be dynamic or passed in to avoid circular deps if needed
# but we will assume standard structure
# from backend.connectors.square import SquareClient
# from backend.connectors.qbo import QBOClient

logger = logging.getLogger(__name__)
DB_PATH = "reconciliation.db"

class ReconciliationEngine:
    def __init__(self, square_client, qbo_client, stripe_client=None, shopify_client=None, paypal_client=None, db_path: str = DB_PATH):
        self.square = square_client
        self.qbo = qbo_client
        self.stripe = stripe_client
        self.shopify = shopify_client
        self.paypal = paypal_client
        self.db_path = db_path
        self._init_results_table()

    def _init_results_table(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Ensure we have a table for the detailed entries
        # We might migrate or create a new one. For now, creating 'audit_log'
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                payout_id TEXT PRIMARY KEY,
                date TEXT,
                status TEXT,
                gross_sales REAL,
                net_deposit REAL,
                calculated_fees REAL,
                ledger_fee REAL,
                sales_tax_collected REAL,
                refund_amount REAL,
                refund_fee_reversal REAL,
                variance_amount REAL,
                variance_type TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _save_entry(self, entry: ReconciliationEntry):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO audit_log (
                payout_id, date, status, gross_sales, net_deposit, 
                calculated_fees, ledger_fee, sales_tax_collected, 
                refund_amount, refund_fee_reversal, variance_amount, variance_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.payout_id,
            entry.date,
            entry.status.value,
            float(entry.gross_sales),
            float(entry.net_deposit),
            float(entry.calculated_fees),
            float(entry.ledger_fee),
            float(entry.sales_tax_collected),
            float(entry.refund_amount),
            float(entry.refund_fee_reversal),
            float(entry.variance_amount),
            entry.variance_type.value if entry.variance_type else None
        ))
        conn.commit()
        conn.close()

    async def run_for_period(self, start_date: datetime, end_date: datetime, auto_fix: bool = False):
        payouts = await self.square.get_payouts(begin_time=start_date, end_time=end_date)
        if self.stripe:
            stripe_payouts = await self.stripe.get_payouts(begin_time=start_date, end_time=end_date)
            payouts.extend(stripe_payouts)

        if self.shopify:
            shopify_payouts = await self.shopify.get_payouts(begin_time=start_date, end_time=end_date)
            payouts.extend(shopify_payouts)

        if self.paypal:
            paypal_payouts = await self.paypal.get_payouts(begin_time=start_date, end_time=end_date)
            payouts.extend(paypal_payouts)
            
        logger.info(f"Fetched {len(payouts)} payouts for processing.")
        
        results = []
        for payout in payouts:
            result = await self.process_payout(payout, auto_fix)
            results.append(result)
        return results

    async def process_payout(self, payout: Payout, auto_fix: bool) -> ReconciliationEntry:
        logger.info(f"Processing Payout {payout.id} | Net: {payout.amount_money}")

        # 1. Fetch detailed Payout Entries to calculate Gross, Tax, and Fees
        # We need to call a method on square_client that returns entries
        # Assuming we add `get_payout_entries` to SquareClient
        if payout.source == "Square":
            entries = await self.square.get_payout_entries_detailed(payout.id)
        elif payout.source == "Stripe":
             # Ensure stripe client is available
             if self.stripe:
                 entries = await self.stripe.get_payout_entries_detailed(payout.id)
             else:
                 entries = []
        elif payout.source == "Shopify":
             if self.shopify:
                 entries = await self.shopify.get_payout_entries_detailed(payout.id)
             else:
                 entries = []
        elif payout.source == "PayPal":
             if self.paypal:
                 entries = await self.paypal.get_payout_entries_detailed(payout.id)
             else:
                 entries = []
        else:
            entries = []
        
        total_gross_sales = Decimal("0.00")
        total_tax = Decimal("0.00")
        total_fees = Decimal("0.00")
        total_refunds = Decimal("0.00")
        refund_fee_reversal = Decimal("0.00")
        
        for entry in entries:
            # Entry dict structure needs to be standardized in the connector or handled here.
            # Assuming connector gives us a dict with type, amount, fee, and order_id
            
            e_type = entry.get("type") # CHARGE, REFUND, FEE, etc.
            gross_amt = Decimal(str(entry.get("gross_amount", 0)))
            fee_amt = Decimal(str(entry.get("fee_amount", 0)))
            tax_amt = Decimal(str(entry.get("tax_amount", 0))) # This might need fetching from Order
            
            if e_type == "CHARGE" or e_type == "PAYMENT":
                total_gross_sales += gross_amt
                total_tax += tax_amt
                total_fees += abs(fee_amt)
            
            elif e_type == "REFUND":
                # Refunds are negative in gross_amt usually
                total_refunds += abs(gross_amt)
                # If fee was reversed, it might be positive or a separate adjustment
                refund_fee_reversal += abs(fee_amt) # Check sign logic later
                
            elif e_type == "FEE" or e_type == "ADJUSTMENT":
                total_fees += abs(fee_amt) # If standalone fee

        # Adjust total fees by reversals
        total_fees -= refund_fee_reversal

        # 2. Logic: Gross Revenue = Total Charge - Sales Tax
        # Actually total_gross_sales usually includes tax in Stripe/Square "Amount".
        # So Real Revenue = Gross - Tax.
        real_revenue = total_gross_sales - total_tax

        # 3. Find QBO Deposit
        date_from = payout.created_at - timedelta(days=3)
        date_to = payout.created_at + timedelta(days=3)
        ledger_entry = await self.qbo.find_deposit(payout.amount_money, date_from, date_to)

        status = ReconciliationStatus.MATCHED
        ledger_fee = Decimal("0.00")
        variance = Decimal("0.00")
        v_type = None

        if not ledger_entry:
            status = ReconciliationStatus.MISSING_DEPOSIT
            variance = payout.amount_money # Entire amount is "variance" if missing? Or just mark missing.
        else:
            ledger_fee = abs(ledger_entry.fee_amount)
            # Variance = Calculated Fee - Ledger Fee
            # (If ledger records the fee)
            
            # Or if checking Net Match:
            # Payout Net should match Deposit Amount (if fees are taken out before deposit)
            # If QBO Deposit is Net, then we are good on the cash side.
            # We audit the Fees.
            
            fee_variance = total_fees - ledger_fee
            if abs(fee_variance) > Decimal("0.01"):
                status = ReconciliationStatus.VARIANCE_DETECTED
                variance = fee_variance
                v_type = VarianceType.FEE_MISMATCH
        
        # Construct Entry
        entry = ReconciliationEntry(
            date=payout.created_at.strftime("%Y-%m-%d"),
            payout_id=payout.id,
            status=status,
            gross_sales=float(total_gross_sales),
            net_deposit=float(payout.amount_money),
            calculated_fees=float(total_fees),
            ledger_fee=float(ledger_fee),
            sales_tax_collected=float(total_tax),
            refund_amount=float(total_refunds),
            refund_fee_reversal=float(refund_fee_reversal),
            variance_amount=float(variance),
            variance_type=v_type
        )
        
        self._save_entry(entry)

        entry_summary_for_log = {
            "payout_id": entry.payout_id,
            "status": entry.status,
            "net": entry.net_deposit,
            "tax": entry.sales_tax_collected,
            "refunds": entry.refund_amount
        }
        logger.info(f"Processed Payout Result: {entry_summary_for_log}")

        if status == ReconciliationStatus.VARIANCE_DETECTED and auto_fix:
            await self._auto_fix(entry, ledger_entry)
            
        return entry

    async def _auto_fix(self, entry: ReconciliationEntry, ledger_entry: Optional[LedgerEntry]):
        if not ledger_entry:
            logger.warning("Cannot auto-fix without a ledger entry (deposit).")
            return
            
        logger.info(f"Auto-fixing variance for Payout {entry.payout_id}...")
        import hashlib
        idempotency_key = hashlib.sha256(entry.payout_id.encode()).hexdigest()
        
        try:
            # Call QBO to creating Journal Entry
            # We need to handle Tax Liability separation here too if requested?
            # "Journal Entry Output: Credit Sales Revenue, Credit Sales Tax Payable, Debit Fees, Debit Undeposited Funds"
            
            # This logic depends on how the user records the initial Sale.
            # If they use "Undeposited Funds" for the Gross Sale, then we just need to relieve Undeposited Funds.
            
            await self.qbo.create_journal_entry(
                deposit_id=ledger_entry.id,
                variance_amount=Decimal(str(entry.variance_amount)),
                idempotency_key=idempotency_key
            )
            # Note: We might need a more complex create_journal_entry_for_tax method
            # if we want to book the Tax Liability specifically.
            # The user requirement says "Journal Entry Output..." for Feature A.
            # This implies we are creating the JE for the Payout processing.
            
            logger.info("Auto-fix applied.")
        except Exception as e:
            logger.error(f"Failed to auto-fix: {e}")

