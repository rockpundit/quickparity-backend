"""
Edge case fixtures for testing "invisible" data anomalies.
These represent real-world scenarios that cause silent failures or accounting mismatches.
"""
from decimal import Decimal
from datetime import datetime, timedelta

# --- Emoji / Unicode Bomb ---
# Test: 4-byte unicode, Chinese characters, and SQL injection strings in descriptions
EMOJI_BOMB_PAYLOADS = [
    {"id": "po_emoji_1", "description": "🚀 Rocket Launch Sale 🎉", "amount": Decimal("100.00")},
    {"id": "po_emoji_2", "description": "订单 12345 - 中文测试", "amount": Decimal("50.00")},
    {"id": "po_emoji_3", "description": "'; DROP TABLE payments; --", "amount": Decimal("75.00")},
    {"id": "po_emoji_4", "description": "Café ☕ & Naïve résumé", "amount": Decimal("25.00")},
]

# --- Field Overflow ---
# Test: Payout with excessive line items (exceeds QBO's ~4000 char description limit)
OVERFLOW_PAYOUT = {
    "id": "po_overflow",
    "description": "A" * 5000,  # 5000 character description
    "line_items": [{"id": f"item_{i}", "amount": Decimal("1.00")} for i in range(5000)],
    "amount": Decimal("5000.00"),
}

# --- Ghost Customer (Guest Checkout) ---
# Test: Transaction with null customer - should fallback to "Generic Customer"
GHOST_CUSTOMER_PAYOUT = {
    "id": "po_ghost",
    "customer": None,
    "customer_name": None,
    "customer_email": None,
    "amount": Decimal("99.99"),
    "description": "Guest checkout order",
}

# --- Micro-Penny Precision ---
# Test: Floating point hostile numbers that expose precision errors
MICRO_PENNY_CASES = [
    {"inputs": [Decimal("0.1"), Decimal("0.2")], "expected": Decimal("0.3")},
    {"inputs": [Decimal("1.01"), Decimal("2.02"), Decimal("3.03")], "expected": Decimal("6.06")},
    {"inputs": [Decimal("0.07"), Decimal("0.14"), Decimal("0.21")], "expected": Decimal("0.42")},
    {"inputs": [Decimal("19.99"), Decimal("0.01")], "expected": Decimal("20.00")},
]

# --- Void vs Refund ---
# Test: Voided transactions (pre-settlement) vs actual refunds
VOID_TRANSACTION = {
    "id": "txn_void",
    "status": "voided",
    "amount": Decimal("100.00"),
    "fee": Decimal("2.90"),
    "description": "Voided before settlement",
}

REFUND_TRANSACTION = {
    "id": "txn_refund",
    "status": "refunded",
    "amount": Decimal("-100.00"),
    "fee": Decimal("2.90"),  # Fee not reversed
    "description": "Actual refund issued",
}

# --- Zero Value Filtering ---
# Test: 100% free items - should not create $0.00 Journal Entry
ZERO_VALUE_PAYOUT = {
    "id": "po_zero",
    "amount": Decimal("0.00"),
    "fee": Decimal("0.00"),
    "line_items": [
        {"id": "free_1", "amount": Decimal("0.00"), "description": "Free sample"},
        {"id": "free_2", "amount": Decimal("0.00"), "description": "Promo item"},
    ],
}

# --- Fiscal Year Boundary ---
# Test: Payout date differs from transaction dates (accrual accounting)
now = datetime.now()
FISCAL_BOUNDARY_PAYOUT = {
    "id": "po_fiscal",
    "payout_date": datetime(now.year, 1, 2),  # Jan 2
    "transactions": [
        {"id": "txn_1", "date": datetime(now.year - 1, 12, 31), "amount": Decimal("500.00")},
        {"id": "txn_2", "date": datetime(now.year - 1, 12, 30), "amount": Decimal("300.00")},
    ],
    "amount": Decimal("800.00"),
}
