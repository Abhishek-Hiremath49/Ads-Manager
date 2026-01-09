"""
OAuth API Endpoints for Ads Manager
Meta (Facebook / Instagram Ads) OAuth

Handles OAuth flows for connecting ad platforms including:
- Facebook Ads
- Instagram Ads

Features:
- Secure state validation
- Token exchange and refresh
- Account selection and connection
- Comprehensive error handling and logging
"""

import frappe
import secrets
import requests
import logging
from frappe import _
from frappe.utils import get_url, now_datetime, add_to_date
from urllib.parse import quote as quoted
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from ads_manager.ads_manager.providers import get_provider

logger = logging.getLogger(__name__)

# Constants
OAUTH_STATE_CACHE_TTL = 600  # 10 minutes
SESSION_CACHE_TTL = 600  # 10 minutes
REQUEST_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
BACKOFF_FACTOR = 0.3


# ======================================================================
# Helper Functions
# ======================================================================


def _make_request(method: str, url: str, **kwargs) -> requests.Response:
    """
    Make HTTP request with retry logic and timeout handling.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: Request URL
        **kwargs: Additional requests parameters

    Returns:
        Response object

    Raises:
        requests.RequestException: If request fails after retries
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # Set default timeout if not provided
    if "timeout" not in kwargs:
        kwargs["timeout"] = REQUEST_TIMEOUT

    try:
        response = session.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        logger.error(f"HTTP request failed: {method} {url} - {str(e)}")
        frappe.log_error(f"HTTP request failed: {str(e)}", "HTTP Request Error")
        raise


def _validate_platform(platform: str) -> None:
    """
    Validate that the provided platform is supported.

    Args:
        platform: Platform name to validate

    Raises:
        frappe.ValidationError: If platform is not supported
    """
    supported_platforms = ["Facebook", "Instagram"]
    if platform not in supported_platforms:
        frappe.throw(_(f"Unsupported platform: {platform}. Supported: {', '.join(supported_platforms)}"))


def _validate_settings() -> dict:
    """
    Validate Ads Settings configuration.

    Returns:
        Settings document

    Raises:
        frappe.ValidationError: If required settings are missing
    """
    settings = frappe.get_single("Ads Setting")

    if not settings.facebook_app_id:
        frappe.throw(_("Facebook App ID not configured in Ads Setting"))

    if not settings.get_password("facebook_app_secret"):
        frappe.throw(_("Facebook App Secret not configured in Ads Setting"))

    return settings

def _get_user_pages(access_token: str) -> list:
    """Fetch user's managed Facebook pages using the user access token"""
    settings = frappe.get_single("Ads Setting")
    api_version = settings.facebook_api_version or "v21.0"
    endpoint = f"https://graph.facebook.com/{api_version}/me/accounts"
    params = {
        "access_token": access_token,
        "fields": "id,name,access_token,picture{url}"
    }
    try:
        response = _make_request("GET", endpoint, params=params)
        data = response.json()
        return data.get("data", [])
    except Exception as e:
        logger.warning(f"Failed to fetch user pages: {str(e)}")
        return []

# ======================================================================
# OAuth Initiation
# ======================================================================


