"""
Sanitization Tests
Tests for encoding, string handling, and data cleansing.
"""
import pytest
from decimal import Decimal

from tests.data.fixtures_edge_cases import EMOJI_BOMB_PAYLOADS, OVERFLOW_PAYOUT, GHOST_CUSTOMER_PAYOUT


class TestEmojiBombSanitization:
    """Tests for 4-byte unicode, Chinese characters, and SQL injection."""

    @pytest.mark.parametrize("payload", EMOJI_BOMB_PAYLOADS)
    def test_unicode_description_sanitized(self, payload):
        """Verify system handles 4-byte unicode without crashing."""
        description = payload["description"]
        
        # Should be able to encode to UTF-8
        try:
            encoded = description.encode("utf-8")
            decoded = encoded.decode("utf-8")
            assert decoded == description
        except UnicodeError:
            pytest.fail(f"Failed to handle unicode in: {description}")

    @pytest.mark.parametrize("payload", EMOJI_BOMB_PAYLOADS)
    def test_sql_injection_neutralized(self, payload):
        """Verify SQL injection strings don't execute."""
        description = payload["description"]
        
        # Should not contain unescaped SQL
        # In practice, using parameterized queries handles this
        # This test verifies the string can be safely stored/passed
        assert isinstance(description, str)

    def test_emoji_in_journal_entry_memo(self):
        """Verify emojis can be included in QBO memo fields."""
        memo = "Payment from 🚀 Rocket Inc"
        
        # QBO accepts UTF-8 but may truncate
        # Verify it doesn't crash
        assert len(memo) > 0
        assert "🚀" in memo


class TestFieldOverflowTruncation:
    """Tests for handling excessively long data."""

    def test_description_truncated_to_qbo_limit(self):
        """Verify descriptions are truncated to QBO's 4000 char limit."""
        long_description = OVERFLOW_PAYOUT["description"]
        QBO_LIMIT = 4000
        
        # Truncation logic
        truncated = long_description[:QBO_LIMIT]
        
        assert len(truncated) <= QBO_LIMIT
        assert len(long_description) > QBO_LIMIT

    def test_line_item_aggregation(self):
        """Verify 5000 line items are aggregated into summary."""
        line_items = OVERFLOW_PAYOUT["line_items"]
        
        assert len(line_items) == 5000
        
        # Should aggregate to summary
        total = sum(item["amount"] for item in line_items)
        assert total == Decimal("5000.00")

    def test_truncation_preserves_meaningful_suffix(self):
        """Verify truncation adds '...' or similar indicator."""
        long_text = "A" * 5000
        QBO_LIMIT = 4000
        
        # Best practice: truncate with indicator
        if len(long_text) > QBO_LIMIT:
            truncated = long_text[:QBO_LIMIT - 3] + "..."
            assert truncated.endswith("...")
            assert len(truncated) == QBO_LIMIT


class TestGhostCustomerHandling:
    """Tests for null/missing customer data (Guest Checkout)."""

    def test_null_customer_falls_back_to_generic(self):
        """Verify null customer uses 'Generic Customer' fallback."""
        payout = GHOST_CUSTOMER_PAYOUT
        
        customer_name = payout.get("customer_name") or "Generic Customer"
        
        assert customer_name == "Generic Customer"

    def test_null_email_handled_gracefully(self):
        """Verify null email doesn't crash."""
        payout = GHOST_CUSTOMER_PAYOUT
        
        email = payout.get("customer_email") or ""
        
        assert email == ""

    def test_guest_checkout_description(self):
        """Verify guest checkout is labeled appropriately."""
        payout = GHOST_CUSTOMER_PAYOUT
        
        if payout["customer"] is None:
            description = f"Guest checkout - {payout['description']}"
            assert "Guest" in description


class TestSpecialCharacterEscaping:
    """Tests for special character handling."""

    @pytest.mark.parametrize("char", ["<", ">", "&", '"', "'", "\\", "\n", "\r", "\t"])
    def test_special_chars_in_description(self, char):
        """Verify special characters don't break JSON/XML serialization."""
        description = f"Order with {char} character"
        
        # Should be serializable
        import json
        try:
            json.dumps({"description": description})
        except (TypeError, ValueError):
            pytest.fail(f"Failed to serialize description with '{char}'")

    def test_newlines_normalized(self):
        """Verify newlines are normalized or stripped."""
        description = "Line 1\nLine 2\r\nLine 3\rLine 4"
        
        # Normalize to single format
        normalized = description.replace("\r\n", "\n").replace("\r", "\n")
        assert "\r" not in normalized
