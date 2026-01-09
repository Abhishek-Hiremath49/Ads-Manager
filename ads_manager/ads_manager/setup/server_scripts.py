import frappe

def create_server_scripts():
    SCRIPT_NAME = "Marketing Campaign → Create Facebook Campaign"

    if frappe.db.exists("Server Script", SCRIPT_NAME):
        return

    script = frappe.get_doc({
        "doctype": "Server Script",
        "name": SCRIPT_NAME,
        "script_type": "DocType Event",
        "reference_doctype": "Marketing Campaign",
        "event": "After Save",
        "enabled": 1,
        "script": """
# Auto-create Facebook Campaign on save

if not doc.facebook:
    return

if doc.campagin_id:
    return

result = frappe.call(
    "ads_manager.ads_manager.api.facebook.create_facebook_campaign",
    campaign_name=doc.campaign_name,
    objective=doc.objective,
    status=doc.status,
    special_ad_categories=doc.special_ad_categories
)

if result and result.get("campaign_id"):
    doc.db_set("campagin_id", result["campaign_id"], update_modified=False)
"""
    })

    script.insert(ignore_permissions=True)
    frappe.db.commit()
