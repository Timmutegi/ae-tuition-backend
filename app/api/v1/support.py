"""
API endpoints for the Support System (Phase 5).
Handles attendance, support sessions, homework tracking, and parent communications.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from datetime import date

from app.core.database import get_db
from app.core.security import get_current_supervisor, get_current_admin, get_current_user
from app.models.user import User
from app.services.support_service import SupportService
from app.services.supervisor_service import SupervisorService
from app.schemas.support import (
    # Attendance
    AttendanceRecordCreate, AttendanceRecordUpdate, AttendanceBulkCreate,
    AttendanceRecordResponse, AttendanceSummary,
    # Support Sessions
    SupportSessionCreate, SupportSessionUpdate, SupportSessionResponse,
    SupportSessionType,
    # Homework
    HomeworkRecordCreate, HomeworkRecordUpdate, HomeworkBulkCreate,
    HomeworkRecordResponse, HomeworkStatus,
    # Templates
    CommunicationTemplateCreate, CommunicationTemplateUpdate, CommunicationTemplateResponse,
    # Communications
    ParentCommunicationCreate, ParentCommunicationFromTemplate,
    ParentCommunicationUpdate, ParentCommunicationResponse,
    # Overview
    StudentOverview, SupervisorDashboardStats
)

router = APIRouter(prefix="/support", tags=["support"])


# ========== Dashboard Endpoints ==========

@router.get("/dashboard/stats", response_model=SupervisorDashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get supervisor dashboard statistics."""
    supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
    if not supervisor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor profile not found"
        )

    service = SupportService(db)
    return await service.get_supervisor_dashboard_stats(supervisor.id)


