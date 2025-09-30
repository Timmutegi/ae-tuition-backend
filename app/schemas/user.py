from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from uuid import UUID

from app.models.user import UserRole

# Base User schema
class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    role: UserRole
    timezone: str = 'Europe/London'
    is_active: bool = True

# Schema for creating a user
class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None
    role: UserRole = UserRole.STUDENT
    timezone: str = 'Europe/London'

# Schema for user response
class User(UserBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True

# Alias for backwards compatibility
UserResponse = User

# Schema for login request
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# Schema for token response
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User

# Schema for user update
class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    timezone: Optional[str] = None
    is_active: Optional[bool] = None

# Schema for password reset
class PasswordReset(BaseModel):
    new_password: str