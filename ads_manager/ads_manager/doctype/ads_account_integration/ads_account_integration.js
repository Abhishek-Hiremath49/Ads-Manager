// Copyright (c) 2026, Abhishek and contributors
// For license information, please see license.txt

frappe.ui.form.on('Ads Account Integration', {
    refresh: function (frm) {
        // Block manual creation - redirect to list
        if (frm.is_new()) {
            frappe.show_alert({
                message: __('Use "Connect Account" button to add integrations'),
                indicator: 'orange'
            });
            frappe.set_route('List', 'Ads Account Integration');
            return;
        }

        // Add Connect button for disconnected integrations
        if (frm.doc.connection_status !== 'Connected') {
            frm.add_custom_button(__('Connect Account'), function () {
                frm.trigger('connect_account');
            }, __('Actions'));
        }

        // Add buttons for connected integrations
        if (frm.doc.connection_status === 'Connected') {
            frm.add_custom_button(__('Disconnect'), function () {
                frm.trigger('disconnect_account');
            }, __('Actions'));

            frm.add_custom_button(__('Test Connection'), function () {
                frm.trigger('test_connection');
            }, __('Actions'));

            frm.add_custom_button(__('Sync Campaigns'), function () {
                frm.trigger('sync_campaigns');
            }, __('Actions'));
        }

        frm.trigger('update_status_indicator');
    },

    connect_account: function (frm) {
        // Call OAuth initiation
        frappe.call({
            method: 'ads_manager.ads_manager.api.oauth.get_facebook_oauth_url',
            callback: function (r) {
                if (r.message.oauth_url) {
                    window.location.href = r.message.oauth_url;
                }
            }
        });
    },

    test_connection: function (frm) {
        frappe.call({
            method: 'ads_manager.ads_manager.api.oauth.test_connection',
            args: { integration: frm.doc.name },
            freeze: true,
            freeze_message: __('Testing connection...'),
            callback: function (r) {
                if (r.message.success) {
                    frappe.msgprint(__('Connection successful!'));
                    frm.reload_doc();
                } else {
                    frappe.msgprint(__('Connection failed: ') + r.message.error);
                }
            }
        });
    },
    disconnect_account: function (frm) {
        frappe.confirm(
            __('Are you sure you want to disconnect this account?'),
            function () {
                frappe.call({
                    method: 'ads_manager.ads_manager.api.oauth.disconnect',
                    args: { integration: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Disconnecting...'),
                    callback: function (r) {
                        if (r.message.success) {
                            frappe.msgprint(__('Account disconnected.'));
                            frm.reload_doc();
                        } else {
                            frappe.msgprint(__('Failed to disconnect: ') + r.message.error);
                        }
                    }
                });
            }
        );
    },
    update_status_indicator: function (frm) {
        let indicator = 'grey';
        let status = frm.doc.connection_status;

        if (status === 'Connected') indicator = 'green';
        else if (status === 'Expired') indicator = 'orange';
        else if (status === 'Error') indicator = 'red';

        frm.page.set_indicator(status, indicator);
    }
});