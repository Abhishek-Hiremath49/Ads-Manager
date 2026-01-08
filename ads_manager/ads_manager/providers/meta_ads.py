"""
Meta Ads Provider - Direct calls to Meta Graph API (no SDK)
"""

import requests
import frappe
from typing import Dict
from ads_manager.providers.base import (
    BaseProvider,
    LaunchResult,
    AnalyticsResult,
    TokenRefreshResult,
)


class MetaAdsProvider(BaseProvider):
    PLATFORM = "Meta"  # Unified for FB/IG Ads
    MAX_BUDGET = 100000  # USD, example
    SUPPORTS_IMAGES = True
    SUPPORTS_VIDEO = True
    DAILY_API_LIMIT = 200

    def __init__(self, integration_name: str = None):
        super().__init__(integration_name)
        self.integration = frappe.get_doc("Ads Account Integration", integration_name)
        self.base_url = f"https://graph.facebook.com/{self.integration.facebook_api_version or 'v21.0'}"
        self.access_token = self.integration.get_access_token()
        self.account_id = self.integration.ad_account_id
        if not self.access_token:
            raise ValueError("Access token required")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Dict = None,
        json_data: Dict = None,
        headers: Dict = None,
    ) -> Dict:
        """Helper for API requests with auth and error handling"""
        url = f"{self.base_url}/{endpoint}"
        default_headers = {
            "Content-Type": "application/json",
        }
        if headers:
            default_headers.update(headers)

        # For GET, use params; for POST, use json
        kwargs = {"headers": default_headers}
        if method.upper() == "GET":
            kwargs["params"] = params or {}
            kwargs["params"]["access_token"] = self.access_token
        else:
            kwargs["json"] = json_data or {}
            kwargs["params"] = {"access_token": self.access_token}

        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise ValueError(data["error"].get("message", "API Error"))
            self.increment_rate_limit()
            return data
        except requests.RequestException as e:
            error_msg = str(
                e.response.json() if e.response and e.response.content else e
            )
            frappe.log_error(
                f"Meta API request failed: {error_msg} | Endpoint: {endpoint}",
                "Meta Ads API Error",
            )
            raise

    def launch_campaign(self, payload: Dict) -> LaunchResult:
        """Create a campaign via direct API POST"""
        endpoint = f"{self.account_id}/campaigns"
        data = {
            "name": payload.get("name", "New Campaign"),
            "objective": payload.get(
                "objective", "REACH"
            ),  # e.g., 'LINK_CLICKS', 'CONVERSIONS'
            "status": "PAUSED" if payload.get("start_paused", False) else "ACTIVE",
            "special_ad_categories": (
                payload.get("special_ad_category", [None])
                if payload.get("special_ad_category")
                else []
            ),
            "daily_budget": int(
                (payload.get("budget", 1000) or 0) * 100
            ),  # Convert to cents
            "bid_strategy": payload.get(
                "bid_strategy", "LOWEST_COST_WITHOUT_CAP"
            ),  # e.g., 'LOWEST_COST_WITH_BID_CAP'
            "helio_configured": False,  # For advanced bidding if needed
        }
        # Add platform targeting (e.g., Instagram only)
        if payload.get("target_instagram") and not payload.get("target_facebook"):
            data["attached_audience"] = {
                "instagram_account_ids": [
                    self.integration.instagram_business_account_id
                ]
            }

        try:
            result_data = self._make_request("POST", endpoint, json_data=data)

            if "id" in result_data:
                # Optionally chain AdSet creation (simplified; expand as needed)
                adset_data = self._create_adset(result_data["id"], payload)
                if adset_data.get("id"):
                    # Chain Ad creation
                    creative_id = payload.get("creative_id")  # From Ad Creative doc
                    if creative_id:
                        self._create_ad(
                            adset_data["id"], {"creative": {"creative_id": creative_id}}
                        )

                frappe.log_error(
                    f"Campaign launched: {result_data['id']}", "Ad Launch Success"
                )
                return LaunchResult(
                    success=True,
                    campaign_id=result_data["id"],
                    raw_response=result_data,
                )
            else:
                return LaunchResult(
                    success=False,
                    error_message=result_data.get("error", {}).get(
                        "message", "Launch failed"
                    ),
                )
        except Exception as e:
            return LaunchResult(success=False, error_message=str(e))

    def _create_adset(self, campaign_id: str, payload: Dict) -> Dict:
        """Helper: Create AdSet under campaign"""
        endpoint = f"{campaign_id}/adsets"
        data = {
            "name": f"{payload.get('name')}-AdSet",
            "daily_budget": int((payload.get("budget", 1000) or 0) * 100),
            "optimization_goal": "LINK_CLICKS",  # Map from objective
            "targeting": {
                "geo_locations": {"countries": ["US"]},  # Default; pull from campaign
                "device_platforms": (
                    ["mobile", "desktop"]
                    if payload.get("target_instagram")
                    else ["facebook"]
                ),
            },
            "status": "PAUSED",
        }
        try:
            return self._make_request("POST", endpoint, json_data=data)
        except Exception as e:
            frappe.log_error(f"Failed to create AdSet: {str(e)}", "Meta Ads Provider")
            return {}

    def _create_ad(self, adset_id: str, creative_data: Dict) -> Dict:
        """Helper: Create Ad under AdSet"""
        endpoint = f"{adset_id}/ads"
        data = {
            "name": "New Ad",
            "adset_id": adset_id,
            "creative": creative_data,
            "status": "PAUSED",
        }
        try:
            return self._make_request("POST", endpoint, json_data=data)
        except Exception as e:
            frappe.log_error(f"Failed to create Ad: {str(e)}", "Meta Ads Provider")
            return {}

    def fetch_account_analytics(self) -> AnalyticsResult:
        """Get account-level insights via GET"""
        endpoint = f"{self.account_id}/insights"
        params = {
            "fields": "impressions,spend,clicks,ctr,reach,cpm,cpc",
            "date_preset": "last_7d",
            "level": "account",
        }

        try:
            data = self._make_request("GET", endpoint, params=params)
            insights = data.get("data", [])
            metrics = {
                "impressions": sum(int(i.get("impressions", 0)) for i in insights),
                "spend": sum(float(i.get("spend", 0)) for i in insights),
                "clicks": sum(int(i.get("clicks", 0)) for i in insights),
                "ctr": (
                    round(
                        sum(float(i.get("ctr", 0)) for i in insights) / len(insights), 4
                    )
                    if insights
                    else 0
                ),
                "cpm": (
                    round(
                        sum(float(i.get("cpm", 0)) for i in insights) / len(insights), 2
                    )
                    if insights
                    else 0
                ),
                "cpc": (
                    round(
                        sum(float(i.get("cpc", 0)) for i in insights) / len(insights), 2
                    )
                    if insights
                    else 0
                ),
                "reach": sum(int(i.get("reach", 0)) for i in insights),
            }
            return AnalyticsResult(success=True, metrics=metrics, raw_response=data)
        except Exception as e:
            frappe.log_error(
                f"Account analytics failed: {str(e)}", "Meta Analytics Error"
            )
            return AnalyticsResult(success=False, error_message=str(e))

    def fetch_campaign_analytics(self, campaign_id: str) -> AnalyticsResult:
        """Get campaign-level insights"""
        endpoint = f"{campaign_id}/insights"
        params = {
            "fields": "impressions,spend,clicks,ctr",
            "date_preset": "last_7d",
            "level": "campaign",
        }

        try:
            data = self._make_request("GET", endpoint, params=params)
            insights = data.get("data", [])
            metrics = {
                "impressions": sum(int(i.get("impressions", 0)) for i in insights),
                "spend": sum(float(i.get("spend", 0)) for i in insights),
                "clicks": sum(int(i.get("clicks", 0)) for i in insights),
                "ctr": (
                    round(
                        sum(float(i.get("ctr", 0)) for i in insights) / len(insights), 4
                    )
                    if insights
                    else 0
                ),
            }
            return AnalyticsResult(success=True, metrics=metrics, raw_response=data)
        except Exception as e:
            frappe.log_error(
                f"Campaign {campaign_id} analytics failed: {str(e)}",
                "Campaign Analytics Error",
            )
            return AnalyticsResult(success=False, error_message=str(e))

    def refresh_token(self, integration_name: str = None) -> TokenRefreshResult:
        """Exchange short-lived token for long-lived (up to 60 days)"""
        settings = frappe.get_single("Ads Setting")
        endpoint = "oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": settings.facebook_app_id,
            "client_secret": settings.facebook_app_secret,
            "fb_exchange_token": self.access_token,
        }

        try:
            data = self._make_request("GET", endpoint, params=params)
            if "access_token" in data:
                return TokenRefreshResult(
                    success=True,
                    access_token=data["access_token"],
                    expires_in=data.get(
                        "expires_in", 5184000
                    ),  # Default 60 days in seconds
                )
            else:
                return TokenRefreshResult(
                    success=False,
                    error_message=data.get("error", {}).get(
                        "message", "Refresh failed"
                    ),
                )
        except Exception as e:
            return TokenRefreshResult(success=False, error_message=str(e))

    def get_daily_limit(self) -> int:
        """Daily API call limit (Meta's is ~200 for most apps)"""
        return self.DAILY_API_LIMIT

    def validate_credentials(self) -> Dict:
        """Test connection with simple GET to ad account"""
        try:
            endpoint = self.account_id
            params = {"fields": "name,account_status"}
            data = self._make_request("GET", endpoint, params=params)
            return {"success": True, "account_name": data.get("name")}
        except Exception as e:
            return {"success": False, "error": str(e)}
