from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from typing import Optional
from backend.services.tenant import TenantManager

router = APIRouter(prefix="/settings", tags=["Settings"])

def get_tenant_manager():
    return TenantManager()

class SettingsUpdate(BaseModel):
    sync_frequency: str
    email_notifications: bool
    alert_email: Optional[str] = None

@router.get("/")
async def get_settings(tm: TenantManager = Depends(get_tenant_manager)):
    # Assuming single tenant for demo
    tenants = tm.list_tenants()
    if not tenants:
        return {}
    
    t = tenants[0]
    return {
        "sync_frequency": t.sync_frequency,
        "email_notifications": t.email_notifications,
        "alert_email": t.alert_email,
        "last_sync_at": t.last_sync_at
    }

@router.post("/")
async def update_settings(settings: SettingsUpdate, tm: TenantManager = Depends(get_tenant_manager)):
    tenants = tm.list_tenants()
    if not tenants:
        raise HTTPException(status_code=404, detail="No tenant found")
    
    t = tenants[0]
    tm.update_notification_settings(t.id, settings.sync_frequency, settings.email_notifications, settings.alert_email)
    return {"status": "success"}
