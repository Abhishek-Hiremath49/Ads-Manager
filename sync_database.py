"""
Database Schema Sync Script
Syncs the updated DocType definitions with the database
Run this after deploying the production-ready code
"""

import frappe

def sync_doctypes():
    """
    Sync all Ads Manager DocTypes with the database
    This creates/updates database tables to match the DocType definitions
    """
    doctypes_to_sync = [
        "Ad Post",
        "Ad Creative",
        "Ad Set",
        "Ads Account Integration",
        "Ad Campaign",
        "Facebook Pages",
        "Ad Media",
    ]
    
    print("Starting DocType synchronization...")
    
    for doctype in doctypes_to_sync:
        try:
            print(f"Syncing {doctype}...", end=" ")
            # This will update the database schema based on DocType definition
            frappe.reload_doc("ads_manager", "doctype", frappe.scrub(doctype))
            print("✓ Done")
        except Exception as e:
            print(f"✗ Error: {str(e)}")
    
    # Commit changes
    frappe.db.commit()
    print("\nDocType synchronization completed!")
    print("Database schema has been updated.")

if __name__ == "__main__":
    sync_doctypes()
