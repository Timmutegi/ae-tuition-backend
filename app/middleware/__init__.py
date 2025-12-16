"""
Security middleware package for AE Tuition API.
All middleware is production-only - development environment remains unchanged.
"""
import os

# Check environment - only export middleware in production
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
IS_PRODUCTION = ENVIRONMENT == "production"

if IS_PRODUCTION:
    from .security import SecurityMiddleware, ip_tracker
    from .rate_limit import limiter, setup_rate_limiting, RateLimits
    from .headers import SecurityHeadersMiddleware
    from .alerts import SecurityAlertService, security_alerts

    __all__ = [
        "SecurityMiddleware",
        "ip_tracker",
        "limiter",
        "setup_rate_limiting",
        "RateLimits",
        "SecurityHeadersMiddleware",
        "SecurityAlertService",
        "security_alerts",
    ]
else:
    # In development, export placeholder functions
    __all__ = []
