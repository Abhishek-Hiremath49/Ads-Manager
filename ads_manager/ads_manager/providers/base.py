"""
Base Provider for Ad Platforms
"""

import frappe
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List


@dataclass
class LaunchResult:  # Renamed from PublishResult
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
    SUPPORTS_IMAGES = False
    SUPPORTS_VIDEO = False
    # ... other ad-specific

    @abstractmethod
    def launch_campaign(self, payload: Dict) -> LaunchResult:
        pass

    @abstractmethod
    def fetch_account_analytics(self) -> AnalyticsResult:
        pass

    @abstractmethod
    def fetch_campaign_analytics(self, campaign_id: str) -> AnalyticsResult:
        pass

    def refresh_token(self, integration_name: str = None) -> TokenRefreshResult:
        """Refresh OAuth token"""
        return TokenRefreshResult(success=False, error_message="Token refresh not supported")

    def increment_rate_limit(self):
        """Increment API call counter"""
        cache_key = f"ad_rate_limit_{self.PLATFORM.lower()}"
        current = frappe.cache.get_value(cache_key) or 0
        frappe.cache.set_value(cache_key, current + 1, expires_in_sec=86400)

    def check_rate_limit(self) -> bool:
        """Check if under rate limit"""
        cache_key = f"ad_rate_limit_{self.PLATFORM.lower()}"
        current = frappe.cache.get_value(cache_key) or 0
        return current < 200  # Example limit