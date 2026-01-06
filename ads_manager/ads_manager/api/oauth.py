"""
OAuth API Endpoints for Ads Manager
Meta (Facebook / Instagram Ads) OAuth
"""

import frappe
import secrets
import requests
from frappe import _
from frappe.utils import get_url, now_datetime, add_to_date, quoted


# =============================================================================
# OAuth Initiation
# =============================================================================


@frappe.whitelist()
def initiate_oauth(
    platform: str,
    account_name: str = None,
    account_description: str = None,
    organization: str = None,
) -> dict:
    """Initiate OAuth flow"""
    state = secrets.token_urlsafe(32)
    cache_data = {
        "platform": platform,
        "account_name": account_name,
        "account_description": account_description,
        "organization": organization,
        "user": frappe.session.user,
    }

    redirect_uri = get_callback_url(platform)
    settings = frappe.get_single("Ads Setting")

    auth_url = _get_meta_auth_url(platform, settings, redirect_uri, state)
    frappe.cache().set_value(f"ads_oauth_state_{state}", cache_data, expires_in_sec=600)

    return {"authorization_url": auth_url, "state": state}


def get_callback_url(platform: str) -> str:
    """Generate callback URL"""
    return f"{get_url()}/api/method/ads_manager.ads_manager.api.oauth.callback_{platform.lower()}"


def _get_meta_auth_url(platform: str, settings, redirect_uri: str, state: str) -> str:
    """Generate Meta OAuth URL"""
    if platform == "Facebook":
        scopes = [
            "pages_show_list",
            "pages_read_engagement",
            "pages_manage_posts",
            "pages_read_user_content",
            "business_management",
            "email",
            "public_profile",
            "ads_management",
            "ads_read",
        ]
        params = {
            "client_id": settings.facebook_app_id,
            "redirect_uri": redirect_uri,
            "scope": ",".join(scopes),
            "response_type": "code",
            "state": state,
        }
        return f"https://www.facebook.com/v21.0/dialog/oauth?{'&'.join(f'{k}={quoted(str(v))}' for k, v in params.items())}"

    # Add Instagram handling if needed
    return None


# =============================================================================
# OAuth Callback
# =============================================================================
@frappe.whitelist(allow_guest=True)
def callback_facebook():
    """Facebook OAuth callback"""
    return callback_meta("Facebook")


def callback_meta(platform: str = ""):
    """Handle Meta OAuth callback"""
    code = frappe.form_dict.get("code")
    state = frappe.form_dict.get("state")
    error = frappe.form_dict.get("error")

    if error:
        return _oauth_error_redirect(f"{platform}: {error}")

    # Validate state
    cache_data = frappe.cache().get_value(f"ads_oauth_state_{state}")
    if not cache_data or cache_data.get("platform") != platform:
        return _oauth_error_redirect("Invalid OAuth state")

    settings = frappe.get_single("Ads Setting")
    api_version = settings.facebook_api_version or "v21.0"

    try:
        # Step 1: Get short-lived token
        short_token_response = requests.get(
            f"https://graph.facebook.com/{api_version}/oauth/access_token",
            params={
                "client_id": settings.facebook_app_id,
                "client_secret": settings.get_password("facebook_app_secret"),
                "redirect_uri": get_callback_url(platform),
                "code": code,
            },
            timeout=30,
        )
        short_token_response.raise_for_status()
        short_token = short_token_response.json().get("access_token")

        if not short_token:
            return _oauth_error_redirect("Failed to get access token")

        # Step 2: Exchange for long-lived token
        long_token_response = requests.get(
            f"https://graph.facebook.com/{api_version}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.facebook_app_id,
                "client_secret": settings.get_password("facebook_app_secret"),
                "fb_exchange_token": short_token,
            },
            timeout=30,
        )
        long_token_response.raise_for_status()
        long_token = long_token_response.json()

        user_token = long_token.get("access_token", short_token)
        expires_in = long_token.get("expires_in", 5184000)

        # Step 3: Get user info
        user_response = requests.get(
            f"https://graph.facebook.com/{api_version}/me",
            params={"access_token": user_token, "fields": "id,name,email"},
            timeout=30,
        )
        user_response.raise_for_status()
        ads_data = user_response.json()

        # Step 4: Get ad accounts
        ad_accounts_response = requests.get(
            f"https://graph.facebook.com/{api_version}/me/adaccounts",
            params={
                "access_token": user_token,
                "fields": "id,name,account_status,currency,timezone_name,amount_spent",
            },
            timeout=30,
        )
        ad_accounts_response.raise_for_status()
        ad_accounts = ad_accounts_response.json().get("data", [])

        if not ad_accounts:
            return _oauth_error_redirect("No ad accounts found")

        # Store session data
        session_key = secrets.token_urlsafe(32)
        frappe.cache().set_value(
            f"meta_ads_{session_key}",
            {
                "platform": platform,
                "user": cache_data["user"],
                "user_access_token": user_token,
                "expires_in": expires_in,
                "ad_accounts": ad_accounts,
                "ads_data": ads_data,
                "auth_user_id": ads_data.get("id"),
                "auth_user_name": ads_data.get("name"),
                "account_name": cache_data.get("account_name"),
                "account_description": cache_data.get("account_description"),
                "organization": cache_data.get("organization"),
            },
            expires_in_sec=600,
        )

        # Clean up OAuth state
        frappe.cache().delete_value(f"ads_oauth_state_{state}")

        # If single account, connect directly
        if len(ad_accounts) == 1:
            frappe.set_user(cache_data["user"])
            return _connect_ad_account(session_key, 0)

        # Multiple accounts - redirect to selection page
        frappe.local.response.update(
            {
                "type": "redirect",
                "location": f"/select-ads-account?session={session_key}&platform={platform}",
            }
        )

    except requests.RequestException as e:
        frappe.log_error(f"OAuth callback error: {str(e)}", "OAuth Error")
        return _oauth_error_redirect(f"Connection failed: {str(e)}")
    except Exception as e:
        frappe.log_error(f"Unexpected OAuth error: {str(e)}", "OAuth Error")
        return _oauth_error_redirect("An unexpected error occurred")


