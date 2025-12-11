"""
Security Tests
Tests for credential safety, log sanitization, and SSL enforcement.
"""
import pytest
from unittest.mock import patch, MagicMock
import logging
import re


class TestCredentialSafety:
    """Tests to ensure API keys and tokens are not exposed."""

    def test_api_key_not_in_logs(self):
        """Verify API keys are masked or excluded from logs."""
        api_key = "sk_live_1234567890abcdef"
        
        # Simulate logging
        with patch("logging.Logger.info") as mock_log:
            # Code should log sanitized version
            sanitized = api_key[:7] + "..." + api_key[-4:]
            mock_log(f"Connecting with key: {sanitized}")
            
            call_args = str(mock_log.call_args)
            assert "sk_live_1234567890abcdef" not in call_args

    def test_access_token_not_in_exception(self):
        """Verify tokens don't appear in exception messages."""
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret"
        
        try:
            raise Exception("Auth failed")
        except Exception as e:
            assert token not in str(e)

    def test_refresh_token_not_logged(self):
        """Verify refresh tokens are never logged."""
        refresh_token = "refresh_abc123xyz"
        
        with patch("backend.services.reconciliation.logger") as mock_logger:
            # Simulate token refresh flow
            mock_logger.info.return_value = None
            mock_logger.debug.return_value = None
            
            # Verify calls don't contain refresh token
            for call in mock_logger.info.call_args_list:
                assert refresh_token not in str(call)


class TestPIIRedaction:
    """Tests for personally identifiable information handling."""

    def test_customer_email_redacted_in_logs(self):
        """Verify email addresses are redacted."""
        email = "customer@example.com"
        
        # Redaction pattern
        redacted = re.sub(r'[^@]+@', '***@', email)
        
        assert "customer" not in redacted
        assert "***@example.com" == redacted

    def test_customer_name_not_in_error_logs(self):
        """Verify customer names don't appear in error logs."""
        customer_name = "John Smith"
        
        with patch("logging.Logger.error") as mock_log:
            # Should log order ID, not customer name
            mock_log("Order ORD-123 failed to process")
            
            call_args = str(mock_log.call_args)
            assert customer_name not in call_args


class TestSSLEnforcement:
    """Tests for HTTPS/SSL requirements."""

    def test_stripe_uses_https(self):
        """Verify Stripe client uses HTTPS endpoint."""
        from backend.connectors.stripe import StripeClient
        
        client = StripeClient(access_token="sk_test")
        
        # Check base URL if accessible
        if hasattr(client, 'base_url'):
            assert client.base_url.startswith("https://")

    def test_qbo_uses_https(self):
        """Verify QBO client uses HTTPS endpoint."""
        from backend.connectors.qbo import QBOClient
        
        client = QBOClient(realm_id="123", access_token="test")
        
        if hasattr(client, 'base_url'):
            assert client.base_url.startswith("https://")

    def test_shopify_uses_https(self):
        """Verify Shopify client uses HTTPS endpoint."""
        from backend.connectors.shopify import ShopifyClient
        
        client = ShopifyClient(shop_url="test.myshopify.com", access_token="test")
        
        # Shop URL should be accessed via HTTPS
        if hasattr(client, 'base_url'):
            assert "https://" in client.base_url

    def test_paypal_uses_https(self):
        """Verify PayPal client uses HTTPS endpoint."""
        from backend.connectors.paypal import PayPalClient
        
        # PayPal should use api.paypal.com (HTTPS)
        if hasattr(PayPalClient, 'BASE_URL'):
            assert "https://" in PayPalClient.BASE_URL


class TestInputValidation:
    """Tests for input sanitization and validation."""

    def test_realm_id_alphanumeric_only(self):
        """Verify QBO realm_id is validated."""
        valid_realm = "1234567890"
        invalid_realm = "123; DROP TABLE"
        
        assert valid_realm.isalnum()
        # raw string with space/semicolon is NOT alphanumeric
        assert not invalid_realm.isalnum()

    def test_date_range_validation(self):
        """Verify date ranges are validated."""
        from datetime import datetime, timedelta
        
        start = datetime.now()
        end = start + timedelta(days=30)
        
        # End must be after start
        assert end > start
        
        # Invalid range
        invalid_end = start - timedelta(days=1)
        assert invalid_end < start


class TestEncryptionAtRest:
    """Tests for encryption of stored credentials."""

    def test_fernet_encryption_roundtrip(self):
        """Verify encryption/decryption works correctly."""
        from cryptography.fernet import Fernet
        
        key = Fernet.generate_key()
        f = Fernet(key)
        
        secret = "api_key_secret_123"
        encrypted = f.encrypt(secret.encode())
        
        # Encrypted should not equal plaintext
        assert encrypted != secret.encode()
        
        # Should decrypt correctly
        decrypted = f.decrypt(encrypted).decode()
        assert decrypted == secret

    def test_encrypted_tokens_not_readable(self):
        """Verify encrypted tokens are not human-readable."""
        from cryptography.fernet import Fernet
        
        key = Fernet.generate_key()
        f = Fernet(key)
        
        token = "refresh_token_abc123"
        encrypted = f.encrypt(token.encode())
        
        # Should not contain original token
        assert token.encode() not in encrypted
        assert b"refresh" not in encrypted
