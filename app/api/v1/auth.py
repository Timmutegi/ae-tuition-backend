from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, get_current_admin
from app.core.config import settings
from app.schemas.user import (
    LoginRequest, TokenResponse, User as UserSchema, UserUpdate,
    ChangePasswordRequest, ChangePasswordResponse
)
from app.services.auth import AuthService
from app.models.user import User

router = APIRouter()

# Conditionally import rate limiting for production
if settings.is_production:
    from app.middleware.rate_limit import limiter, RateLimits


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Unified login endpoint for both admin and student users.
    Students can login with their student code.
    Admins can login with email or username.
    Returns JWT token and user information.

    Rate limited to 5 requests per minute in production.
    """
    user = await AuthService.authenticate_user(
        db=db,
        identifier=login_data.identifier,
        password=login_data.password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect student code/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate access token
    access_token = AuthService.create_access_token_for_user(user)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserSchema.model_validate(user)
    )

# Apply rate limiting decorator in production
if settings.is_production:
    login = limiter.limit(RateLimits.AUTH_LOGIN)(login)

@router.get("/me", response_model=UserSchema)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user information.
    """
    return UserSchema.model_validate(current_user)

@router.put("/me", response_model=UserSchema)
async def update_current_user_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update current authenticated user's profile information including timezone.
    """
    updated_user = await AuthService.update_user_profile(db, current_user.id, user_update)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return UserSchema.model_validate(updated_user)

@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user)
):
    """
    Logout endpoint.
    In a stateless JWT system, logout is handled client-side by removing the token.
    This endpoint exists for consistency and future token blacklisting if needed.
    """
    return {"message": "Successfully logged out"}

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Refresh access token.
    Returns a new JWT token for the current user.

    Rate limited to 30 requests per minute in production.
    """
    # Generate new access token
    access_token = AuthService.create_access_token_for_user(current_user)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserSchema.model_validate(current_user)
    )

# Apply rate limiting decorator in production
if settings.is_production:
    refresh_token = limiter.limit(RateLimits.AUTH_REFRESH)(refresh_token)

# Admin-specific endpoints
@router.get("/admin/me", response_model=UserSchema)
async def get_admin_info(
    current_admin: User = Depends(get_current_admin)
):
    """
    Get current admin user information.
    Requires admin role.
    """
    return UserSchema.from_orm(current_admin)


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    request: Request,
    password_data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Change current user's password.
    Works for all user roles (admin, teacher, supervisor, student).
    Also clears the must_change_password flag if set.

    Rate limited to 3 requests per minute in production.
    """
    # Verify current password
    if not AuthService.verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Update password and clear must_change_password flag
    try:
        await AuthService.change_user_password(
            db=db,
            user_id=current_user.id,
            new_password=password_data.new_password
        )
        return ChangePasswordResponse(
            message="Password changed successfully",
            success=True
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to change password: {str(e)}"
        )

# Apply rate limiting decorator in production
if settings.is_production:
    change_password = limiter.limit(RateLimits.AUTH_PASSWORD_RESET)(change_password)