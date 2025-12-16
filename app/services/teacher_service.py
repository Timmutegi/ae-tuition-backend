import logging
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload

from app.models.user import User, UserRole
from app.models.teacher import TeacherProfile, TeacherClassAssignment
from app.models.class_model import Class
from app.models.student import Student
from app.schemas.teacher import (
    TeacherCreateRequest,
    TeacherProfileCreate,
    TeacherProfileUpdate,
    TeacherClassAssignmentCreate,
    BulkClassAssignment
)
from app.core.security import get_password_hash
from app.utils.password_generator import generate_secure_password
from app.services.email_service import EmailService


logger = logging.getLogger(__name__)


class TeacherService:
    """Service for managing teachers and their class assignments."""

    @staticmethod
    async def create_teacher(
        db: AsyncSession,
        teacher_data: TeacherCreateRequest,
        created_by: Optional[UUID] = None
    ) -> TeacherProfile:
        """Create a new teacher with user account and profile.

        Password is auto-generated and sent via email.
        User must change password on first login.
        """
        # Generate secure password
        password = generate_secure_password(12)

        # Generate username from email (part before @)
        username = teacher_data.email.split('@')[0].lower()

        # Ensure username is unique by appending numbers if needed
        base_username = username
        counter = 1
        while True:
            existing = await db.execute(
                select(User).where(User.username == username)
            )
            if not existing.scalars().first():
                break
            username = f"{base_username}{counter}"
            counter += 1

        # Create user
        user = User(
            email=teacher_data.email,
            username=username,
            password_hash=get_password_hash(password),
            full_name=teacher_data.full_name,
            role=UserRole.TEACHER,
            timezone=teacher_data.timezone,
            is_active=True,
            must_change_password=True  # Force password change on first login
        )
        db.add(user)
        await db.flush()

        # Create teacher profile
        teacher_profile = TeacherProfile(
            user_id=user.id
        )
        db.add(teacher_profile)
        await db.commit()
        await db.refresh(teacher_profile)

        # Send welcome email with credentials
        try:
            email_service = EmailService()
            await email_service.send_teacher_welcome_email(
                teacher={
                    "email": teacher_data.email,
                    "full_name": teacher_data.full_name,
                    "username": username
                },
                password=password
            )
        except Exception as e:
            logger.error(f"Failed to send welcome email to teacher {teacher_data.email}: {e}")
            # Don't fail the creation if email fails

        return teacher_profile

    @staticmethod
    async def get_teacher_by_id(
        db: AsyncSession,
        teacher_id: UUID
    ) -> Optional[TeacherProfile]:
        """Get teacher profile by ID."""
        result = await db.execute(
            select(TeacherProfile)
            .options(selectinload(TeacherProfile.user))
            .options(selectinload(TeacherProfile.class_assignments))
            .where(TeacherProfile.id == teacher_id)
        )
        return result.scalars().first()

    @staticmethod
    async def get_teacher_by_user_id(
        db: AsyncSession,
        user_id: UUID
    ) -> Optional[TeacherProfile]:
        """Get teacher profile by user ID."""
        result = await db.execute(
            select(TeacherProfile)
            .options(selectinload(TeacherProfile.user))
            .options(selectinload(TeacherProfile.class_assignments))
            .where(TeacherProfile.user_id == user_id)
        )
        return result.scalars().first()

    @staticmethod
    async def get_all_teachers(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None
    ) -> List[TeacherProfile]:
        """Get all teachers with optional filtering."""
        query = select(TeacherProfile).options(
            selectinload(TeacherProfile.user),
            selectinload(TeacherProfile.class_assignments)
        )

        if is_active is not None:
            query = query.join(User).where(User.is_active == is_active)

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def update_teacher(
        db: AsyncSession,
        teacher_id: UUID,
        teacher_data: TeacherProfileUpdate
    ) -> Optional[TeacherProfile]:
        """Update teacher profile."""
        teacher = await TeacherService.get_teacher_by_id(db, teacher_id)
        if not teacher:
            return None

        update_data = teacher_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(teacher, field, value)

        await db.commit()
        await db.refresh(teacher)
        return teacher

    @staticmethod
    async def delete_teacher(
        db: AsyncSession,
        teacher_id: UUID
    ) -> bool:
        """Delete teacher (also deletes associated user)."""
        teacher = await TeacherService.get_teacher_by_id(db, teacher_id)
        if not teacher:
            return False

        # Delete user (cascade will delete teacher profile)
        await db.execute(delete(User).where(User.id == teacher.user_id))
        await db.commit()
        return True

    @staticmethod
    async def assign_class(
        db: AsyncSession,
        assignment_data: TeacherClassAssignmentCreate,
        assigned_by: Optional[UUID] = None
    ) -> TeacherClassAssignment:
        """Assign a teacher to a class."""
        assignment = TeacherClassAssignment(
            teacher_id=assignment_data.teacher_id,
            class_id=assignment_data.class_id,
            is_primary=assignment_data.is_primary,
            assigned_by=assigned_by
        )
        db.add(assignment)
        await db.commit()
        await db.refresh(assignment)
        return assignment

    @staticmethod
    async def bulk_assign_classes(
        db: AsyncSession,
        bulk_data: BulkClassAssignment,
        assigned_by: Optional[UUID] = None
    ) -> List[TeacherClassAssignment]:
        """Assign multiple classes to a teacher."""
        assignments = []
        for class_id in bulk_data.class_ids:
            # Check if assignment already exists
            existing = await db.execute(
                select(TeacherClassAssignment).where(
                    TeacherClassAssignment.teacher_id == bulk_data.teacher_id,
                    TeacherClassAssignment.class_id == class_id
                )
            )
            if existing.scalars().first():
                continue

            assignment = TeacherClassAssignment(
                teacher_id=bulk_data.teacher_id,
                class_id=class_id,
                is_primary=bulk_data.is_primary,
                assigned_by=assigned_by
            )
            db.add(assignment)
            assignments.append(assignment)

        await db.commit()
        return assignments

    @staticmethod
    async def remove_class_assignment(
        db: AsyncSession,
        teacher_id: UUID,
        class_id: UUID
    ) -> bool:
        """Remove a class assignment from a teacher."""
        result = await db.execute(
            delete(TeacherClassAssignment).where(
                TeacherClassAssignment.teacher_id == teacher_id,
                TeacherClassAssignment.class_id == class_id
            )
        )
        await db.commit()
        return result.rowcount > 0

    @staticmethod
    async def get_teacher_classes(
        db: AsyncSession,
        teacher_id: UUID
    ) -> List[Class]:
        """Get all classes assigned to a teacher."""
        result = await db.execute(
            select(Class)
            .join(TeacherClassAssignment)
            .options(selectinload(Class.students))
            .where(TeacherClassAssignment.teacher_id == teacher_id)
        )
        return result.scalars().all()

    @staticmethod
    async def get_teacher_students(
        db: AsyncSession,
        teacher_id: UUID
    ) -> List[Student]:
        """Get all students in classes assigned to a teacher."""
        # Get class IDs assigned to teacher
        class_result = await db.execute(
            select(TeacherClassAssignment.class_id)
            .where(TeacherClassAssignment.teacher_id == teacher_id)
        )
        class_ids = [row[0] for row in class_result.fetchall()]

        if not class_ids:
            return []

        # Get students in those classes
        result = await db.execute(
            select(Student)
            .options(selectinload(Student.user))
            .options(selectinload(Student.class_info))
            .where(Student.class_id.in_(class_ids))
        )
        return result.scalars().all()

    @staticmethod
    async def count_teachers(
        db: AsyncSession,
        is_active: Optional[bool] = None
    ) -> int:
        """Count total teachers."""
        query = select(func.count(TeacherProfile.id))
        if is_active is not None:
            query = query.join(User).where(User.is_active == is_active)
        result = await db.execute(query)
        return result.scalar() or 0
