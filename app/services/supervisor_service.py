import logging
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload

from app.models.user import User, UserRole
from app.models.supervisor import SupervisorProfile, SupervisorStudentAssignment, SupervisorClassAssignment
from app.models.student import Student
from app.models.class_model import Class
from app.schemas.supervisor import (
    SupervisorCreateRequest,
    SupervisorProfileCreate,
    SupervisorProfileUpdate,
    SupervisorStudentAssignmentCreate,
    BulkStudentAssignment,
    SupervisorClassAssignmentCreate,
    SupervisorBulkClassAssignment
)
from app.core.security import get_password_hash
from app.utils.password_generator import generate_secure_password
from app.services.email_service import EmailService


logger = logging.getLogger(__name__)


class SupervisorService:
    """Service for managing supervisors and their student assignments."""

    @staticmethod
    async def create_supervisor(
        db: AsyncSession,
        supervisor_data: SupervisorCreateRequest,
        created_by: Optional[UUID] = None
    ) -> SupervisorProfile:
        """Create a new supervisor with user account and profile.

        Password is auto-generated and sent via email.
        User must change password on first login.
        """
        # Generate secure password
        password = generate_secure_password(12)

        # Generate username from email (part before @)
        username = supervisor_data.email.split('@')[0].lower()

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
            email=supervisor_data.email,
            username=username,
            password_hash=get_password_hash(password),
            full_name=supervisor_data.full_name,
            role=UserRole.SUPERVISOR,
            timezone=supervisor_data.timezone,
            is_active=True,
            must_change_password=True  # Force password change on first login
        )
        db.add(user)
        await db.flush()

        # Create supervisor profile
        supervisor_profile = SupervisorProfile(
            user_id=user.id
        )
        db.add(supervisor_profile)
        await db.commit()
        await db.refresh(supervisor_profile)

        # Send welcome email with credentials
        try:
            email_service = EmailService()
            await email_service.send_supervisor_welcome_email(
                supervisor={
                    "email": supervisor_data.email,
                    "full_name": supervisor_data.full_name,
                    "username": username
                },
                password=password
            )
        except Exception as e:
            logger.error(f"Failed to send welcome email to supervisor {supervisor_data.email}: {e}")
            # Don't fail the creation if email fails

        return supervisor_profile

    @staticmethod
    async def get_supervisor_by_id(
        db: AsyncSession,
        supervisor_id: UUID
    ) -> Optional[SupervisorProfile]:
        """Get supervisor profile by ID."""
        result = await db.execute(
            select(SupervisorProfile)
            .options(selectinload(SupervisorProfile.user))
            .options(selectinload(SupervisorProfile.student_assignments))
            .where(SupervisorProfile.id == supervisor_id)
        )
        return result.scalars().first()

    @staticmethod
    async def get_supervisor_by_user_id(
        db: AsyncSession,
        user_id: UUID
    ) -> Optional[SupervisorProfile]:
        """Get supervisor profile by user ID."""
        result = await db.execute(
            select(SupervisorProfile)
            .options(selectinload(SupervisorProfile.user))
            .options(selectinload(SupervisorProfile.student_assignments))
            .where(SupervisorProfile.user_id == user_id)
        )
        return result.scalars().first()

    @staticmethod
    async def get_all_supervisors(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None
    ) -> List[SupervisorProfile]:
        """Get all supervisors with optional filtering."""
        query = select(SupervisorProfile).options(
            selectinload(SupervisorProfile.user),
            selectinload(SupervisorProfile.student_assignments)
        )

        if is_active is not None:
            query = query.join(User).where(User.is_active == is_active)

        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def update_supervisor(
        db: AsyncSession,
        supervisor_id: UUID,
        supervisor_data: SupervisorProfileUpdate
    ) -> Optional[SupervisorProfile]:
        """Update supervisor profile."""
        supervisor = await SupervisorService.get_supervisor_by_id(db, supervisor_id)
        if not supervisor:
            return None

        update_data = supervisor_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(supervisor, field, value)

        await db.commit()
        await db.refresh(supervisor)
        return supervisor

    @staticmethod
    async def delete_supervisor(
        db: AsyncSession,
        supervisor_id: UUID
    ) -> bool:
        """Delete supervisor (also deletes associated user)."""
        supervisor = await SupervisorService.get_supervisor_by_id(db, supervisor_id)
        if not supervisor:
            return False

        # Delete user (cascade will delete supervisor profile)
        await db.execute(delete(User).where(User.id == supervisor.user_id))
        await db.commit()
        return True

    @staticmethod
    async def assign_student(
        db: AsyncSession,
        assignment_data: SupervisorStudentAssignmentCreate,
        assigned_by: Optional[UUID] = None
    ) -> SupervisorStudentAssignment:
        """Assign a student to a supervisor."""
        assignment = SupervisorStudentAssignment(
            supervisor_id=assignment_data.supervisor_id,
            student_id=assignment_data.student_id,
            notes=assignment_data.notes,
            assigned_by=assigned_by
        )
        db.add(assignment)
        await db.commit()
        await db.refresh(assignment)
        return assignment

    @staticmethod
    async def bulk_assign_students(
        db: AsyncSession,
        bulk_data: BulkStudentAssignment,
        assigned_by: Optional[UUID] = None
    ) -> List[SupervisorStudentAssignment]:
        """Assign multiple students to a supervisor."""
        assignments = []
        for student_id in bulk_data.student_ids:
            # Check if assignment already exists
            existing = await db.execute(
                select(SupervisorStudentAssignment).where(
                    SupervisorStudentAssignment.supervisor_id == bulk_data.supervisor_id,
                    SupervisorStudentAssignment.student_id == student_id
                )
            )
            if existing.scalars().first():
                continue

            assignment = SupervisorStudentAssignment(
                supervisor_id=bulk_data.supervisor_id,
                student_id=student_id,
                notes=bulk_data.notes,
                assigned_by=assigned_by
            )
            db.add(assignment)
            assignments.append(assignment)

        await db.commit()
        return assignments

    @staticmethod
    async def remove_student_assignment(
        db: AsyncSession,
        supervisor_id: UUID,
        student_id: UUID
    ) -> bool:
        """Remove a student assignment from a supervisor."""
        result = await db.execute(
            delete(SupervisorStudentAssignment).where(
                SupervisorStudentAssignment.supervisor_id == supervisor_id,
                SupervisorStudentAssignment.student_id == student_id
            )
        )
        await db.commit()
        return result.rowcount > 0

    @staticmethod
    async def get_supervisor_students(
        db: AsyncSession,
        supervisor_id: UUID
    ) -> List[Student]:
        """Get all students assigned to a supervisor."""
        result = await db.execute(
            select(Student)
            .join(SupervisorStudentAssignment)
            .options(selectinload(Student.user))
            .options(selectinload(Student.class_info))
            .where(SupervisorStudentAssignment.supervisor_id == supervisor_id)
        )
        return result.scalars().all()

    @staticmethod
    async def count_supervisors(
        db: AsyncSession,
        is_active: Optional[bool] = None
    ) -> int:
        """Count total supervisors."""
        query = select(func.count(SupervisorProfile.id))
        if is_active is not None:
            query = query.join(User).where(User.is_active == is_active)
        result = await db.execute(query)
        return result.scalar() or 0

    @staticmethod
    async def update_assignment_notes(
        db: AsyncSession,
        supervisor_id: UUID,
        student_id: UUID,
        notes: str
    ) -> Optional[SupervisorStudentAssignment]:
        """Update notes for a student assignment."""
        result = await db.execute(
            select(SupervisorStudentAssignment).where(
                SupervisorStudentAssignment.supervisor_id == supervisor_id,
                SupervisorStudentAssignment.student_id == student_id
            )
        )
        assignment = result.scalars().first()
        if not assignment:
            return None

        assignment.notes = notes
        await db.commit()
        await db.refresh(assignment)
        return assignment

    # ==================== Class Assignment Methods ====================

    @staticmethod
    async def assign_class(
        db: AsyncSession,
        assignment_data: SupervisorClassAssignmentCreate,
        assigned_by: Optional[UUID] = None
    ) -> SupervisorClassAssignment:
        """Assign a class to a supervisor."""
        # Check if assignment already exists
        existing = await db.execute(
            select(SupervisorClassAssignment).where(
                SupervisorClassAssignment.supervisor_id == assignment_data.supervisor_id,
                SupervisorClassAssignment.class_id == assignment_data.class_id
            )
        )
        if existing.scalars().first():
            raise ValueError("Supervisor is already assigned to this class")

        assignment = SupervisorClassAssignment(
            supervisor_id=assignment_data.supervisor_id,
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
        bulk_data: SupervisorBulkClassAssignment,
        assigned_by: Optional[UUID] = None
    ) -> List[SupervisorClassAssignment]:
        """Assign multiple classes to a supervisor."""
        assignments = []
        for class_id in bulk_data.class_ids:
            # Check if assignment already exists
            existing = await db.execute(
                select(SupervisorClassAssignment).where(
                    SupervisorClassAssignment.supervisor_id == bulk_data.supervisor_id,
                    SupervisorClassAssignment.class_id == class_id
                )
            )
            if existing.scalars().first():
                continue

            assignment = SupervisorClassAssignment(
                supervisor_id=bulk_data.supervisor_id,
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
        supervisor_id: UUID,
        class_id: UUID
    ) -> bool:
        """Remove a class assignment from a supervisor."""
        result = await db.execute(
            delete(SupervisorClassAssignment).where(
                SupervisorClassAssignment.supervisor_id == supervisor_id,
                SupervisorClassAssignment.class_id == class_id
            )
        )
        await db.commit()
        return result.rowcount > 0

    @staticmethod
    async def get_supervisor_classes(
        db: AsyncSession,
        supervisor_id: UUID
    ) -> List[Class]:
        """Get all classes assigned to a supervisor."""
        result = await db.execute(
            select(Class)
            .join(SupervisorClassAssignment)
            .options(selectinload(Class.students))
            .where(SupervisorClassAssignment.supervisor_id == supervisor_id)
        )
        return result.scalars().all()

    @staticmethod
    async def get_supervisor_class_students(
        db: AsyncSession,
        supervisor_id: UUID
    ) -> List[Student]:
        """Get all students from classes assigned to a supervisor."""
        # Get class IDs assigned to the supervisor
        class_ids_result = await db.execute(
            select(SupervisorClassAssignment.class_id)
            .where(SupervisorClassAssignment.supervisor_id == supervisor_id)
        )
        class_ids = [row[0] for row in class_ids_result.fetchall()]

        if not class_ids:
            return []

        # Get students from those classes
        result = await db.execute(
            select(Student)
            .options(selectinload(Student.user))
            .options(selectinload(Student.class_info))
            .where(Student.class_id.in_(class_ids))
        )
        return result.scalars().all()

    @staticmethod
    async def update_class_assignment(
        db: AsyncSession,
        supervisor_id: UUID,
        class_id: UUID,
        is_primary: bool
    ) -> Optional[SupervisorClassAssignment]:
        """Update is_primary status for a class assignment."""
        result = await db.execute(
            select(SupervisorClassAssignment).where(
                SupervisorClassAssignment.supervisor_id == supervisor_id,
                SupervisorClassAssignment.class_id == class_id
            )
        )
        assignment = result.scalars().first()
        if not assignment:
            return None

        assignment.is_primary = is_primary
        await db.commit()
        await db.refresh(assignment)
        return assignment
