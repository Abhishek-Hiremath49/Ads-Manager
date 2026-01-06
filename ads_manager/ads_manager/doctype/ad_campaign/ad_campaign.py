# Copyright (c) 2026, Abhishek and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from ads_manager.services.campaign_service import CampaignService

# from ads_manager.utils.media import normalize_file_type  # Assume utils added


class AdCampaign(Document):

    VALID_TRANSITIONS = {
        "Draft": ["Scheduled", "Launching", "Cancelled"],
        "Scheduled": ["Launching", "Draft", "Cancelled"],
        "Launching": ["Active", "Partially Active", "Failed"],
        "Active": [],
        "Partially Active": ["Launching"],
        "Failed": ["Scheduled", "Launching", "Cancelled"],
        "Cancelled": ["Draft"],
    }

    MAX_RETRIES = 3

    def before_save(self):
        """Handle defaults before saving"""
        if self.platform == "Instagram":
            if not (self.target_instagram):
                self.target_instagram = 1  # Default

        if (
            self.budget_optimization == "Campaign"
            and not self.campaign_daily_budget
            and not self.campaign_lifetime_budget
        ):
            frappe.throw(_("Budget is required for campaign optimization"))

    def validate(self):
        if self.docstatus == 1 and self.status not in self.VALID_TRANSITIONS.get(
            self.status, []
        ):
            frappe.throw(_("Invalid status transition"))

        if self.start_time and self.end_time and self.start_time > self.end_time:
            frappe.throw(_("Start time cannot be after end time"))

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def set_status(self, new_status: str):
        """Set status with validation"""
        if self.can_transition_to(new_status):
            self.status = new_status
            self.save(ignore_permissions=True)
        else:
            frappe.throw(f"Cannot change status from {self.status} to {new_status}")

    def validate_update_after_submit(self):
        """Allow status updates after submission"""
        if self.get_doc_before_save():
            old_status = self.get_doc_before_save().status
            if self.status != old_status:
                return

        super().validate_update_after_submit()

    def on_submit(self):
        """Launch campaign on submit if scheduled"""
        if self.status == "Scheduled":
            CampaignService.launch_campaign(self.name)


@frappe.whitelist()
def get_platforms_for_organization(organization):
    """Get available platforms for an organization"""
    if not organization:
        return []

    return frappe.db.get_all(
        "Ads Account Integration",
        filters={
            "organization": organization,
            "enabled": 1,
            "connection_status": "Connected",
        },
        pluck="platform",
        distinct=True,
        order_by="platform asc",
    )
