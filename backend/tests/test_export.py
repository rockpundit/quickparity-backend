
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.tenant import TenantManager
import os

client = TestClient(app)

# Helper to adding a test tenant
def create_test_tenant(tier="free"):
    tm = TenantManager()
    # Unique name to avoid conflicts
    import uuid
    name = f"Test Tenant {uuid.uuid4()}"
    try:
        t = tm.add_tenant(name, "sq", "qbo", "realm", subscription_tier=tier)
        return t
    except Exception as e:
        # If it exists (unlikely with uuid), find it
        tenants = tm.list_tenants()
        return tenants[-1] # risky but okay for local test if isolated

def test_tenant_status():
    tenant = create_test_tenant("free")
    response = client.get(f"/api/tenant/status?tenant_id={tenant.id}")
    assert response.status_code == 200
    assert response.json()["subscription_tier"] == "free"
    
    tenant_paid = create_test_tenant("paid")
    response = client.get(f"/api/tenant/status?tenant_id={tenant_paid.id}")
    assert response.status_code == 200
    assert response.json()["subscription_tier"] == "paid"

def test_export_access_control():
    # 1. Free tenant -> 403
    tenant_free = create_test_tenant("free")
    response = client.get(f"/api/reconciliation/export?tenant_id={tenant_free.id}")
    assert response.status_code == 403
    assert "paid subscribers" in response.json()["detail"]

    # 2. Paid tenant -> 200 and file
    tenant_paid = create_test_tenant("paid")
    response = client.get(f"/api/reconciliation/export?tenant_id={tenant_paid.id}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "reconciliation_export.xlsx" in response.headers["content-disposition"]