# =============================================================================
# Ad Account Selection
# =============================================================================


@frappe.whitelist()
def get_available_ad_accounts(session_key: str) -> dict:
    """Return ad accounts for selection UI"""
    cache_data = frappe.cache().get_value(f"meta_ads_{session_key}")
    if not cache_data or cache_data["user"] != frappe.session.user:
        frappe.throw(_("Session expired or invalid"))

    platform = cache_data["platform"]
    ad_accounts = cache_data.get("ad_accounts", [])

    formatted = []
    for i, acct in enumerate(ad_accounts):
        formatted.append(
            {
                "index": i,
                "id": acct.get("id", ""),
                "name": acct.get("name", "Unknown"),
                "currency": acct.get("currency", "N/A"),
                "timezone": acct.get("timezone_name", "N/A"),
                "status": acct.get("account_status", "N/A"),
                "amount_spent": acct.get("amount_spent", "0"),
            }
        )

    return {
        "platform": platform,
        "ad_accounts": formatted,
        "authorized_by": cache_data.get("auth_user_name"),
    }


@frappe.whitelist()
def connect_ad_account(session_key: str, index: int) -> dict:
    """Connect a specific ad account"""
    return _connect_ad_account(session_key, int(index))


def _connect_ad_account(session_key: str, index: int):
    """Internal function to connect ad account"""
    cache_data = frappe.cache().get_value(f"meta_ads_{session_key}")
    if not cache_data:
        frappe.throw(_("Session expired"))

    ad_accounts = cache_data.get("ad_accounts", [])
    if index >= len(ad_accounts):
        frappe.throw(_("Invalid account index"))

    acct = ad_accounts[index]
    platform = cache_data["platform"]

    # Save integration
    integration = _save_ads_integration(
        platform=platform,
        ad_account_id=acct.get("id"),
        account_name=cache_data.get("account_name") or acct.get("name"),
        account_description=cache_data.get("account_description"),
        organization=cache_data.get("organization"),
        currency=acct.get("currency"),
        timezone=acct.get("timezone_name"),
        account_status=acct.get("account_status"),
        amount_spent=acct.get("amount_spent"),
        access_token=cache_data["user_access_token"],
        expires_in=cache_data["expires_in"],
        auth_user_id=cache_data.get("auth_user_id"),
        auth_user_name=cache_data.get("auth_user_name"),
        auth_user_email=cache_data.get("ads_data", {}).get("email"),
    )

    return _oauth_success_redirect(integration.name)


def _save_ads_integration(
    platform: str,
    ad_account_id: str,
    account_name: str,
    access_token: str,
    expires_in: int = None,
    account_description: str = None,
    organization: str = None,
    currency: str = None,
    timezone: str = None,
    account_status: str = None,
    amount_spent: float = None,
    refresh_token: str = None,
    auth_user_id: str = None,
    auth_user_name: str = None,
    auth_user_email: str = None,
):
    """Create or update Ads Account Integration"""
    existing = frappe.db.get_value(
        "Ads Account Integration",
        {"platform": platform, "ad_account_id": ad_account_id},
    )

    if existing:
        integration = frappe.get_doc("Ads Account Integration", existing)
    else:
        integration = frappe.new_doc("Ads Account Integration")
        integration.platform = platform
        integration.ad_account_id = ad_account_id

    integration.account_name = account_name
    integration.connection_status = "Connected"
    integration.enabled = 1
    integration.last_error = None
    integration.authorization_date = now_datetime()

    if account_description:
        integration.account_description = account_description
    if organization:
        integration.organization = organization
    if currency:
        integration.currency = currency
    if timezone:
        integration.timezone = timezone
    if account_status is not None:
        integration.account_status = str(account_status)
    if amount_spent is not None:
        integration.amount_spent = float(amount_spent)

    # OAuth fields
    integration.access_token = access_token
    if refresh_token:
        integration.refresh_token = refresh_token
    if expires_in:
        integration.token_expiry = add_to_date(now_datetime(), seconds=expires_in)

    # Authorized user fields
    if auth_user_id:
        integration.authorized_user_id = auth_user_id
    if auth_user_name:
        integration.authorized_user_name = auth_user_name
    if auth_user_email:
        integration.authorized_user_email = auth_user_email

    integration.save(ignore_permissions=True)
    frappe.db.commit()

    return integration


@frappe.whitelist()
def disconnect(integration: str) -> dict:
    """Disconnect an integration"""
    doc = frappe.get_doc("Ads Account Integration", integration)
    doc.connection_status = "Disconnected"
    doc.access_token = None
    doc.refresh_token = None
    doc.page_access_token = None
    doc.enabled = 0
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True}


# =============================================================================
# Redirect Helpers
# =============================================================================


def _oauth_error_redirect(message: str):
    """Redirect to error page"""
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = (
        f"/app/ads-account-integration?error={frappe.utils.quoted(message)}"
    )


def _oauth_success_redirect(integration_name: str):
    """Redirect to success page"""
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = (
        f"/app/ads-account-integration/{integration_name}"
    )
