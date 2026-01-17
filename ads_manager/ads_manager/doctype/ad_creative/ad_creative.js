// Copyright (c) 2026, Abhishek and contributors
// For license information, please see license.txt

frappe.ui.form.on('Ad Creative', {
    refresh(frm) {
        // Show creative ID info if already created
        if (frm.doc.creative_id) {
            frm.set_df_property('creative_id', 'description',
                `<span style="color: green; font-weight: bold;">✓ Creative created on Meta: ${frm.doc.creative_id}</span>`);
        }

        // Disable creative_id field
        frm.set_df_property('creative_id', 'read_only', 1);

        // Initial page setup if account is selected
        if (frm.doc.account) {
            frm.trigger("account");
        }
    },

    validate(frm) {
        if (!frm.doc.account) frappe.throw(__('Please select Ads Account'));
        if (!frm.doc.name1) frappe.throw(__('Creative Name is required'));
        if (!frm.doc.page) frappe.throw(__('Please select Facebook Page'));

        // Check for media files - filter out empty rows
        if (!frm.doc.media || !Array.isArray(frm.doc.media)) {
            frappe.throw(__('At least one media file is required'));
        }

        let media_with_files = frm.doc.media.filter(row => row.media_file);
        if (!media_with_files || media_with_files.length === 0) {
            frappe.throw(__('At least one media file is required'));
        }
    },

    account: function (frm) {
        if (!frm.doc.account) {
            frm.set_value('page', '');
            frm.set_df_property('page', 'options', '');
            return;
        }

        // Fetch pages for selected account
        frappe.call({
            method: 'ads_manager.ads_manager.doctype.ad_creative.ad_creative.get_pages_for_account',
            args: {
                doctype: 'Ad Creative',
                txt: '',
                searchfield: 'page',
                start: 0,
                page_len: 50,
                filters: { account: frm.doc.account }
            },
            callback: function (r) {
                if (r.message && r.message.length > 0) {
                    // Build options with page labels and store the mapping
                    let page_options = [];
                    frm.page_mapping = {};  // Store mapping of label -> page_id

                    r.message.forEach(item => {
                        let page_id = item[0];
                        let label = item[1];  // "Page Name (ID)"
                        page_options.push(label);
                        frm.page_mapping[label] = page_id;
                    });

                    // Set dropdown options
                    frm.set_df_property('page', 'options', page_options.join('\n'));
                } else {
                    frappe.msgprint(__('No pages found for this account. Please add pages to the account integration.'));
                    frm.set_df_property('page', 'options', '');
                    frm.set_value('page', '');
                }
            },
            error: function () {
                frappe.msgprint(__('Error loading pages. Please try again.'));
            }
        });
    },

    page: function (frm) {
        // When user selects a page from dropdown, store the page_id
        if (frm.doc.page && frm.page_mapping) {
            let selected_label = frm.doc.page;
            let page_id = frm.page_mapping[selected_label];
            if (page_id) {
                // Store as metadata for use when creating creative
                frm.doc.selected_page_id = page_id;
            }
        }
    },

    before_save(frm) {
        if (frm.is_new()) {
            frappe.show_alert({
                message: __('Creating creative on Meta Ads...'),
                indicator: 'blue'
            });
        }
    }
});