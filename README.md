# Ads Manager

Social Media Ads Scheduler and Management Platform

A comprehensive Frappe app for managing advertising campaigns across multiple social media platforms including Facebook, Instagram, and more.

## Features

- **Multi-Platform Support**: Manage ads across Facebook and Instagram
- **OAuth 2.0 Integration**: Secure authentication with Meta platforms
- **Campaign Management**: Create, schedule, and manage advertising campaigns
- **Analytics Tracking**: Real-time performance metrics and insights
- **Token Refresh**: Automatic OAuth token refresh and management
- **Multi-Account Support**: Handle multiple ad accounts per platform
- **Error Handling**: Comprehensive error logging and recovery

## Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/Abhishek-Hiremath49/Ads-Manager.git --branch main
bench install-app ads_manager
```

## Configuration

### Required Settings

After installation, configure the following in **Ads Setting**:

1. **Facebook App ID**: Your Meta app ID
2. **Facebook App Secret**: Your Meta app secret (stored securely)
3. **Facebook API Version**: Graph API version (default: v21.0)

### Environment Variables

Configure the following optional environment variables for production:

```bash
# OAuth Configuration
ADS_OAUTH_STATE_TTL=600              # OAuth state expiry (seconds, default: 600)
ADS_SESSION_CACHE_TTL=600            # Session cache TTL (seconds, default: 600)

# Request Configuration
ADS_REQUEST_TIMEOUT=30               # HTTP request timeout (seconds, default: 30)
ADS_MAX_RETRIES=3                    # Max retry attempts (default: 3)
ADS_BACKOFF_FACTOR=0.3               # Exponential backoff factor (default: 0.3)

# API Configuration
ADS_FACEBOOK_API_VERSION=v21.0       # Graph API version

# Feature Flags
ADS_ENABLE_REQUEST_LOGGING=False     # Enable detailed request logging
ADS_ENABLE_DETAILED_ERRORS=False     # Enable detailed error messages
ADS_RATE_LIMIT_ENABLED=True          # Enable rate limiting
ADS_RATE_LIMIT_CALLS=100             # Calls per period
ADS_RATE_LIMIT_PERIOD=3600           # Rate limit period (seconds)
```

## API Endpoints

### OAuth Flow

- `POST /api/method/ads_manager.ads_manager.api.oauth.initiate_oauth`
  - Initiate OAuth flow for a platform
  
- `GET /api/method/ads_manager.ads_manager.api.oauth.callback_facebook`
  - OAuth callback handler (auto-redirected by Meta)

- `GET /api/method/ads_manager.ads_manager.api.oauth.get_available_ad_accounts`
  - Get available accounts from session
  
- `POST /api/method/ads_manager.ads_manager.api.oauth.connect_ad_account`
  - Connect a selected ad account

### Integration Management

- `POST /api/method/ads_manager.ads_manager.api.oauth.disconnect`
  - Disconnect an integration
  
- `POST /api/method/ads_manager.ads_manager.api.oauth.validate_credentials`
  - Validate integration credentials
  
- `POST /api/method/ads_manager.ads_manager.api.oauth.sync_campaigns`
  - Sync campaigns from platform

## Security

### Best Practices

1. **Secrets Management**
   - Store all secrets (app secret, access tokens) in Frappe's secure password fields
   - Never commit secrets to version control
   - Use environment variables for sensitive configuration

2. **OAuth Security**
   - State tokens are validated to prevent CSRF attacks
   - Session data expires after 10 minutes by default
   - User context is verified on all operations

3. **Access Control**
   - All API endpoints require authentication
   - Permission checks are enforced on sensitive operations
   - Audit trail logging for all critical operations

4. **Data Protection**
   - Access tokens are stored encrypted in the database
   - Tokens are cleared immediately on disconnection
   - Sensitive data is not logged or exposed in error messages

### Known Security Measures

- ✅ CSRF protection via state token validation
- ✅ HTTPS required for OAuth redirects
- ✅ Secure random token generation (cryptographically secure)
- ✅ Input validation on all API parameters
- ✅ SQL injection prevention (using Frappe ORM)
- ✅ Rate limiting support (configurable)
- ✅ Comprehensive error logging without sensitive data
- ✅ Permission-based access control
- ✅ Token expiry management

## Development

### Setup Development Environment

```bash
# Install dependencies
cd apps/ads_manager
pip install -r requirements.txt