@frappe.whitelist()
def initiate_oauth(
    platform: str,
    account_name: str = None,
    account_description: str = None,
    organization: str = None,
) -> dict:
    """
    Initiate OAuth flow for the specified platform.

    Args:
        platform: Platform name (Facebook or Instagram)
        account_name: Optional account name for identification
        account_description: Optional account description
        organization: Optional organization reference

    Returns:
        Dictionary with authorization URL and state token

    Raises:
        frappe.ValidationError: If validation fails
    """
    try:
        # Input validation
        if not platform or not isinstance(platform, str):
            frappe.throw(_("Platform is required and must be a string"))

        platform = platform.strip()
        _validate_platform(platform)

        # Validate account_name length
        if account_name and len(str(account_name)) > 140:
            frappe.throw(_("Account name is too long (max 140 characters)"))

        # Get and validate settings
        settings = _validate_settings()

        # Generate secure state token
        state = secrets.token_urlsafe(32)

        # Prepare cache data
        cache_data = {
            "platform": platform,
            "account_name": account_name,
            "account_description": account_description,
            "organization": organization,
            "user": frappe.session.user,
            "created_at": now_datetime(),
        }

        # Store state in cache with TTL
        frappe.cache().set_value(f"ads_oauth_state_{state}", cache_data, expires_in_sec=OAUTH_STATE_CACHE_TTL)

        # Generate authorization URL
        redirect_uri = get_callback_url(platform)
        auth_url = _get_meta_auth_url(platform, settings, redirect_uri, state)

        logger.info(f"OAuth flow initiated for {platform} by user {frappe.session.user}")

        return {
            "authorization_url": auth_url,
            "state": state,
            "expires_in": OAUTH_STATE_CACHE_TTL,
        }

    except frappe.ValidationError:
        raise
    except Exception as e:
        logger.error(f"OAuth initiation failed: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "OAuth Initiation Error")
        frappe.throw(_("Failed to initiate OAuth flow. Please try again."))


def get_callback_url(platform: str) -> str:
    """Generate callback URL"""
    return f"{get_url()}/api/method/ads_manager.ads_manager.api.oauth.callback_{platform.lower()}"


def _get_meta_auth_url(platform: str, settings, redirect_uri: str, state: str) -> str:
    """Generate Meta OAuth URL"""
    if platform in ["Facebook", "Instagram"]:
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
        
        if platform == "Instagram":
            scopes.extend(["instagram_basic", "instagram_manage_insights"])
            
        params = {
            "client_id": settings.facebook_app_id,
            "redirect_uri": redirect_uri,
            "scope": ",".join(scopes),
            "response_type": "code",
            "state": state,
        }
        return f"https://www.facebook.com/v21.0/dialog/oauth?{'&'.join(f'{k}={quoted(str(v))}' for k, v in params.items())}"

    frappe.throw(_(f"Unsupported platform: {platform}"))


# =============================================================================
# OAuth Callback
# =============================================================================
@frappe.whitelist(allow_guest=True)
def callback_facebook():
    """Facebook OAuth callback"""
    return callback_meta("Facebook")


def callback_meta(platform: str = "") -> str:
    """
    Handle Meta OAuth callback.

    Exchanges authorization code for access tokens and fetches ad accounts.

    Args:
        platform: Platform name (Facebook or Instagram)

    Returns:
        Redirect URL (error or success)
    """
    try:
        # Extract callback parameters
        code = frappe.form_dict.get("code", "").strip()
        state = frappe.form_dict.get("state", "").strip()
        error = frappe.form_dict.get("error", "").strip()

        # Handle OAuth errors
        if error:
            error_desc = frappe.form_dict.get("error_description", error)
            logger.warning(f"OAuth error from {platform}: {error} - {error_desc}")
            return _oauth_error_redirect(f"{platform}: {error_desc}")

        # Validate required parameters
        if not code or not state:
            logger.warning(f"Missing OAuth parameters: code={bool(code)}, state={bool(state)}")
            return _oauth_error_redirect("Invalid OAuth response: missing code or state")

        # Validate state to prevent CSRF attacks
        cache_data = frappe.cache().get_value(f"ads_oauth_state_{state}")
        if not cache_data:
            logger.warning(f"Invalid or expired OAuth state: {state}")
            return _oauth_error_redirect("OAuth state expired or invalid")

        if cache_data.get("platform") != platform:
            logger.warning(f"Platform mismatch: expected {platform}, got {cache_data.get('platform')}")
            return _oauth_error_redirect("Platform mismatch in OAuth response")

        # Get settings
        settings = _validate_settings()
        api_version = settings.facebook_api_version or "v21.0"

        # Step 1: Exchange code for short-lived token
        short_token = _exchange_code_for_token(api_version, settings, platform, code)
        if not short_token:
            return _oauth_error_redirect("Failed to obtain access token")

        # Step 2: Exchange for long-lived token
        user_token, expires_in = _exchange_for_long_lived_token(api_version, settings, short_token)
        if not user_token:
            return _oauth_error_redirect("Failed to exchange for long-lived token")

        # Step 3: Get user information
        ads_data = _fetch_user_info(api_version, user_token)
        if not ads_data:
            return _oauth_error_redirect("Failed to fetch user information")

        # Step 4: Get ad accounts
        ad_accounts = _fetch_ad_accounts(api_version, user_token)
        if not ad_accounts:
            return _oauth_error_redirect("No ad accounts found for this user")

        # Store session data
        session_key = secrets.token_urlsafe(32)
        session_data = {
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
            "created_at": now_datetime(),
        }

        frappe.cache().set_value(f"meta_ads_{session_key}", session_data, expires_in_sec=SESSION_CACHE_TTL)

        # Clean up OAuth state
        frappe.cache().delete_value(f"ads_oauth_state_{state}")

        logger.info(f"OAuth callback successful for {platform}, found {len(ad_accounts)} account(s)")

        # If single account, connect directly
        if len(ad_accounts) == 1:
            try:
                frappe.set_user(cache_data["user"])
                result = _connect_ad_account(session_key, 0)
                location = _oauth_success_redirect(result.name)
                frappe.local.response.update({"type": "redirect", "location": location})
                return location
            except Exception as e:
                logger.error(f"Failed to auto-connect single account: {str(e)}")
                return _oauth_error_redirect("Failed to connect account automatically")

        # Multiple accounts - redirect to selection page
        frappe.set_user(cache_data["user"])
        location = f"/select-ads-account?session={quoted(session_key)}&platform={quoted(platform)}"
        frappe.local.response.update(
            {
                "type": "redirect",
                "location": location,
            }
        )
        return location

    except requests.RequestException as e:
        logger.error(f"Network error during OAuth callback: {str(e)}")
        frappe.log_error(f"OAuth callback network error: {str(e)}", "OAuth Error")
        return _oauth_error_redirect("Network error. Please try again.")
    except Exception as e:
        logger.error(f"Unexpected error during OAuth callback: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "OAuth Callback Error")
        return _oauth_error_redirect("An unexpected error occurred. Please try again.")


def _exchange_code_for_token(api_version: str, settings, platform: str, code: str) -> str:
    """
    Exchange authorization code for short-lived access token.

    Args:
        api_version: Facebook Graph API version
        settings: Ads Setting document
        platform: Platform name
        code: Authorization code

    Returns:
        Access token or None
    """
    try:
        url = f"https://graph.facebook.com/{api_version}/oauth/access_token"
        response = _make_request(
            "GET",
            url,
            params={
                "client_id": settings.facebook_app_id,
                "client_secret": settings.get_password("facebook_app_secret"),
                "redirect_uri": get_callback_url(platform),
                "code": code,
            },
        )
        data = response.json()

        if "error" in data:
            logger.warning(f"Token exchange error: {data['error']}")
            return None

        return data.get("access_token")
    except Exception as e:
        logger.error(f"Failed to exchange code for token: {str(e)}")
        return None


def _exchange_for_long_lived_token(api_version: str, settings, short_token: str) -> tuple:
    """
    Exchange short-lived token for long-lived token.

    Args:
        api_version: Facebook Graph API version
        settings: Ads Setting document
        short_token: Short-lived access token

    Returns:
        Tuple of (access_token, expires_in) or (None, None)
    """
    try:
        url = f"https://graph.facebook.com/{api_version}/oauth/access_token"
        response = _make_request(
            "GET",
            url,
            params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.facebook_app_id,
                "client_secret": settings.get_password("facebook_app_secret"),
                "fb_exchange_token": short_token,
            },
        )
        data = response.json()

        if "error" in data:
            logger.warning(f"Long-lived token exchange error: {data['error']}")
            return None, None

        access_token = data.get("access_token", short_token)
        expires_in = data.get("expires_in", 5184000)  # 60 days default

        return access_token, expires_in
    except Exception as e:
        logger.error(f"Failed to exchange for long-lived token: {str(e)}")
        return None, None


def _fetch_user_info(api_version: str, access_token: str) -> dict:
    """
    Fetch authenticated user information.

    Args:
        api_version: Facebook Graph API version
        access_token: Valid access token

    Returns:
        User data dict or None
    """
    try:
        url = f"https://graph.facebook.com/{api_version}/me"
        response = _make_request(
            "GET",
            url,
            params={
                "access_token": access_token,
                "fields": "id,name,email,picture",
            },
        )
        data = response.json()

        if "error" in data:
            logger.warning(f"User info fetch error: {data['error']}")
            return None

        return data
    except Exception as e:
        logger.error(f"Failed to fetch user info: {str(e)}")
        return None


def _fetch_ad_accounts(api_version: str, access_token: str) -> list:
    """
    Fetch ad accounts for the authenticated user.

    Args:
        api_version: Facebook Graph API version
        access_token: Valid access token

    Returns:
        List of ad account dicts or empty list
    """
    try:
        url = f"https://graph.facebook.com/{api_version}/me/adaccounts"
        response = _make_request(
            "GET",
            url,
            params={
                "access_token": access_token,
                "fields": "id,name,account_status,currency,timezone_name,amount_spent,account_id",
                "limit": 100,
            },
        )
        data = response.json()

        if "error" in data:
            logger.warning(f"Ad accounts fetch error: {data['error']}")
            return []

        return data.get("data", [])
    except Exception as e:
        logger.error(f"Failed to fetch ad accounts: {str(e)}")
        return []


# =============================================================================
# Ad Account Selection
# =============================================================================


@frappe.whitelist()
def get_available_ad_accounts(session_key: str) -> dict:
    """
    Retrieve ad accounts from session cache for selection UI.

    Args:
        session_key: Session key from OAuth callback

    Returns:
        Dictionary with platform, formatted account list, and authorized user name

    Raises:
        frappe.ValidationError: If session is invalid or expired
    """
    try:
        # Validate session key
        if not session_key or not isinstance(session_key, str) or len(session_key) < 20:
            frappe.throw(_("Invalid session key"))

        # Retrieve session data
        cache_data = frappe.cache().get_value(f"meta_ads_{session_key}")
        if not cache_data:
            frappe.throw(_("Session expired. Please reinitiate OAuth flow."))

        # Verify user context
        if cache_data.get("user") != frappe.session.user:
            logger.warning(
                f"Session user mismatch: expected {cache_data.get('user')}, got {frappe.session.user}"
            )
            frappe.throw(_("Session invalid for current user"))

        platform = cache_data.get("platform", "")
        ad_accounts = cache_data.get("ad_accounts", [])

        # Format accounts for UI
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
                    "amount_spent": acct.get("amount_spent", 0),
                    "ad_id": acct.get("account_id", ""),
                }
            )

        logger.info(f"Retrieved {len(formatted)} ad account(s) for session {session_key[:10]}...")

        return {
            "platform": platform,
            "ad_accounts": formatted,
            "authorized_by": cache_data.get("auth_user_name", "Unknown"),
            "account_count": len(formatted),
        }

    except frappe.ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to get available ad accounts: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Get Ad Accounts Error")
        frappe.throw(_("Failed to retrieve ad accounts. Please try again."))


