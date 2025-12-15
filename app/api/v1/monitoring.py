"""
Monitoring API Endpoints for Anti-Cheating System

Provides endpoints for:
- Logging suspicious activities from the frontend
- Heartbeat updates from active test sessions
- Real-time monitoring data for teachers and admins
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from datetime import datetime

from app.core.database import get_db
from app.core.security import get_current_user, get_current_teacher
from app.models.user import User
from app.models.monitoring import ActivityType, SessionStatus
from app.services.anti_cheat_service import AntiCheatService


router = APIRouter()


# ==================== Request/Response Schemas ====================

class ActivityLogRequest(BaseModel):
    """Request to log a suspicious activity."""
    attempt_id: UUID
    activity_type: str = Field(..., description="Type of activity (e.g., 'tab_switch', 'copy_attempt')")
    metadata: Optional[dict] = None
    question_number: Optional[int] = None
    question_id: Optional[UUID] = None
    duration_seconds: Optional[int] = None


class BulkActivityLogRequest(BaseModel):
    """Request to log multiple activities at once."""
    attempt_id: UUID
    activities: List[dict] = Field(..., description="List of activities to log")


class HeartbeatRequest(BaseModel):
    """Heartbeat update from active test session."""
    attempt_id: UUID
    current_question: int
    questions_answered: int
    time_remaining_seconds: int


class SessionCreateRequest(BaseModel):
    """Request to create an active session when test starts."""
    attempt_id: UUID
    student_id: UUID
    test_id: UUID
    assignment_id: Optional[UUID] = None
    total_questions: int
    duration_minutes: int
    browser_info: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    screen_resolution: Optional[str] = None


class ActivityLogResponse(BaseModel):
    """Response for a logged activity."""
    id: str
    activity_type: str
    severity: str
    description: str
    occurred_at: datetime

    class Config:
        from_attributes = True


class SessionResponse(BaseModel):
    """Response for an active session."""
    id: str
    attempt_id: str
    student_id: str
    student_name: str
    student_email: str
    test_id: str
    test_title: str
    status: str
    current_question: int
    questions_answered: int
    total_questions: int
    progress_percentage: int
    started_at: Optional[str]
    last_heartbeat: Optional[str]
    time_remaining_seconds: Optional[int]
    tab_switches: int
    copy_attempts: int
    paste_attempts: int
    idle_periods: int
    total_idle_seconds: int
    warnings_count: int
    is_flagged: bool
    flag_reason: Optional[str]
    requires_attention: bool

    class Config:
        from_attributes = True


# ==================== Student Endpoints (Activity Logging) ====================

@router.post("/activities/log", response_model=ActivityLogResponse)
async def log_activity(
    request: ActivityLogRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Log a suspicious activity during a test session.

    Called by the frontend when suspicious activity is detected.
    """
    try:
        activity_type = ActivityType(request.activity_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid activity type: {request.activity_type}"
        )

    # Get student_id and test_id from the attempt
    from app.models.test import TestAttempt
    from sqlalchemy import select

    result = await db.execute(
        select(TestAttempt).where(TestAttempt.id == request.attempt_id)
    )
    attempt = result.scalar_one_or_none()

    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test attempt not found"
        )

    service = AntiCheatService(db)
    log = await service.log_activity(
        attempt_id=request.attempt_id,
        student_id=attempt.student_id,
        test_id=attempt.test_id,
        activity_type=activity_type,
        metadata=request.metadata,
        question_number=request.question_number,
        question_id=request.question_id,
        duration_seconds=request.duration_seconds
    )

    return ActivityLogResponse(
        id=str(log.id),
        activity_type=log.activity_type.value,
        severity=log.severity.value,
        description=log.description,
        occurred_at=log.occurred_at
    )


