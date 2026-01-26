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
            if not self.campaign:
                frappe.throw(_("Campaign is required to create an ad set"))
            if not self.ad_set_name:
                frappe.throw(_("Ad Set Name is required"))
            if not self.billing_event:
                frappe.throw(_("Billing Event is required"))
            if not self.daily_budget:
                frappe.throw(_("Daily Budget is required"))

            # Get the campaign document to fetch account and campaign_id
            campaign_doc = frappe.get_doc("Ads Campaign", self.campaign)
            if not campaign_doc.campaign_id:
                frappe.throw(_("Selected campaign has no Meta campaign ID"))
            if not campaign_doc.account:
                frappe.throw(_("Selected campaign has no associated account"))

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
        """
        # Build targeting
        targeting = {
            "geo_locations": {
                "countries": ["IN"]  # fallback
            },
            "age_min": self.age_min or 18,
            "age_max": self.age_max or 65,
        }

        if self.geo_location:
            country_code = frappe.db.get_value("Country", self.geo_location, "code") or "IN"
            targeting["geo_locations"]["countries"] = [country_code.upper()]

        # Required: optimization_goal (match your campaign objective!)
        # Start with REACH + IMPRESSIONS – safe for many cases
        # Later: map from self.performance_goal when ready
        optimization_goal = "REACH"  # or "IMPRESSIONS", "LINK_CLICKS", etc.

        # Required/strongly recommended: bid_strategy
        bid_strategy = "LOWEST_COST_WITHOUT_CAP"  # safest default, no bid_amount needed

        payload = {
            "name": self.ad_set_name,
            "campaign_id": campaign_doc.campaign_id,
            "daily_budget": int(float(self.daily_budget or 0) * 100),  # MUST be in cents!
            "billing_event": self.billing_event,
            "optimization_goal": optimization_goal,
            "bid_strategy": bid_strategy,
            "targeting": targeting,
            "status": "ACTIVE" if self.enable_ad_set else "PAUSED",
        }

        # Only add bid_amount for cap strategies
        if self.bid_amount and self.bid_strategy in ["LOWEST_COST_WITH_BID_CAP", "COST_CAP"]:
            payload["bid_amount"] = int(float(self.bid_amount) * 100)

        # Safeguard: Meta often rejects very low budgets
        if payload["daily_budget"] < 1000:  # < $10
            frappe.throw(_("Daily budget too low. Minimum ~$10 (1000 cents) recommended."))

        # Debug: Log the exact payload being sent
        logger.info("Meta AdSet Payload being sent:\n" + frappe.as_json(payload, indent=2))

        return payload