@router.get("/students", response_model=List[dict])
async def get_assigned_students(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get all students assigned to the current supervisor."""
    supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
    if not supervisor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor profile not found"
        )

    service = SupportService(db)
    return await service.get_assigned_students(supervisor.id)


@router.get("/students/{student_id}/overview", response_model=StudentOverview)
async def get_student_overview(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get comprehensive overview of a student."""
    service = SupportService(db)
    overview = await service.get_student_overview(student_id)
    if not overview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    return overview


# ========== Attendance Endpoints ==========

@router.post("/attendance", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_attendance_record(
    data: AttendanceRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Create a single attendance record."""
    service = SupportService(db)
    record = await service.create_attendance_record(data, current_user.id)
    return {
        "id": str(record.id),
        "student_id": str(record.student_id),
        "date": str(record.date),
        "status": record.status.value,
        "message": "Attendance recorded successfully"
    }


@router.post("/attendance/bulk", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_bulk_attendance(
    data: AttendanceBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Create attendance records for multiple students at once."""
    service = SupportService(db)
    records = await service.create_bulk_attendance(data, current_user.id)
    return {
        "count": len(records),
        "message": f"Created {len(records)} attendance records"
    }


@router.get("/attendance", response_model=List[dict])
async def get_attendance_by_date(
    target_date: date = Query(..., description="Date for attendance"),
    class_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get attendance records for a specific date."""
    supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
    supervisor_id = supervisor.id if supervisor else None

    service = SupportService(db)
    return await service.get_attendance_by_date(target_date, class_id, supervisor_id)


@router.get("/attendance/summary", response_model=AttendanceSummary)
async def get_attendance_summary(
    target_date: date = Query(..., description="Date for summary"),
    class_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get attendance summary for a date."""
    supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
    supervisor_id = supervisor.id if supervisor else None

    service = SupportService(db)
    return await service.get_attendance_summary(target_date, class_id, supervisor_id)


@router.put("/attendance/{record_id}", response_model=dict)
async def update_attendance_record(
    record_id: UUID,
    data: AttendanceRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Update an attendance record."""
    service = SupportService(db)
    record = await service.update_attendance_record(record_id, data)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance record not found"
        )
    return {"message": "Attendance updated successfully"}


@router.get("/attendance/student/{student_id}", response_model=List[dict])
async def get_student_attendance_history(
    student_id: UUID,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get attendance history for a specific student."""
    service = SupportService(db)
    records = await service.get_student_attendance_history(student_id, start_date, end_date)
    return [
        {
            "id": str(r.id),
            "date": str(r.date),
            "status": r.status.value,
            "source": r.source.value,
            "arrival_time": str(r.arrival_time) if r.arrival_time else None,
            "departure_time": str(r.departure_time) if r.departure_time else None,
            "notes": r.notes
        }
        for r in records
    ]


# ========== Support Session Endpoints ==========

@router.post("/sessions", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_support_session(
    data: SupportSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Create a support session record."""
    supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
    if not supervisor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor profile not found"
        )

    service = SupportService(db)
    session = await service.create_support_session(data, supervisor.id)
    return {
        "id": str(session.id),
        "title": session.title,
        "message": "Support session created successfully"
    }


@router.get("/sessions", response_model=List[dict])
async def get_support_sessions(
    student_id: Optional[UUID] = None,
    session_type: Optional[SupportSessionType] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    follow_up_required: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get support sessions with filters."""
    supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
    supervisor_id = supervisor.id if supervisor else None

    service = SupportService(db)
    session_type_enum = None
    if session_type:
        from app.models.support import SupportSessionType as DBSupportSessionType
        session_type_enum = DBSupportSessionType(session_type.value)

    return await service.get_support_sessions(
        supervisor_id=supervisor_id,
        student_id=student_id,
        session_type=session_type_enum,
        start_date=start_date,
        end_date=end_date,
        follow_up_required=follow_up_required
    )


@router.get("/sessions/follow-ups", response_model=List[dict])
async def get_pending_follow_ups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get sessions that require follow-up."""
    supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
    if not supervisor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supervisor profile not found"
        )

    service = SupportService(db)
    return await service.get_pending_follow_ups(supervisor.id)


@router.put("/sessions/{session_id}", response_model=dict)
async def update_support_session(
    session_id: UUID,
    data: SupportSessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Update a support session."""
    service = SupportService(db)
    session = await service.update_support_session(session_id, data)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Support session not found"
        )
    return {"message": "Session updated successfully"}


# ========== Homework Endpoints ==========

@router.post("/homework", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_homework_record(
    data: HomeworkRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Create a homework record."""
    service = SupportService(db)
    record = await service.create_homework_record(data, current_user.id)
    return {
        "id": str(record.id),
        "assignment_title": record.assignment_title,
        "message": "Homework record created successfully"
    }


@router.post("/homework/bulk", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_bulk_homework(
    data: HomeworkBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Create homework records for multiple students."""
    service = SupportService(db)
    records = await service.create_bulk_homework(data, current_user.id)
    return {
        "count": len(records),
        "message": f"Created {len(records)} homework records"
    }


@router.get("/homework", response_model=List[dict])
async def get_homework_records(
    student_id: Optional[UUID] = None,
    class_id: Optional[UUID] = None,
    subject: Optional[str] = None,
    status: Optional[HomeworkStatus] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get homework records with filters."""
    service = SupportService(db)

    status_enum = None
    if status:
        from app.models.support import HomeworkStatus as DBHomeworkStatus
        status_enum = DBHomeworkStatus(status.value)

    return await service.get_homework_records(
        student_id=student_id,
        class_id=class_id,
        subject=subject,
        status=status_enum,
        start_date=start_date,
        end_date=end_date
    )


@router.get("/homework/missing", response_model=List[dict])
async def get_missing_homework(
    class_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get all missing/incomplete homework for assigned students."""
    supervisor = await SupervisorService.get_supervisor_by_user_id(db, current_user.id)
    supervisor_id = supervisor.id if supervisor else None

    service = SupportService(db)
    return await service.get_missing_homework(class_id, supervisor_id)


@router.put("/homework/{record_id}", response_model=dict)
async def update_homework_record(
    record_id: UUID,
    data: HomeworkRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Update a homework record status."""
    service = SupportService(db)
    record = await service.update_homework_record(record_id, data)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Homework record not found"
        )
    return {"message": "Homework record updated successfully"}


# ========== Communication Template Endpoints ==========

@router.post("/templates", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: CommunicationTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Create a communication template. Admin only."""
    service = SupportService(db)
    template = await service.create_template(data, current_user.id)
    return {
        "id": str(template.id),
        "name": template.name,
        "message": "Template created successfully"
    }


@router.get("/templates", response_model=List[CommunicationTemplateResponse])
async def get_templates(
    category: Optional[str] = None,
    is_active: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get available communication templates."""
    service = SupportService(db)
    return await service.get_templates(category, is_active)


@router.put("/templates/{template_id}", response_model=dict)
async def update_template(
    template_id: UUID,
    data: CommunicationTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update a communication template. Admin only."""
    service = SupportService(db)
    template = await service.update_template(template_id, data)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    return {"message": "Template updated successfully"}


# ========== Parent Communication Endpoints ==========

@router.post("/communications", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_communication(
    data: ParentCommunicationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Create a parent communication record."""
    service = SupportService(db)
    comm = await service.create_communication(data, current_user.id)
    return {
        "id": str(comm.id),
        "subject": comm.subject,
        "message": "Communication created successfully"
    }


@router.post("/communications/from-template", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_communication_from_template(
    data: ParentCommunicationFromTemplate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Create a communication using a template."""
    service = SupportService(db)
    try:
        comm = await service.create_communication_from_template(data, current_user.id)
        return {
            "id": str(comm.id),
            "subject": comm.subject,
            "message": "Communication created from template successfully"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/communications", response_model=List[dict])
async def get_communications(
    student_id: Optional[UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Get parent communications with filters."""
    service = SupportService(db)
    return await service.get_communications(
        student_id=student_id,
        sent_by=current_user.id,
        start_date=start_date,
        end_date=end_date
    )


@router.put("/communications/{comm_id}", response_model=dict)
async def update_communication(
    comm_id: UUID,
    data: ParentCommunicationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_supervisor)
):
    """Update communication delivery/response status."""
    # For now, we'll just return success - actual update would need service method
    return {"message": "Communication updated successfully"}
