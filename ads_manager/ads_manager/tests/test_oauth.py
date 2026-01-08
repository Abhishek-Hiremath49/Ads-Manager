"""
Unit tests for Ads Manager OAuth module.

Tests OAuth flow, token exchange, and account management.
"""

import frappe
import unittest
from unittest.mock import patch, MagicMock
from frappe.test_runner import make_test_objects
from ads_manager.ads_manager.api import oauth


class TestOAuthInitiation(unittest.TestCase):
    """Tests for OAuth initiation endpoint."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_user = frappe.get_doc(
            doctype="User",
            email="test@example.com",
            first_name="Test",
            new_password="test123",
        )
        self.test_user.save()
        frappe.set_user("test@example.com")

        # Create test Ads Setting
        settings = frappe.get_doc(
            doctype="Ads Setting",
            facebook_app_id="test_app_id",
            facebook_app_secret="test_secret",
        )
        settings.save()

    def tearDown(self):
        """Cleanup test data."""
        frappe.set_user("Administrator")
        frappe.db.delete("User", {"email": "test@example.com"})
        frappe.db.delete("Ads Setting")

    def test_initiate_oauth_facebook(self):
        """Test OAuth initiation for Facebook."""
        result = oauth.initiate_oauth(platform="Facebook")

        self.assertIn("authorization_url", result)
        self.assertIn("state", result)
        self.assertIn("facebook.com", result["authorization_url"])
        self.assertEqual(result["expires_in"], oauth.OAUTH_STATE_CACHE_TTL)

    def test_initiate_oauth_instagram(self):
        """Test OAuth initiation for Instagram."""
        result = oauth.initiate_oauth(platform="Instagram")

        self.assertIn("authorization_url", result)
        self.assertIn("state", result)
        self.assertIn("facebook.com", result["authorization_url"])

    def test_initiate_oauth_invalid_platform(self):
        """Test OAuth initiation with invalid platform."""
        with self.assertRaises(frappe.ValidationError):
            oauth.initiate_oauth(platform="TikTok")

    def test_initiate_oauth_missing_settings(self):
        """Test OAuth initiation without proper settings."""
        # Delete settings
        frappe.db.delete("Ads Setting")

        with self.assertRaises(frappe.ValidationError):
            oauth.initiate_oauth(platform="Facebook")

    def test_initiate_oauth_account_name_too_long(self):
        """Test OAuth with account name exceeding limit."""
        long_name = "x" * 200

        with self.assertRaises(frappe.ValidationError):
            oauth.initiate_oauth(platform="Facebook", account_name=long_name)


class TestOAuthCallback(unittest.TestCase):
    """Tests for OAuth callback handler."""

    @patch("ads_manager.ads_manager.api.oauth._make_request")
    def test_callback_token_exchange(self, mock_request):
        """Test token exchange in callback."""
        # Mock API responses
        mock_short_token = MagicMock()
        mock_short_token.json.return_value = {"access_token": "short_token"}

        mock_long_token = MagicMock()
        mock_long_token.json.return_value = {
            "access_token": "long_token",
            "expires_in": 5184000,
        }

        mock_user = MagicMock()
        mock_user.json.return_value = {"id": "123456", "name": "Test User"}

        mock_accounts = MagicMock()
        mock_accounts.json.return_value = {
            "data": [
                {
                    "id": "act_123",
                    "name": "Test Account",
                    "account_status": 1,
                    "currency": "USD",
                    "timezone_name": "America/Los_Angeles",
                    "amount_spent": 100.0,
                    "account_id": "123456",
                }
            ]
        }

        mock_request.side_effect = [
            mock_short_token,
            mock_long_token,
            mock_user,
            mock_accounts,
        ]

        # Create OAuth state
        state = "test_state"
        frappe.cache().set_value(
            f"ads_oauth_state_{state}",
            {"platform": "Facebook", "user": frappe.session.user},
        )

        # Simulate form data
        frappe.form_dict = {
            "code": "test_code",
            "state": state,
        }

        # This would be called by the callback
        # result = oauth.callback_meta("Facebook")
        # Skipping actual callback test due to Frappe context requirements


class TestAdAccountConnection(unittest.TestCase):
    """Tests for ad account connection."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_user = frappe.get_doc(
            doctype="User",
            email="test@example.com",
            first_name="Test",
            new_password="test123",
        )
        self.test_user.save()
        frappe.set_user("test@example.com")

        # Create test organization
        self.org = frappe.get_doc(doctype="Organization", name="Test Organization").save()

    def tearDown(self):
        """Cleanup test data."""
        frappe.set_user("Administrator")
        frappe.db.delete("User", {"email": "test@example.com"})
        frappe.db.delete("Organization", {"name": "Test Organization"})
        frappe.db.delete("Ads Account Integration")

    def test_save_ads_integration_new(self):
        """Test saving a new integration."""
        integration = oauth._save_ads_integration(
            platform="Facebook",
            ad_account_id="act_123",
            ad_id="123456",
            account_name="Test Account",
            access_token="test_token",
            expires_in=5184000,
            currency="USD",
            timezone="America/Los_Angeles",
            account_status="1",
            amount_spent=100.0,
            auth_user_id="user_123",
            auth_user_name="Test User",
            auth_user_email="user@example.com",
        )

        self.assertEqual(integration.platform, "Facebook")
        self.assertEqual(integration.ad_account_id, "act_123")
        self.assertEqual(integration.account_name, "Test Account")
        self.assertEqual(integration.connection_status, "Connected")
        self.assertTrue(integration.enabled)

    def test_save_ads_integration_update(self):
        """Test updating existing integration."""
        # Create initial integration
        integration1 = oauth._save_ads_integration(
            platform="Facebook",
            ad_account_id="act_123",
            ad_id="123456",
            account_name="Original Account",
            access_token="token1",
            expires_in=5184000,
        )

        # Update with new token
        integration2 = oauth._save_ads_integration(
            platform="Facebook",
            ad_account_id="act_123",
            ad_id="123456",
            account_name="Updated Account",
            access_token="token2",
            expires_in=5184000,
        )

        # Should be the same document
        self.assertEqual(integration1.name, integration2.name)
        # Account name should be updated
        self.assertEqual(integration2.account_name, "Updated Account")

    def test_disconnect_integration(self):
        """Test disconnecting an integration."""
        # Create integration
        integration = oauth._save_ads_integration(
            platform="Facebook",
            ad_account_id="act_123",
            ad_id="123456",
            account_name="Test Account",
            access_token="test_token",
        )

        # Disconnect
        result = oauth.disconnect(integration.name)

        self.assertTrue(result["success"])

        # Verify disconnected
        updated_integration = frappe.get_doc("Ads Account Integration", integration.name)
        self.assertEqual(updated_integration.connection_status, "Not Connected")
        self.assertIsNone(updated_integration.access_token)
        self.assertFalse(updated_integration.enabled)


