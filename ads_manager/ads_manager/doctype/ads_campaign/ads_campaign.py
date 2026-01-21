# Copyright (c) 2026, Abhishek and contributors
# For license information, please see license.txt

import frappe
import logging
from frappe import _
from frappe.model.document import Document
from ads_manager.ads_manager.providers.meta_ads import MetaAdsProvider

logger = logging.getLogger(__name__)


class AdsCampaign(Document):
    """
    Ads Campaign Document
    Creates and manages ad campaigns on Meta platforms (Facebook/Instagram)
    """

    def before_save(self):
        """Create campaign on Meta Ads before saving"""
        # Only create campaign if this is new or campaign_id is empty
        if self.is_new() or not self.campaign_id:
            self._create_meta_campaign()

    def _create_meta_campaign(self):
        """
        Create campaign via Meta Ads provider and store the campaign_id

        Raises:
                frappe.ValidationError: If required fields are missing or API call fails
        """
        try:
            # Validate required fields
            if not self.account:
                frappe.throw(_("Account is required to create a campaign"))
            if not self.campaign_name:
                frappe.throw(_("Campaign Name is required"))
            if not self.objective:
                frappe.throw(_("Objective is required"))

            # Initialize provider with the account integration
            provider = MetaAdsProvider(self.account)

            # Prepare and validate payload with all mappings
            payload = self._build_campaign_payload()

            logger.info(f"Creating campaign '{self.campaign_name}' on Meta Ads")

            # Create campaign on Meta
            result = provider.create_campaign(payload)

            if result.success:
                # Store the campaign_id returned from Meta
                self.campaign_id = result.campaign_id
                # Update the document with campaign_id
                frappe.db.set_value(self.doctype, self.name, "campaign_id", self.campaign_id)
                logger.info(f"✓ Campaign created successfully on Meta: {result.campaign_id}")
                frappe.msgprint(
                    _("Campaign created successfully on Meta Ads. ID: {0}").format(result.campaign_id),
                    alert=True,
                )
            else:
                error_msg = result.error_message or "Unknown error from Meta API"
                logger.error(f"Failed to create campaign on Meta: {error_msg}")
                frappe.throw(_("Failed to create campaign on Meta Ads: {0}").format(error_msg))

        except frappe.DoesNotExistError:
            frappe.throw(
                _("Account '{0}' does not exist. Please select a valid account.").format(self.account)
            )
        except ValueError as e:
            frappe.throw(_("Invalid account configuration: {0}").format(str(e)))
        except frappe.ValidationError:
            # Re-raise Frappe validation errors
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unexpected error creating campaign: {error_msg}")
            frappe.log_error(frappe.get_traceback(), "Ads Campaign Creation Error")
            frappe.throw(_("Failed to create campaign: {0}").format(error_msg))

    def _build_campaign_payload(self) -> dict:
        """
        Build and validate campaign payload with all mappings and transformations
        All validation and mapping happens here before sending to Meta API
        """
        # Map campaign objectives to Meta API format
        objective_map = {
            "Awareness": "OUTCOME_AWARENESS",
            "Traffic": "OUTCOME_TRAFFIC",
            "Engagement": "OUTCOME_ENGAGEMENT",
            "Leads": "OUTCOME_LEADS",
            "Sales": "OUTCOME_SALES",
            "App promotion": "OUTCOME_APP_PROMOTION",
        }
        objective = objective_map.get(self.objective, self.objective)

        # Map special ad categories to Meta format (MUST be array)
        special_ad_categories = []
        if self.category and self.category != "NONE":
            cat_map = {
                "Housing": "HOUSING",
                "Employment": "EMPLOYMENT",
                "Finacial Product and Services": "FINANCIAL_PRODUCTS_SERVICES",
                "Social issues, elections or politics":"ISSUES_ELECTIONS_POLITICS",
            }
            special_ad_categories = [cat_map.get(self.category, self.category)]

        # Map buying type to Meta format
        buying_type_map = {
            "Auction": "AUCTION",
            "Reservation": "RESERVATION",
        }
        buying_type = buying_type_map.get(self.choose_buying_type, "AUCTION")

        # Build final payload - only send what Meta API expects
        payload = {
            "name": self.campaign_name.strip()[:100],
            "objective": objective,
            "status": "ACTIVE" if self.enable else "PAUSED",
            "buying_type": buying_type,
            "special_ad_categories": special_ad_categories,
            "is_adset_budget_sharing_enabled": False,
        }

        return payload
