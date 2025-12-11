import pytest
import os
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from backend.main import app

@pytest.fixture
def client():
    return TestClient(app)

# --- Test Stripe Auth ---

@patch("backend.api.auth.os.getenv")
def test_stripe_connect_redirect(mock_getenv, client):
    """
    Test redirect to Stripe OAuth.
    """
    mock_getenv.side_effect = lambda key, default=None: {
        "STRIPE_CLIENT_ID": "ca_test_123",
        "DEMO_MODE": "false",
        "API_BASE_URL": "http://testserver"
    }.get(key, default)
    
    response = client.get("/api/auth/stripe/connect", follow_redirects=False)
    assert response.status_code == 307
    assert "connect.stripe.com" in response.headers["location"]
    assert "client_id=ca_test_123" in response.headers["location"]

@patch("backend.api.auth.httpx.AsyncClient")
@patch("backend.api.auth.TenantManager")
@patch("backend.api.auth.os.getenv")
def test_stripe_callback_success(mock_getenv, mock_tm_cls, mock_httpx_cls, client):
    """
    Test Stripe callback token exchange.
    """
    mock_getenv.side_effect = lambda key, default=None: {
        "STRIPE_SECRET_KEY": "sk_test_123",
        "FRONTEND_URL": "http://localhost:3000"
    }.get(key, default)
    
    # Mock HTTPX response
    from unittest.mock import AsyncMock
    mock_client = mock_httpx_cls.return_value
    mock_client.__aenter__.return_value = mock_client
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "sk_access_token",
        "stripe_user_id": "acct_123"
    }
    mock_client.post = AsyncMock(return_value=mock_response)
    
    # Mock Tenant Manager
    mock_tm = mock_tm_cls.return_value
    mock_tm.list_tenants.return_value = [MagicMock(id="t1")]
    
    response = client.get("/api/auth/stripe/callback?code=auth_code_123", follow_redirects=False)
    
    assert response.status_code == 307
    assert "/onboarding?success=stripe" in response.headers["location"]
    mock_tm.update_tenant_token.assert_called_with("t1", "stripe", "sk_access_token")

# --- Test Square Auth ---

@patch("backend.api.auth.os.getenv")
def test_square_connect_redirect(mock_getenv, client):
    """
    Test redirect to Square OAuth.
    """
    mock_getenv.side_effect = lambda key, default=None: {
        "SQUARE_APP_ID": "sq0idb-test",
        "DEMO_MODE": "false"
    }.get(key, default)
    
    response = client.get("/api/auth/square/connect", follow_redirects=False)
    assert response.status_code == 307
    assert "connect.squareupsandbox.com" in response.headers["location"]

# --- Test QBO Auth ---

@patch("backend.api.auth.os.getenv")
def test_qbo_connect_redirect(mock_getenv, client):
    """
    Test redirect to QBO OAuth.
    """
    mock_getenv.side_effect = lambda key, default=None: {
        "QBO_CLIENT_ID": "checklist_id_123",
        "DEMO_MODE": "false"
    }.get(key, default)
    
    response = client.get("/api/auth/qbo/connect", follow_redirects=False)
    assert response.status_code == 307
    assert "appcenter.intuit.com" in response.headers["location"]
    assert "scope=com.intuit.quickbooks.accounting" in response.headers["location"]
