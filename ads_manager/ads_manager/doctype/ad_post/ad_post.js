// ad_post.js - Production Ready

frappe.ui.form.on('Ad Post', {
    refresh(frm) {
        // Show ad creation status
        if (frm.doc.ad_id) {
            frm.set_df_property('ad_id', 'description',
                `<span style="color: green; font-weight: bold;">✓ Ad created on Meta: ${frm.doc.ad_id}</span>`);
        }

        // Set field properties based on state
        frm.trigger('set_field_states');

        // Update child table status indicators
        frm.trigger('update_creative_indicators');
        frm.trigger('update_media_indicators');
    },

    update_creative_indicators(frm) {
        // Show visual indicators for created creatives
        if (frm.doc.ad_creative) {
            frm.doc.ad_creative.forEach((row, idx) => {
                if (row.creative_id && row.creative_id !== 'pending') {
                    setTimeout(() => {
                        let grid_row = frm.fields_dict['ad_creative'].grid.grid_rows_by_docname[row.name];
                        if (grid_row) {
                            grid_row.doc.creative_id = row.creative_id;
                            $(grid_row.wrapper).find('[data-fieldname="creative_id"]')
                                .css('background-color', '#d4edda')
                                .attr('title', 'Created on Meta');
                        }
                    }, 100);
                }
            });
        }
    },

    update_media_indicators(frm) {
        // Show visual indicators for uploaded media
        if (frm.doc.media) {
            frm.doc.media.forEach((row, idx) => {
                if (row.uploaded_to_platform && row.media_hash) {
                    setTimeout(() => {
                        let grid_row = frm.fields_dict['media'].grid.grid_rows_by_docname[row.name];
                        if (grid_row) {
                            $(grid_row.wrapper).find('[data-fieldname="media_hash"]')
                                .css('background-color', '#d4edda')
                                .attr('title', 'Uploaded to Meta');
                        }
                    }, 100);
                }
            });
        }
    },

    ads_account(frm) {
        // Clear dependent fields when account changes
        frm.set_value('select_facebook_page', '');
        frm.set_value('select_instagram_account', '');

        if (!frm.doc.ads_account) {
            frm.set_df_property('select_facebook_page', 'options', '');
            return;
        }

        // Fetch and populate Facebook pages
        frm.trigger('load_facebook_pages');
    },

    load_facebook_pages(frm) {
        if (!frm.doc.ads_account) return;

        frappe.call({
            method: 'ads_manager.ads_manager.doctype.ad_post.ad_post.get_pages_for_account',
            args: {
                filters: { account: frm.doc.ads_account }
            },
            freeze: true,
            freeze_message: __('Loading Facebook pages...'),
            callback: (r) => {
                if (r.message && r.message.length > 0) {
                    // r.message = [[page_id, label], ...]
                    let options = r.message.map(item => item[1]).join('\n');
                    frm.set_df_property('select_facebook_page', 'options', options);

                    frappe.show_alert({
                        message: __('Loaded {0} Facebook page(s)', [r.message.length]),
                        indicator: 'green'
                    }, 3);
                } else {
                    frm.set_df_property('select_facebook_page', 'options', '');
                    frappe.msgprint({
                        title: __('No Pages Found'),
                        indicator: 'orange',
                        message: __('No Facebook pages found for this account. Please ensure pages are linked in the Ads Account Integration.')
                    });
                }
            },
            error: (err) => {
                frm.set_df_property('select_facebook_page', 'options', '');
                frappe.msgprint({
                    title: __('Error'),
                    indicator: 'red',
                    message: __('Failed to load Facebook pages. Please try again.')
                });
            }
        });
    },

    set_field_states(frm) {
        // Make select_facebook_page mandatory if account is selected
        frm.set_df_property('select_facebook_page', 'reqd', !!frm.doc.ads_account);

        // Enable/disable fields based on ad creation status
        if (frm.doc.ad_id) {
            frm.set_df_property('ads_account', 'read_only', 1);
            frm.set_df_property('campaign', 'read_only', 1);
            frm.set_df_property('ad_set', 'read_only', 1);
            frm.set_df_property('select_facebook_page', 'read_only', 1);
        }
    },

    enable(frm) {
        // Update status when enable checkbox changes
        if (frm.doc.ad_id) {
            frm.set_value('status', frm.doc.enable ? 'ACTIVE' : 'PAUSED');
        }
    },

    validate(frm) {
        // Validate required fields before save
        if (!frm.doc.ads_account) {
            frappe.msgprint(__('Please select an Ads Account'));
            frappe.validated = false;
            return false;
        }

        if (!frm.doc.select_facebook_page) {
            frappe.msgprint(__('Please select a Facebook Page'));
            frappe.validated = false;
            return false;
        }

        if (!frm.doc.ad_creative || frm.doc.ad_creative.length === 0) {
            frappe.msgprint(__('Please add at least one Ad Creative'));
            frappe.validated = false;
            return false;
        }

        if (!frm.doc.media || frm.doc.media.length === 0) {
            frappe.msgprint(__('Please add at least one Media file'));
            frappe.validated = false;
            return false;
        }
    }
});

// Ad Creative child table events
frappe.ui.form.on('Ad Creative', {
    creative_name(frm, cdt, cdn) {
        // Auto-generate creative ID based on name (placeholder until Meta creates it)
        let row = locals[cdt][cdn];
        if (row.creative_name && !row.creative_id) {
            row.creative_id = 'pending';
            frm.refresh_field('ad_creative');
        }
    },

    creative_id(frm, cdt, cdn) {
        // Update description when creative_id is set
        let row = locals[cdt][cdn];
        if (row.creative_id && row.creative_id !== 'pending') {
            frm.fields_dict['ad_creative'].grid.grid_rows_by_docname[cdn].set_field_property(
                'creative_id',
                'description',
                `<span style="color: green;">✓ Created on Meta</span>`
            );
        }
    }
});

// Ad Media child table events
frappe.ui.form.on('Ad Media', {
    media_file(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        // Auto-detect media type from file extension
        if (row.media_file) {
            let ext = row.media_file.toLowerCase().split('.').pop();

            if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) {
                frappe.model.set_value(cdt, cdn, 'media_type', 'Image');
            } else if (['mp4', 'mov', 'avi', 'wmv', 'webm'].includes(ext)) {
                frappe.model.set_value(cdt, cdn, 'media_type', 'Video');
            }
        }
    },

    media_hash(frm, cdt, cdn) {
        // Update description when media is uploaded
        let row = locals[cdt][cdn];
        if (row.media_hash && row.uploaded_to_platform) {
            frm.fields_dict['media'].grid.grid_rows_by_docname[cdn].set_field_property(
                'media_hash',
                'description',
                `<span style="color: green;">✓ Uploaded to Meta</span>`
            );
        }
    }
});