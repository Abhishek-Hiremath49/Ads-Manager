// Copyright (c) 2026, Abhishek and contributors
// For license information, please see license.txt

frappe.ui.form.on('Ads Campaign', {
	// refresh(frm) {
	// Show campaign ID info if already created
	// if (frm.doc.campaign_id) {
	// 	frm.set_df_property('campaign_id', 'description', 
	// 		`<span style="color: green; font-weight: bold;">✓ Campaign created on Meta: ${frm.doc.campaign_id}</span>`);
	// }

	// Add custom buttons for connected campaigns
	// if (frm.doc.campaign_id && !frm.is_new()) {
	// 	frm.add_custom_button(__('View on Meta'), function() {
	// 		frappe.msgprint(__('Campaign ID: {0}', [frm.doc.campaign_id]));
	// 	}, __('Actions'));

	// 	frm.add_custom_button(__('Sync Analytics'), function() {
	// 		frm.trigger('sync_analytics');
	// 	}, __('Actions'));
	// }

	// Disable campaign_id field since it's set automatically
	// frm.set_df_property('campaign_id', 'read_only', 1);
	// },

	// validate(frm) {
	// 	// Validate required fields before save
	// 	if (!frm.doc.account) {
	// 		frappe.throw(__('Please select an Account'));
	// 	}
	// 	if (!frm.doc.campaign_name) {
	// 		frappe.throw(__('Campaign Name is required'));
	// 	}
	// 	if (!frm.doc.objective) {
	// 		frappe.throw(__('Campaign Objective is required'));
	// 	}
	// },

	// account(frm) {
	// 	// When account changes, fetch account details
	// 	if (frm.doc.account) {
	// 		frappe.call({
	// 			method: 'frappe.client.get',
	// 			args: {
	// 				doctype: 'Ads Account Integration',
	// 				name: frm.doc.account
	// 			},
	// 			callback(r) {
	// 				if (r.message) {
	// 					// Set platform based on account
	// 					frm.set_value('platform', r.message.platform);
	// 					// Set organization if available
	// 					if (r.message.organisation) {
	// 						frm.set_value('organization', r.message.organisation);
	// 					}
	// 				}
	// 			}
	// 		});
	// 	}
	// },

	// sync_analytics(frm) {
	// 	// Placeholder for future analytics sync functionality
	// 	frappe.call({
	// 		method: 'ads_manager.ads_manager.api.campaigns.sync_campaign_analytics',
	// 		args: {
	// 			campaign: frm.doc.name
	// 		},
	// 		freeze: true,
	// 		freeze_message: __('Syncing analytics...'),
	// 		callback(r) {
	// 			if (r.message && r.message.success) {
	// 				frappe.msgprint(__('Analytics synced successfully'));
	// 				frm.reload_doc();
	// 			} else {
	// 				frappe.msgprint(__('Failed to sync analytics'));
	// 			}
	// 		}
	// 	});
	// },

	// before_save(frm) {
	// 	// Show saving message
	// 	if (frm.is_new()) {
	// 		frappe.show_alert({
	// 			message: __('Creating campaign on Meta Ads...'),
	// 			indicator: 'blue'
	// 		});
	// 	}
	// }
});
