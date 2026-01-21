# Copyright (c) 2026, Abhishek and contributors
# For license information, please see license.txt

import frappe
import logging
from frappe import _
from frappe.model.document import Document
from ads_manager.ads_manager.providers.meta_ads import MetaAdsProvider

logger = logging.getLogger(__name__)


class AdSet(Document):
    """
    Ad Set Document
    Creates and manages ad sets on Meta platforms (Facebook/Instagram)
    """

    def before_save(self):
        """Create ad set on Meta Ads before saving"""
        # Only create ad set if this is new or adset_id is empty
        if self.is_new() or not self.adset_id:
            self._create_meta_ad_set()

    def _create_meta_ad_set(self):
        """
        Create ad set via Meta Ads provider and store the adset_id

        Raises:
            frappe.ValidationError: If required fields are missing or API call fails
        """
        try:
            # Validate required fields
            # if not self.campaign:
            #     frappe.throw(_("Campaign is required to create an ad set"))
            # if not self.ad_set_name:
            #     frappe.throw(_("Ad Set Name is required"))
            # if not self.billing_event:
            #     frappe.throw(_("Billing Event is required"))
            # if not self.daily_budget:
            #     frappe.throw(_("Daily Budget is required"))

            # Get the campaign document to fetch account and campaign_id
            campaign_doc = frappe.get_doc("Ads Campaign", self.campaign)
            # if not campaign_doc.campaign_id:
            #     frappe.throw(_("Selected campaign has no Meta campaign ID"))
            # if not campaign_doc.account:
            #     frappe.throw(_("Selected campaign has no associated account"))

            # Initialize provider with the account integration
            provider = MetaAdsProvider(campaign_doc.account)

            # Prepare and validate payload with all mappings
            payload = self._build_ad_set_payload(campaign_doc)

            logger.info(f"Creating ad set '{self.ad_set_name}' on Meta Ads")

            # Create ad set on Meta
            result = provider.create_ad_set(payload)

            if result.success:
                # Store the adset_id returned from Meta
                self.adset_id = result.adset_id
                # Update the document with adset_id
                frappe.db.set_value(self.doctype, self.name, "adset_id", self.adset_id)
                logger.info(f"✓ Ad Set created successfully on Meta: {result.campaign_id}")
                frappe.msgprint(
                    _("Ad Set created successfully on Meta Ads. ID: {0}").format(result.campaign_id),
                    alert=True,
                )
            else:
                error_msg = result.error_message or "Unknown error from Meta API"
                logger.error(f"Failed to create ad set on Meta: {error_msg}")
                frappe.throw(_("Failed to create ad set on Meta Ads: {0}").format(error_msg))

        except frappe.DoesNotExistError:
            frappe.throw(_("Campaign '{0}' does not exist.").format(self.campaign))
        except ValueError as e:
            frappe.throw(_("Invalid configuration: {0}").format(str(e)))
        except frappe.ValidationError:
            # Re-raise Frappe validation errors
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unexpected error creating ad set: {error_msg}")
            frappe.log_error(frappe.get_traceback(), "Ad Set Creation Error")
            frappe.throw(_("Failed to create ad set: {0}").format(error_msg))

    def _build_ad_set_payload(self, campaign_doc) -> dict:
        """
        Build and validate ad set payload with all mappings and transformations
        All validation and mapping happens here before sending to Meta API
        """
        # Map performance goal to Meta optimization goal
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
        
        optimization_goal = performance_goal_map.get(self.performance_goal or "None", "NONE")

        # Build targeting object
        targeting = {}
        
        # Add geo targeting if provided
        if self.geo_location:
            targeting["geo_locations"] = [{"countries": [{"key": self.geo_location}]}]
        
        # Add age targeting
        if self.age_min or self.age_max:
            targeting["age_min"] = self.age_min or 18
            targeting["age_max"] = self.age_max or 65
        
        # Add gender targeting
        if self.gender and self.gender != "All":
            gender_map = {"Male": 1, "Female": 2, "All": 0}
            targeting["genders"] = [gender_map.get(self.gender, 0)]

        # Build final payload - only send what Meta API expects
        payload = {
            "name": self.ad_set_name,
            "campaign_id": campaign_doc.campaign_id,
            "daily_budget": int(self.daily_budget) if self.daily_budget else None,
            "targeting": targeting,
            "billing_event": self.billing_event,
            "status": "ACTIVE" if self.enable_ad_set else "PAUSED",
            "bid_amount": int(self.bid_amount) if self.bid_amount else None,
            # "optimization_goal": optimization_goal,
            # "bid_strategy": (self.bid_strategy or "LOWEST_COST_WITHOUT_CAP").upper(),
        }
        
        # Add bid_amount if bid_strategy requires it
        # if self.bid_amount and self.bid_strategy in ["LOWEST_COST_WITH_BID_CAP", "COST_CAP"]:
        #     payload["bid_amount"] = int(self.bid_amount * 100)  # Convert to cents
        
        # # Add lifetime_budget if provided
        # if self.lifetime_budget:
        #     payload["lifetime_budget"] = int(self.lifetime_budget * 100)  # Convert to cents
        
        # # Add start/end times if provided
        # if self.start_time:
        #     payload["start_time"] = int(self.start_time.timestamp())
        # if self.end_time:
        #     payload["end_time"] = int(self.end_time.timestamp())

        return payload
