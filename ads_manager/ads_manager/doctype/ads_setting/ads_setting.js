// Copyright (c) 2026, Abhishek and contributors
// For license information, please see license.txt

frappe.ui.form.on('Ads Setting', {
    refresh: function (frm) {
        frm.add_custom_button(__('View Integrations'), function () {
            frappe.set_route('List', 'Ads Account Integration');
        }, __("Action"));

        frm.add_custom_button(__('View Ad Posts'), function () {
            frappe.set_route('List', 'Ad Post');
        }, __("Action"));

        frm.add_custom_button(__('Reset Daily Counters'), function () {
            frappe.confirm(
                __('Reset all daily ad counters and quota tracking?'),
                function () {
                    frm.set_value('instagram_posts_today', 0);
                    frm.set_value('facebook_api_calls_today', 0);
                    frm.save();
                    frappe.show_alert({ message: __('Counters reset'), indicator: 'green' });
                }
            );
        }, __("Action"));

        frm.trigger('show_quota_dashboard')

    },

    show_quota_dashboard: function (frm) {
        let html = `
            <div class="row" style="margin-top: 15px;">
                <div class="col-sm-6">  
                    <div class="stat-box">
                        <h6>Facebook Posts Today</h6>
                        <h3>${frm.doc.facebook_posts_today || 0} / ${frm.doc.facebook_daily_limit || 50}</h3>
                    </div>
                </div>
                <div class="col-sm-6">
                    <div class="stat-box">
                        <h6>Instagram Posts Today</h6>
                        <h3>${frm.doc.instagram_posts_today || 0} / ${frm.doc.instagram_daily_limit || 25}</h3>
                    </div>
                </div>
            </div>
        `;
        frm.dashboard.set_headline('');
        frm.dashboard.add_section(html);
    }
});