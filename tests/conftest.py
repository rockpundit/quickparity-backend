import pytest
from unittest.mock import AsyncMock, MagicMock
import os
import sqlite3
import tempfile
from decimal import Decimal
from datetime import datetime
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from backend
from backend.services.reconciliation import ReconciliationEngine
from backend.connectors.square import SquareClient
from backend.connectors.qbo import QBOClient
# Assume these exist based on user file updates and ls output
from backend.connectors.stripe import StripeClient
from backend.connectors.shopify import ShopifyClient
from backend.connectors.paypal import PayPalClient

@pytest.fixture
def mock_square():
    return AsyncMock(spec=SquareClient)

@pytest.fixture
def mock_qbo():
    return AsyncMock(spec=QBOClient)

@pytest.fixture
def mock_stripe():
    return AsyncMock(spec=StripeClient)

@pytest.fixture
def mock_shopify():
    return AsyncMock(spec=ShopifyClient)

@pytest.fixture
def mock_paypal():
    return AsyncMock(spec=PayPalClient)

@pytest.fixture
def test_db_path():
    # Create a temp file for the DB
    fd, path = tempfile.mkstemp()
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.remove(path)

@pytest.fixture
def engine(mock_square, mock_qbo, mock_stripe, mock_shopify, mock_paypal, test_db_path):
    eng = ReconciliationEngine(
        square_client=mock_square, 
        qbo_client=mock_qbo, 
        stripe_client=mock_stripe,
        shopify_client=mock_shopify,
        paypal_client=mock_paypal,
        db_path=test_db_path
    )
    return eng
