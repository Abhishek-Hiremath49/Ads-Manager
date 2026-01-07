// Copyright (c) 2026, Abhishek and contributors
// For license information, please see license.txt

frappe.ui.form.on('Ad Post', {
    refresh: function (frm) {
        if (frm.is_new()) {
            $('.page-actions button.text-muted.btn.btn-default.icon-btn').hide();
            $('.page-actions button.btn.btn-default.icon-btn').hide();
            $('.page-actions button.btn.btn-default.ellipsis').hide();
        } else {
            $('.page-actions button.btn.btn-default.ellipsis').show();
            $('.btn-secondary[data-label="Cancel"]').remove();
            document.querySelector('.menu-btn-group').style.display = 'none';
            $('.page-actions button.text-muted.btn.btn-default.icon-btn').hide();
            $('.page-actions button.text-muted.btn.btn-default.prev-doc').show();
            $('.page-actions button.text-muted.btn.btn-default.next-doc').show();
        }

        frm.dashboard.clear_headline();
        apply_filters(frm);
        update_account_details(frm);
        update_budget_preview(frm);  // New for ads
        frm.trigger('update_status_indicator');
    },

    platform: function (frm) {
        // Update targeting fields based on platform
        if (frm.doc.platform === "Instagram") {
            frm.set_value("target_facebook", 0);
            frm.set_value("target_instagram", 1);
        } else if (frm.doc.platform === "Facebook") {
            frm.set_value("target_instagram", 0);
            frm.set_value("target_facebook", 1);
        }
    },

    objective: function (frm) {
        // Suggest bid strategy based on objective
        let bid_map = {
            "Awareness": "Lowest Cost",
            "Traffic": "Bid Cap",
            "Sales": "Cost Cap"
        };
        if (bid_map[frm.doc.objective]) {
            frm.set_value("bid_strategy", bid_map[frm.doc.objective]);
        }
    },

    update_status_indicator: function (frm) {
        let indicator = 'grey';
        let status = frm.doc.status;

        if (status === 'Draft') indicator = 'grey';
        else if (status === 'Scheduled') indicator = 'blue';
        else if (status === 'Launching') indicator = 'royalblue';
        else if (status === 'Active') indicator = 'green';
        else if (status === 'Failed') indicator = 'orange';
        else if (status === 'Cancelled') indicator = 'red';

        frm.page.set_indicator(status, indicator);
    },

    // Budget preview
    budget_optimization: function (frm) {
        update_budget_preview(frm);
    },

    campaign_daily_budget: function (frm) {
        update_budget_preview(frm);
    }
});

function update_budget_preview(frm) {
    if (frm.doc.budget_optimization === "Campaign" && frm.doc.campaign_daily_budget) {
        let preview = `Estimated daily spend: $${frm.doc.campaign_daily_budget}`;
        frm.dashboard.add_section(preview, 'Budget Preview');
    }
}

function apply_filters(frm) {
    // Filter accounts by platform
    frm.set_query("ads_account", function () {
        return {
            filters: {
                "platform": frm.doc.platform,
                "enabled": 1,
                "connection_status": "Connected"
            }
        };
    });
}

function update_account_details(frm) {
    if (frm.doc.ads_account) {
        frm.call({
            method: "ads_manager.api.providers.get_account_info",
            args: { account: frm.doc.ads_account },
            callback: (r) => {
                frm.set_df_property("account_info_html", "options", r.message || "<div>Loading...</div>");
            }
        });
    }
}