import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Load env before imports that might check them (optional pattern)
load_dotenv()

from connectors.qbo import QBOClient
from connectors.square import SquareClient
from models import LedgerEntry, Payout, ReconciliationResult, ReconciliationStatus

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ReconciliationDaemon")

# Constants
DB_PATH = "reconciliation.db"

import argparse
import sys
import uuid
from typing import List

from models import LedgerEntry, Payout, ReconciliationResult, ReconciliationStatus, Tenant

# ... imports ...

# Constants
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
            # Generate a key if not exists and print it (for first run/setup experience)
            # In production, this should be a hard error.
            key = Fernet.generate_key().decode()
            logger.warning(f"No {ENCRYPTION_KEY_ENV} found. Generated temporary key: {key}")
            logger.warning(f"SAVE THIS KEY TO YOUR ENV VARS: export {ENCRYPTION_KEY_ENV}={key}")
        return Fernet(key.encode())

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Transactions table (existing)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                payout_id TEXT PRIMARY KEY,
                ledger_entry_id TEXT,
                variance_amount TEXT,
                status TEXT,
                timestamp TEXT
            )
        """)
        
        # Tenants table (new)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE,
                encrypted_sq_token TEXT,
                encrypted_qbo_token TEXT,
                qbo_realm_id TEXT
            )
        """)
        conn.commit()
        conn.close()

    def add_tenant(self, name: str, sq_token: str, qbo_token: str, qbo_realm: str):
        encrypted_sq = self.cipher.encrypt(sq_token.encode()).decode()
        encrypted_qbo = self.cipher.encrypt(qbo_token.encode()).decode()
        
        tenant_id = str(uuid.uuid4())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO tenants (id, name, encrypted_sq_token, encrypted_qbo_token, qbo_realm_id)
                VALUES (?, ?, ?, ?, ?)
            """, (tenant_id, name, encrypted_sq, encrypted_qbo, qbo_realm))
            conn.commit()
            logger.info(f"Tenant '{name}' added successfully.")
        except sqlite3.IntegrityError:
            logger.error(f"Tenant '{name}' already exists.")
        finally:
            conn.close()

    def list_tenants(self) -> List[Tenant]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, encrypted_sq_token, encrypted_qbo_token, qbo_realm_id FROM tenants")
        rows = cursor.fetchall()
        conn.close()
        
        return [
            Tenant(
                id=r[0], name=r[1], 
                encrypted_sq_token=r[2], 
                encrypted_qbo_token=r[3], 
                qbo_realm_id=r[4]
            ) 
            for r in rows
        ]
        
    def decrypt_token(self, encrypted_token: str) -> str:
        return self.cipher.decrypt(encrypted_token.encode()).decode()

class ReconciliationEngine:
    def __init__(self, square_client: SquareClient, qbo_client: QBOClient, db_path: str = DB_PATH):
        self.square = square_client
        self.qbo = qbo_client
        self.db_path = db_path
        # No init db here, shared responsibility or assumed existing

    def _save_result(self, result: ReconciliationResult):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO transactions (payout_id, ledger_entry_id, variance_amount, status, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (
            result.payout_id,
            result.ledger_entry_id,
            str(result.variance_amount),
            result.status.value,
            result.timestamp.isoformat()
        ))
        conn.commit()
        conn.close()

    async def run(self, auto_fix: bool = False):
        logger.info("Starting Reconciliation Run...")
        yesterday = datetime.now() - timedelta(days=1)
        start_of_day = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        try:
            payouts = await self.square.get_payouts(begin_time=start_of_day, end_time=end_of_day)
        except Exception as e:
            logger.critical(f"Failed to fetch payouts: {e}")
            return

        logger.info(f"Fetched {len(payouts)} payouts from Square.")
        for payout in payouts:
            await self.process_payout(payout, auto_fix)
        logger.info("Reconciliation Run Complete.")

    async def process_payout(self, payout: Payout, auto_fix: bool):
        logger.info(f"Processing Payout {payout.id} | Net: {payout.amount_money}")
        
        # Scan for matching QBO Deposit
        date_from = payout.created_at - timedelta(days=3)
        date_to = payout.created_at + timedelta(days=3)
        ledger_entry = await self.qbo.find_deposit(payout.amount_money, date_from, date_to)

        if not ledger_entry:
            logger.warning(f"No matching deposit found for Payout {payout.id}")
            result = ReconciliationResult(
                payout_id=payout.id,
                status=ReconciliationStatus.MISSING_DEPOSIT,
                gross_sales=Decimal("0.00"), 
                net_deposit=payout.amount_money,
                calculated_fee=payout.processing_fee,
                ledger_fee=Decimal("0.00"),
                variance_amount=payout.amount_money
            )
            self._save_result(result)
            return

        calc_variance = payout.processing_fee - abs(ledger_entry.fee_amount)
        status = ReconciliationStatus.MATCHED
        if abs(calc_variance) > Decimal("0.01"):
            status = ReconciliationStatus.VARIANCE_DETECTED
            logger.info(f"Variance Detected: Expected {payout.processing_fee}, Found {abs(ledger_entry.fee_amount)}")
        
        result = ReconciliationResult(
            payout_id=payout.id,
            ledger_entry_id=ledger_entry.id,
            status=status,
            gross_sales=ledger_entry.total_amount + abs(ledger_entry.fee_amount),
            net_deposit=payout.amount_money,
            calculated_fee=payout.processing_fee,
            ledger_fee=abs(ledger_entry.fee_amount),
            variance_amount=calc_variance
        )
        self._save_result(result)

        if status == ReconciliationStatus.VARIANCE_DETECTED and auto_fix:
            logger.info(f"Auto-fixing variance for Payout {payout.id}...")
            import hashlib
            idempotency_key = hashlib.sha256(payout.id.encode()).hexdigest()
            try:
                await self.qbo.create_journal_entry(
                    deposit_id=ledger_entry.id,
                    variance_amount=calc_variance,
                    idempotency_key=idempotency_key
                )
                logger.info("Journal Entry Created successfully.")
            except Exception as e:
                logger.error(f"Failed to auto-fix: {e}")

async def run_audit(tm: TenantManager):
    tenants = tm.list_tenants()
    if not tenants:
        logger.warning("No tenants found. Use 'add-tenant' to add a customer.")
        return

    logger.info(f"Found {len(tenants)} tenants to audit.")
    
    for tenant in tenants:
        logger.info(f"--- Auditing Tenant: {tenant.name} ---")
        try:
            sq_token = tm.decrypt_token(tenant.encrypted_sq_token)
            qbo_token = tm.decrypt_token(tenant.encrypted_qbo_token)
            
            square_client = SquareClient(access_token=sq_token)
            qbo_client = QBOClient(realm_id=tenant.qbo_realm_id, access_token=qbo_token)
            
            engine = ReconciliationEngine(square_client, qbo_client)
            await engine.run(auto_fix=True)
            
            await square_client.close()
            await qbo_client.close()
        except Exception as e:
            logger.error(f"Failed to audit tenant {tenant.name}: {e}")
            continue

def main():
    parser = argparse.ArgumentParser(description="Net-to-Gross Reconciliation Daemon")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Add Tenant Command
    add_parser = subparsers.add_parser("add-tenant", help="Add a new customer")
    add_parser.add_argument("--name", required=True, help="Customer Name")
    add_parser.add_argument("--sq-token", required=True, help="Square Access Token")
    add_parser.add_argument("--qbo-token", required=True, help="QBO Access Token")
    add_parser.add_argument("--qbo-realm", required=True, help="QBO Realm ID")
    
    # Run Command
    run_parser = subparsers.add_parser("run", help="Run reconciliation for all tenants")
    
    args = parser.parse_args()
    
    tm = TenantManager()
    
    if args.command == "add-tenant":
        tm.add_tenant(args.name, args.sq_token, args.qbo_token, args.qbo_realm)
    elif args.command == "run":
        asyncio.run(run_audit(tm))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
