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
        """Create Meta campaign with v24.0 requirements (matching Ads Campaign doctype)"""
        endpoint = f"{self.account_id}/campaigns"

        # 🚨 CRITICAL: v24.0 MAPPING (matching doctype objectives)
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
        # Use 'category' field from Ads Campaign doctype
        category = payload.get("category") or payload.get("special_ad_category") or None
        special_ad_categories = []
        if category and category != "NONE":
            cat_map = {"Housing": "HOUSING", "Employment": "EMPLOYMENT", "Credit": "CREDIT"}
            if isinstance(category, str):
                special_ad_categories = [cat_map.get(category, category)]
            else:
                special_ad_categories = [cat_map.get(c, c) for c in category if c]

        # 🚨 MINIMAL v24.0 REQUIRED PAYLOAD (from Ads Campaign doctype)
        campaign_data = {
            "name": payload.get("campaign_name", payload.get("name", "Campaign")).strip()[:100],  # Max 100 chars, from doctype
            "objective": objective,
            "status": (payload.get("status") or "PAUSED").upper(),
            "buying_type": (payload.get("choose_buying_type") or "AUCTION").upper(),  # From doctype field
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
        """Create Meta ad set with v24.0 requirements (matching Ad Set doctype)"""
        endpoint = f"{self.account_id}/adsets"

        # Map doctype performance_goal to Meta optimization_goal
        performance_goal_map = {
            "None": "NONE",
            "Maximise reach of ads": "REACH",
            "Maximise number of impression": "IMPRESSIONS",
            "Maximise ad recall lift": "AD_RECALL_LIFT",
            "Maximise ThruPlay views": "THRUPLAY",
            "Maximise 2-second continuous video plays": "VIDEO_2_SEC_CONTINUOUS_VIEWS",
            "Maximise number of landing page views": "LANDING_PAGE_VIEWS",
            "Maximise number of link clicks": "LINK_CLICKS",
            "Maximise daily unique reach": "DAILY_UNIQUE_REACH",
            "Maximise number of conversations": "CONVERSATIONS",
            "Maximise number of Instagram profile visits": "PROFILE_VISIT",
            "Maximise number of calls": "CALLS",
            "Maximise engagement with a post": "POST_ENGAGEMENT",
            "Maximise number of event responses": "EVENT_RESPONSES",
            "Maximise number of app events": "APP_EVENTS",
            "Maximise reminders set": "REMINDERS_SET",
            "Maximise number of Page likes": "PAGE_LIKES",
            "Maximise number of leads": "LEAD_GENERATION",
            "Maximise number of conversion leads": "CONVERSION_LEAD_RATE",
            "Maximise number of leads through messaging": "MESSAGING_PURCHASE_CONVERSION",
            "Maximise number of app installs": "APP_INSTALLS",
            "Maximise value of conversions": "MAXIMIZE_CONVERSION_VALUE",
        }
        
        optimization_goal = payload.get("performance_goal", "NONE")
        optimization_goal = performance_goal_map.get(optimization_goal, optimization_goal)

        # Build targeting from doctype fields
        targeting = payload.get("targeting", {})
        
        # Add geo targeting if geo_location provided
        if payload.get("geo_location"):
            targeting["geo_locations"] = [{"regions": [{"key": payload.get("geo_location")}]}]
        
        # Add age targeting from doctype
        if payload.get("age_min") or payload.get("age_max"):
            targeting["age_min"] = payload.get("age_min", 18)
            targeting["age_max"] = payload.get("age_max", 65)
        
        # Add gender targeting
        if payload.get("gender") and payload.get("gender") != "All":
            gender_map = {"Male": 1, "Female": 2, "All": 0}
            targeting["genders"] = [gender_map.get(payload.get("gender"), 0)]

        # Required payload with doctype fields (from Ad Set doctype)
        ad_set_data = {
            "name": payload.get("ad_set_name", payload.get("name", "Ad Set")).strip()[:100],  # From doctype
            "campaign_id": payload.get("campaign") or payload.get("campaign_id"),  # Link to campaign doctype
            "daily_budget": int(payload.get("daily_budget", 0) * 100) if payload.get("daily_budget") else None,  # In cents
            "targeting": targeting,
            "billing_event": payload.get("billing_event"),
            "status": "PAUSED",  # Force PAUSED on creation
            "optimization_goal": optimization_goal,
            "bid_strategy": (payload.get("bid_strategy") or "LOWEST_COST_WITHOUT_CAP").upper(),  # From doctype
        }
        
        # Add bid_amount if bid_strategy requires it
        if payload.get("bid_amount") and payload.get("bid_strategy") in ["LOWEST_COST_WITH_BID_CAP", "COST_CAP"]:
            ad_set_data["bid_amount"] = int(payload.get("bid_amount") * 100)  # In cents
        
        # Add lifetime_budget if provided
        if payload.get("lifetime_budget"):
            ad_set_data["lifetime_budget"] = int(payload.get("lifetime_budget") * 100)  # In cents
        
        # Add start/end times if provided
        if payload.get("start_time"):
            ad_set_data["start_time"] = int(payload.get("start_time").timestamp())
        if payload.get("end_time"):
            ad_set_data["end_time"] = int(payload.get("end_time").timestamp())

        if not ad_set_data["campaign_id"]:
            raise ValueError("campaign_id or campaign link required")

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
        """Create Meta creative with v24.0 requirements (matching Ad Creative doctype)"""
        endpoint = f"{self.account_id}/adcreatives"

        # Map CTA options to Meta values (from Ad Creative doctype)
        cta_map = {
            "Learn More": "LEARN_MORE",
            "Shop Now": "SHOP_NOW",
            "Sign Up": "SIGN_UP",
        }
        
        call_to_action = payload.get("call_to_action", "LEARN_MORE")
        call_to_action = cta_map.get(call_to_action, call_to_action)

        # Build object_story_spec from doctype fields
        object_story_spec = payload.get("object_story_spec", {})
        
        # If not provided, construct from creative doctype fields
        if not object_story_spec:
            link_data = {
                "message": payload.get("body", ""),
                "link": payload.get("link_url") or payload.get("object_url", ""),
            }
            
            if payload.get("title"):
                link_data["caption"] = payload.get("title")
            
            # Check ad type from Ad Creative doctype
            if payload.get("select_ad_type") == "Create ad":
                # Single image or video ad
                if payload.get("single_image_or_video"):
                    if payload.get("image_hash"):
                        object_story_spec = {
                            "link_data": {
                                **link_data,
                                "image_hash": payload.get("image_hash"),
                                "call_to_action_type": call_to_action,
                            }
                        }
                    elif payload.get("video_id"):
                        object_story_spec = {
                            "video_data": {
                                "message": payload.get("body", ""),
                                "video_id": payload.get("video_id"),
                                "call_to_action_type": call_to_action,
                            }
                        }
                # Carousel ad
                elif payload.get("carousel"):
                    object_story_spec = {
                        "link_data": {
                            "message": payload.get("body", ""),
                            "link": link_data.get("link", ""),
                            "multi_share_end_card": False,
                        }
                    }
                # Collection ad
                elif payload.get("collection"):
                    object_story_spec = {
                        "link_data": link_data
                    }
            elif payload.get("select_ad_type") == "Use existing post":
                # Story-based ad from existing post
                object_story_spec = {
                    "page_id": payload.get("select_facebook_page", ""),
                    "story_id": payload.get("object_url", ""),
                }
            else:
                # Default to link data
                object_story_spec = {
                    "link_data": link_data
                }

        creative_data = {
            "name": payload.get("creative_name", payload.get("name", "Creative")).strip()[:100],  # From Ad Creative doctype
            "object_story_spec": object_story_spec,
        }
        
        # Add object_type if specified in doctype
        if payload.get("object_type"):
            creative_data["object_type"] = payload.get("object_type")

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

    def create_ad(self, payload: Dict) -> PublishResult:
        """Create Meta ad with v24.0 requirements (matching Ad Post doctype)"""
        endpoint = f"{self.account_id}/ads"

        ad_data = {
            "name": payload.get("ad_name", payload.get("name", "Ad")).strip()[:100],  # From Ad Post doctype
            "adset_id": payload.get("ad_set") or payload.get("adset_id"),  # Link to Ad Set doctype
            "creative": {"creative_id": payload.get("ad_creative") or payload.get("creative_id")},  # Link to Ad Creative doctype (child table)
            "status": "PAUSED",
        }
        
        # Add partnership ad fields if enabled (from Ad Post doctype)
        if payload.get("enable_partnership_ad"):
            if payload.get("select_facebook_page"):
                ad_data["adlabels"] = [{"name": "Partnership Ad"}]
            if payload.get("select_instagram_account"):
                ad_data["instagram_handle"] = payload.get("select_instagram_account")

        logger.info(f"Creating ad on {endpoint}: {ad_data}")

        try:
            response = self._make_request("POST", endpoint, json_data=ad_data)
            ad_id = response.get("id")

            if ad_id:
                logger.info(f"✅ Ad created: {ad_id}")
                return PublishResult(success=True, campaign_id=ad_id, raw_response=response)  # Reuse for ad_id
            else:
                raise ValueError(f"No ad ID in response: {response}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ad creation FAILED: {error_msg}")
            frappe.log_error(
                message=error_msg,
                title="Meta Ad Creation Failed",
                content={
                    "account_id": self.account_id,
                    "sent_payload": ad_data,
                    "meta_error": str(e),
                },
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
