import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta
from backend.services.scheduler import SchedulerService

@pytest.fixture
def scheduler():
    mock_tm = MagicMock()
    service = SchedulerService(tenant_manager=mock_tm)
    # Mock internal email service
    service.email_service = MagicMock()
    return service

@pytest.mark.asyncio
async def test_scheduler_manual_skip(scheduler):
    """
    Ensure 'manual' sync frequency is ignored.
    """
    mock_tenant = MagicMock(sync_frequency="manual", id="t1")
    scheduler.tm.list_tenants.return_value = [mock_tenant]
    
    await scheduler.check_sync_schedule()
    
    # Should NOT decrypt tokens or try to sync
    scheduler.tm.decrypt_token.assert_not_called()

@patch("backend.connectors.square.SquareClient")
@patch("backend.connectors.qbo.QBOClient")
@patch("backend.services.reconciliation.ReconciliationEngine")
@pytest.mark.asyncio
async def test_scheduler_trigger_daily(mock_engine_cls, mock_qbo_cls, mock_sq_cls, scheduler):
    """
    Ensure 'daily' sync triggers when time elapsed > 1 day.
    """
    # Setup Tenant
    last_sync = datetime.now() - timedelta(days=1, hours=1)
    mock_tenant = MagicMock(
        sync_frequency="daily", 
        last_sync_at=last_sync, 
        id="t_daily",
        encrypted_sq_token="enc_sq",
        encrypted_qbo_token="enc_qbo",
        qbo_realm_id="realm",
        email_notifications=True,
        alert_email="admin@test.com"
    )
    scheduler.tm.list_tenants.return_value = [mock_tenant]
    scheduler.tm.decrypt_token.side_effect = lambda x: "decrypted_token"
    
    # Setup Engine Mock
    mock_engine = mock_engine_cls.return_value
    mock_result = MagicMock()
    mock_result.discrepancy_count = 1
    mock_result.discrepancies = ["mock_discrepancy"]
    mock_engine.run.return_value = mock_result
    
    await scheduler.check_sync_schedule()
    
    # Verify Sync Flow
    mock_sq_cls.assert_called()
    mock_qbo_cls.assert_called()
    mock_engine.run.assert_called_with(auto_fix=False)
    
    # Verify Email Alert
    scheduler.email_service.send_discrepancy_alert.assert_called_with("admin@test.com", ["mock_discrepancy"])
    
    # Verify Update Last Sync
    scheduler.tm.update_last_sync.assert_called()
