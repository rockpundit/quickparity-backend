import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from backend.models import Payout, LedgerEntry, ReconciliationStatus

class MockDataGenerator:
    """
    Generates realistic synthetic data for financial reconciliation testing.
    """
    
    def __init__(self):
        self.sources = ["Square", "Stripe", "Shopify", "PayPal"]
        self.variance_scenarios = [
            "PERFECT_MATCH",
            "PERFECT_MATCH", 
            "PERFECT_MATCH", # Weighted to be common
            "FEE_MISMATCH",
            "MISSING_DEPOSIT",
            "REFUND_DRIFT", # Refund timing issue
            "INTERNATIONAL_FEE",
            "MISSING_TAX"
        ]

    def _random_money(self, min_val=10.0, max_val=1000.0) -> Decimal:
        return Decimal(str(round(random.uniform(min_val, max_val), 2)))

    def generate_payout(self, source: Optional[str] = None, scenario: Optional[str] = None) -> Tuple[Payout, Optional[LedgerEntry], str]:
        """
        Generates a Payout and its corresponding (or missing/mismatched) LedgerEntry.
        Returns (Payout, LedgerEntry, ScenarioName).
        """
        if not source:
            source = random.choice(self.sources)
        
        if not scenario:
            scenario = random.choice(self.variance_scenarios)

        now = datetime.now()
        # Randomize time in the last 30 days
        days_ago = random.randint(0, 30)
        created_at = now - timedelta(days=days_ago)
        
        # Base transaction values
        gross_sales = self._random_money(100, 2000)
        
        # Calculate realistic fees (approx 2.9% + 30c)
        fee_rate = Decimal("0.029")
        fixed_fee = Decimal("0.30")
        calculated_fee = (gross_sales * fee_rate) + fixed_fee
        calculated_fee = Decimal(str(round(calculated_fee, 2)))
        
        # Sales tax (approx 8.875%, random)
        tax_rate = Decimal("0.08875")
        tax_amount = (gross_sales * tax_rate)
        tax_amount = Decimal(str(round(tax_amount, 2)))
        
        # Net Deposit = Gross + Tax - Fee
        # (Assuming Tax is collected by merchant and paid out, so it increases deposit)
        # OR is the "Gross Sales" figure inclusive of tax? 
        # Usually: Charge $108.88 (Item $100 + Tax $8.88). 
        # Fee based on $108.88.
        # Net = $108.88 - Fee.
        
        total_charge = gross_sales + tax_amount
        # Recalculate fee on total charge
        real_fee = (total_charge * fee_rate) + fixed_fee
        real_fee = Decimal(str(round(real_fee, 2)))
        
        net_deposit = total_charge - real_fee
        
        payout_id = f"po_{source.lower()}_{uuid.uuid4().hex[:8]}"
        
        payout = Payout(
            id=payout_id,
            status="PAID",
            amount_money=net_deposit,
            created_at=created_at,
            arrival_date=created_at + timedelta(days=2),
            processing_fee=real_fee,
            source=source,
            currency="USD"
        )
        
        ledger_entry = None
        
        # Handle Scenarios
        if scenario == "PERFECT_MATCH":
            # Ledger Entry matches exactly
            ledger_entry = LedgerEntry(
                id=f"txn_{uuid.uuid4().hex[:8]}",
                txn_date=created_at + timedelta(days=2), # Deposit hits later
                total_amount=net_deposit,
                has_fee_line_item=True, # QBO tracks fee? 
                # If QBO tracks Gross -> Undeposited Funds
                # Then Deposit is Undeposited Funds -> Checking (Net)
                # The Deposit amount in Checking is Net.
                # The Fee is usually a separate line item or split.
                # For `find_deposit` we usually look for the Net Amount hitting the bank.
                fee_amount=real_fee * -1 # Fees are negative deductions
            )
            
        elif scenario == "MISSING_DEPOSIT":
            # No ledger entry exists
            ledger_entry = None
            
        elif scenario == "FEE_MISMATCH":
            # Bank fee was different than expected
            drift = Decimal("0.50")
            skewed_fee = real_fee + drift
            # Valid deposit amount would be Total - SkewedFee
            # But usually the BANK DEPOSIT is the source of truth for the Net Amount.
            # If the Payout says Net is X, and Bank says Net is Y, that's a huge issue.
            # Typically Fee Mismatch means: 
            # Payout Logic: Net 97, Fee 3.
            # Bank Feed: Net 96.50. Fee 3.50.
            # So the Payout Amount implies the Bank Deposit Amount.
            
            # Scenario: The Payout Object from Stripe says one thing, but maybe we want to simulate
            # a discrepancy where the Ledger recorded a different Fee?
            # Or the Mock Payout itself has a weird fee?
            
            # Let's say the Ledger Entry *matches the Payout Net* but has a different internal Fee breakdown?
            # Or the Ledger Entry has a slightly different Amount?
            
            # "Fee Mismatch" often means the calculated fee by our engine differs from what the processor said?
            # Or what the bank said?
            # Let's simple simulate: Ledger Entry Amount is slightly different due to unexpected fee.
            
            skewed_net = net_deposit - drift # e.g. Extra fee taken
            ledger_entry = LedgerEntry(
                id=f"txn_{uuid.uuid4().hex[:8]}",
                txn_date=created_at + timedelta(days=2),
                total_amount=skewed_net,
                has_fee_line_item=True,
                fee_amount=(real_fee + drift) * -1
            )
            
        elif scenario == "REFUND_DRIFT":
            # Refund happened, affecting net
            refund_amt = self._random_money(10, 50)
            
            # Payout includes a refund, reducing the net
            payout.amount_money -= refund_amt
             # Let's say we drift by date? Or the ledger missed the refund?
             # Let's say Ledger Matches perfectly for now to show "Drift" logic validation (which handles refunds correctly)
             # Actually, if it's "Refund Drift", maybe the Ledger DOESN'T show the refund?
             # Ledger shows original net without refund deduction.
             
            ledger_entry = LedgerEntry(
                id=f"txn_{uuid.uuid4().hex[:8]}",
                txn_date=created_at + timedelta(days=2),
                total_amount=net_deposit, # Original amount w/o refund
                has_fee_line_item=True,
                fee_amount=real_fee * -1
            )
            
        elif scenario == "INTERNATIONAL_FEE":
            # Extra 1% fee taken by processor
            intl_fee = gross_sales * Decimal("0.01")
            intl_fee = Decimal(str(round(intl_fee, 2)))
            
            # Payout Net is reduced by this extra fee
            payout.amount_money -= intl_fee
            
            # Ledger Entry matches the REDUCED amount usually (if bank feed matches payout)
            # BUT wait, the Variance is between "Calculated Fee" and "Ledger Fee"
            # OR between "Calculated Net" and "Actual Net".
            # The engine logic: 
            #   Calculated Fees = 2.9% + 30c.
            #   Ledger Fee = Bank says we paid X.
            #   Variance = Calculated - Ledger.
            
            # So here: Ledger Fee should be HIGHER than standard.
            
            ledger_entry = LedgerEntry(
                id=f"txn_{uuid.uuid4().hex[:8]}",
                txn_date=created_at + timedelta(days=2),
                total_amount=net_deposit - intl_fee,
                has_fee_line_item=True,
                fee_amount=(real_fee + intl_fee) * -1
            )
            
        elif scenario == "MISSING_TAX":
            # Tax was not withheld/payout out differently?
            # Scenario: "Unrecorded State Tax"
            # Payout Logic: Gross + Tax - Fee = Net.
            # Variance triggers if Net matches (Gross - Fee). i.e. Tax is missing from the deposit.
            # Or if the Ledger Entry is missing the tax component?
            
            # Let's say the Payout amount is LESS than expected by exactly the Tax amount.
            # Expected Net: Gross + Tax - Fee.
            # Actual Net: Gross - Fee (Tax wasn't passed through).
            
            payout.amount_money -= tax_amount
            
            # Ledger confirms this lower amount
            ledger_entry = LedgerEntry(
                id=f"txn_{uuid.uuid4().hex[:8]}",
                txn_date=created_at + timedelta(days=2),
                total_amount=net_deposit - tax_amount,
                has_fee_line_item=True,
                fee_amount=real_fee * -1
            )
        
        return payout, ledger_entry, scenario
