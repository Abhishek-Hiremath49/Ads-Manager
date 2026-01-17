# Copyright (c) 2026, Abhishek and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today, getdate


class AdsSetting(Document):
    def validate(self):
        self.update_daily_limits()

    def update_daily_limits(self):
        """Update daily ad limits based on account tier (placeholder)"""
        # Fetch from Meta API in production
        self.facebook_daily_budget_limit = 10000  # Example
        self.instagram_daily_post_limit = 25

    def can_launch_campaign(self, platform: str) -> bool:
        if platform == "Facebook":
            return (self.facebook_posts_today or 0) < self.facebook_daily_limit
        elif platform == "Instagram":
            return (self.instagram_posts_today or 0) < self.instagram_daily_limit
        return True

    def increment_launches(self, platform: str):
        if platform == "Facebook":
            self.facebook_posts_today = (self.facebook_posts_today or 0) + 1
        elif platform == "Instagram":
            self.instagram_posts_today = (self.instagram_posts_today or 0) + 1
        self.save(ignore_permissions=True)

    def reset_daily_counters(self):
        """Reset daily counters - called by scheduled job"""
        self.facebook_posts_today = 0
        self.instagram_posts_today = 0
        self.facebook_api_calls_today = 0

        if self.rate_limit_reset_date != today():
            self.facebook_api_calls_today = 0
            self.rate_limit_reset_date = today()

        self.save(ignore_permissions=True)
