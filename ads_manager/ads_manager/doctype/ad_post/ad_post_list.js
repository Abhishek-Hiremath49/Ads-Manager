frappe.listview_settings['Ad Post'] = {
    add_fields: ['status'],

    get_indicator: function (doc) {
        if (doc.status === 'Draft') {
            return [__("Draft"), "grey", "status,=,Draft"];
        } else if (doc.status === 'Scheduled') {
            return [__("Scheduled"), "blue", "status,=,Scheduled"];
        } else if (doc.status === 'Launching') {
            return [__("Launching"), "royalblue", "status,=,Launching"];
        } else if (doc.status === 'Active') {
            return [__("Active"), "green", "status,=,Active"];
        } else if (doc.status === 'Failed') {
            return [__("Failed"), "orange", "status,=,Failed"];
        } else if (doc.status === 'Cancelled') {
            return [__("Cancelled"), "red", "status,=,Cancelled"];
        }
    },

    onload: function (listview) {
        listview.page.clear_primary_action();
        listview.page.set_primary_action(
            __('New Campaign'),
            () => frappe.new_doc('Ad Post'),
            'add'
        );

        setTimeout(() => {
            if (!listview.data || listview.data.length === 0) {
                const $empty = listview.$page.find('.no-result');
                if ($empty.length) {
                    $empty.find('p').first().text(__("No campaigns yet. Create your first ad campaign."));
                    $empty.find('.btn-new-doc').text(__("Create Campaign"));
                }
            }
        }, 100);
    },

    refresh: function (listview) {
        listview.page.clear_primary_action();
        listview.page.set_primary_action(
            __('New Campaign'),
            () => frappe.new_doc('Ad Post'),
            'add'
        );
    }
};