# Common Scaling Errors & Mitigations

As the volume of transactions increases, the Reconciliation Daemon faces specific challenges.

## 1. Rate Limiting (API Throttling)

### Symptom
Logs show frequent `429 Too Many Requests` or slow processing due to constant backoff.

### Mitigation Strategy
1.  **Exponential Backoff**: The current implementation uses base-2 exponential backoff. If 429s persist, increase the base or max retries in `SquareClient` / `QBOClient`.
2.  **Batching**: QBO supports batch operations (up to 30 requests per batch).
    - *Action*: Refactor `create_journal_entry` to accept a list of entries and use the `/batch` endpoint.
3.  **Spread Execution**: Instead of running once a day, run hourly to process smaller chunks.

## 2. Database Growth (SQLite Limits)

### Symptom
`sqlite3.OperationalError: database is locked` or slow queries.

### Mitigation Strategy
1.  **Migrate to PostgreSQL**:
    - SQLite is for local dev/single-threaded use.
    - Change connection string in `ReconciliationEngine` to use `psycopg2` or `SQLAlchemy`.
2.  **Pruning**:
    - Implement a retention policy to delete non-variance records after 90 days.
    - `DELETE FROM transactions WHERE status='MATCHED' AND timestamp < date('now', '-90 days');`

## 3. Memory Usage

### Symptom
Process killed by OOM (Out of Memory) on AWS Lambda/Docker.
**Cause**: Loading all payouts into a list: `payouts = await ... get_payouts()`.

### Mitigation Strategy
1.  **Generators/Pagination**:
    - Modify `connector.get_payouts` to `yield` payouts page-by-page instead of returning a full list.
    - Process each payout immediately to keep memory footprint constant.
