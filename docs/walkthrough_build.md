# Common Build Errors & Fixes

This guide addresses common issues encountered when setting up and running the Net-to-Gross Reconciliation Daemon.

## 1. Environment & Dependencies

### Python Version Mismatch
**Error**: `ModuleNotFoundError: No module named 'match'` or syntax errors with types.
**Cause**: The project uses Python 3.10+ features (e.g., structural pattern matching, newer type hinting).
**Fix**:
```bash
python3 --version
# Ensure it is >= 3.10.0
# If not:
brew install python@3.10
```

### Missing Dependencies
**Error**: `ModuleNotFoundError: No module named 'pydantic'`
**Fix**:
```bash
pip install -r requirements.txt
```
> [!NOTE]
> Ensure you are in the active virtual environment (`source venv/bin/activate`).

### Cryptography/OpenSSL Issues
**Error**: `ImportError: ... symbol not found` in `cryptography` on macOS.
**Cause**: Mismatch between system OpenSSL and wheel.
**Fix**:
```bash
pip uninstall cryptography
LDFLAGS="-L$(brew --prefix openssl)/lib" CFLAGS="-I$(brew --prefix openssl)/include" pip install cryptography
```

## 2. Configuration & Runtime

### Missing Environment Variables
**Error**: `ValueError: Square Access Token is missing` (or similar behavior).
**Fix**: Ensure a `.env` file exists in the root:
```ini
SQUARE_ACCESS_TOKEN=your_token
QBO_REALM_ID=123
QBO_ACCESS_TOKEN=your_token
```

### SQLite Permission Denied
**Error**: `sqlite3.OperationalError: attempt to write a readonly database`
**Fix**: Ensure the user running the script has write permissions to the directory containing `.db` file.
```bash
chmod +w .
```
