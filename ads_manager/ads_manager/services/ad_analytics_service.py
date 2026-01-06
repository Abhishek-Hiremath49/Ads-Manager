"""
Ad Analytics Service - Handles ad performance collection and storage
"""

import frappe
from frappe.utils import now_datetime, today, add_days, getdate
from typing import Dict, Any, List
from ads_manager.providers import get_provider


class AdAnalyticsService:
    CAMPAIGN_ANALYTICS_LOOKBACK_DAYS = 7

    @staticmethod
    def fetch_account_analytics(integration_name: str) -> Dict[str, Any]:
        """Fetch and store account-level ad analytics"""
        integration = frappe.get_doc("Ads Account Integration", integration_name)

        if not integration.enabled or integration.connection_status != "Connected":
            return {"success": False, "error_message": "Not enabled or connected"}

        try:
            provider = get_provider(integration.platform)(integration_name)
            result = provider.fetch_account_analytics()

            if not result.success:
                return {"success": False, "error_message": result.error_message}

            # Get or create analytics doc for today
            existing = frappe.db.exists(
                "Ad Analytics", {"integration": integration_name, "date": today()}
            )
            if existing:
                doc = frappe.get_doc("Ad Analytics", existing)
            else:
                doc = frappe.new_doc("Ad Analytics")
                doc.integration = integration_name
                doc.date = today()

            doc.impressions = result.metrics.get("impressions", 0)
            doc.spend = result.metrics.get("spend", 0)
            doc.clicks = result.metrics.get("clicks", 0)
            doc.save(ignore_permissions=True)
            frappe.db.commit()

            return {"success": True, "analytics_doc": doc.name}
        except Exception as e:
            frappe.log_error(
                f"Account analytics fetch failed: {e}", "Ad Analytics Error"
            )
            return {"success": False, "error_message": str(e)}

    @staticmethod
    def get_analytics_summary(integration_name: str, days: int = 30) -> Dict[str, Any]:
        """Get ad analytics summary"""
        start_date = add_days(today(), -days)

        data = frappe.get_all(
            "Ad Analytics",
            filters={"integration": integration_name, "date": [">=", start_date]},
            fields=["*"],
            order_by="date asc",
        )

        if not data:
            return {"has_data": False}

        return {
            "has_data": True,
            "period_days": days,
            "data_points": len(data),
            "totals": {
                "impressions": sum(d.impressions or 0 for d in data),
                "spend": sum(d.spend or 0 for d in data),
                "clicks": sum(d.clicks or 0 for d in data),
                "ctr": sum(d.ctr or 0 for d in data) / len(data) if data else 0,
            },
            "roas": {
                "start": data[0].roas,
                "end": data[-1].roas,
                "change": (data[-1].roas or 0) - (data[0].roas or 0),
            },
        }

    @staticmethod
    def fetch_hourly_performance():
        """Scheduled: Hourly sync for all active campaigns"""
        integrations = frappe.get_all("Ads Account Integration", filters={"enabled": 1})
        for intg in integrations:
            AdAnalyticsService.fetch_account_analytics(intg.name)

    @staticmethod
    def sync_campaign_performance(campaign_id: str):
        """Sync performance for a specific campaign"""
        # Provider call to get insights
        pass  # Implement with provider
