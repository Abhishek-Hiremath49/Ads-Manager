"""
Base Provider for Ad Platforms
"""

import frappe
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List


@dataclass
class PublishResult:
    success: bool
    campaign_id: Optional[str] = None
    campaign_url: Optional[str] = None
    error_message: Optional[str] = None
    raw_response: Optional[Dict] = None


@dataclass
class AnalyticsResult:
    success: bool
    metrics: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    raw_response: Optional[Dict] = None


@dataclass
class TokenRefreshResult:
    success: bool
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    error_message: Optional[str] = None


class BaseProvider(ABC):
    """Abstract base class for ad platforms"""

    PLATFORM: str = ""
    MAX_BUDGET: int = 0
    MAX_IMAGES: int = 0
    MAX_CONTENT_LENGTH: int = 0
    SUPPORTS_IMAGES = False
    SUPPORTS_VIDEO = False

    def __init__(self, integration_name: str = None):
        self.settings = frappe.get_single("Ads Setting")
        self.integration = None
        self.integration_name = integration_name
        if integration_name:
            self.integration = frappe.get_doc(
                "Ads Account Integration", integration_name
            )

    def get_integration_doc(self, integration_name: str = None):
        """Get integration document"""
        name = integration_name or self.integration_name
        if not name:
            frappe.throw("Integration name required")
        return frappe.get_doc("Ads Account Integration", name)

    @abstractmethod
    def publish_post(self, payload: Dict) -> PublishResult:
        pass

    @abstractmethod
    def fetch_account_analytics(self) -> AnalyticsResult:
        pass

    @abstractmethod
    def fetch_post_analytics(self, campaign_id: str) -> AnalyticsResult:
        pass

    @abstractmethod
    def get_daily_limit(self) -> int:
        """Get daily rate limit for this platform"""
        pass

    def refresh_token(self, integration_name: str = None) -> TokenRefreshResult:
        """Refresh OAuth token"""
        return TokenRefreshResult(
            success=False, error_message="Token refresh not supported"
        )

    def increment_rate_limit(self):
        """Increment API call counter"""
        cache_key = f"ad_rate_limit_{self.PLATFORM.lower()}"
        current = frappe.cache.get_value(cache_key) or 0
        frappe.cache.set_value(cache_key, current + 1, expires_in_sec=86400)

    def check_rate_limit(self) -> bool:
        """Check if under rate limit"""
        cache_key = f"ad_rate_limit_{self.PLATFORM.lower()}"
        current = frappe.cache.get_value(cache_key) or 0
        return current < self.get_daily_limit()