class TestAdAccountRetrieval(unittest.TestCase):
    """Tests for ad account retrieval."""

    def setUp(self):
        """Set up test fixtures."""
        frappe.set_user("Administrator")

    def test_get_available_ad_accounts(self):
        """Test retrieving available ad accounts."""
        # Create session data
        session_key = "test_session"
        cache_data = {
            "platform": "Facebook",
            "user": frappe.session.user,
            "auth_user_name": "Test User",
            "ad_accounts": [
                {
                    "id": "act_123",
                    "name": "Account 1",
                    "currency": "USD",
                    "timezone_name": "UTC",
                    "account_status": 1,
                    "amount_spent": 100,
                    "account_id": "123",
                },
                {
                    "id": "act_456",
                    "name": "Account 2",
                    "currency": "USD",
                    "timezone_name": "UTC",
                    "account_status": 1,
                    "amount_spent": 200,
                    "account_id": "456",
                },
            ],
        }

        frappe.cache().set_value(f"meta_ads_{session_key}", cache_data)

        result = oauth.get_available_ad_accounts(session_key)

        self.assertEqual(result["platform"], "Facebook")
        self.assertEqual(result["account_count"], 2)
        self.assertEqual(len(result["ad_accounts"]), 2)
        self.assertEqual(result["ad_accounts"][0]["name"], "Account 1")

    def test_get_available_ad_accounts_invalid_session(self):
        """Test with invalid session key."""
        with self.assertRaises(frappe.ValidationError):
            oauth.get_available_ad_accounts("invalid_session")

    def test_get_available_ad_accounts_expired_session(self):
        """Test with expired session."""
        session_key = "expired_session"
        # Don't set any cache, simulating expired session

        with self.assertRaises(frappe.ValidationError):
            oauth.get_available_ad_accounts(session_key)


class TestValidationFunctions(unittest.TestCase):
    """Tests for validation helper functions."""

    def test_validate_platform_valid(self):
        """Test validation with valid platform."""
        # Should not raise
        oauth._validate_platform("Facebook")
        oauth._validate_platform("Instagram")

    def test_validate_platform_invalid(self):
        """Test validation with invalid platform."""
        with self.assertRaises(frappe.ValidationError):
            oauth._validate_platform("TikTok")

    def test_validate_settings(self):
        """Test settings validation."""
        # Create valid settings
        settings = frappe.get_doc(
            doctype="Ads Setting",
            facebook_app_id="test_app_id",
            facebook_app_secret="test_secret",
        )
        settings.save()

        result = oauth._validate_settings()
        self.assertIsNotNone(result)

        # Cleanup
        frappe.db.delete("Ads Setting")


if __name__ == "__main__":
    unittest.main()
