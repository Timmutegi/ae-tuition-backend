"""
Rate limiting configuration using slowapi with Redis backend.
This middleware is production-only.
"""
import os
import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request, FastAPI

logger = logging.getLogger("rate_limit")


def get_client_ip(request: Request) -> str:
    """
    Get client IP for rate limiting, handling proxied requests.
    """
    # Check X-Forwarded-For header (set by Nginx)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip

    # Fall back to slowapi default
    return get_remote_address(request)


# Get Redis URL from environment or use memory storage
REDIS_URL = os.getenv("REDIS_URL", "memory://")

# Create limiter instance with custom key function
limiter = Limiter(
    key_func=get_client_ip,
    default_limits=["200/minute", "5000/hour"],
    storage_uri=REDIS_URL,
    strategy="fixed-window",
)


class RateLimits:
    """Centralized rate limit configurations."""

    # Authentication endpoints - strict limits to prevent brute force
    AUTH_LOGIN = "5/minute"
    AUTH_PASSWORD_RESET = "3/minute"
    AUTH_REGISTER = "10/minute"
    AUTH_REFRESH = "30/minute"

    # Admin endpoints - moderate limits
    ADMIN_DEFAULT = "100/minute"
    ADMIN_BULK_OPERATIONS = "10/minute"
    ADMIN_REPORTS = "30/minute"

    # Student endpoints - higher limits for normal usage
    STUDENT_DEFAULT = "200/minute"
    STUDENT_TEST_SUBMIT = "10/minute"  # Prevent rapid submissions
    STUDENT_DASHBOARD = "60/minute"

    # Teacher/Supervisor endpoints
    TEACHER_DEFAULT = "150/minute"
    SUPERVISOR_DEFAULT = "150/minute"

    # Public endpoints
    PUBLIC_DEFAULT = "50/minute"
    HEALTH_CHECK = "100/minute"

    # File operations
    FILE_UPLOAD = "20/minute"
    FILE_DOWNLOAD = "100/minute"


def setup_rate_limiting(app: FastAPI) -> Limiter:
    """
    Configure rate limiting for the FastAPI application.
    """
    # Add rate limiter to app state
    app.state.limiter = limiter

    # Add exception handler for rate limit exceeded
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Add middleware
    app.add_middleware(SlowAPIMiddleware)

    logger.info(f"Rate limiting enabled with storage: {REDIS_URL}")

    return limiter


def get_limiter() -> Limiter:
    """Get the limiter instance."""
    return limiter
