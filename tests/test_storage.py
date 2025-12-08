import pytest
import sqlite3
from backend.models import ReconciliationEntry, ReconciliationStatus
from decimal import Decimal
from datetime import datetime

def test_db_persistence(engine):
    """
    Test that results are correctly saved to SQLite (audit_log table).
    REFACTORED: The new engine uses 'audit_log' table and 'ReconciliationEntry'.
    The old 'ReconciliationResult' and 'transactions' table might be deprecated or used by old code.
    We should test what the engine actually does.
    """
    from backend.models import ReconciliationEntry, ReconciliationStatus as Status
    
    entry = ReconciliationEntry(
        date="2023-01-01",
        payout_id="po_test_db",
        status=Status.MATCHED,
        gross_sales=100.0,
        net_deposit=97.0,
        calculated_fees=3.0,
        ledger_fee=3.0,
        sales_tax_collected=0.0,
        refund_amount=0.0,
        refund_fee_reversal=0.0,
        variance_amount=0.0,
        variance_type=None
    )
    
    engine._save_entry(entry)
    
    conn = sqlite3.connect(engine.db_path)
    # Check audit_log
    row = conn.execute("SELECT * FROM audit_log WHERE payout_id='po_test_db'").fetchone()
    conn.close()
    
    assert row is not None
    assert row[0] == "po_test_db"
    assert row[2] == "MATCHED"

def test_db_initialization(engine):
    """
    Ensure table exists.
    """
    conn = sqlite3.connect(engine.db_path)
    # check if table exists
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    assert cursor.fetchone() is not None
    conn.close()
