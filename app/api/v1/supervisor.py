from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_admin, get_current_supervisor
from app.models.user import User
from app.models.student import Student
from app.models.supervisor import SupervisorClassAssignment
from app.services.supervisor_service import SupervisorService
from app.schemas.supervisor import (
    SupervisorCreateRequest,
    SupervisorProfileUpdate,
    SupervisorProfileResponse,
    SupervisorListResponse,
    SupervisorStudentAssignmentCreate,
    SupervisorStudentAssignmentResponse,
    BulkStudentAssignment,
    AssignedStudentInfo,
    SupervisorClassAssignmentCreate,
    SupervisorClassAssignmentResponse,
    SupervisorBulkClassAssignment,
    SupervisorAssignedClassInfo
)

router = APIRouter(prefix="/supervisors", tags=["supervisors"])


# ============================================================
# Supervisor's own endpoints (for supervisor portal)
# IMPORTANT: These must be defined BEFORE /{supervisor_id} routes
# to avoid FastAPI matching "me" as a supervisor_id parameter
# ============================================================

@router.get("/me/profile", response_model=SupervisorProfileResponse)
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get current supervisor's profile."""
    supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
    if not supervisor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor profile not found"
        )
    return supervisor


@router.get("/me/students", response_model=List[AssignedStudentInfo])
async def get_my_students(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get students from classes assigned to the current supervisor."""
    supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
    if not supervisor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor profile not found"
        )

    # Get students from assigned classes
    students = await SupervisorService.get_supervisor_class_students(db, supervisor.id)
    result = []
    for student in students:
        result.append(AssignedStudentInfo(
            id=student.id,
            student_id=student.id,
            user_id=student.user_id,
            full_name=student.user.full_name if student.user else None,
            email=student.user.email if student.user else "",
            student_code=student.student_code,
            year_group=student.year_group,
            class_name=student.class_info.name if student.class_info else None,
            notes=None
        ))
    return result


@router.put("/me/students/{student_id}/notes")
async def update_student_notes(
    student_id: UUID,
    notes: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Update notes for an assigned student."""
    supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
    if not supervisor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor profile not found"
        )

    assignment = await SupervisorService.update_assignment_notes(
        db, supervisor.id, student_id, notes
    )
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student assignment not found"
        )

    return {"message": "Notes updated successfully"}


@router.get("/me/classes", response_model=List[SupervisorAssignedClassInfo])
async def get_my_classes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get current supervisor's assigned classes."""
    supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
    if not supervisor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor profile not found"
        )

    classes = await SupervisorService.get_supervisor_classes(db, supervisor.id)
    result = []
    for cls in classes:
        student_count = len(cls.students) if hasattr(cls, 'students') and cls.students else 0
        result.append(SupervisorAssignedClassInfo(
            id=cls.id,
            name=cls.name,
            year_group=cls.year_group,
            academic_year=cls.academic_year,
            student_count=student_count,
            is_primary=False
        ))
    return result


@router.get("/me/class-students", response_model=List[AssignedStudentInfo])
async def get_my_class_students(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get all students from classes assigned to current supervisor."""
    supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
    if not supervisor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor profile not found"
        )

    students = await SupervisorService.get_supervisor_class_students(db, supervisor.id)
    result = []
    for student in students:
        result.append(AssignedStudentInfo(
            id=student.id,
            student_id=student.id,
            user_id=student.user_id,
            full_name=student.user.full_name if student.user else None,
            email=student.user.email if student.user else "",
            student_code=student.student_code,
            year_group=student.year_group,
            class_name=student.class_info.name if student.class_info else None,
            notes=None
        ))
    return result


# ============================================================
# Admin-only endpoints for supervisor management
# ============================================================

@router.post("", response_model=SupervisorProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_supervisor(
    supervisor_data: SupervisorCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Create a new supervisor account. Admin only."""
    try:
        supervisor = await SupervisorService.create_supervisor(db, supervisor_data, current_user.id)
        return supervisor
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create supervisor: {str(e)}"
        )


