from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import create_tables, AsyncSessionLocal
from app.api.v1.router import api_router
from app.services.auth import AuthService

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting up AE Tuition API...")

    # Create database tables
    await create_tables()
    print("Database tables created successfully")

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
            print(f"Default admin created/verified: {admin_user.email}")
        except Exception as e:
            print(f"Error creating default admin: {e}")

    print("AE Tuition API startup complete")

    yield

    # Shutdown
    print("Shutting down AE Tuition API...")

# Create FastAPI application
app = FastAPI(
    title="AE Tuition API",
    description="Ed-Tech platform API for online test management and administration",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
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
        "status": "running"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "message": "AE Tuition API is running successfully"
    }