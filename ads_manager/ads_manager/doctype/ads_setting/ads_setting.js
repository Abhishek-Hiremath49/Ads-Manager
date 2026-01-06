// Copyright (c) 2026, Abhishek and contributors
// For license information, please see license.txt

frappe.ui.form.on('Ads Setting', {
    refresh: function (frm) {
        frm.add_custom_button(__('View Integrations'), function () {
            frappe.set_route('List', 'Ads Account Integration');
        });

        frm.add_custom_button(__('View Campaigns'), function () {
            frappe.set_route('List', 'Ad Campaign', { status: 'Scheduled' });
        });

        frm.add_custom_button(__('Reset Daily Counters'), function () {
            frappe.confirm(
                __('Reset all daily ad counters and quota tracking?'),
                function () {
                    frappe.call({
                        method: 'ads_manager.ads_manager.services.scheduler.reset_daily_ad_limits',
                        callback: function () {
                            frm.reload_doc();
                            frappe.show_alert(__('Counters reset!'), 3);
                        }
                    });
                }
            );
        });

        // Dashboard stats
        let html = `
            <div class="row" style="margin-top: 15px;">
                <div class="col-sm-6">
                    <div class="stat-box">
                        <h6>Facebook Posts Today</h6>
                        <h3>${frm.doc.facebook_launches_today || 0} / ${frm.doc.facebook_daily_launch_limit || 50}</h3>
                    </div>
                </div>
                <div class="col-sm-6">
                    <div class="stat-box">
                        <h6>Instagram Posts Today</h6>
                        <h3>${frm.doc.instagram_launches_today || 0} / ${frm.doc.instagram_daily_launch_limit || 25}</h3>
                    </div>
                </div>
            </div>
        `;
        frm.dashboard.set_headline('');
        frm.dashboard.add_section(html);
    }
});