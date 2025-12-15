from typing import Optional
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.user import User, UserRole
from app.models.student import Student
from app.schemas.user import UserCreate, UserUpdate, LoginRequest
from app.core.security import verify_password, get_password_hash, create_access_token

class AuthService:
    @staticmethod
    async def authenticate_user(db: AsyncSession, identifier: str, password: str) -> Optional[User]:
        """
        Authenticate user with identifier (student code, email, or username) and password.
        For students, student code is the primary login method.
        For admins, email or username can be used.
        """
        user = None

        # Try to find user by student code first (for students)
        try:
            result = await db.execute(
                select(User)
                .join(Student, User.id == Student.user_id)
                .where(Student.student_code == identifier.upper())
            )
            user = result.scalars().first()
        except Exception:
            pass

        # If not found by student code, try email
        if not user:
            result = await db.execute(select(User).where(User.email == identifier))
            user = result.scalars().first()

        # If not found by email, try username
        if not user:
            result = await db.execute(select(User).where(User.username == identifier))
            user = result.scalars().first()

        if not user:
            return None

        if not verify_password(password, user.password_hash):
            return None

        if not user.is_active:
            return None

        # Update last login
        user.last_login = datetime.utcnow()
        await db.commit()
        await db.refresh(user)

        return user

    @staticmethod
    async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
        """Create a new user."""
        # Check if user with email already exists
        result = await db.execute(select(User).where(User.email == user_data.email))
        if result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Check if user with username already exists
        result = await db.execute(select(User).where(User.username == user_data.username))
        if result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )

        # Create new user
        hashed_password = get_password_hash(user_data.password)
        db_user = User(
            email=user_data.email,
            username=user_data.username,
            password_hash=hashed_password,
            full_name=user_data.full_name,
            role=user_data.role,
            timezone=user_data.timezone,
            is_active=True
        )

        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)

        return db_user

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """Get user by email."""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalars().first()

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
        """Get user by ID."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalars().first()

    @staticmethod
    def create_access_token_for_user(user: User) -> str:
        """Create access token for user."""
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.value,
            "username": user.username
        }
        return create_access_token(token_data)

    @staticmethod
    async def create_default_admin(db: AsyncSession, admin_data: dict) -> User:
        """Create default admin user if not exists."""
        # Check if admin already exists
        existing_admin = await AuthService.get_user_by_email(db, admin_data["email"])
        if existing_admin:
            return existing_admin

        # Create admin user
        user_create = UserCreate(
            email=admin_data["email"],
            username=admin_data["username"],
            password=admin_data["password"],
            full_name=admin_data["full_name"],
            role=UserRole.ADMIN
        )

        return await AuthService.create_user(db, user_create)

    @staticmethod
    async def update_user_profile(db: AsyncSession, user_id: UUID, user_update: UserUpdate) -> Optional[User]:
        """Update user profile information including timezone."""
        # Get existing user
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()

        if not user:
            return None

        # Update fields that are provided
        update_data = user_update.model_dump(exclude_unset=True)

        # Check for email uniqueness if email is being updated
        if 'email' in update_data and update_data['email'] != user.email:
            existing_user = await db.execute(select(User).where(User.email == update_data['email']))
            if existing_user.scalars().first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )

        # Check for username uniqueness if username is being updated
        if 'username' in update_data and update_data['username'] != user.username:
            existing_user = await db.execute(select(User).where(User.username == update_data['username']))
            if existing_user.scalars().first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already taken"
                )

        # Apply updates
        for field, value in update_data.items():
            setattr(user, field, value)

        await db.commit()
        await db.refresh(user)

        return user

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against a hashed password."""
        return verify_password(plain_password, hashed_password)

    @staticmethod
    async def change_user_password(db: AsyncSession, user_id: UUID, new_password: str) -> User:
        """Change user password and clear must_change_password flag."""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Hash the new password
        user.password_hash = get_password_hash(new_password)
        # Clear the must_change_password flag
        user.must_change_password = False

        await db.commit()
        await db.refresh(user)

        return user