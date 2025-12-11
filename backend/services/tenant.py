import os
import sqlite3
import uuid
from typing import List
import json
from datetime import datetime
from cryptography.fernet import Fernet
from backend.models import Tenant
import logging

logger = logging.getLogger(__name__)

DB_PATH = "reconciliation.db"
ENCRYPTION_KEY_ENV = "ENCRYPTION_KEY"

class TenantManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()
        self.cipher = self._get_cipher()

    def _get_cipher(self) -> Fernet:
        key = os.getenv(ENCRYPTION_KEY_ENV)
        if not key:
            # Use a static key for dev convenience to ensure consistency across threads/restarts
            # if the env var isn't set.
            key = "kxskS9PbGTarlthp-4JyGZYh5YVJv1US6NRn0_sYGPo=" 
            logger.warning(f"No {ENCRYPTION_KEY_ENV} found. Using static dev key.")
        return Fernet(key.encode())

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tenants table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE,
                encrypted_sq_token TEXT,
                encrypted_stripe_token TEXT,
                encrypted_shopify_token TEXT,
                encrypted_paypal_token TEXT,
                encrypted_qbo_token TEXT,
                qbo_realm_id TEXT
            )
        """)
        
        # Simple migration for existing dev database
        try:
             cursor.execute("ALTER TABLE tenants ADD COLUMN encrypted_shopify_token TEXT")
        except sqlite3.OperationalError:
             pass # Column likely exists
             
        try:
             cursor.execute("ALTER TABLE tenants ADD COLUMN encrypted_paypal_token TEXT")
        except sqlite3.OperationalError:
             pass # Column likely exists

        # Migration for mappings settings
        try:
             cursor.execute("ALTER TABLE tenants ADD COLUMN deposit_mapping TEXT")
             cursor.execute("ALTER TABLE tenants ADD COLUMN refund_mapping TEXT")
             cursor.execute("ALTER TABLE tenants ADD COLUMN auto_fix BOOLEAN")
        except sqlite3.OperationalError:
             pass # Columns likely exist
             
        try:
             cursor.execute("ALTER TABLE tenants ADD COLUMN encrypted_qbo_refresh_token TEXT")
        except sqlite3.OperationalError:
             pass # Column likely exists
             
        try:
             cursor.execute("ALTER TABLE tenants ADD COLUMN subscription_tier TEXT DEFAULT 'free'")
        except sqlite3.OperationalError:
             pass # Column likely exists

        # Migrations for sync settings
        try:
             cursor.execute("ALTER TABLE tenants ADD COLUMN sync_frequency TEXT DEFAULT 'manual'")
        except sqlite3.OperationalError:
             pass
        try:
             cursor.execute("ALTER TABLE tenants ADD COLUMN email_notifications BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
             pass
        try:
             cursor.execute("ALTER TABLE tenants ADD COLUMN alert_email TEXT")
        except sqlite3.OperationalError:
             pass
        try:
             cursor.execute("ALTER TABLE tenants ADD COLUMN last_sync_at TIMESTAMP")
        except sqlite3.OperationalError:
             pass
             
        conn.commit()
        conn.close()

    def add_tenant(self, name: str, sq_token: str, qbo_token: str, qbo_realm: str, stripe_token: str = None, shopify_token: str = None, paypal_token: str = None, qbo_refresh_token: str = None, subscription_tier: str = "free") -> Tenant:
        encrypted_sq = self.cipher.encrypt(sq_token.encode()).decode()
        encrypted_qbo = self.cipher.encrypt(qbo_token.encode()).decode()
        encrypted_stripe = self.cipher.encrypt(stripe_token.encode()).decode() if stripe_token else None
        encrypted_shopify = self.cipher.encrypt(shopify_token.encode()).decode() if shopify_token else None
        encrypted_paypal = self.cipher.encrypt(paypal_token.encode()).decode() if paypal_token else None
        encrypted_qbo_refresh = self.cipher.encrypt(qbo_refresh_token.encode()).decode() if qbo_refresh_token else None
        
        tenant_id = str(uuid.uuid4())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO tenants (id, name, encrypted_sq_token, encrypted_stripe_token, encrypted_shopify_token, encrypted_paypal_token, encrypted_qbo_token, qbo_realm_id, encrypted_qbo_refresh_token, subscription_tier)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (tenant_id, name, encrypted_sq, encrypted_stripe, encrypted_shopify, encrypted_paypal, encrypted_qbo, qbo_realm, encrypted_qbo_refresh, subscription_tier))
            conn.commit()
            logger.info(f"Tenant '{name}' added successfully.")
            return Tenant(
                id=tenant_id,
                name=name,
                encrypted_sq_token=encrypted_sq,
                encrypted_qbo_token=encrypted_qbo,
                encrypted_qbo_refresh_token=encrypted_qbo_refresh,
                qbo_realm_id=qbo_realm,
                encrypted_shopify_token=encrypted_shopify,
                encrypted_paypal_token=encrypted_paypal,
                subscription_tier=subscription_tier
            )
        except sqlite3.IntegrityError:
            logger.error(f"Tenant '{name}' already exists.")
            raise ValueError(f"Tenant '{name}' already exists.")
        finally:
            conn.close()

    def list_tenants(self) -> List[Tenant]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, encrypted_sq_token, encrypted_stripe_token, encrypted_shopify_token, encrypted_paypal_token, encrypted_qbo_token, qbo_realm_id, deposit_mapping, refund_mapping, auto_fix, encrypted_qbo_refresh_token, subscription_tier, sync_frequency, email_notifications, alert_email, last_sync_at FROM tenants")
        rows = cursor.fetchall()
        conn.close()
        
        return [
            Tenant(
                id=r[0], name=r[1], 
                encrypted_sq_token=r[2], 
                encrypted_stripe_token=r[3],
                encrypted_shopify_token=r[4],
                encrypted_paypal_token=r[5],
                encrypted_qbo_token=r[6], 
                qbo_realm_id=r[7],
                deposit_account_mapping=json.loads(r[8]) if r[8] else {},
                refund_account_mapping=r[9] if r[9] else "returns",
                auto_fix_variances=bool(r[10]) if r[10] is not None else False,
                encrypted_qbo_refresh_token=r[11] if len(r) > 11 else None,
                subscription_tier=r[12] if len(r) > 12 and r[12] else "free",
                sync_frequency=r[13] if len(r) > 13 and r[13] else "manual",
                email_notifications=bool(r[14]) if len(r) > 14 and r[14] is not None else False,
                alert_email=r[15] if len(r) > 15 else None,
                last_sync_at=datetime.fromisoformat(r[16]) if len(r) > 16 and r[16] else None
            ) 
            for r in rows
        ]
        
    
    def update_tenant_token(self, tenant_id: str, token_type: str, token_value: str):
        """
        Updates a specific token for a tenant.
        token_type: 'stripe', 'qbo', 'square'
        """
        encrypted_token = self.cipher.encrypt(token_value.encode()).decode()
        
        column_map = {
            "stripe": "encrypted_stripe_token",
            "qbo": "encrypted_qbo_token",
            "qbo_refresh": "encrypted_qbo_refresh_token",
            "square": "encrypted_sq_token",
            "shopify": "encrypted_shopify_token",
            "paypal": "encrypted_paypal_token"
        }
        
        if token_type not in column_map:
            raise ValueError(f"Invalid token type: {token_type}")
            
        column = column_map[token_type]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE tenants SET {column} = ? WHERE id = ?", (encrypted_token, tenant_id))
        conn.commit()
        conn.close()

    def decrypt_token(self, encrypted_token: str) -> str:
        if not encrypted_token:
            return None
        return self.cipher.decrypt(encrypted_token.encode()).decode()

    def update_settings(self, tenant_id: str, deposit_map: dict, refund_map: str, auto_fix: bool):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tenants 
            SET deposit_mapping = ?, refund_mapping = ?, auto_fix = ?
            WHERE id = ?
        """, (json.dumps(deposit_map), refund_map, auto_fix, tenant_id))
        conn.commit()
        conn.close()

    def update_notification_settings(self, tenant_id: str, sync_frequency: str, email_notifications: bool, alert_email: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tenants 
            SET sync_frequency = ?, email_notifications = ?, alert_email = ?
            WHERE id = ?
        """, (sync_frequency, email_notifications, alert_email, tenant_id))
        conn.commit()
        conn.close()
        
    def update_last_sync(self, tenant_id: str, last_sync: datetime):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tenants 
            SET last_sync_at = ?
            WHERE id = ?
        """, (last_sync.isoformat(), tenant_id))
        conn.commit()
        conn.close()
