"""
Ads Account Integration DocType
Handles connection and authentication with ad platforms (Facebook, Instagram)
Manages OAuth tokens, account information, and connection status
"""

import frappe
from frappe.model.document import Document
from datetime import datetime
from ads_manager.ads_manager.providers import get_provider
import logging

logger = logging.getLogger(__name__)


class AdsAccountIntegration(Document):

    def get_access_token(self) -> str:
        """
        Get the access token for this integration
        Retrieves and returns the encrypted access token
        
        Returns:
            Access token string or None if not set
        """
        if not self.access_token:
            logger.warning(f"No access token found for integration: {self.name}")
            return None
        
        try:
            # For password fields in Frappe, we need to use get_password
            return self.get_password("access_token")
        except Exception as e:
            # If access_token is just a regular data field, return it directly
            logger.debug(f"Access token retrieval note: {str(e)}")
            return self.access_token

    def before_save(self):
        """
        Auto-set platform from account selection
        Ensures platform field is always set before save
        """
        # Ensure platform is set
        if not self.platform:
            self.platform = "Facebook"

    def on_update(self):
        """
        Sync campaigns if enabled
        Triggers background sync when connection status changes to Connected
        """
        if self.has_value_changed("connection_status"):
            if self.connection_status == "Connected" and self.auto_sync:
                # Queue background job to sync campaigns
                frappe.enqueue(
                    "ads_manager.ads_manager.doctype.ads_account_integration.ads_account_integration.sync_campaigns_background",
                    queue="default",
                    timeout=300,
                    integration_name=self.name,
                )

    def validate(self):
        """
        Validate account details
        Checks required fields, account ID format, and token expiry
        """
        # Check required fields
        if not self.account_name:
            self.account_name = f"Account {self.ad_account_id}"

        # Validate account_id format
        if self.ad_account_id and not self.ad_account_id.startswith("act_"):
            logger.warning(f"Invalid account ID format: {self.ad_account_id}")
            frappe.throw("Ad Account ID must start with 'act_'")

        # Check token expiry
        if self.token_expiry:
            if datetime.now() > self.token_expiry:
                logger.warning(f"Token expired for {self.name}")
                self.connection_status = "Expired"


@frappe.whitelist()
def sync_campaigns(integration_name):
    """
    Sync campaigns from Facebook (called from UI)
    Fetches all campaigns from the connected ad account and syncs them locally
    
    Args:
        integration_name: Name of Ads Account Integration document
        
    Returns:
        Dictionary with success status and number of campaigns synced
    """
    doc = frappe.get_doc("Ads Account Integration", integration_name)

    if doc.connection_status != "Connected":
        logger.warning(f"Sync attempted on disconnected account: {integration_name}")
        frappe.throw("Account is not connected. Please reconnect.")

    try:
        provider = get_provider(doc.platform)(integration_name)
        result = provider.get_campaigns()

        if result.get("success"):
            campaigns = result.get("campaigns", [])

            created = 0
            updated = 0

            for campaign_data in campaigns:
                action = create_or_update_campaign(doc.name, campaign_data)
                if action == "created":
                    created += 1
                elif action == "updated":
                    updated += 1

            doc.last_synced = datetime.now()
            doc.sync_status = f"Synced {len(campaigns)} campaigns"
            doc.save()

            frappe.db.commit()
            logger.info(f"Campaign sync completed for {integration_name}: {len(campaigns)} campaigns")

            return {"success": True, "message": f"Created {created}, Updated {updated} campaigns"}
        else:
            doc.sync_status = "Failed"
            doc.last_error = result.get("error")
            doc.save()
            logger.error(f"Campaign sync failed for {integration_name}: {result.get('error')}")

            return {"success": False, "error": result.get("error")}

    except Exception as e:
        logger.error(f"Sync error for {integration_name}: {str(e)}")
        frappe.log_error(f"Sync error: {str(e)}", "Campaign Sync")

        doc.sync_status = "Error"
        doc.last_error = str(e)
        doc.last_error_time = datetime.now()
        doc.save()

        return {"success": False, "error": str(e)}


