"""
Campaign Service - Handles ad campaign launching workflow
"""

import frappe
from typing import Dict, Any
from ads_manager.providers import get_provider
from ads_manager.providers.base import LaunchResult  # Assume dataclass added


def validate_media(media_files):
    """Validate ad media"""
    if not media_files:
        return False, "Media required for ads"
    # Add size/type checks
    return True, ""


class CampaignService:
    MAX_RETRIES = 3

    @staticmethod
    def launch_campaign(campaign_name: str) -> LaunchResult:
        """Launch/schedule ad campaign"""
        campaign = frappe.get_doc("Ad Campaign", campaign_name)
        
        if campaign.status != "Scheduled":
            return LaunchResult(success=False, error_message="Campaign not scheduled")

        integration = frappe.get_doc("Ads Account Integration", campaign.ads_account)
        provider = get_provider(integration.platform)(integration.name)

        # Validate budget/objective
        if not campaign.objective:
            return LaunchResult(success=False, error_message="Objective required")

        # Prepare payload (campaign, adset, ad)
        payload = {
            "name": campaign.campaign_name,
            "objective": campaign.objective,
            "budget": campaign.campaign_daily_budget,
            "targeting": {"platform": campaign.platform},
            # Creatives, media from linked docs
        }

        # Check limits
        settings = frappe.get_single("Ads Setting")
        if not settings.can_launch_campaign(campaign.platform):
            return LaunchResult(success=False, error_message="Daily launch limit exceeded")

        try:
            result = provider.launch_campaign(payload)
            
            if result.success:
                campaign.status = "Launching"
                campaign.campaign_id = result.campaign_id
                campaign.save(ignore_permissions=True)
                settings.increment_launches(campaign.platform)
                frappe.db.commit()
                
                # Schedule performance sync
                frappe.enqueue("ads_manager.services.ad_analytics_service.sync_campaign_performance", queue="long", campaign_id=result.campaign_id)
                
            return result
        except Exception as e:
            frappe.log_error(f"Campaign launch failed: {e}", "Campaign Launch Error")
            return LaunchResult(success=False, error_message=str(e))

    @staticmethod
    def cancel_scheduled_campaign(campaign_name: str) -> Dict[str, Any]:
        campaign = frappe.get_doc("Ad Campaign", campaign_name)

        if campaign.status not in ["Draft", "Scheduled", "Failed"]:
            return {"success": False, "message": f"Cannot cancel campaign from status '{campaign.status}'"}

        campaign.db_set("status", "Cancelled")
        frappe.db.commit()

        return {"success": True}