@frappe.whitelist()
def connect_ad_account(session_key: str, index: int) -> dict:
    """
    Connect a specific ad account from selection.

    Args:
        session_key: Session key from OAuth callback
        index: Index of account to connect

    Returns:
        Integration name and redirect location
    """
    try:
        result = _connect_ad_account(session_key, int(index))
        return {"success": True, "integration": result.name, "location": _oauth_success_redirect(result.name)}
    except frappe.ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to connect ad account: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Connect Ad Account Error")
        frappe.throw(_("Failed to connect ad account. Please try again."))


def _connect_ad_account(session_key: str, index: int):
    """
    Internal function to connect a specific ad account.

    Args:
        session_key: Session key from OAuth callback
        index: Index of account in session data

    Returns:
        Integration document
    """
    # Retrieve session data
    cache_data = frappe.cache().get_value(f"meta_ads_{session_key}")
    if not cache_data:
        frappe.throw(_("Session expired"))

    # Ensure user context
    user = cache_data.get("user")
    if user and frappe.session.user != user:
        frappe.set_user(user)

    # Validate account index
    ad_accounts = cache_data.get("ad_accounts", [])
    if not isinstance(index, int) or index < 0 or index >= len(ad_accounts):
        frappe.throw(_("Invalid account selection"))

    acct = ad_accounts[index]
    platform = cache_data["platform"]

    # Save integration
    integration = _save_ads_integration(
        platform=platform,
        account_name=cache_data.get("account_name") or acct.get("name"),
        account_description=cache_data.get("account_description"),
        organization=cache_data.get("organization"),
        account_status=acct.get("account_status"),
        access_token=cache_data["user_access_token"],
        ad_account_id=acct.get("id"),
        ad_id=acct.get("account_id"),
        currency=acct.get("currency"),
        timezone=acct.get("timezone_name"),
        amount_spent=acct.get("amount_spent"),
        expires_in=cache_data["expires_in"],
        auth_user_id=cache_data.get("auth_user_id"),
        auth_user_name=cache_data.get("auth_user_name"),
        auth_user_email=cache_data.get("ads_data", {}).get("email"),
        long_lived_token=cache_data["user_access_token"],
    )

    # Clean up session cache
    frappe.cache().delete_value(f"meta_ads_{session_key}")

    return integration


