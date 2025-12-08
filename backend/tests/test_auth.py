from fastapi.testclient import TestClient
from backend.main import app
from backend.services.tenant import TenantManager
import pytest
import os

client = TestClient(app)

# Helper to clear DB
@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists("reconciliation.db"):
        os.remove("reconciliation.db")
    yield
    if os.path.exists("reconciliation.db"):
        os.remove("reconciliation.db")

def test_auth_status_empty():
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.json() == {"stripe": False, "qbo": False}

def test_stripe_connect_redirect():
    response = client.get("/api/auth/stripe/connect", follow_redirects=False)
    assert response.status_code == 307
    assert "connect.stripe.com" in response.headers["location"]

def test_stripe_callback_mock():
    # Simulate callback with mock code
    response = client.get("/api/auth/stripe/callback?code=mock_code", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:3000/onboarding?success=stripe"
    
    # Verify DB update
    response = client.get("/api/auth/status")
    assert response.json() == {"stripe": True, "qbo": False}

def test_qbo_connect_redirect():
    response = client.get("/api/auth/qbo/connect", follow_redirects=False)
    assert response.status_code == 307
    assert "appcenter.intuit.com" in response.headers["location"]

def test_qbo_callback_mock():
    # Simulate callback with mock code
    response = client.get("/api/auth/qbo/callback?code=mock_code&realmId=123", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:3000/onboarding?success=qbo"
    
    # Verify DB update
    response = client.get("/api/auth/status")
    # Stripe might be false if DB was cleared between tests, but strict order isn't guaranteed here
    # Check just QBO
    assert response.json()["qbo"] == True
