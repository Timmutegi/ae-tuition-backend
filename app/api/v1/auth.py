from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, get_current_admin
from app.schemas.user import LoginRequest, TokenResponse, User as UserSchema, UserUpdate
from app.services.auth import AuthService
from app.models.user import User

router = APIRouter()

@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Unified login endpoint for both admin and student users.
    Students can login with their student code.
    Admins can login with email or username.
    Returns JWT token and user information.
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
    current_user: User = Depends(get_current_user)
):
    """
    Refresh access token.
    Returns a new JWT token for the current user.
    """
    # Generate new access token
    access_token = AuthService.create_access_token_for_user(current_user)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserSchema.model_validate(current_user)
    )

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