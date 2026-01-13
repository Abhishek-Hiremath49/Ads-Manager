# Copyright (c) 2026, Abhishek and contributors
# For license information, please see license.txt

import frappe
import logging
import json
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
        # Validate required fields
        if not self.campaign:
            frappe.throw(_("Campaign is required to create an ad set"))
        if not self.name:
            frappe.throw(_("Name is required"))
        if not self.billing_event:
            frappe.throw(_("Billing Event is required"))
        if not self.daily_budget:
            frappe.throw(_("Daily Budget is required"))

        try:
            # Get the campaign document to fetch account
            campaign_doc = frappe.get_doc("Ads Campaign", self.campaign)
            if not campaign_doc.campaign_id:
                frappe.throw(_("Selected campaign has no Meta campaign ID"))
            if not campaign_doc.account:
                frappe.throw(_("Selected campaign has no associated account"))

            # Initialize provider with the account integration
            provider = MetaAdsProvider(campaign_doc.account)

            # Prepare payload for Meta API
            payload = {
                "name": self.name1,
                "campaign_id": campaign_doc.campaign_id,
                "daily_budget": int(self.daily_budget * 100),  # Convert to cents
                "targeting": json.loads(self.target) if self.target else {},  # Assume target is JSON string
                "billing_event": self.billing_event,
                "status": self.status or "PAUSED",
                "bid_amount": int(self.bid_amount * 100) if self.bid_amount else None,
            }

            logger.info(f"Creating ad set '{self.name}' on Meta Ads for campaign {campaign_doc.campaign_id}")

            # Create ad set on Meta
            result = provider.create_ad_set(payload)

            if result.success:
                # Store the adset_id returned from Meta
                self.adset_id = result.campaign_id  # Reuse field name
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
        except json.JSONDecodeError:
            frappe.throw(_("Invalid targeting JSON"))
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unexpected error creating ad set: {error_msg}")
            frappe.log_error(frappe.get_traceback(), "Ad Set Creation Error")
            frappe.throw(_("Failed to create ad set: {0}").format(error_msg))