def _save_ads_integration(
    platform: str,
    ad_account_id: str,
    ad_id: str,
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
    long_lived_token: str = None,
) -> dict:
    """
    Create or update Ads Account Integration document.

    Args:
        platform: Platform name
        ad_account_id: Ad account ID from platform
        ad_id: Ad ID from platform
        account_name: Human-readable account name
        access_token: OAuth access token
        expires_in: Token expiry time in seconds
        account_description: Optional account description
        organization: Optional organization reference
        currency: Account currency
        timezone: Account timezone
        account_status: Account status from platform
        amount_spent: Amount spent so far
        refresh_token: Refresh token if available
        auth_user_id: Authenticated user ID
        auth_user_name: Authenticated user name
        auth_user_email: Authenticated user email

    Returns:
        Integration document
    """
    try:
        # Check if integration already exists
        existing = frappe.db.get_value(
            "Ads Account Integration",
            {"platform": platform, "ad_account_id": ad_account_id},
        )

        if existing:
            integration = frappe.get_doc("Ads Account Integration", existing)
            is_new = False
        else:
            integration = frappe.new_doc("Ads Account Integration")
            integration.platform = platform
            integration.ad_account_id = ad_account_id
            integration.ad_id = ad_id
            is_new = True

        # Update main fields
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

        # OAuth tokens
        integration.access_token = access_token
        if refresh_token:
            integration.refresh_token = refresh_token
        if expires_in:
            integration.token_expiry = add_to_date(now_datetime(), seconds=expires_in)

        # Authorized user info
        if auth_user_id:
            integration.authorized_user_id = auth_user_id
        if auth_user_name:
            integration.authorized_user_name = auth_user_name
        if auth_user_email:
            integration.authorized_user_email = auth_user_email

        # === FETCH AND STORE FACEBOOK PAGES (using integration only) ===
        if long_lived_token:
            pages = _get_user_pages(long_lived_token)
            # Clear existing pages to avoid duplicates on reconnect
            integration.fb_pages = []
            for page in pages:
                picture_url = f"https://graph.facebook.com/{page.get('id')}/picture?type=square&height=100&width=100"
                integration.append("fb_pages", {
                    "page_name": page.get("name"),
                    "page_id": page.get("id"),
                    "image": picture_url
                })

        # Save everything (main doc + child table)
        integration.save(ignore_permissions=True)
        frappe.db.commit()

        # Clear cache
        frappe.clear_document_cache("Ads Account Integration", integration.name)

        action = "created" if is_new else "updated"
        logger.info(f"Integration {integration.name} {action} for {platform} account {ad_account_id}")

        return integration

    except frappe.DuplicateEntryError:
        logger.error(f"Duplicate integration for {platform} account {ad_account_id}")
        frappe.throw(_("An integration for this account already exists"))
    except Exception as e:
        logger.error(f"Failed to save integration: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Save Integration Error")
        frappe.throw(_("Failed to save integration. Please try again."))


