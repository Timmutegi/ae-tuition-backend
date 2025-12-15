from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_admin, get_current_teacher
from app.models.user import User
from app.services.teacher_service import TeacherService
from app.schemas.teacher import (
    TeacherCreateRequest,
    TeacherProfileUpdate,
    TeacherProfileResponse,
    TeacherListResponse,
    TeacherClassAssignmentCreate,
    TeacherClassAssignmentResponse,
    BulkClassAssignment,
    AssignedClassInfo
)

router = APIRouter(prefix="/teachers", tags=["teachers"])


# ============================================================
# Teacher's own endpoints (for teacher portal)
# IMPORTANT: These must be defined BEFORE /{teacher_id} routes
# to avoid FastAPI matching "me" as a teacher_id parameter
# ============================================================

@router.get("/me/profile", response_model=TeacherProfileResponse)
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Get current teacher's profile."""
    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )
    return teacher


@router.get("/me/classes", response_model=List[AssignedClassInfo])
async def get_my_classes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Get current teacher's assigned classes."""
    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )

    classes = await TeacherService.get_teacher_classes(db, teacher.id)
    result = []
    for cls in classes:
        result.append(AssignedClassInfo(
            id=cls.id,
            name=cls.name,
            year_group=cls.year_group,
            academic_year=cls.academic_year,
            student_count=len(cls.students) if cls.students else 0,
            is_primary=False
        ))
    return result


@router.get("/me/students")
async def get_my_students(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Get all students in current teacher's assigned classes."""
    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )

    students = await TeacherService.get_teacher_students(db, teacher.id)
    result = []
    for student in students:
        result.append({
            "id": str(student.id),
            "user_id": str(student.user_id),
            "full_name": student.user.full_name if student.user else None,
            "email": student.user.email if student.user else None,
            "student_code": student.student_code,
            "year_group": student.year_group,
            "class_name": student.class_info.name if student.class_info else None,
            "status": student.status.value if student.status else None
        })
    return result


@router.get("/me/tests")
async def get_my_tests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Get tests assigned to the current teacher's classes."""
    from app.models.test import Test, TestAssignment
    from app.models.teacher import TeacherClassAssignment

    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )

    # Get class IDs assigned to this teacher
    class_result = await db.execute(
        select(TeacherClassAssignment.class_id)
        .where(TeacherClassAssignment.teacher_id == teacher.id)
    )
    class_ids = [row[0] for row in class_result.fetchall()]

    if not class_ids:
        return {"tests": []}

    # Get tests assigned to those classes
    test_result = await db.execute(
        select(Test)
        .join(TestAssignment)
        .where(TestAssignment.class_id.in_(class_ids))
        .distinct()
    )
    tests = test_result.scalars().all()

    result = []
    for test in tests:
        result.append({
            "id": str(test.id),
            "title": test.title,
            "description": test.description,
            "subject": test.subject,
            "year_group": test.year_group,
            "duration_minutes": test.duration_minutes,
            "total_points": test.total_points,
            "is_active": test.is_active,
            "start_date": test.start_date.isoformat() if test.start_date else None,
            "end_date": test.end_date.isoformat() if test.end_date else None,
            "created_at": test.created_at.isoformat() if test.created_at else None
        })

    return {"tests": result}


# ============================================================
# Admin-only endpoints for teacher management
# ============================================================

@router.post("", response_model=TeacherProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_teacher(
    teacher_data: TeacherCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Create a new teacher account. Admin only."""
    try:
        teacher = await TeacherService.create_teacher(db, teacher_data, current_user.id)
        return teacher
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create teacher: {str(e)}"
        )


@router.get("", response_model=List[TeacherListResponse])
async def get_all_teachers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get all teachers. Admin only."""
    teachers = await TeacherService.get_all_teachers(db, skip, limit, is_active)
    result = []
    for teacher in teachers:
        result.append(TeacherListResponse(
            id=teacher.id,
            user_id=teacher.user_id,
            specialization=teacher.specialization,
            is_head_teacher=teacher.is_head_teacher,
            full_name=teacher.user.full_name if teacher.user else None,
            email=teacher.user.email if teacher.user else "",
            is_active=teacher.user.is_active if teacher.user else False,
            assigned_classes_count=len(teacher.class_assignments) if teacher.class_assignments else 0
        ))
    return result


@router.get("/count")
async def get_teachers_count(
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get total count of teachers. Admin only."""
    count = await TeacherService.count_teachers(db, is_active)
    return {"count": count}


@router.get("/{teacher_id}", response_model=TeacherProfileResponse)
async def get_teacher(
    teacher_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get teacher by ID. Admin only."""
    teacher = await TeacherService.get_teacher_by_id(db, teacher_id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )
    return teacher


@router.put("/{teacher_id}", response_model=TeacherProfileResponse)
async def update_teacher(
    teacher_id: UUID,
    teacher_data: TeacherProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update teacher profile. Admin only."""
    teacher = await TeacherService.update_teacher(db, teacher_id, teacher_data)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )
    return teacher


@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_teacher(
    teacher_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Delete teacher. Admin only."""
    success = await TeacherService.delete_teacher(db, teacher_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )


# Class assignment endpoints
@router.post("/{teacher_id}/classes", response_model=TeacherClassAssignmentResponse)
async def assign_class_to_teacher(
    teacher_id: UUID,
    class_id: UUID,
    is_primary: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Assign a class to a teacher. Admin only."""
    assignment_data = TeacherClassAssignmentCreate(
        teacher_id=teacher_id,
        class_id=class_id,
        is_primary=is_primary
    )
    try:
        assignment = await TeacherService.assign_class(db, assignment_data, current_user.id)
        return assignment
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to assign class: {str(e)}"
        )


@router.post("/{teacher_id}/classes/bulk", response_model=List[TeacherClassAssignmentResponse])
async def bulk_assign_classes(
    teacher_id: UUID,
    bulk_data: BulkClassAssignment,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Assign multiple classes to a teacher. Admin only."""
    bulk_data.teacher_id = teacher_id
    assignments = await TeacherService.bulk_assign_classes(db, bulk_data, current_user.id)
    return assignments


@router.delete("/{teacher_id}/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_class_from_teacher(
    teacher_id: UUID,
    class_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Remove a class assignment from a teacher. Admin only."""
    success = await TeacherService.remove_class_assignment(db, teacher_id, class_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class assignment not found"
        )


@router.get("/{teacher_id}/classes", response_model=List[AssignedClassInfo])
async def get_teacher_classes(
    teacher_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get all classes assigned to a teacher. Admin only."""
    classes = await TeacherService.get_teacher_classes(db, teacher_id)
    result = []
    for cls in classes:
        result.append(AssignedClassInfo(
            id=cls.id,
            name=cls.name,
            year_group=cls.year_group,
            academic_year=cls.academic_year,
            student_count=len(cls.students) if cls.students else 0,
            is_primary=False  # TODO: Add is_primary from assignment
        ))
    return result


@router.get("/{teacher_id}/students")
async def get_teacher_students(
    teacher_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get all students from classes assigned to a teacher. Admin only."""
    students = await TeacherService.get_teacher_students(db, teacher_id)
    result = []
    for student in students:
        result.append({
            "id": str(student.id),
            "user_id": str(student.user_id),
            "full_name": student.user.full_name if student.user else None,
            "email": student.user.email if student.user else None,
            "student_code": student.student_code,
            "year_group": student.year_group,
            "class_name": student.class_info.name if student.class_info else None,
            "status": student.status.value if student.status else None
        })
    return result
