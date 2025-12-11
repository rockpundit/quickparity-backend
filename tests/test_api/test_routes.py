import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from backend.main import app
from backend.models import ReconciliationEntry

client_fixture = TestClient(app)

@pytest.fixture
def client():
    # We can also yield and close if needed, but TestClient handles it usually.
    # But creating it inside fixture ensures it happens during test phase not collection.
    return TestClient(app)

# --- Test POST /reconcile ---

@patch("backend.api.routes.TenantManager")
def test_trigger_reconciliation(mock_tm_cls, client):
    """
    Test triggering a reconciliation task.
    """
    mock_tm = mock_tm_cls.return_value
    mock_tm.list_tenants.return_value = [MagicMock(id="tenant_123")]
    
    with patch("fastapi.BackgroundTasks.add_task") as mock_add_task:
        response = client.post("/api/reconcile", json={"tenant_id": "tenant_123"})
        
        assert response.status_code == 202
        assert response.json()["message"] == "Reconciliation started"
        mock_add_task.assert_called()

# --- Test GET /payouts ---

@patch("sqlite3.connect")
def test_get_payouts_empty(mock_connect, client):
    """
    Test fetching payouts report when DB is empty or table missing.
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    # Simulate table missing error first? Or just empty list.
    # Code handles OperationalError
    import sqlite3
    mock_cursor.execute.side_effect = sqlite3.OperationalError("no such table")
    
    response = client.get("/api/payouts")
    assert response.status_code == 200
    data = response.json()
    assert data["entries"] == []
    assert data["total_variance"] == 0.0

@patch("sqlite3.connect")
def test_get_payouts_success(mock_connect, client):
    """
    Test fetching payouts report with data.
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    # Mock row data (sqlite3.Row behavior is dict-like access)
    row_data = {
        "date": "2023-01-01T12:00:00",
        "payout_id": "po_123",
        "status": "MATCHED",
        "gross_sales": 100.0,
        "net_deposit": 97.0,
        "calculated_fees": 3.0,
        "ledger_fee": 3.0,
        "sales_tax_collected": 0.0,
        "refund_amount": 0.0,
        "refund_fee_reversal": 0.0,
        "variance_amount": 0.0,
        "variance_type": None,
        "variance_reason": None
    }
    mock_cursor.fetchall.return_value = [row_data]
    
    response = client.get("/api/payouts")
    assert response.status_code == 200
    data = response.json()
    assert len(data["entries"]) == 1
    assert data["entries"][0]["payout_id"] == "po_123"

# --- Test POST /settings ---

@patch("backend.api.routes.TenantManager")
def test_save_settings(mock_tm_cls, client):
    """
    Test saving settings.
    """
    mock_tm = mock_tm_cls.return_value
    mock_tm.list_tenants.return_value = [MagicMock(id="tenant_123")]
    
    payload = {
        "deposit_map": {"Stripe": "Checking"},
        "refund_map": "Returns",
        "auto_fix": True
    }
    
    response = client.post("/api/settings", json=payload)
    assert response.status_code == 200
    mock_tm.update_settings.assert_called()

# --- Test POST /reconciliation/fix/{payout_id} ---

@patch("sqlite3.connect")
@patch("backend.api.routes.TenantManager")
@patch("backend.api.routes.ReconciliationEngine")
def test_apply_fix(mock_engine_cls, mock_tm_cls, mock_connect, client):
    """
    Test manual fix application endpoint.
    """
    # 1. Mock DB Payout Fetch
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    row_data = {
        "date": "2023-01-01", "payout_id": "po_fix_me", "status": "VARIANCE_DETECTED",
        "gross_sales": 100, "net_deposit": 90, "calculated_fees": 3, "ledger_fee": 3,
        "sales_tax_collected": 0, "refund_amount": 0, "refund_fee_reversal": 0,
        "variance_amount": 7.0, "variance_type": "fee_mismatch", "variance_reason": "Foo"
    }
    mock_cursor.fetchone.return_value = row_data
    
    # 2. Mock Tenant Manager
    mock_tm = mock_tm_cls.return_value
    mock_tenant = MagicMock()
    mock_tenant.id = "t1"
    mock_tenant.encrypted_sq_token = "enc_sq"
    mock_tenant.encrypted_qbo_token = "enc_qbo"
    mock_tm.list_tenants.return_value = [mock_tenant]
    mock_tm.decrypt_token.return_value = "token"
    
    # 3. Mock Engine
    mock_engine = mock_engine_cls.return_value
    # Async mock for apply_fix
    mock_engine.apply_fix = MagicMock(side_effect=None)
    # We need to ensure it's awaitable if the actual code awaits it.
    # Since we are testing via TestClient inside an async test or sync...
    # FastAPI TestClient runs sync. The endpoint is async. TestClient handles the loop.
    # But mock_engine.apply_fix is called with `await`. So the mock return value must be awaitable.
    
    async def async_success(*args, **kwargs):
        return (True, "Fixed")
    
    mock_engine.apply_fix.side_effect = async_success

    # Note: TestClient is synchronous wrapper. We don't need pytest.mark.asyncio unless we use async client
    # OR unless we need async behavior in our setup.
    # For TestClient, standard def is fine.
    
    response = client.post("/api/reconciliation/fix/po_fix_me")
    assert response.status_code == 200
    assert response.json()["status"] == "FIXED"