@frappe.whitelist()
def disconnect(integration: str) -> dict:
    """
    Disconnect an ad account integration.

    Revokes access tokens and marks integration as disconnected.

    Args:
        integration: Integration name/ID

    Returns:
        Success response dict
    """
    try:
        if not frappe.has_permission("Ads Account Integration", "write", integration):
            frappe.throw(_("You don't have permission to disconnect this integration"))

        doc = frappe.get_doc("Ads Account Integration", integration)

        # Clear sensitive data
        doc.connection_status = "Not Connected"
        doc.access_token = None
        doc.refresh_token = None
        doc.page_access_token = None
        doc.enabled = 0
        doc.disconnected_at = now_datetime()

        doc.save(ignore_permissions=True)
        frappe.db.commit()

        logger.info(f"Integration {integration} disconnected by user {frappe.session.user}")

        return {"success": True, "message": _("Integration disconnected successfully")}

    except frappe.ValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to disconnect integration {integration}: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Disconnect Integration Error")
        frappe.throw(_("Failed to disconnect integration. Please try again."))


# =============================================================================
# Redirect Helpers
# =============================================================================


def _oauth_error_redirect(message: str):
    """Redirect to error page"""
    location = f"/app/ads-account-integration?error={quoted(message)}"
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = location
    return location


