import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from backend.services.reconciliation import ReconciliationEngine
from backend.models import ReconciliationStatus, VarianceType

def test_detect_international_fee_high_fidelity():
    engine = ReconciliationEngine(MagicMock(), MagicMock(), db_path=":memory:")
    
    # Setup: 100 Gross, 2.00 Variance (Mismatch Amount, but Explicit Text says why)
    variance = Decimal("2.00")
    gross = Decimal("100.00")
    
    # Metadata has explicit reason
    metadata = {
        "fee_descriptions": ["Stripe Processing Fee", "International Card Fee"]
    }
    
    v_type, reason = engine._analyze_variance(variance, gross, Decimal("0.00"), Decimal("0.00"), metadata)
    
    assert v_type == VarianceType.INTERNATIONAL_FEE
    assert "detected" in reason # "International Fee detected: International Card Fee"

def test_detect_missing_tax_high_fidelity():
    engine = ReconciliationEngine(MagicMock(), MagicMock(), db_path=":memory:")
    
    variance = Decimal("5.00")
    metadata = {
        "fee_descriptions": ["State Tax Withholding"]
    }
    
    v_type, reason = engine._analyze_variance(variance, Decimal("100.00"), Decimal("0.00"), Decimal("0.00"), metadata)
    
    assert v_type == VarianceType.MISSING_TAX
    assert "Tax Fee detected" in reason

def test_detect_international_fee_heuristic_fallback():
    # Still works without metadata
    engine = ReconciliationEngine(MagicMock(), MagicMock(), db_path=":memory:")
    
    variance = Decimal("1.00") # Exactly 1%
    gross = Decimal("100.00")
    
    v_type, reason = engine._analyze_variance(variance, gross, Decimal("0.00"), Decimal("0.00"), {})
    
    assert v_type == VarianceType.INTERNATIONAL_FEE
    assert v_type == VarianceType.INTERNATIONAL_FEE
    assert "Likely Hidden International Fee" in reason # Heuristic message

def test_detect_missing_tax_heuristic_fallback():
    engine = ReconciliationEngine(MagicMock(), MagicMock(), db_path=":memory:")
    
    variance = Decimal("8.88")
    tax = Decimal("8.88")
    
    v_type, reason = engine._analyze_variance(variance, Decimal("100.00"), tax, Decimal("0.00"), {})
    
    assert v_type == VarianceType.MISSING_TAX
    assert v_type == VarianceType.MISSING_TAX
    assert "Likely Unrecorded Tax" in reason