@router.get("", response_model=List[SupervisorListResponse])
async def get_all_supervisors(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get all supervisors. Admin only."""
    supervisors = await SupervisorService.get_all_supervisors(db, skip, limit, is_active)
    result = []
    for supervisor in supervisors:
        # Count assigned classes using async query
        classes_count_result = await db.execute(
            select(func.count(SupervisorClassAssignment.id))
            .where(SupervisorClassAssignment.supervisor_id == supervisor.id)
        )
        assigned_classes_count = classes_count_result.scalar() or 0

        result.append(SupervisorListResponse(
            id=supervisor.id,
            user_id=supervisor.user_id,
            full_name=supervisor.user.full_name if supervisor.user else None,
            email=supervisor.user.email if supervisor.user else "",
            is_active=supervisor.user.is_active if supervisor.user else False,
            assigned_students_count=len(supervisor.student_assignments) if supervisor.student_assignments else 0,
            assigned_classes_count=assigned_classes_count
        ))
    return result


@router.get("/count")
async def get_supervisors_count(
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get total count of supervisors. Admin only."""
    count = await SupervisorService.count_supervisors(db, is_active)
    return {"count": count}


@router.get("/{supervisor_id}", response_model=SupervisorProfileResponse)
async def get_supervisor(
    supervisor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get supervisor by ID. Admin only."""
    supervisor = await SupervisorService.get_supervisor_by_id(db, supervisor_id)
    if not supervisor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor not found"
        )
    return supervisor


@router.put("/{supervisor_id}", response_model=SupervisorProfileResponse)
async def update_supervisor(
    supervisor_id: UUID,
    supervisor_data: SupervisorProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update supervisor profile. Admin only."""
    supervisor = await SupervisorService.update_supervisor(db, supervisor_id, supervisor_data)
    if not supervisor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor not found"
        )
    return supervisor


@router.delete("/{supervisor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supervisor(
    supervisor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Delete supervisor. Admin only."""
    success = await SupervisorService.delete_supervisor(db, supervisor_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor not found"
        )


# Student assignment endpoints
@router.post("/{supervisor_id}/students", response_model=SupervisorStudentAssignmentResponse)
async def assign_student_to_supervisor(
    supervisor_id: UUID,
    student_id: UUID,
    notes: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Assign a student to a supervisor. Admin only."""
    assignment_data = SupervisorStudentAssignmentCreate(
        supervisor_id=supervisor_id,
        student_id=student_id,
        notes=notes
    )
    try:
        assignment = await SupervisorService.assign_student(db, assignment_data, current_user.id)
        return assignment
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to assign student: {str(e)}"
        )


@router.post("/{supervisor_id}/students/bulk", response_model=List[SupervisorStudentAssignmentResponse])
async def bulk_assign_students(
    supervisor_id: UUID,
    bulk_data: BulkStudentAssignment,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Assign multiple students to a supervisor. Admin only."""
    bulk_data.supervisor_id = supervisor_id
    assignments = await SupervisorService.bulk_assign_students(db, bulk_data, current_user.id)
    return assignments


@router.delete("/{supervisor_id}/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_student_from_supervisor(
    supervisor_id: UUID,
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Remove a student assignment from a supervisor. Admin only."""
    success = await SupervisorService.remove_student_assignment(db, supervisor_id, student_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student assignment not found"
        )


@router.get("/{supervisor_id}/students", response_model=List[AssignedStudentInfo])
async def get_supervisor_students(
    supervisor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get all students from classes assigned to a supervisor. Admin only."""
    # Get students from assigned classes (not direct student assignments)
    students = await SupervisorService.get_supervisor_class_students(db, supervisor_id)
    result = []
    for student in students:
        result.append(AssignedStudentInfo(
            id=student.id,
            student_id=student.id,
            user_id=student.user_id,
            full_name=student.user.full_name if student.user else None,
            email=student.user.email if student.user else "",
            student_code=student.student_code,
            year_group=student.year_group,
            class_name=student.class_info.name if student.class_info else None,
            notes=None
        ))
    return result


# ==================== Class Assignment Endpoints (Admin) ====================

@router.post("/{supervisor_id}/classes", response_model=SupervisorClassAssignmentResponse)
async def assign_class_to_supervisor(
    supervisor_id: UUID,
    class_id: UUID,
    is_primary: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Assign a class to a supervisor. Admin only."""
    assignment_data = SupervisorClassAssignmentCreate(
        supervisor_id=supervisor_id,
        class_id=class_id,
        is_primary=is_primary
    )
    try:
        assignment = await SupervisorService.assign_class(db, assignment_data, current_user.id)
        return assignment
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to assign class: {str(e)}"
        )


@router.post("/{supervisor_id}/classes/bulk", response_model=List[SupervisorClassAssignmentResponse])
async def bulk_assign_classes_to_supervisor(
    supervisor_id: UUID,
    class_ids: List[UUID],
    is_primary: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Assign multiple classes to a supervisor. Admin only."""
    bulk_data = SupervisorBulkClassAssignment(
        supervisor_id=supervisor_id,
        class_ids=class_ids,
        is_primary=is_primary
    )
    assignments = await SupervisorService.bulk_assign_classes(db, bulk_data, current_user.id)
    return assignments


@router.delete("/{supervisor_id}/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_class_from_supervisor(
    supervisor_id: UUID,
    class_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Remove a class assignment from a supervisor. Admin only."""
    success = await SupervisorService.remove_class_assignment(db, supervisor_id, class_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class assignment not found"
        )


@router.get("/{supervisor_id}/classes", response_model=List[SupervisorAssignedClassInfo])
async def get_supervisor_classes(
    supervisor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get all classes assigned to a supervisor. Admin only."""
    classes = await SupervisorService.get_supervisor_classes(db, supervisor_id)
    result = []
    for cls in classes:
        # Count students in the class using async query
        student_count_result = await db.execute(
            select(func.count(Student.id)).where(Student.class_id == cls.id)
        )
        student_count = student_count_result.scalar() or 0

        result.append(SupervisorAssignedClassInfo(
            id=cls.id,
            name=cls.name,
            year_group=cls.year_group,
            academic_year=cls.academic_year,
            student_count=student_count,
            is_primary=False  # TODO: Get from assignment
        ))
    return result


@router.put("/{supervisor_id}/classes/{class_id}")
async def update_class_assignment(
    supervisor_id: UUID,
    class_id: UUID,
    is_primary: bool,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update class assignment (e.g., is_primary status). Admin only."""
    assignment = await SupervisorService.update_class_assignment(
        db, supervisor_id, class_id, is_primary
    )
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class assignment not found"
        )
    return {"message": "Class assignment updated successfully"}
