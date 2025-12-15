"""
API endpoints for weekly attendance tracking with test scores integration.

These endpoints allow supervisors and teachers to:
- View weekly attendance with test scores
- Mark attendance (present/absent)
- Update book-based comments (Help in, Incomplete, Unmarked, At home)
- View overall performance across all weeks
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app.core.database import get_db
from app.core.security import (
    get_current_user,
    get_current_supervisor,
    get_current_teacher,
    get_current_teacher_or_supervisor
)
from app.models.user import User, UserRole
from app.services.weekly_attendance_service import WeeklyAttendanceService
from app.services.supervisor_service import SupervisorService
from app.services.teacher_service import TeacherService
from app.services.academic_calendar_service import calendar_service
from app.schemas.weekly_attendance import (
    WeeklyAttendanceCreate,
    WeeklyAttendanceUpdate,
    WeeklyAttendanceCommentsUpdate,
    WeeklyAttendanceResponse,
    WeeklyAttendanceDataResponse,
    OverallPerformanceResponse,
    BulkAttendanceCreate,
    BulkAttendanceResponse
)

router = APIRouter(prefix="/attendance", tags=["Weekly Attendance"])


# ========== Get Weekly Attendance with Scores ==========

@router.get("/weekly", response_model=WeeklyAttendanceDataResponse)
async def get_weekly_attendance(
    week: Optional[int] = Query(None, ge=1, le=52, description="Week number. Defaults to current week."),
    class_id: Optional[UUID] = Query(None, description="Filter by class"),
    student_code: Optional[str] = Query(None, description="Filter by student code"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher_or_supervisor)
):
    """
    Get weekly attendance data with integrated test scores.

    - Supervisors see their assigned students
    - Teachers see students from their assigned classes
    - Admins can see all students (with optional filters)

    Returns student data with:
    - Attendance status (present/absent)
    - Test scores for English, VR GL, NVR, Maths
    - Book comments (H, I/c, u/m, a/h)
    """
    # Get current week if not specified
    target_week = week if week else calendar_service.get_current_week()
    if target_week == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active academic week"
        )

    academic_year = calendar_service.get_academic_year_string()

    # Determine filters based on user role
    supervisor_id = None
    teacher_id = None

    if current_user.role == UserRole.SUPERVISOR:
        # Get supervisor profile
        supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
        if supervisor:
            supervisor_id = supervisor.id
    elif current_user.role == UserRole.TEACHER:
        # Get teacher profile
        teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
        if teacher:
            teacher_id = teacher.id

    # Admin can see all (no supervisor_id or teacher_id filter)

    result = await WeeklyAttendanceService.get_weekly_attendance_with_scores(
        db=db,
        week_number=target_week,
        academic_year=academic_year,
        class_id=class_id,
        student_code=student_code,
        supervisor_id=supervisor_id,
        teacher_id=teacher_id
    )

    return result


@router.get("/overall", response_model=OverallPerformanceResponse)
async def get_overall_performance(
    class_id: Optional[UUID] = Query(None, description="Filter by class"),
    student_code: Optional[str] = Query(None, description="Filter by student code"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher_or_supervisor)
):
    """
    Get overall performance (average scores across all weeks).

    Returns:
    - Attendance rate per student
    - Average percentage per subject
    """
    academic_year = calendar_service.get_academic_year_string()

    # Determine filters based on user role
    supervisor_id = None
    teacher_id = None

    if current_user.role == UserRole.SUPERVISOR:
        supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
        if supervisor:
            supervisor_id = supervisor.id
    elif current_user.role == UserRole.TEACHER:
        teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
        if teacher:
            teacher_id = teacher.id

    result = await WeeklyAttendanceService.get_overall_performance(
        db=db,
        academic_year=academic_year,
        class_id=class_id,
        student_code=student_code,
        supervisor_id=supervisor_id,
        teacher_id=teacher_id
    )

    return result


# ========== Create/Update Attendance ==========

@router.post("/weekly", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_or_update_attendance(
    data: WeeklyAttendanceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher_or_supervisor)
):
    """
    Create or update weekly attendance for a single student.

    If a record already exists for the student/week/year combination,
    it will be updated. Otherwise, a new record is created.
    """
    record = await WeeklyAttendanceService.create_or_update_attendance(
        db=db,
        data=data,
        recorded_by=current_user.id
    )

    return {
        "id": str(record.id),
        "student_id": str(record.student_id),
        "week_number": record.week_number,
        "is_present": record.is_present,
        "message": "Attendance saved successfully"
    }


@router.put("/weekly/{attendance_id}", response_model=dict)
async def update_attendance(
    attendance_id: UUID,
    data: WeeklyAttendanceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher_or_supervisor)
):
    """Update an existing attendance record."""
    record = await WeeklyAttendanceService.update_attendance(
        db=db,
        attendance_id=attendance_id,
        data=data,
        recorded_by=current_user.id
    )

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance record not found"
        )

    return {
        "id": str(record.id),
        "message": "Attendance updated successfully"
    }


@router.put("/weekly/comments", response_model=dict)
async def update_comments(
    data: WeeklyAttendanceCommentsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher_or_supervisor)
):
    """
    Update only the book comments for a student's weekly attendance.

    Creates a new attendance record if one doesn't exist.
    """
    record = await WeeklyAttendanceService.update_comments(
        db=db,
        data=data,
        recorded_by=current_user.id
    )

    return {
        "id": str(record.id),
        "student_id": str(record.student_id),
        "week_number": record.week_number,
        "message": "Comments updated successfully"
    }


@router.post("/weekly/bulk", response_model=BulkAttendanceResponse, status_code=status.HTTP_201_CREATED)
async def bulk_create_attendance(
    data: BulkAttendanceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher_or_supervisor)
):
    """
    Create or update attendance for multiple students at once.

    Useful for marking all students in a class at once.
    """
    academic_year = calendar_service.get_academic_year_string()

    result = await WeeklyAttendanceService.bulk_create_attendance(
        db=db,
        week_number=data.week_number,
        academic_year=academic_year,
        student_attendance=data.student_attendance,
        recorded_by=current_user.id
    )

    return BulkAttendanceResponse(**result)


# ========== Utility Endpoints ==========

@router.get("/current-week")
async def get_current_week_info(
    current_user: User = Depends(get_current_user)
):
    """Get information about the current academic week."""
    current_week = calendar_service.get_current_week()

    if current_week == 0:
        return {
            "current_week": 0,
            "message": "No active academic week"
        }

    week_info = calendar_service.get_week_info(current_week)

    return {
        "current_week": current_week,
        "academic_year": calendar_service.get_academic_year_string(),
        "total_weeks": 40,
        "week_info": {
            "week_number": week_info.week_number,
            "start_date": week_info.start_date.isoformat(),
            "end_date": week_info.end_date.isoformat(),
            "is_break": week_info.is_break,
            "break_name": week_info.break_name,
            "week_label": calendar_service.get_week_label(current_week)
        }
    }
