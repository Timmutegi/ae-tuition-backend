import logging
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import create_tables, AsyncSessionLocal
from app.api.v1.router import api_router
from app.services.auth import AuthService
from app.core.security import get_current_admin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up AE Tuition API...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # Create database tables
    await create_tables()
    logger.info("Database tables created successfully")

    # Create default admin user
    async with AsyncSessionLocal() as db:
        try:
            admin_data = {
                "email": settings.DEFAULT_ADMIN_EMAIL,
                "username": settings.DEFAULT_ADMIN_USERNAME,
                "password": settings.DEFAULT_ADMIN_PASSWORD,
                "full_name": settings.DEFAULT_ADMIN_FULL_NAME
            }

            admin_user = await AuthService.create_default_admin(db, admin_data)
            logger.info(f"Default admin created/verified: {admin_user.email}")
        except Exception as e:
            logger.error(f"Error creating default admin: {e}")

    logger.info("AE Tuition API startup complete")

    yield

    # Shutdown
    logger.info("Shutting down AE Tuition API...")


# Create FastAPI application
app = FastAPI(
    title="AE Tuition API",
    description="Ed-Tech platform API for online test management and administration",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,  # Disable automatic redirects to prevent 307 errors with CloudFront
    # Optionally hide docs in production
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)


# Production-only security middleware
if settings.is_production:
    logger.info("Production environment detected - enabling security middleware")

    from app.middleware.security import SecurityMiddleware, ip_tracker
    from app.middleware.rate_limit import setup_rate_limiting
    from app.middleware.headers import SecurityHeadersMiddleware
    from app.middleware.alerts import security_alerts

    # Setup rate limiting FIRST (must be before other middleware)
    setup_rate_limiting(app)
    logger.info("Rate limiting enabled")

    # Add security middleware (order matters - first added = last executed)
    # Request flow: SecurityMiddleware -> SecurityHeaders -> CORS -> Rate Limit -> App
    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("Security headers middleware enabled")

    app.add_middleware(SecurityMiddleware, alert_service=security_alerts)
    logger.info("Security middleware enabled with alerting")


# Configure CORS (always enabled)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "https://d2nylqijymu9wv.cloudfront.net",
        settings.FRONTEND_URL,
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")


# Health check endpoint
@app.get("/")
async def root():
    return {
        "message": "AE Tuition API",
        "version": "1.0.0",
        "status": "running",
        "environment": settings.ENVIRONMENT
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "message": "AE Tuition API is running successfully"
    }


# Security statistics endpoint (admin only, production only)
if settings.is_production:
    @app.get("/api/v1/admin/security/stats")
    async def security_stats(current_user=Depends(get_current_admin)):
        """Get current security statistics (admin only)."""
        from app.middleware.security import ip_tracker
        return {
            "status": "ok",
            "security": ip_tracker.get_stats()
        }