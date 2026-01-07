"""
Campaign Service - Handles ad campaign launching workflow
"""

import frappe
from typing import Dict, Any
from ads_manager.ads_manager.providers import get_provider
from ads_manager.ads_manager.providers.base import PublishResult
from frappe.utils import now_datetime


def validate_media(media_files):
    """Validate ad media"""
    if not media_files:
        return False, "Media required for ads"

    # Add validation for media types and sizes
    for media in media_files:
        if not media.get("file_url"):
            return False, "Invalid media file"

    return True, ""


class PostService:
    MAX_RETRIES = 3

    @staticmethod
    def launch_campaign(campaign_name: str) -> PublishResult:
        """Launch/schedule ad campaign"""
        try:
            campaign = frappe.get_doc("Ad Campaign", campaign_name)

            # Validate campaign status
            if campaign.status != "Scheduled":
                return PublishResult(
                    success=False,
                    error_message=f"Campaign not in Scheduled status (current: {campaign.status})",
                )

            # Validate integration
            if not campaign.ads_account:
                return PublishResult(success=False, error_message="No Ads Account Integration specified")

            integration = frappe.get_doc("Ads Account Integration", campaign.ads_account)

            # Check integration status
            if integration.connection_status != "Connected":
                return PublishResult(
                    success=False,
                    error_message=f"Integration not connected (status: {integration.connection_status})",
                )

            if not integration.enabled:
                return PublishResult(success=False, error_message="Integration is disabled")

            # Get provider
            try:
                provider = get_provider(integration.platform)(integration.name)
            except Exception as e:
                return PublishResult(
                    success=False,
                    error_message=f"Failed to initialize provider: {str(e)}",
                )

            # Validate required fields
            if not campaign.objective:
                return PublishResult(success=False, error_message="Campaign objective is required")

            if not campaign.campaign_name:
                return PublishResult(success=False, error_message="Campaign name is required")

            if not campaign.campaign_daily_budget or campaign.campaign_daily_budget <= 0:
                return PublishResult(success=False, error_message="Valid campaign budget is required")

            # Validate media
            media_valid, media_error = validate_media(campaign.creatives)
            if not media_valid:
                return PublishResult(success=False, error_message=media_error)

            # Check limits
            settings = frappe.get_single("Ads Setting")
            if not settings.can_launch_campaign(integration.platform):
                return PublishResult(
                    success=False,
                    error_message=f"Daily limit reached for {integration.platform}",
                )

            # Prepare payload
            payload = {
                "name": campaign.campaign_name,
                "objective": campaign.objective,
                "budget": campaign.campaign_daily_budget,
                "targeting": {"platform": integration.platform},
                "creatives": campaign.creatives,
            }

            # Launch campaign
            result = provider.launch_campaign(payload)

            if result.success:
                campaign.status = "Active"
                campaign.external_campaign_id = result.external_id
                campaign.launched_at = now_datetime()
                campaign.save(ignore_permissions=True)
                frappe.db.commit()

                frappe.log_error(
                    f"Campaign {campaign_name} launched successfully",
                    "Campaign Launch Success",
                )
            else:
                campaign.status = "Failed"
                campaign.last_error = result.error_message
                campaign.save(ignore_permissions=True)
                frappe.db.commit()

                frappe.log_error(
                    f"Campaign launch failed: {result.error_message}",
                    "Campaign Launch Failed",
                )

            return result

        except frappe.DoesNotExistError as e:
            error_msg = f"Document not found: {str(e)}"
            frappe.log_error(error_msg, "Campaign Launch Error")
            return PublishResult(success=False, error_message=error_msg)
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Campaign Launch Error")
            return PublishResult(success=False, error_message=f"Unexpected error: {str(e)}")

    @staticmethod
    def cancel_scheduled_campaign(campaign_name: str) -> Dict[str, Any]:
        """Cancel a scheduled campaign"""
        try:
            campaign = frappe.get_doc("Ad Campaign", campaign_name)

            if campaign.status not in ["Scheduled", "Active"]:
                return {
                    "success": False,
                    "error_message": f"Cannot cancel campaign in {campaign.status} status",
                }

            campaign.status = "Cancelled"
            campaign.save(ignore_permissions=True)
            frappe.db.commit()

            return {"success": True, "message": "Campaign cancelled successfully"}

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Campaign Cancellation Error")
            return {"success": False, "error_message": str(e)}