# Enable pre-commit hooks
pre-commit install
```

### Code Quality

This app uses the following tools for code quality:

- **ruff**: Fast Python linter
- **eslint**: JavaScript linting
- **prettier**: Code formatting
- **pyupgrade**: Python syntax modernization
- **semgrep**: Security and quality rules

Run checks manually:

```bash
# Python linting
ruff check ads_manager/

# Format check
ruff format ads_manager/ --check

# Security scanning
semgrep --config=p/frappe ads_manager/
```

### Testing

Run the test suite:

```bash
cd $PATH_TO_YOUR_BENCH
bench --site [site-name] run-tests --app ads_manager
```

## Logging and Monitoring

### Log Locations

- **Error Log**: Frappe Error Log (Admin → Error Log)
- **Request Log**: Console and log files
- **Audit Trail**: Integration document change log

### Monitoring Key Metrics

1. **OAuth Flow Success Rate**: Track initiate_oauth → callback → connect_ad_account conversions
2. **Token Refresh**: Monitor token expiry and refresh frequency
3. **API Response Times**: Track Graph API call durations
4. **Integration Health**: Monitor connection status and last error timestamps

## Troubleshooting

### Common Issues

**"Facebook App ID not configured"**
- Ensure Ads Setting has Facebook App ID and Secret set
- Verify secrets are set in the correct fields

**"Session expired"**
- OAuth and session tokens expire after 10 minutes
- Restart the OAuth flow if session expires

**"Invalid OAuth state"**
- State tokens are single-use and expire after 10 minutes
- Browser cookies might be blocked - check privacy settings

**"No ad accounts found"**
- User account must be a Facebook admin or have ad account access
- Check permissions in Facebook Business Manager

### Debug Mode

Enable detailed logging:

```bash
# Set environment variable
export ADS_ENABLE_DETAILED_ERRORS=True
export ADS_ENABLE_REQUEST_LOGGING=True

# Restart bench
bench start
```

Then check Error Log for detailed messages.

## Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it:

```bash
cd apps/ads_manager
pre-commit install
```

### Code Standards

- Follow PEP 8 for Python code
- Add docstrings to all functions and classes
- Include type hints where possible
- Write tests for new features
- Update documentation for API changes

## Performance

### Optimization Tips

1. **Cache Configuration**
   - Adjust `OAUTH_STATE_CACHE_TTL` based on user behavior
   - Use Redis cache backend in production

2. **Request Retry**
   - Adjust `MAX_RETRIES` and `BACKOFF_FACTOR` for your infrastructure
   - Higher retries increase resilience but add latency

3. **Rate Limiting**
   - Enable rate limiting in production
   - Adjust `RATE_LIMIT_CALLS` and `RATE_LIMIT_PERIOD` based on API usage

## Roadmap

- [ ] Support for TikTok Ads
- [ ] Support for Google Ads
- [ ] Support for LinkedIn Ads
- [ ] Campaign cloning and templates
- [ ] Advanced reporting and analytics dashboard
- [ ] Bulk operations support
- [ ] Webhook support for real-time updates

## License

MIT

## Support

For issues, feature requests, or questions:
- Create an issue on [GitHub](https://github.com/Abhishek-Hiremath49/Ads-Manager/issues)
- Check existing documentation
- Review error logs for detailed information

## Changelog

### v1.0.0 (Current)
- Initial release
- Facebook/Instagram OAuth integration
- Multi-account support
- Campaign management foundation
- Comprehensive error handling and logging

