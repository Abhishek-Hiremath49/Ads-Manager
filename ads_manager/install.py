"""
Installation hooks for Ads Manager
"""

import frappe


def after_install():
    """Run after app installation"""
    create_default_settings()
    create_custom_fields()
    frappe.log_error("Ads Manager installed successfully!", "Installation Success")


def create_default_settings():
    """Create default Ads Setting if not exists"""
    if not frappe.db.exists("Ads Setting"):
        settings = frappe.new_doc("Ads Setting")
        settings.insert(ignore_permissions=True)
        frappe.db.commit()


def create_custom_fields():
    """Create any custom fields needed"""
    # Add to other DocTypes if needed (e.g., Marketing Campaign link)
    pass
