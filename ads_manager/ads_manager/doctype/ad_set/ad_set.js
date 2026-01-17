// Copyright (c) 2026, Abhishek and contributors
// For license information, please see license.txt

frappe.ui.form.on('Ad Set', {
    refresh(frm) {
        // Show adset ID info if already created
        if (frm.doc.adset_id) {
            frm.set_df_property('adset_id', 'description', 
                `<span style="color: green; font-weight: bold;">✓ Ad Set created on Meta: ${frm.doc.adset_id}</span>`);
        }

        // Disable adset_id field
        frm.set_df_property('adset_id', 'read_only', 1);
    },

    validate(frm) {
        // Validate required fields
        if (!frm.doc.campaign) {
            frappe.throw(__('Please select a Campaign'));
        }
        if (!frm.doc.name) {
            frappe.throw(__('Name is required'));
        }
        if (!frm.doc.billing_event) {
            frappe.throw(__('Billing Event is required'));
        }
        if (!frm.doc.daily_budget) {
            frappe.throw(__('Daily Budget is required'));
        }
    },

    campaign(frm) {
        // Optional: Fetch campaign details if needed
    },

    before_save(frm) {
        if (frm.is_new()) {
            frappe.show_alert({
                message: __('Creating ad set on Meta Ads...'),
                indicator: 'blue'
            });
        }
    }
});