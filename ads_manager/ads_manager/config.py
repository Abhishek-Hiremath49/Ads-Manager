"""
Configuration management for Ads Manager.

Handles environment-based configuration and defaults.
"""

import os
from typing import Optional

# OAuth Configuration
OAUTH_STATE_CACHE_TTL = int(os.environ.get("ADS_OAUTH_STATE_TTL", "600"))  # 10 minutes
SESSION_CACHE_TTL = int(os.environ.get("ADS_SESSION_CACHE_TTL", "600"))  # 10 minutes
REQUEST_TIMEOUT = int(os.environ.get("ADS_REQUEST_TIMEOUT", "30"))  # seconds

# Retry Configuration
MAX_RETRIES = int(os.environ.get("ADS_MAX_RETRIES", "3"))
BACKOFF_FACTOR = float(os.environ.get("ADS_BACKOFF_FACTOR", "0.3"))

# API Configuration
FACEBOOK_API_VERSION = os.environ.get("ADS_FACEBOOK_API_VERSION", "v21.0")

# Feature Flags
ENABLE_REQUEST_LOGGING = os.environ.get("ADS_ENABLE_REQUEST_LOGGING", "False").lower() == "true"
ENABLE_DETAILED_ERRORS = os.environ.get("ADS_ENABLE_DETAILED_ERRORS", "False").lower() == "true"

# Rate Limiting
RATE_LIMIT_ENABLED = os.environ.get("ADS_RATE_LIMIT_ENABLED", "True").lower() == "true"
RATE_LIMIT_CALLS = int(os.environ.get("ADS_RATE_LIMIT_CALLS", "100"))
RATE_LIMIT_PERIOD = int(os.environ.get("ADS_RATE_LIMIT_PERIOD", "3600"))  # 1 hour


def get_config_value(key: str, default: any = None) -> any:
    """
    Get configuration value from environment or defaults.

    Args:
        key: Configuration key
        default: Default value if not found

    Returns:
        Configuration value
    """
    env_key = f"ADS_{key}"
    if env_key in os.environ:
        return os.environ.get(env_key)
    return default
