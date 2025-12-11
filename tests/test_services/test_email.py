import pytest
import os
from unittest.mock import MagicMock, patch
from backend.services.email_service import EmailService
from backend.models import ReconciliationEntry

@pytest.fixture
def email_service():
    with patch.dict(os.environ, {
        "SMTP_USER": "alert@example.com", 
        "SMTP_PASSWORD": "secret_password"
    }):
        yield EmailService()

@patch("smtplib.SMTP")
def test_send_discrepancy_alert(mock_smtp, email_service):
    # Mock Server Context Manager
    mock_server = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_server
    
    discrepancies = [
        ReconciliationEntry(
            date="2023-01-01", payout_id="po_1", status="VARIANCE_DETECTED",
            gross_sales=100, net_deposit=90, calculated_fees=3, ledger_fee=3,
            sales_tax_collected=0, refund_amount=0, refund_fee_reversal=0,
            variance_amount=7.0, variance_type="fee_mismatch", variance_reason="Test"
        )
    ]
    
    email_service.send_discrepancy_alert("admin@example.com", discrepancies)
    
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_with("alert@example.com", "secret_password")
    mock_server.send_message.assert_called_once()
    
    # Verify Content in call args
    args, _ = mock_server.send_message.call_args
    msg = args[0]
    assert msg['Subject'] == "Action Required: 1 Reconciliation Discrepancies Found"
    assert "po_1" in str(msg)
