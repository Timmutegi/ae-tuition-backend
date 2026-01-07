import logging
from typing import Dict, List, Optional, Tuple
from uuid import UUID
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import joinedload, selectinload

from app.core.database import AsyncSessionLocal
from app.models import User, Student, Class, UserRole, StudentStatus
from app.schemas.student import StudentCreate, StudentUpdate, ClassCreate
from app.services.email_service import EmailService
from app.utils.password_generator import generate_secure_password
from app.core.security import get_password_hash


logger = logging.getLogger(__name__)


class StudentService:
    def __init__(self):
        self.email_service = EmailService()

    async def create_student(self, db, student_data: StudentCreate) -> Dict:
        """Create a single student account."""
        try:
            # Generate password
            password = generate_secure_password()
            password_hash = get_password_hash(password)

            # Create or get class
            class_obj = None
            if student_data.class_name:
                class_obj = await self._get_or_create_class(
                    db, student_data.class_name, student_data.year_group
                )
            elif student_data.class_id:
                result = await db.execute(select(Class).where(Class.id == student_data.class_id))
                class_obj = result.scalar_one_or_none()

            # Create username from email
            username = student_data.email.split('@')[0]
            counter = 1
            original_username = username
            while True:
                existing_user = await db.execute(
                    select(User).where(User.username == username)
                )
                if not existing_user.scalar_one_or_none():
                    break
                username = f"{original_username}{counter}"
                counter += 1

            # Create user
            user = User(
                email=student_data.email,
                username=username,
                password_hash=password_hash,
                full_name=student_data.full_name,
                role=UserRole.STUDENT,
                is_active=True
            )
            db.add(user)
            await db.flush()

            # Use student code from CSV (student_id field)
            student_code = student_data.student_id if student_data.student_id else None

            # Create student profile
            student = Student(
                user_id=user.id,
                class_id=class_obj.id if class_obj else None,
                year_group=student_data.year_group,
                student_code=student_code,
                status=StudentStatus.ACTIVE
            )
            db.add(student)

            # Store user and student data before commit to avoid lazy loading issues
            user_email = user.email
            user_full_name = user.full_name
            student_code = student.student_code

            await db.commit()

            # Send welcome email using stored data
            student_dict = {
                "email": user_email,
                "full_name": user_full_name,
                "student_code": student_code
            }
            email_sent = await self.email_service.send_welcome_email(student_dict, password)
            logger.info(f"Student created successfully: {user_email} (email sent: {email_sent})")

            return {
                "success": True,
                "student": student,
                "user": user,
                "user_email": user_email,
                "user_full_name": user_full_name,
                "student_code": student_code,
                "password": password
            }

        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating student: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def create_bulk_students(self, db, students_data: List[StudentCreate]) -> Dict:
        """Create multiple students from CSV data."""
        results = {
            "successful": [],
            "failed": [],
            "total": len(students_data),
            "email_results": {"sent": 0, "failed": 0}
        }

        for student_data in students_data:
            result = await self.create_student(db, student_data)
            if result["success"]:
                results["successful"].append({
                    "email": result["user_email"],
                    "name": result["user_full_name"],
                    "student_code": result["student_code"]
                })
            else:
                results["failed"].append({
                    "email": student_data.email,
                    "name": student_data.full_name,
                    "error": result["error"]
                })

        return results

    async def get_students(
        self,
        db,
        page: int = 1,
        limit: int = 50,
        search: Optional[str] = None,
        class_id: Optional[UUID] = None,
        year_group: Optional[int] = None,
        status: Optional[StudentStatus] = None
    ) -> Dict:
        """Get paginated list of students with filters."""
        try:
            # Build query with proper joins
            query = select(Student).options(
                joinedload(Student.user),
                joinedload(Student.class_info)
            )

            # Apply filters
            filters = []
            if search:
                # For search, we need to join with User table
                query = query.join(Student.user)
                search_filter = or_(
                    User.full_name.ilike(f"%{search}%"),
                    User.email.ilike(f"%{search}%"),
                    User.username.ilike(f"%{search}%")
                )
                filters.append(search_filter)

            if class_id:
                filters.append(Student.class_id == class_id)

            if year_group:
                filters.append(Student.year_group == year_group)

            if status:
                filters.append(Student.status == status)

            if filters:
                query = query.where(and_(*filters))

            # Count total
            count_query = select(func.count(Student.id)).select_from(Student)
            if search:
                # Only join User for count if we have search filters
                count_query = count_query.join(Student.user)
            if filters:
                count_query = count_query.where(and_(*filters))

            total = await db.execute(count_query)
            total_count = total.scalar()

            # Apply pagination
            offset = (page - 1) * limit
            query = query.offset(offset).limit(limit)

            # Execute query
            result = await db.execute(query)
            students = result.scalars().all()

            return {
                "students": students,
                "total": total_count,
                "page": page,
                "pages": (total_count + limit - 1) // limit,
                "limit": limit
            }

        except Exception as e:
            logger.error(f"Error getting students: {str(e)}")
            raise e

    async def get_student(self, db, student_id: UUID) -> Optional[Student]:
        """Get single student by ID."""
        result = await db.execute(
            select(Student)
            .options(joinedload(Student.user), joinedload(Student.class_info))
            .where(Student.id == student_id)
        )
        return result.scalar_one_or_none()

    async def update_student(
        self, db, student_id: UUID, student_data: StudentUpdate
    ) -> Optional[Student]:
        """Update student information."""
        try:
            student = await self.get_student(db, student_id)
            if not student:
                return None

            # Update student fields
            if student_data.class_id is not None:
                student.class_id = student_data.class_id
            if student_data.year_group is not None:
                student.year_group = student_data.year_group
            if student_data.status is not None:
                student.status = student_data.status

            # Update user fields
            if student_data.full_name is not None:
                student.user.full_name = student_data.full_name

            await db.commit()
            return student

        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating student: {str(e)}")
            raise e

    async def delete_student(self, db, student_id: UUID) -> bool:
        """Permanently delete student and associated user account (hard delete)."""
        try:
            student = await self.get_student(db, student_id)
            if not student:
                return False

            # Get user_id before deleting student
            user_id = student.user_id

            # Import necessary models for cascade deletion
            from app.models.test import TestResult, TestAttempt
            from sqlalchemy import delete as sql_delete

            # Delete test results first (they reference both student and test_attempts)
            await db.execute(
                sql_delete(TestResult).where(TestResult.student_id == student_id)
            )
            await db.flush()

            # Delete test attempts (they reference student)
            await db.execute(
                sql_delete(TestAttempt).where(TestAttempt.student_id == student_id)
            )
            await db.flush()

            # Now delete student record
            await db.delete(student)
            await db.flush()

            # Explicitly delete user record (permanent deletion)
            user = await db.get(User, user_id)
            if user:
                await db.delete(user)

            await db.commit()
            logger.info(f"Permanently deleted student {student_id}, associated test data, and user {user_id}")
            return True

        except Exception as e:
            await db.rollback()
            logger.error(f"Error deleting student: {str(e)}")
            raise e

    async def reset_password(self, db, student_id: UUID) -> Dict:
        """Reset student password and send email."""
        try:
            student = await self.get_student(db, student_id)
            if not student:
                return {"success": False, "error": "Student not found"}

            # Store user info before commit (objects expire after commit in async SQLAlchemy)
            user_email = student.user.email
            user_full_name = student.user.full_name

            # Generate new password
            new_password = generate_secure_password()
            password_hash = get_password_hash(new_password)

            # Update user password
            student.user.password_hash = password_hash
            await db.commit()

            # Send email using stored values (not accessing expired relationship)
            student_dict = {
                "email": user_email,
                "full_name": user_full_name
            }
            email_sent = await self.email_service.send_password_reset(
                student_dict, new_password
            )

            return {
                "success": True,
                "email_sent": email_sent,
                "message": "Password reset successfully"
            }

        except Exception as e:
            await db.rollback()
            logger.error(f"Error resetting password: {str(e)}")
            return {"success": False, "error": str(e)}

    async def _get_or_create_class(self, db, class_name: str, year_group: int) -> Class:
        """Get existing class or create new one."""
        # Try to find existing class
        result = await db.execute(
            select(Class).where(
                and_(Class.name == class_name, Class.year_group == year_group)
            )
        )
        class_obj = result.scalar_one_or_none()

        if not class_obj:
            # Create new class
            class_obj = Class(
                name=class_name,
                year_group=year_group,
                academic_year="2023-2024"  # You might want to make this configurable
            )
            db.add(class_obj)
            await db.flush()

        return class_obj

    async def get_classes(self, db, page: int = 1, limit: int = 50, search: Optional[str] = None, year_group: Optional[int] = None) -> Dict:
        """Get paginated list of classes with optional filters."""
        try:
            # Build base query
            query = select(Class).options(selectinload(Class.students))

            # Apply filters
            if search:
                search_pattern = f"%{search}%"
                query = query.where(
                    or_(
                        Class.name.ilike(search_pattern),
                        Class.academic_year.ilike(search_pattern)
                    )
                )

            if year_group:
                query = query.where(Class.year_group == year_group)

            # Count total records for pagination
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await db.execute(count_query)
            total = total_result.scalar()

            # Apply pagination
            offset = (page - 1) * limit
            query = query.offset(offset).limit(limit).order_by(Class.name)

            # Execute query
            result = await db.execute(query)
            classes = result.scalars().all()

            # Convert to response format with student count
            class_responses = []
            for class_obj in classes:
                class_responses.append({
                    "id": class_obj.id,
                    "name": class_obj.name,
                    "year_group": class_obj.year_group,
                    "academic_year": class_obj.academic_year,
                    "teacher_id": class_obj.teacher_id,
                    "created_at": class_obj.created_at,
                    "updated_at": class_obj.updated_at,
                    "student_count": len(class_obj.students) if class_obj.students else 0
                })

            # Calculate pages
            pages = (total + limit - 1) // limit

            return {
                "classes": class_responses,
                "total": total,
                "page": page,
                "pages": pages,
                "limit": limit
            }

        except Exception as e:
            logger.error(f"Error getting classes: {str(e)}")
            raise