@router.post("/activities/bulk-log")
async def log_bulk_activities(
    request: BulkActivityLogRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Log multiple suspicious activities at once.

    Useful for batch reporting accumulated events.
    """
    from app.models.test import TestAttempt
    from sqlalchemy import select

    result = await db.execute(
        select(TestAttempt).where(TestAttempt.id == request.attempt_id)
    )
    attempt = result.scalar_one_or_none()

    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test attempt not found"
        )

    service = AntiCheatService(db)
    logs = await service.log_bulk_activities(
        attempt_id=request.attempt_id,
        student_id=attempt.student_id,
        test_id=attempt.test_id,
        activities=request.activities
    )

    return {"logged_count": len(logs)}


@router.post("/sessions/heartbeat")
async def send_heartbeat(
    request: HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Send a heartbeat update from an active test session.

    Called every 10 seconds by the frontend to update session status.
    """
    service = AntiCheatService(db)
    session = await service.update_heartbeat(
        attempt_id=request.attempt_id,
        current_question=request.current_question,
        questions_answered=request.questions_answered,
        time_remaining_seconds=request.time_remaining_seconds
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active session not found"
        )

    return {
        "status": session.status.value,
        "is_flagged": session.is_flagged,
        "warnings_count": session.warnings_count
    }


@router.post("/sessions/create")
async def create_session(
    request: SessionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create an active test session for monitoring.

    Called when a student starts a test.
    """
    service = AntiCheatService(db)

    # Check if session already exists
    existing = await service.get_session(request.attempt_id)
    if existing:
        return {"session_id": str(existing.id), "status": existing.status.value}

    session = await service.create_active_session(
        attempt_id=request.attempt_id,
        student_id=request.student_id,
        test_id=request.test_id,
        assignment_id=request.assignment_id,
        total_questions=request.total_questions,
        duration_minutes=request.duration_minutes,
        browser_info=request.browser_info,
        ip_address=request.ip_address,
        user_agent=request.user_agent,
        screen_resolution=request.screen_resolution
    )

    return {"session_id": str(session.id), "status": session.status.value}


@router.post("/sessions/{attempt_id}/end")
async def end_session(
    attempt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    End an active test session when test is submitted.
    """
    service = AntiCheatService(db)
    await service.end_session(attempt_id)
    return {"status": "completed"}


# ==================== Teacher/Admin Endpoints (Monitoring) ====================

@router.get("/sessions/active", response_model=List[SessionResponse])
async def get_all_active_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Get all currently active test sessions.

    For admin/teacher invigilation dashboard.
    """
    service = AntiCheatService(db)
    sessions = await service.get_all_active_sessions()
    return sessions


@router.get("/sessions/test/{test_id}", response_model=List[SessionResponse])
async def get_sessions_for_test(
    test_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Get all active sessions for a specific test.

    For monitoring a particular test.
    """
    service = AntiCheatService(db)
    sessions = await service.get_active_sessions_for_test(test_id)
    return sessions


@router.get("/sessions/flagged", response_model=List[SessionResponse])
async def get_flagged_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Get all flagged sessions that require attention.
    """
    service = AntiCheatService(db)
    sessions = await service.get_flagged_sessions()
    return sessions


@router.get("/sessions/{attempt_id}/activities")
async def get_attempt_activities(
    attempt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Get all suspicious activities for a specific test attempt.
    """
    service = AntiCheatService(db)
    activities = await service.get_activity_log_for_attempt(attempt_id)
    return activities


@router.get("/sessions/{attempt_id}/summary")
async def get_attempt_activity_summary(
    attempt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Get a summary of suspicious activities for an attempt.
    """
    service = AntiCheatService(db)
    summary = await service.get_activity_summary_for_attempt(attempt_id)
    return summary


@router.get("/dashboard/stats")
async def get_monitoring_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Get overall monitoring statistics for the dashboard.
    """
    service = AntiCheatService(db)

    all_sessions = await service.get_all_active_sessions()
    flagged_sessions = await service.get_flagged_sessions()

    active_count = len([s for s in all_sessions if s["status"] == "active"])
    idle_count = len([s for s in all_sessions if s["status"] == "idle"])
    suspicious_count = len([s for s in all_sessions if s["status"] == "suspicious"])

    return {
        "total_active_sessions": len(all_sessions),
        "active_count": active_count,
        "idle_count": idle_count,
        "suspicious_count": suspicious_count,
        "flagged_count": len(flagged_sessions),
        "requires_attention_count": len([s for s in all_sessions if s["requires_attention"]])
    }
