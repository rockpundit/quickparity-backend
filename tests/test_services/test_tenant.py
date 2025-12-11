import pytest
import sqlite3
import os
import json
from unittest.mock import patch, MagicMock
from backend.services.tenant import TenantManager

# Use a temporary file or in-memory DB for isolation
TEST_DB = "test_tenants.db"

@pytest.fixture
def tenant_manager():
    # Setup
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    
    tm = TenantManager(db_path=TEST_DB)
    yield tm
    
    # Teardown
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_add_and_list_tenant(tenant_manager):
    t = tenant_manager.add_tenant(
        name="Test Merchant",
        sq_token="sq_secret",
        qbo_token="qbo_secret",
        qbo_realm="realm_123"
    )
    
    assert t.name == "Test Merchant"
    assert t.encrypted_sq_token != "sq_secret" # Should be encrypted
    
    tenants = tenant_manager.list_tenants()
    assert len(tenants) == 1
    assert tenants[0].id == t.id
    
    # Verify Decryption
    decrypted_sq = tenant_manager.decrypt_token(t.encrypted_sq_token)
    assert decrypted_sq == "sq_secret"

def test_update_settings(tenant_manager):
    t = tenant_manager.add_tenant("Settings Tester", "sq", "qbo", "realm")
    
    new_map = {"Stripe": "Checking"}
    tenant_manager.update_settings(t.id, new_map, "sales", True)
    
    updated_list = tenant_manager.list_tenants()
    updated_t = updated_list[0]
    
    assert updated_t.deposit_account_mapping == new_map
    assert updated_t.refund_account_mapping == "sales"
    assert updated_t.auto_fix_variances is True

def test_duplicate_tenant_error(tenant_manager):
    tenant_manager.add_tenant("Duplicate", "sq", "qbo", "realm")
    with pytest.raises(ValueError):
        tenant_manager.add_tenant("Duplicate", "sq2", "qbo2", "realm2")
