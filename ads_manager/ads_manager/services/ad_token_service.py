"""
Token Service - Handles OAuth token refresh for Ads
Manages token lifecycle, validation, and automatic refresh
"""

import frappe
from frappe.utils import now_datetime, add_to_date
from typing import Dict, Any
from ads_manager.ads_manager.providers import get_provider
import logging

logger = logging.getLogger(__name__)


class TokenService:
    """Service for managing OAuth token refresh and validation"""

    @staticmethod
    def refresh_token(integration_name: str) -> Dict[str, Any]:
        """
        Refresh OAuth token for an integration
        
        Args:
            integration_name: Name of Ads Account Integration document
            
        Returns:
            Dictionary with success status and error message if failed
        """
        try:
            integration = frappe.get_doc("Ads Account Integration", integration_name)

            if not integration.enabled:
                return {"success": False, "error_message": "Integration disabled"}

            if not integration.access_token:
                return {"success": False, "error_message": "No access token found"}

            provider = get_provider(integration.platform)(integration_name)
            result = provider.refresh_token(integration_name)

            if result.success:
                integration.access_token = result.access_token
                if result.refresh_token:
                    integration.refresh_token = result.refresh_token
                if result.expires_in:
                    integration.token_expiry = add_to_date(
                        now_datetime(), seconds=result.expires_in
                    )
                integration.connection_status = "Connected"
                integration.last_error = None
                integration.save(ignore_permissions=True)
                frappe.db.commit()

                frappe.log_error(
                    f"Token refreshed for {integration_name}", "Token Refresh Success"
                )
                logger.info(f"Token successfully refreshed for {integration_name}")
                return {"success": True}
            else:
                integration.connection_status = "Expired"
                integration.last_error = result.error_message
                integration.last_error_time = now_datetime()
                integration.save(ignore_permissions=True)
                frappe.db.commit()

                frappe.log_error(
                    f"Token refresh failed: {result.error_message}",
                    "Token Refresh Failed",
                )
                logger.warning(f"Token refresh failed for {integration_name}: {result.error_message}")
                return {"success": False, "error_message": result.error_message}

        except Exception as e:
            logger.error(f"Token refresh error for {integration_name}: {str(e)}")
            frappe.log_error(frappe.get_traceback(), "Token Refresh Error")
            return {"success": False, "error_message": str(e)}

    @staticmethod
    def check_token_validity(integration_name: str) -> Dict[str, Any]:
        """
        Check if token is valid and not expired
        
        Args:
            integration_name: Name of Ads Account Integration document
            
        Returns:
            Dictionary with valid flag and reason if invalid
        """
        try:
            integration = frappe.get_doc("Ads Account Integration", integration_name)

            if not integration.enabled:
                return {"valid": False, "reason": "Integration disabled"}

            if not integration.access_token:
                return {"valid": False, "reason": "No access token"}

            if integration.token_expiry:
                if now_datetime() > integration.token_expiry:
                    return {"valid": False, "reason": "Token expired"}

            return {"valid": True}

        except frappe.DoesNotExistError:
            logger.debug(f"Integration not found: {integration_name}")
            return {"valid": False, "reason": "Integration not found"}
        except Exception as e:
            logger.error(f"Token validity check error for {integration_name}: {str(e)}")
            frappe.log_error(frappe.get_traceback(), "Token Validity Check Error")
            return {"valid": False, "reason": str(e)}

    @staticmethod
    def refresh_expiring_tokens():
        """
        Scheduled: Refresh all expiring tokens
        This should be called periodically (hourly or daily) to ensure tokens don't expire
        """
        try:
            integrations = frappe.get_all(
                "Ads Account Integration",
                filters={
                    "enabled": True,
                    "connection_status": ["in", ["Connected", "Expired"]],
                },
                fields=["name", "token_expiry"],
            )

            expiring_soon = []
            for integration in integrations:
                if integration.token_expiry:
                    time_until_expiry = (
                        integration.token_expiry - now_datetime()
                    ).total_seconds()
                    # Refresh if expiring within 24 hours
                    if 0 < time_until_expiry < 86400:
                        expiring_soon.append(integration.name)

            if expiring_soon:
                frappe.log_error(
                    f"Refreshing {len(expiring_soon)} expiring tokens",
                    "Token Refresh Scheduled",
                )
                for integration_name in expiring_soon:
                    TokenService.refresh_token(integration_name)

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Token Refresh Scheduler Error")
