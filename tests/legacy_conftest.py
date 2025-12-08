import pytest
from unittest.mock import AsyncMock, MagicMock
import os
import sqlite3
import tempfile
from decimal import Decimal
from datetime import datetime

# Add project root to path if needed, though pytest usually handles this
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import ReconciliationEngine
from connectors.square import SquareClient
from connectors.qbo import QBOClient

@pytest.fixture
def mock_square():
    return AsyncMock(spec=SquareClient)

@pytest.fixture
def mock_qbo():
    return AsyncMock(spec=QBOClient)

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
def engine(mock_square, mock_qbo, test_db_path):
    eng = ReconciliationEngine(mock_square, mock_qbo, db_path=test_db_path)
    # Ensure DB is init
    eng._init_db()
    return eng