def _oauth_success_redirect(integration_name: str):
    """Redirect to success page"""
    location = f"/app/ads-account-integration/{integration_name}"
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = location
    return location


@frappe.whitelist()
def validate_credentials(integration: str) -> dict:
    """
    Validate integration credentials by testing API connection.

    Args:
        integration: Integration name/ID

    Returns:
        Dictionary with validation result
    """
    try:
        if not frappe.has_permission("Ads Account Integration", "read", integration):
            frappe.throw(_("You don't have permission to access this integration"))

        integration_doc = frappe.get_doc("Ads Account Integration", integration)

        if not integration_doc.enabled or not integration_doc.access_token:
            return {
                "success": False,
                "message": _("Integration is not active or has no access token"),
            }

        provider = get_provider(integration_doc.platform)(integration)
        result = provider.validate_connection()

        logger.info(f"Credentials validation for {integration}: {result.get('success', False)}")

        return {
            "success": result.get("success", False),
            "message": result.get("message", _("Validation failed")),
            "account_name": result.get("account_name", "Unknown"),
        }

    except frappe.ValidationError:
        raise
    except Exception as e:
        logger.error(f"Credential validation failed for {integration}: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Credential Validation Error")
        return {
            "success": False,
            "error": str(e),
            "message": _("Failed to validate credentials"),
        }


@frappe.whitelist()
def sync_campaigns(integration: str) -> dict:
    """
    Sync campaigns from ad platform.

    Args:
        integration: Integration name/ID

    Returns:
        Dictionary with sync result
    """
    try:
        if not frappe.has_permission("Ads Account Integration", "read", integration):
            frappe.throw(_("You don't have permission to access this integration"))

        integration_doc = frappe.get_doc("Ads Account Integration", integration)
        provider = get_provider(integration_doc.platform)(integration)
        result = provider.sync_campaigns()

        logger.info(f"Campaign sync for {integration}: {result.get('success', False)}")

        return {
            "success": result.get("success", False),
            "message": result.get("message", _("Sync completed")),
            "error_message": result.get("error_message", ""),
            "campaigns_synced": result.get("campaigns_synced", 0),
        }

    except frappe.ValidationError:
        raise
    except Exception as e:
        logger.error(f"Campaign sync failed for {integration}: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Campaign Sync Error")
        return {
            "success": False,
            "error_message": str(e),
            "message": _("Failed to sync campaigns"),
        }
