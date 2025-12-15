"""
Anti-Cheating Service for AE Tuition

This service handles:
- Logging suspicious activities (tab switches, copy-paste, idle time)
- Managing active test sessions with heartbeat tracking
- Generating alerts based on configurable thresholds
- Providing real-time monitoring data for teachers
"""

from typing import Dict, List, Optional, Any
from uuid import UUID
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_, func
from sqlalchemy.orm import selectinload

from app.models.monitoring import (
    SuspiciousActivityLog, ActiveTestSession, AlertConfiguration,
    ActivityType, AlertSeverity, SessionStatus
)
from app.models.test import TestAttempt, Test, AttemptStatus
from app.models.student import Student
from app.models.user import User


class AntiCheatService:
    """Service for anti-cheating detection and monitoring."""

    # Default alert thresholds
    DEFAULT_THRESHOLDS = {
        ActivityType.TAB_SWITCH: {"count": 5, "severity": AlertSeverity.MEDIUM},
        ActivityType.TAB_HIDDEN: {"count": 3, "severity": AlertSeverity.MEDIUM},
        ActivityType.COPY_ATTEMPT: {"count": 2, "severity": AlertSeverity.HIGH},
        ActivityType.PASTE_ATTEMPT: {"count": 2, "severity": AlertSeverity.HIGH},
        ActivityType.IDLE_TIMEOUT: {"count": 3, "severity": AlertSeverity.LOW},
        ActivityType.DEVTOOLS_OPEN: {"count": 1, "severity": AlertSeverity.CRITICAL},
        ActivityType.FULLSCREEN_EXIT: {"count": 3, "severity": AlertSeverity.MEDIUM},
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Activity Logging ====================

    async def log_activity(
        self,
        attempt_id: UUID,
        student_id: UUID,
        test_id: UUID,
        activity_type: ActivityType,
        metadata: Optional[Dict[str, Any]] = None,
        question_number: Optional[int] = None,
        question_id: Optional[UUID] = None,
        duration_seconds: Optional[int] = None
    ) -> SuspiciousActivityLog:
        """
        Log a suspicious activity during a test session.

        Args:
            attempt_id: The test attempt ID
            student_id: The student ID
            test_id: The test ID
            activity_type: Type of suspicious activity
            metadata: Additional context about the activity
            question_number: Current question number when activity occurred
            question_id: Current question ID
            duration_seconds: Duration for time-based activities (idle, hidden)

        Returns:
            The created activity log entry
        """
        # Determine severity based on activity type
        threshold_info = self.DEFAULT_THRESHOLDS.get(
            activity_type,
            {"severity": AlertSeverity.LOW}
        )
        severity = threshold_info["severity"]

        # Create activity description
        description = self._generate_description(activity_type, metadata)

        activity_log = SuspiciousActivityLog(
            attempt_id=attempt_id,
            student_id=student_id,
            test_id=test_id,
            activity_type=activity_type,
            severity=severity,
            description=description,
            extra_data=metadata or {},
            question_number=question_number,
            question_id=question_id,
            duration_seconds=duration_seconds,
            occurred_at=datetime.now(timezone.utc)
        )

        self.db.add(activity_log)

        # Update active session counters
        await self._update_session_counters(attempt_id, activity_type, duration_seconds)

        # Check if we need to flag the session
        await self._check_alert_thresholds(attempt_id, activity_type)

        await self.db.commit()
        await self.db.refresh(activity_log)

        return activity_log

    async def log_bulk_activities(
        self,
        attempt_id: UUID,
        student_id: UUID,
        test_id: UUID,
        activities: List[Dict[str, Any]]
    ) -> List[SuspiciousActivityLog]:
        """
        Log multiple activities at once (for batch reporting).

        Args:
            attempt_id: The test attempt ID
            student_id: The student ID
            test_id: The test ID
            activities: List of activity dicts with type, metadata, etc.

        Returns:
            List of created activity log entries
        """
        logs = []
        for activity in activities:
            activity_type = ActivityType(activity.get("activity_type"))
            log = await self.log_activity(
                attempt_id=attempt_id,
                student_id=student_id,
                test_id=test_id,
                activity_type=activity_type,
                metadata=activity.get("metadata"),
                question_number=activity.get("question_number"),
                question_id=activity.get("question_id"),
                duration_seconds=activity.get("duration_seconds")
            )
            logs.append(log)
        return logs

    def _generate_description(
        self,
        activity_type: ActivityType,
        metadata: Optional[Dict[str, Any]]
    ) -> str:
        """Generate a human-readable description for an activity."""
        descriptions = {
            ActivityType.TAB_SWITCH: "Student switched browser tabs",
            ActivityType.TAB_HIDDEN: "Browser tab was hidden/minimized",
            ActivityType.COPY_ATTEMPT: "Copy action detected",
            ActivityType.PASTE_ATTEMPT: "Paste action detected",
            ActivityType.CUT_ATTEMPT: "Cut action detected",
            ActivityType.RIGHT_CLICK: "Right-click context menu detected",
            ActivityType.KEYBOARD_SHORTCUT: "Suspicious keyboard shortcut used",
            ActivityType.IDLE_TIMEOUT: "Student was idle for extended period",
            ActivityType.WINDOW_BLUR: "Browser window lost focus",
            ActivityType.WINDOW_FOCUS: "Browser window regained focus",
            ActivityType.FULLSCREEN_EXIT: "Exited fullscreen mode",
            ActivityType.DEVTOOLS_OPEN: "Developer tools detected",
            ActivityType.PRINT_ATTEMPT: "Print action detected",
            ActivityType.SCREENSHOT_ATTEMPT: "Screenshot attempt detected",
            ActivityType.MULTIPLE_MONITORS: "Multiple monitors detected",
            ActivityType.BROWSER_RESIZE: "Browser window resized significantly",
        }

        base_description = descriptions.get(activity_type, f"Activity: {activity_type.value}")

        if metadata:
            if "key" in metadata:
                base_description += f" (Key: {metadata['key']})"
            if "duration" in metadata:
                base_description += f" (Duration: {metadata['duration']}s)"

        return base_description

    async def _update_session_counters(
        self,
        attempt_id: UUID,
        activity_type: ActivityType,
        duration_seconds: Optional[int]
    ) -> None:
        """Update the activity counters on the active session."""
        result = await self.db.execute(
            select(ActiveTestSession).where(ActiveTestSession.attempt_id == attempt_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            return

        # Update specific counters based on activity type
        if activity_type in [ActivityType.TAB_SWITCH, ActivityType.TAB_HIDDEN]:
            session.tab_switches = (session.tab_switches or 0) + 1
        elif activity_type == ActivityType.COPY_ATTEMPT:
            session.copy_attempts = (session.copy_attempts or 0) + 1
        elif activity_type == ActivityType.PASTE_ATTEMPT:
            session.paste_attempts = (session.paste_attempts or 0) + 1
        elif activity_type == ActivityType.IDLE_TIMEOUT:
            session.idle_periods = (session.idle_periods or 0) + 1
            if duration_seconds:
                session.total_idle_seconds = (session.total_idle_seconds or 0) + duration_seconds

        session.last_activity = datetime.now(timezone.utc)

    async def _check_alert_thresholds(
        self,
        attempt_id: UUID,
        activity_type: ActivityType
    ) -> None:
        """Check if activity count exceeds thresholds and flag session if needed."""
        # Count activities of this type for this attempt
        result = await self.db.execute(
            select(func.count(SuspiciousActivityLog.id))
            .where(and_(
                SuspiciousActivityLog.attempt_id == attempt_id,
                SuspiciousActivityLog.activity_type == activity_type
            ))
        )
        count = result.scalar()

        threshold_info = self.DEFAULT_THRESHOLDS.get(activity_type)
        if threshold_info and count >= threshold_info.get("count", 999):
            # Flag the session
            await self.db.execute(
                update(ActiveTestSession)
                .where(ActiveTestSession.attempt_id == attempt_id)
                .values(
                    is_flagged=True,
                    requires_attention=True,
                    flag_reason=f"Exceeded threshold for {activity_type.value} ({count} occurrences)",
                    warnings_count=ActiveTestSession.warnings_count + 1
                )
            )

    # ==================== Session Management ====================

    async def create_active_session(
        self,
        attempt_id: UUID,
        student_id: UUID,
        test_id: UUID,
        assignment_id: Optional[UUID],
        total_questions: int,
        duration_minutes: int,
        browser_info: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        screen_resolution: Optional[str] = None
    ) -> ActiveTestSession:
        """
        Create a new active test session for monitoring.

        Called when a student starts a test.
        """
        now = datetime.now(timezone.utc)

        session = ActiveTestSession(
            attempt_id=attempt_id,
            student_id=student_id,
            test_id=test_id,
            assignment_id=assignment_id,
            status=SessionStatus.ACTIVE,
            current_question=1,
            questions_answered=0,
            total_questions=total_questions,
            progress_percentage=0,
            started_at=now,
            last_heartbeat=now,
            last_activity=now,
            time_remaining_seconds=duration_minutes * 60,
            browser_info=browser_info,
            ip_address=ip_address,
            user_agent=user_agent,
            screen_resolution=screen_resolution
        )

        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        return session

    async def update_heartbeat(
        self,
        attempt_id: UUID,
        current_question: int,
        questions_answered: int,
        time_remaining_seconds: int
    ) -> Optional[ActiveTestSession]:
        """
        Update session with heartbeat data.

        Called every 10 seconds from the frontend.
        """
        result = await self.db.execute(
            select(ActiveTestSession).where(ActiveTestSession.attempt_id == attempt_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            return None

        now = datetime.now(timezone.utc)

        # Check for idle (no heartbeat for > 30 seconds)
        if session.last_heartbeat:
            time_since_last = (now - session.last_heartbeat).total_seconds()
            if time_since_last > 30:
                session.status = SessionStatus.IDLE
            else:
                session.status = SessionStatus.ACTIVE

        # Update session data
        session.current_question = current_question
        session.questions_answered = questions_answered
        session.time_remaining_seconds = time_remaining_seconds
        session.last_heartbeat = now
        session.last_activity = now

        # Calculate progress
        if session.total_questions > 0:
            session.progress_percentage = int(
                (questions_answered / session.total_questions) * 100
            )

        await self.db.commit()
        await self.db.refresh(session)

        return session

    async def end_session(self, attempt_id: UUID) -> None:
        """Mark a session as completed when test is submitted."""
        await self.db.execute(
            update(ActiveTestSession)
            .where(ActiveTestSession.attempt_id == attempt_id)
            .values(status=SessionStatus.COMPLETED)
        )
        await self.db.commit()

    async def get_session(self, attempt_id: UUID) -> Optional[ActiveTestSession]:
        """Get an active session by attempt ID."""
        result = await self.db.execute(
            select(ActiveTestSession).where(ActiveTestSession.attempt_id == attempt_id)
        )
        return result.scalar_one_or_none()

    # ==================== Monitoring & Reporting ====================

    async def get_active_sessions_for_test(
        self,
        test_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Get all active sessions for a specific test (for teacher invigilation).

        Returns enriched session data with student info.
        """
        result = await self.db.execute(
            select(ActiveTestSession)
            .options(
                selectinload(ActiveTestSession.student).selectinload(Student.user)
            )
            .where(and_(
                ActiveTestSession.test_id == test_id,
                ActiveTestSession.status.in_([SessionStatus.ACTIVE, SessionStatus.IDLE, SessionStatus.SUSPICIOUS])
            ))
            .order_by(ActiveTestSession.started_at.desc())
        )
        sessions = result.scalars().all()

        return [self._session_to_dict(s) for s in sessions]

    async def get_active_sessions_for_teacher(
        self,
        teacher_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Get all active sessions for tests taught by this teacher.

        For the teacher's invigilation dashboard.
        """
        # Get classes assigned to this teacher
        from app.models.teacher import TeacherClassAssignment
        from app.models.test import TestAssignment

        # Get active sessions for tests assigned to teacher's classes
        result = await self.db.execute(
            select(ActiveTestSession)
            .options(
                selectinload(ActiveTestSession.student).selectinload(Student.user),
                selectinload(ActiveTestSession.test)
            )
            .join(TestAssignment, TestAssignment.test_id == ActiveTestSession.test_id)
            .join(TeacherClassAssignment, TeacherClassAssignment.class_id == TestAssignment.class_id)
            .where(and_(
                TeacherClassAssignment.teacher_id == teacher_id,
                ActiveTestSession.status.in_([SessionStatus.ACTIVE, SessionStatus.IDLE, SessionStatus.SUSPICIOUS])
            ))
            .order_by(ActiveTestSession.started_at.desc())
        )
        sessions = result.unique().scalars().all()

        return [self._session_to_dict(s) for s in sessions]

    async def get_all_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all active sessions (for admin monitoring)."""
        result = await self.db.execute(
            select(ActiveTestSession)
            .options(
                selectinload(ActiveTestSession.student).selectinload(Student.user),
                selectinload(ActiveTestSession.test)
            )
            .where(ActiveTestSession.status.in_([
                SessionStatus.ACTIVE, SessionStatus.IDLE, SessionStatus.SUSPICIOUS
            ]))
            .order_by(ActiveTestSession.started_at.desc())
        )
        sessions = result.unique().scalars().all()

        return [self._session_to_dict(s) for s in sessions]

    async def get_flagged_sessions(self) -> List[Dict[str, Any]]:
        """Get all flagged sessions that require attention."""
        result = await self.db.execute(
            select(ActiveTestSession)
            .options(
                selectinload(ActiveTestSession.student).selectinload(Student.user),
                selectinload(ActiveTestSession.test)
            )
            .where(and_(
                ActiveTestSession.is_flagged == True,
                ActiveTestSession.status != SessionStatus.COMPLETED
            ))
            .order_by(ActiveTestSession.updated_at.desc())
        )
        sessions = result.unique().scalars().all()

        return [self._session_to_dict(s) for s in sessions]

    async def get_activity_log_for_attempt(
        self,
        attempt_id: UUID
    ) -> List[Dict[str, Any]]:
        """Get all suspicious activities for a specific test attempt."""
        result = await self.db.execute(
            select(SuspiciousActivityLog)
            .where(SuspiciousActivityLog.attempt_id == attempt_id)
            .order_by(SuspiciousActivityLog.occurred_at.desc())
        )
        logs = result.scalars().all()

        return [self._activity_to_dict(log) for log in logs]

    async def get_activity_summary_for_attempt(
        self,
        attempt_id: UUID
    ) -> Dict[str, Any]:
        """Get a summary of suspicious activities for an attempt."""
        result = await self.db.execute(
            select(
                SuspiciousActivityLog.activity_type,
                func.count(SuspiciousActivityLog.id).label('count')
            )
            .where(SuspiciousActivityLog.attempt_id == attempt_id)
            .group_by(SuspiciousActivityLog.activity_type)
        )
        counts = {row[0].value: row[1] for row in result.all()}

        # Get total idle time
        idle_result = await self.db.execute(
            select(func.sum(SuspiciousActivityLog.duration_seconds))
            .where(and_(
                SuspiciousActivityLog.attempt_id == attempt_id,
                SuspiciousActivityLog.activity_type == ActivityType.IDLE_TIMEOUT
            ))
        )
        total_idle = idle_result.scalar() or 0

        return {
            "activity_counts": counts,
            "total_activities": sum(counts.values()),
            "total_idle_seconds": total_idle,
            "is_suspicious": sum(counts.values()) > 10
        }

    def _session_to_dict(self, session: ActiveTestSession) -> Dict[str, Any]:
        """Convert a session to a dictionary for API response."""
        student_name = "Unknown"
        student_email = ""
        if session.student and session.student.user:
            student_name = session.student.user.full_name or session.student.user.username
            student_email = session.student.user.email

        test_title = "Unknown Test"
        if session.test:
            test_title = session.test.title

        return {
            "id": str(session.id),
            "attempt_id": str(session.attempt_id),
            "student_id": str(session.student_id),
            "student_name": student_name,
            "student_email": student_email,
            "test_id": str(session.test_id),
            "test_title": test_title,
            "status": session.status.value,
            "current_question": session.current_question,
            "questions_answered": session.questions_answered,
            "total_questions": session.total_questions,
            "progress_percentage": session.progress_percentage,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "last_heartbeat": session.last_heartbeat.isoformat() if session.last_heartbeat else None,
            "last_activity": session.last_activity.isoformat() if session.last_activity else None,
            "time_remaining_seconds": session.time_remaining_seconds,
            "tab_switches": session.tab_switches or 0,
            "copy_attempts": session.copy_attempts or 0,
            "paste_attempts": session.paste_attempts or 0,
            "idle_periods": session.idle_periods or 0,
            "total_idle_seconds": session.total_idle_seconds or 0,
            "warnings_count": session.warnings_count or 0,
            "is_flagged": session.is_flagged,
            "flag_reason": session.flag_reason,
            "requires_attention": session.requires_attention,
            "ip_address": session.ip_address,
            "browser_info": session.browser_info
        }

    def _activity_to_dict(self, log: SuspiciousActivityLog) -> Dict[str, Any]:
        """Convert an activity log to a dictionary for API response."""
        return {
            "id": str(log.id),
            "activity_type": log.activity_type.value,
            "severity": log.severity.value,
            "description": log.description,
            "metadata": log.extra_data,
            "occurred_at": log.occurred_at.isoformat() if log.occurred_at else None,
            "duration_seconds": log.duration_seconds,
            "question_number": log.question_number,
            "reviewed": log.reviewed,
            "review_notes": log.review_notes
        }

    # ==================== Session Cleanup ====================

    async def cleanup_stale_sessions(self, timeout_minutes: int = 30) -> int:
        """
        Mark sessions as disconnected if no heartbeat received.

        Should be run periodically (e.g., every 5 minutes).
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

        result = await self.db.execute(
            update(ActiveTestSession)
            .where(and_(
                ActiveTestSession.last_heartbeat < cutoff,
                ActiveTestSession.status.in_([SessionStatus.ACTIVE, SessionStatus.IDLE])
            ))
            .values(status=SessionStatus.DISCONNECTED)
        )
        await self.db.commit()

        return result.rowcount
