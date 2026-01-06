import frappe
from ads_manager.services.campaign_service import CampaignService
from ads_manager.services.ad_analytics_service import AdAnalyticsService
from ads_manager.services.token_service import TokenService
from ads_manager.doctype.ads_setting.ads_setting import AdsSetting


def launch_scheduled_campaigns():
    """Launch due campaigns every minute"""
    due_campaigns = frappe.get_all(
        "Ad Campaign",
        filters={"status": "Scheduled", "start_time": ["<=", frappe.utils.now()]},
        fields=["name"],
    )
    for camp in due_campaigns:
        CampaignService.launch_campaign(camp.name)


def reset_daily_ad_limits():
    """Daily reset of limits"""
    settings = frappe.get_single("Ads Setting")
    settings.reset_daily_counters()


def refresh_expiring_tokens():
    """Hourly token refresh"""
    TokenService.refresh_expiring_tokens()


def fetch_daily_analytics():
    """Daily full analytics sync"""
    AdAnalyticsService.fetch_hourly_performance()  # Reuse
