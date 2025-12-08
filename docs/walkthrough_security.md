# Security Validation & Best Practices

Ensuring the "Headless Auditor" is secure from outside interference and data leaks.

## 1. Outside Interference (Man-in-the-Middle)

### Risk
An attacker intercepts the connection to Square/QBO to inject fake data.

### Validation
- **TLS Verification**: The `httpx` client verifies SSL certificates by default.
    - *Test*: Attempt to proxy traffic through a self-signed proxy (e.g., Charles Proxy) without trusting the root CA. The script MUST fail with `ssl.SSLCertVerificationError`.
- **Source of Truth**: Never accept payouts pushed via unverified webhooks without signature validation. (Current implementation pulls from API, which is safer).

## 2. Data Persistence (PII Leaks)

### Risk
Storing Customer Names or Credit Card numbers in the local database or logs.

### Validation
- **Log Review**: Run the daemon in a test environment. Grep logs for regex of Email patterns (`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`).
    - *Pass Condition*: No matches found.
- **Database Inspection**:
    - Open `reconciliation.db`.
    - stored fields must ONLY be: `payout_id`, `ledger_entry_id`, `variance_amount`, `status`.
    - *Fail Condition*: Any column containing "Customer" or "Description" with raw text.

## 3. Credential Storage

### Risk
Plaintext API tokens in environment variables or code.

### Mitigation
- **Encryption at Rest**:
    - Use `cryptography.fernet` to encrypt tokens in the env or `.env` file.
    - Decrypt only in memory at runtime (as shown in `main.py` scaffolding).
- **Least Privilege**:
    - Square Token Scope: `PAYOUTS_READ` only. (Verify in Square Developer Dashboard).
    - QBO Token Scope: `Accounting` (limited if possible).
