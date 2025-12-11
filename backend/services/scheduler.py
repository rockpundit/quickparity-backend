import asyncio
import logging
from datetime import datetime, timedelta
from typing import List
import os

# We will implement a custom loop or reuse the asyncio loop in main
# For simplicity in this demo without heavy dependencies (Celery), we'll use a loop task.
# But task.md mentioned `Impl/Configure Scheduler`. 
# Let's try to use a simple asyncio background task first rather than full APScheduler if dependencies are an issue, 
# but requirements.txt can be updated. Let's stick to the plan of a simple service class.

from backend.services.tenant import TenantManager
from backend.services.email_service import EmailService
# from backend.main import ReconciliationEngine # Cyclic import risk?
# Ideally key components are injected or imported inside the method.

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self, tenant_manager: TenantManager):
        self.tm = tenant_manager
        self.email_service = EmailService()
        self.is_running = False

    async def start(self):
        self.is_running = True
        logger.info("Scheduler Service started.")
        asyncio.create_task(self._run_loop())

    async def stop(self):
        self.is_running = False
        logger.info("Scheduler Service stopped.")

    async def _run_loop(self):
        while self.is_running:
            try:
                await self.check_sync_schedule()
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
            
            # Check every minute
            await asyncio.sleep(60)

    async def check_sync_schedule(self):
        tenants = self.tm.list_tenants()
        for tenant in tenants:
            if tenant.sync_frequency == "manual":
                continue
            
            should_sync = False
            now = datetime.now()
            last = tenant.last_sync_at
            
            if not last:
                should_sync = True
            elif tenant.sync_frequency == "daily" and (now - last) > timedelta(days=1):
                should_sync = True
            elif tenant.sync_frequency == "weekly" and (now - last) > timedelta(weeks=1):
                should_sync = True
                
            if should_sync:
                logger.info(f"Triggering scheduled sync for tenant {tenant.id}")
                # We need to instantiate the engine dynamically here
                # In a real app, this dependency injection would be cleaner.
                # For now, we'll do a local import to avoid circular dependency
                
                # IMPORTANT: In this simplified architecture without a real database session manager, 
                # we need to be careful. The engine needs clients.
                # We will mock the client creation for this automated task since we can't easily retrieve fresh tokens
                # without the full auth flow or stored refresh tokens.
                # Assuming `tm` has valid encrypted tokens.
                
                try:
                    # Logic to run engine
                    # This is where existing code reuse matters.
                    # We will signal "sync needed" or try to run it.
                    # Given the Complexity, we'll try to run it.
                    # Logic to run engine
                    # This is where existing code reuse matters.

                    
                    # Update last sync FIRST to prevent double run on error
                    # In real DB, transaction needed.
                    # tenant.last_sync_at = now
                    # self.tm.update_tenant(tenant) # We need update method
                    
                    # Actually, let's just log it for now and try to find a way to run `run_audit`
                    # run_audit requires `tm` which we have.
                    # But run_audit logic in main.py is a CLI wrapper.
                    # We need the engine logic.
                    
                    # Let's import ReconciliationEngine, SquareClient, QBOClient
                    from backend.services.reconciliation import ReconciliationEngine
                    from backend.connectors.square import SquareClient
                    from backend.connectors.qbo import QBOClient
                    
                    # Decrypt tokens
                    sq_token = self.tm.decrypt_token(tenant.encrypted_sq_token)
                    qbo_token = self.tm.decrypt_token(tenant.encrypted_qbo_token)
                    
                    if not sq_token or not qbo_token:
                        logger.warning(f"Skipping sync for {tenant.id}: Missing tokens")
                        continue
                        
                    # Initialize clients
                    # Note: These clients might need more args in real app (refresh tokens etc)
                    sq_client = SquareClient(token=sq_token)
                    qbo_client = QBOClient(token=qbo_token, realm_id=tenant.qbo_realm_id)
                    
                    engine = ReconciliationEngine(sq_client, qbo_client)
                    result = engine.run(auto_fix=False) # Auto-auto-fix? Maybe risky. Keep it false for now.
                    
                    # Send email if enabled
                    if tenant.email_notifications and tenant.alert_email and result.discrepancy_count > 0:
                         self.email_service.send_discrepancy_alert(tenant.alert_email, result.discrepancies)
                         
                    # Update local DB for last sync
                    # We need to add `update_last_sync` to TenantManager
                    self.tm.update_last_sync(tenant.id, now)

                except Exception as e:
                    logger.error(f"Failed to sync tenant {tenant.id}: {e}")

