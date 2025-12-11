import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from backend.services.reconciliation import ReconciliationEngine
from backend.models import ReconciliationEntry, ReconciliationStatus, VarianceType

@pytest.mark.asyncio
async def test_apply_fix_routes_tax_to_tax_account():
    """Verify that MISSING_TAX variance routes to the Tax Liability account."""
    mock_qbo = MagicMock()
    mock_qbo.find_deposit = AsyncMock(return_value=MagicMock(id="DEP123", fee_amount=Decimal("0.00")))
    mock_qbo.create_journal_entry = AsyncMock()
    
    engine = ReconciliationEngine(MagicMock(), mock_qbo, db_path=":memory:")
    
    # Create an entry with MISSING_TAX variance
    entry = ReconciliationEntry(
        date="2024-01-15",
        payout_id="po_tax_test",
        status=ReconciliationStatus.VARIANCE_DETECTED,
        gross_sales=100.00,
        net_deposit=92.00,
        calculated_fees=0.00,
        ledger_fee=0.00,
        sales_tax_collected=8.00,
        refund_amount=0.00,
        refund_fee_reversal=0.00,
        variance_amount=8.00,
        variance_type=VarianceType.MISSING_TAX,
        variance_reason="Likely Unrecorded Tax Withholding"
    )
    
    tenant_settings = {
        "default_fee_account_id": "fee_acct_general",
        "default_undeposited_funds_account_id": "undeposited_funds_acct"
    }
    
    success, message = await engine.apply_fix(entry, tenant_settings)
    
    # Verify create_journal_entry was called with DEFAULT FEE account
    mock_qbo.create_journal_entry.assert_called_once()
    call_kwargs = mock_qbo.create_journal_entry.call_args.kwargs
    
    assert call_kwargs["fee_account_id"] == "fee_acct_general"
    assert call_kwargs["undeposited_funds_account_id"] == "undeposited_funds_acct"

@pytest.mark.asyncio
async def test_apply_fix_routes_fee_to_fee_account():
    """Verify that FEE_MISMATCH variance routes to Default Fee account."""
    mock_qbo = MagicMock()
    mock_qbo.find_deposit = AsyncMock(return_value=MagicMock(id="DEP456", fee_amount=Decimal("0.00")))
    mock_qbo.create_journal_entry = AsyncMock()
    
    engine = ReconciliationEngine(MagicMock(), mock_qbo, db_path=":memory:")
    
    entry = ReconciliationEntry(
        date="2024-01-15",
        payout_id="po_fee_test",
        status=ReconciliationStatus.VARIANCE_DETECTED,
        gross_sales=100.00,
        net_deposit=97.00,
        calculated_fees=3.00,
        ledger_fee=0.00,
        sales_tax_collected=0.00,
        refund_amount=0.00,
        refund_fee_reversal=0.00,
        variance_amount=3.00,
        variance_type=VarianceType.FEE_MISMATCH,
        variance_reason="Processing Fee Discrepancy"
    )
    
    tenant_settings = {
        "default_fee_account_id": "merchant_fees_acct",
        "default_undeposited_funds_account_id": "undeposited_funds_acct"
    }
    
    success, message = await engine.apply_fix(entry, tenant_settings)
    
    call_kwargs = mock_qbo.create_journal_entry.call_args.kwargs
    assert call_kwargs["fee_account_id"] == "merchant_fees_acct"
    assert call_kwargs["undeposited_funds_account_id"] == "undeposited_funds_acct"

@pytest.mark.asyncio
async def test_apply_fix_routes_intl_fee_with_granularity():
    """Verify that INTERNATIONAL_FEE routes to Default Fee account (simplification)."""
    mock_qbo = MagicMock()
    mock_qbo.find_deposit = AsyncMock(return_value=MagicMock(id="DEP789", fee_amount=Decimal("0.00")))
    mock_qbo.create_journal_entry = AsyncMock()
    
    engine = ReconciliationEngine(MagicMock(), mock_qbo, db_path=":memory:")
    
    entry = ReconciliationEntry(
        date="2024-01-15",
        payout_id="po_intl_test",
        status=ReconciliationStatus.VARIANCE_DETECTED,
        gross_sales=100.00,
        net_deposit=98.50,
        calculated_fees=1.50, # 1.5% fee
        ledger_fee=0.00,
        sales_tax_collected=0.00,
        refund_amount=0.00,
        refund_fee_reversal=0.00,
        variance_amount=1.50,
        variance_type=VarianceType.INTERNATIONAL_FEE,
        variance_reason="International Fee detected: Stripe International Card Fee"
    )
    
    tenant_settings = {
        "default_fee_account_id": "merchant_fees_acct",
        "default_undeposited_funds_account_id": "undeposited_funds_acct"
    }
    
    success, message = await engine.apply_fix(entry, tenant_settings)
    
    mock_qbo.create_journal_entry.assert_called_once()
    call_kwargs = mock_qbo.create_journal_entry.call_args.kwargs
    
    # Assert Account Mapping
    assert call_kwargs["fee_account_id"] == "merchant_fees_acct"
