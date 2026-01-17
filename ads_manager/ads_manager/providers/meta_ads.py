"""
Meta Ads Provider - Direct calls to Meta Graph API (no SDK)
Handles Facebook and Instagram ad operations through Meta Graph API
"""

import requests
import frappe
from typing import Dict, Optional
from ads_manager.ads_manager.providers.base import (
    BaseProvider,
    PublishResult,
    AnalyticsResult,
    TokenRefreshResult,
)
import logging

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3


class MetaAdsProvider(BaseProvider):
    PLATFORM = "Meta"
    MAX_BUDGET = 100000
    SUPPORTS_IMAGES = True
    SUPPORTS_VIDEO = True
    DAILY_API_LIMIT = 200

    def __init__(self, integration_name: str = None):
        super().__init__(integration_name)
        try:
            self.api_version = self.settings.meta_api_version or "v24.0"
            self.integration = frappe.get_doc("Ads Account Integration", integration_name)
            self.base_url = f"https://graph.facebook.com/{self.api_version}"
            self.access_token = self.integration.get_access_token()
            self.account_id = self.integration.ad_account_id.strip()

            if not self.access_token:
                raise ValueError("No access token")
            if not self.account_id or not self.account_id.startswith("act_"):
                raise ValueError(f"Invalid ad_account_id: {self.account_id}")
        except Exception as e:
            logger.error(f"MetaAdsProvider init failed for {integration_name}: {e}")
            raise

    def _make_request(
        self, method: str, endpoint: str, params: Dict = None, json_data: Dict = None, headers: Dict = None, files: Dict = None
    ) -> Dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        default_headers = {"Content-Type": "application/json"}
        if headers:
            default_headers.update(headers)

        kwargs = {"headers": default_headers, "timeout": REQUEST_TIMEOUT}
        if method.upper() == "GET":
            kwargs["params"] = {**(params or {}), "access_token": self.access_token}
        else:
            if files:
                # For multipart file uploads, don't set Content-Type (requests will set it with boundary)
                kwargs.pop("headers", None)
                kwargs["files"] = files
            else:
                kwargs["json"] = json_data or {}
            kwargs["params"] = {"access_token": self.access_token}

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.request(method.upper(), url, **kwargs)
                response.raise_for_status()
                data = response.json()

                if "error" in data:
                    error = data["error"]
                    error_msg = (
                        f"[{error.get('code')}] {error.get('message')} "
                        f"(type: {error.get('type')}, subcode: {error.get('error_subcode', 'N/A')})"
                    )
                    logger.error(f"Meta API ERROR {endpoint}: {error_msg}")
                    raise ValueError(error_msg)

                self.increment_rate_limit()
                return data

            except requests.HTTPError as e:
                try:
                    err_data = e.response.json()
                    error = err_data.get("error", {})
                    error_msg = (
                        f"HTTP {e.response.status_code} [{error.get('code')}] "
                        f"{error.get('message', e.response.reason)} "
                        f"(subcode: {error.get('error_subcode', 'N/A')})"
                    )
                except:
                    error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                logger.error(f"HTTP ERROR (attempt {attempt+1}): {error_msg}")
                if attempt == MAX_RETRIES - 1:
                    raise ValueError(error_msg)
            except requests.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt+1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    raise ValueError(str(e))

    def create_campaign(self, payload: Dict) -> PublishResult:
        """Create Meta campaign with v24.0 requirements"""
        endpoint = f"{self.account_id}/campaigns"

        # 🚨 CRITICAL: v24.0 MAPPING (your exact objectives from JSON)
        objective_map = {
            "Awareness": "OUTCOME_AWARENESS",
            "Traffic": "OUTCOME_TRAFFIC",
            "Engagement": "OUTCOME_ENGAGEMENT",
            "Leads": "OUTCOME_LEADS",
            "Sales": "OUTCOME_SALES",
        }
        objective = payload.get("objective", "OUTCOME_AWARENESS")
        objective = objective_map.get(objective, objective)

        # 🚨 CRITICAL: special_ad_categories MUST be array (empty = [])
        special_cat = payload.get("special_ad_categories") or payload.get("special_ad_category") or None
        special_ad_categories = []
        if special_cat and special_cat != "NONE":
            cat_map = {"Housing": "HOUSING", "Employment": "EMPLOYMENT", "Credit": "CREDIT"}
            if isinstance(special_cat, str):
                special_ad_categories = [cat_map.get(special_cat, special_cat)]
            else:
                special_ad_categories = [cat_map.get(c, c) for c in special_cat if c]

        # 🚨 MINIMAL v24.0 REQUIRED PAYLOAD
        campaign_data = {
            "name": payload.get("name", "ERPNext Campaign").strip()[:100],  # Max 100 chars
            "objective": objective,
            "status": (payload.get("status") or "PAUSED").upper(),
            "buying_type": "AUCTION",  # ← THIS WAS MISSING! REQUIRED in v24.0
            "special_ad_categories": special_ad_categories,  # ← ALWAYS ARRAY
            "is_adset_budget_sharing_enabled": payload.get("is_adset_budget_sharing_enabled", False),
        }

        logger.info(f"Creating campaign on {endpoint}: {campaign_data}")

        try:
            response = self._make_request("POST", endpoint, json_data=campaign_data)
            campaign_id = response.get("id")

            if campaign_id:
                logger.info(f"✅ Campaign created: {campaign_id}")
                return PublishResult(success=True, campaign_id=campaign_id, raw_response=response)
            else:
                raise ValueError(f"No campaign ID in response: {response}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Campaign creation FAILED: {error_msg}")
            frappe.log_error(
                {
                    "account_id": self.account_id,
                    "payload": campaign_data,
                    "error": error_msg,
                    "response": getattr(e, "response", None),
                },
                "Meta Campaign Creation Error",
            )
            return PublishResult(success=False, error_message=error_msg)

    def create_ad_set(self, payload: Dict) -> PublishResult:
        """Create Meta ad set with v24.0 requirements"""
        endpoint = f"{self.account_id}/adsets"

        # Minimal required payload
        ad_set_data = {
            "name": payload.get("name").strip()[:100],
            "campaign_id": payload["campaign_id"],
            "daily_budget": payload.get("daily_budget"),
            "targeting": payload.get("targeting", {}),
            "billing_event": payload.get("billing_event"),
            "status": "PAUSED",  # Force PAUSED on creation
            "bid_amount": payload.get("bid_amount"),
            # Add optimization_goal if needed, based on campaign
        }

        if not ad_set_data["campaign_id"]:
            raise ValueError("campaign_id required")

        logger.info(f"Creating ad set on {endpoint}: {ad_set_data}")

        try:
            response = self._make_request("POST", endpoint, json_data=ad_set_data)
            ad_set_id = response.get("id")

            if ad_set_id:
                logger.info(f"✅ Ad Set created: {ad_set_id}")
                return PublishResult(
                    success=True, campaign_id=ad_set_id, raw_response=response  # Reuse for adset_id
                )
            else:
                raise ValueError(f"No ad set ID in response: {response}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ad Set creation FAILED: {error_msg}")
            frappe.log_error(
                message=error_msg,
                title="Meta Ad Set Creation Failed",
                content={
                    "account_id": self.account_id,
                    "sent_payload": ad_set_data,
                    "meta_error": str(e),
                },
            )
            return PublishResult(success=False, error_message=error_msg)

    def upload_image(self, payload: Dict) -> PublishResult:
        """Upload image to Meta and return hash"""
        endpoint = f"{self.account_id}/adimages"

        # Assume payload has 'filename' with full path
        filename = payload.get("filename")
        if not filename:
            raise ValueError("filename required for image upload")

        with open(filename, "rb") as f:
            files = {"file": f}
            response = self._make_request("POST", endpoint, files=files)  # Use files for multipart

            if "images" in response:
                image_data = response["images"]
                image_hash = list(image_data.values())[0].get("hash")
                if image_hash:
                    # Store image_hash in campaign_id field since PublishResult doesn't have image_hash
                    return PublishResult(success=True, campaign_id=image_hash)
                else:
                    raise ValueError("No image hash in response")
            else:
                raise ValueError("Image upload failed")

    def create_creative(self, payload: Dict) -> PublishResult:
        """Create Meta creative with v24.0 requirements"""
        endpoint = f"{self.account_id}/adcreatives"

        creative_data = {
            "name": payload.get("name", "ERPNext Creative"),
            "object_story_spec": payload["object_story_spec"],
        }

        logger.info(f"Creating creative on {endpoint}")
        logger.info(f"Creative data: {creative_data}")

        try:
            response = self._make_request("POST", endpoint, json_data=creative_data)
            creative_id = response.get("id")

            if creative_id:
                logger.info(f"✅ Creative created: {creative_id}")
                return PublishResult(success=True, creative_id=creative_id, raw_response=response)
            else:
                raise ValueError(f"No creative ID in response: {response}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Creative creation FAILED: {error_msg}")
            frappe.log_error(
                title="Meta Creative Creation Failed",
                message=f"{error_msg}\n\nAccount ID: {self.account_id}\n\nPayload: {str(creative_data)}"
            )
            return PublishResult(success=False, error_message=error_msg)

    # Required abstract methods (minimal implementations)
    def fetch_account_analytics(self) -> AnalyticsResult:
        try:
            data = self._make_request(
                "GET",
                f"{self.account_id}/insights",
                params={"date_preset": "last_7d", "fields": "impressions,spend"},
            )
            return AnalyticsResult(success=True, metrics=data.get("data", []))
        except Exception as e:
            return AnalyticsResult(success=False, error_message=str(e))

    def fetch_post_analytics(self, campaign_id: str) -> AnalyticsResult:
        try:
            data = self._make_request(
                "GET",
                f"{campaign_id}/insights",
                params={"date_preset": "last_7d", "fields": "impressions,spend"},
            )
            return AnalyticsResult(success=True, metrics=data.get("data", []))
        except Exception as e:
            return AnalyticsResult(success=False, error_message=str(e))

    def get_daily_limit(self) -> int:
        return self.DAILY_API_LIMIT

    def refresh_token(self, integration_name: str = None) -> TokenRefreshResult:
        return TokenRefreshResult(success=False, error_message="Not implemented")

    def validate_credentials(self) -> Dict:
        try:
            data = self._make_request("GET", self.account_id, params={"fields": "name,account_status"})
            return {"success": True, "account_name": data.get("name")}
        except Exception as e:
            return {"success": False, "error": str(e)}