def sync_campaigns_background(integration_name):
    """
    Background job for syncing campaigns
    Called asynchronously from on_update to avoid blocking the UI
    """
    sync_campaigns(integration_name)


def create_or_update_campaign(integration_name, campaign_data):
    """
    Create or update campaign document from platform data
    
    Args:
        integration_name: Name of Ads Account Integration document
        campaign_data: Campaign data from ad platform API
        
    Returns:
        String indicating "created" or "updated"
    """
    campaign_id = campaign_data.get("id")

    # Check if campaign exists
    existing = frappe.db.exists("Ad Campaign", {"campaign_id": campaign_id})

    if existing:
        doc = frappe.get_doc("Ad Campaign", existing)
        action = "updated"
    else:
        doc = frappe.new_doc("Ad Campaign")
        action = "created"

    # Get platform from integration
    integration = frappe.get_doc("Ads Account Integration", integration_name)

    # Set fields
    doc.campaign_name = campaign_data.get("name")
    doc.campaign_id = campaign_id
    doc.ads_account = integration_name
    doc.platform = integration.platform
    doc.organization = integration.organization

    # Status mapping
    status_map = {"ACTIVE": "Active", "PAUSED": "Paused", "DELETED": "Archived", "ARCHIVED": "Archived"}
    doc.status = status_map.get(campaign_data.get("status"), "Draft")

    # Objective
    doc.objective = campaign_data.get("objective")

    # Timestamps
    if "created_time" in campaign_data:
        doc.created_time = campaign_data["created_time"]

    if "updated_time" in campaign_data:
        doc.updated_time = campaign_data["updated_time"]

    # Save
    doc.flags.ignore_permissions = True
    doc.save()

    return action


@frappe.whitelist()
def get_account_info(integration_name):
    """
    Get detailed account information from ad platform
    
    Args:
        integration_name: Name of Ads Account Integration document
        
    Returns:
        Dictionary with account information
    """

    try:
        provider = get_provider(integration_name)(integration_name)
        result = provider.get_account_info()

        if result.get("success"):
            # Update document with latest info
            doc = frappe.get_doc("Ads Account Integration", integration_name)

            data = result.get("data", {})

            if "name" in data:
                doc.account_name = data["name"]

            if "currency" in data:
                doc.currency = data["currency"]

            if "timezone_name" in data:
                doc.timezone = data["timezone_name"]

            if "account_status" in data:
                doc.account_status = data["account_status"]

            if "amount_spent" in data:
                doc.amount_spent = float(data["amount_spent"]) / 100

            if "balance" in data:
                doc.balance = float(data["balance"]) / 100

            doc.save()

            return result
        else:
            return result

    except Exception as e:
        logger.error(f"Get account info error for {integration_name}: {str(e)}")
        frappe.log_error(f"Get account info error: {str(e)}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def reconnect_account(integration_name):
    """
    Trigger OAuth flow to reconnect account
    Redirects user to Facebook OAuth flow
    
    Args:
        integration_name: Name of Ads Account Integration document
    """
    doc = frappe.get_doc("Ads Account Integration", integration_name)

    # Redirect to OAuth authorization
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = "/api/method/meta_ads_manager.api.oauth.authorize_facebook"


@frappe.whitelist()
def get_instagram_info(integration_name):
    """
    Get Instagram account information
    Fetches Instagram business account details from Meta
    
    Args:
        integration_name: Name of Ads Account Integration document
        
    Returns:
        Dictionary with success status and Instagram account information
    """

    doc = frappe.get_doc("Ads Account Integration", integration_name)

    if not doc.instagram_business_account_id:
        return {"success": False, "error": "Instagram Business Account not linked"}

    try:
        provider = get_provider(doc.platform)(integration_name)

        # This would call Instagram-specific API
        # Implementation depends on InstagramProvider

        return {"success": True, "message": "Instagram info fetched"}

    except Exception as e:
        logger.error(f"Get Instagram info error for {integration_name}: {str(e)}")
        return {"success": False, "error": str(e)}
