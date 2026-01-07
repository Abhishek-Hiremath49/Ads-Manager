from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_custom_fields():
    return {
        "Marketing Campaign": [
            {
                "fieldname": "facebook",
                "label": "Facebook Ads",
                "fieldtype": "Check",
            },
            {
                "fieldname": "objective",
                "label": "Objective",
                "fieldtype": "Select",
                "options": "\nAPP_INSTALLS\nBRAND_AWARENESS\nCONVERSIONS\nEVENT_RESPONSES\nLEAD_GENERATION\nLINK_CLICKS\nLOCAL_AWARENESS\nMESSAGES\nOFFER_CLAIMS\nOUTCOME_APP_PROMOTION\nOUTCOME_AWARENESS\nOUTCOME_ENGAGEMENT\nOUTCOME_LEADS\nOUTCOME_SALES\nOUTCOME_TRAFFIC\nPAGE_LIKES\nPOST_ENGAGEMENT\nPRODUCT_CATALOG_SALES\nREACH\nSTORE_VISITS\nVIDEO_VIEWS",
            },
            {
                "fieldname": "status",
                "label": "Status",
                "fieldtype": "Select",
                "options": "\nACTIVE\nPAUSED\nDELETED\nARCHIVED",
            },
            {
                "fieldname": "special_ad_categories",
                "label": "Special Ad Categories",
                "fieldtype": "Select",
                "options": "\nNONE\nEMPLOYMENT\nHOUSING\nCREDIT\nISSUES_ELECTIONS_POLITICS\nONLINE_GAMBLING_AND_GAMING\nFINANCIAL_PRODUCTS_SERVICES",
            },
            {
                "fieldname": "is_adset_budget_sharing_enabled",
                "label": "Enable Adset Budget Sharing",
                "fieldtype": "Check",
                "default": 0,
            },
        ]
    }


def execute():
    create_custom_fields(get_custom_fields())
