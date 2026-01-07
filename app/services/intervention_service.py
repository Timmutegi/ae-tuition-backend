"""
Intervention service for Phase 6: Advanced Analytics & Intervention System.
Handles intervention alerts, thresholds, weekly performance tracking, and analytics.

Updated for Five-Week Review Agent with teacher approval workflow.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from sqlalchemy import select, func, and_, or_, desc, asc, Integer
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intervention import (
    InterventionThreshold, InterventionAlert, AlertRecipient,
    WeeklyPerformance, AlertStatus, AlertPriority, RecipientType
)
from app.models.student import Student, StudentStatus
from app.models.class_model import Class
from app.models.test import TestAttempt, TestResult, AttemptStatus, Test, TestType
from app.models.teacher import TeacherProfile, TeacherClassAssignment
from app.models.user import User
from app.models.support import AttendanceRecord, HomeworkRecord, AttendanceStatus, HomeworkStatus
from app.schemas.intervention import (
    InterventionThresholdCreate, InterventionThresholdUpdate,
    InterventionAlertCreate, InterventionAlertUpdate,
    StudentAnalytics, ClassAnalytics, DashboardStats
)
from app.services.academic_calendar_service import calendar_service

logger = logging.getLogger(__name__)


class InterventionService:
    """Service for managing interventions and performance analytics."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============== Threshold Management ==============

    async def create_threshold(
        self,
        data: InterventionThresholdCreate,
        created_by: UUID
    ) -> InterventionThreshold:
        """Create a new intervention threshold."""
        threshold = InterventionThreshold(
            **data.model_dump(),
            created_by=created_by
        )
        self.db.add(threshold)
        await self.db.commit()
        await self.db.refresh(threshold)
        return threshold

    async def get_threshold(self, threshold_id: UUID) -> Optional[InterventionThreshold]:
        """Get a threshold by ID."""
        result = await self.db.execute(
            select(InterventionThreshold).where(InterventionThreshold.id == threshold_id)
        )
        return result.scalar_one_or_none()

    async def get_all_thresholds(self, active_only: bool = False) -> List[InterventionThreshold]:
        """Get all thresholds."""
        query = select(InterventionThreshold).order_by(InterventionThreshold.name)
        if active_only:
            query = query.where(InterventionThreshold.is_active == True)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_threshold(
        self,
        threshold_id: UUID,
        data: InterventionThresholdUpdate
    ) -> Optional[InterventionThreshold]:
        """Update a threshold."""
        threshold = await self.get_threshold(threshold_id)
        if not threshold:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(threshold, field, value)

        await self.db.commit()
        await self.db.refresh(threshold)
        return threshold

    async def delete_threshold(self, threshold_id: UUID) -> bool:
        """Delete a threshold."""
        threshold = await self.get_threshold(threshold_id)
        if not threshold:
            return False

        await self.db.delete(threshold)
        await self.db.commit()
        return True

    # ============== Alert Management ==============

    async def create_alert(
        self,
        data: InterventionAlertCreate
    ) -> InterventionAlert:
        """Create a new intervention alert."""
        alert = InterventionAlert(
            student_id=data.student_id,
            threshold_id=data.threshold_id,
            subject=data.subject,
            alert_type=data.alert_type,
            priority=data.priority,
            status=AlertStatus.PENDING,
            title=data.title,
            description=data.description,
            recommended_actions=data.recommended_actions,
            current_average=data.current_average,
            previous_average=data.previous_average,
            weeks_failing=data.weeks_failing,
            weekly_scores=data.weekly_scores
        )
        self.db.add(alert)
        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    async def get_alert(self, alert_id: UUID) -> Optional[InterventionAlert]:
        """Get an alert by ID with relationships."""
        result = await self.db.execute(
            select(InterventionAlert)
            .options(
                selectinload(InterventionAlert.recipients),
                joinedload(InterventionAlert.student),
                joinedload(InterventionAlert.threshold)
            )
            .where(InterventionAlert.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def get_alert_by_id(self, alert_id: UUID) -> Optional[InterventionAlert]:
        """Get an alert by ID with student and class info."""
        result = await self.db.execute(
            select(InterventionAlert)
            .options(
                selectinload(InterventionAlert.recipients),
                joinedload(InterventionAlert.student).joinedload(Student.class_info),
                joinedload(InterventionAlert.student).joinedload(Student.user),
                joinedload(InterventionAlert.threshold)
            )
            .where(InterventionAlert.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def get_alerts(
        self,
        student_id: Optional[UUID] = None,
        status: Optional[AlertStatus] = None,
        priority: Optional[AlertPriority] = None,
        subject: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[InterventionAlert], int]:
        """Get alerts with filtering and pagination."""
        query = select(InterventionAlert).options(
            selectinload(InterventionAlert.recipients),
            joinedload(InterventionAlert.student)
        )

        conditions = []
        if student_id:
            conditions.append(InterventionAlert.student_id == student_id)
        if status:
            conditions.append(InterventionAlert.status == status)
        if priority:
            conditions.append(InterventionAlert.priority == priority)
        if subject:
            conditions.append(InterventionAlert.subject == subject)

        if conditions:
            query = query.where(and_(*conditions))

        # Count total
        count_query = select(func.count(InterventionAlert.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Get results
        query = query.order_by(desc(InterventionAlert.created_at)).offset(offset).limit(limit)
        result = await self.db.execute(query)
        alerts = list(result.scalars().unique().all())

        return alerts, total

    async def update_alert(
        self,
        alert_id: UUID,
        data: InterventionAlertUpdate,
        resolved_by: Optional[UUID] = None
    ) -> Optional[InterventionAlert]:
        """Update an alert status."""
        alert = await self.get_alert(alert_id)
        if not alert:
            return None

        if data.status:
            alert.status = data.status
            if data.status == AlertStatus.RESOLVED:
                alert.resolved_at = datetime.utcnow()
                alert.resolved_by = resolved_by

        if data.priority:
            alert.priority = data.priority

        if data.resolution_notes:
            alert.resolution_notes = data.resolution_notes

        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    async def add_alert_recipient(
        self,
        alert_id: UUID,
        recipient_type: RecipientType,
        recipient_id: Optional[UUID] = None,
        recipient_name: Optional[str] = None,
        recipient_email: Optional[str] = None,
        recipient_phone: Optional[str] = None
    ) -> AlertRecipient:
        """Add a recipient to an alert."""
        recipient = AlertRecipient(
            alert_id=alert_id,
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            recipient_name=recipient_name,
            recipient_email=recipient_email,
            recipient_phone=recipient_phone
        )
        self.db.add(recipient)
        await self.db.commit()
        await self.db.refresh(recipient)
        return recipient

    async def mark_recipient_notified(
        self,
        recipient_id: UUID,
        notification_method: str
    ) -> Optional[AlertRecipient]:
        """Mark a recipient as notified."""
        result = await self.db.execute(
            select(AlertRecipient).where(AlertRecipient.id == recipient_id)
        )
        recipient = result.scalar_one_or_none()
        if not recipient:
            return None

        recipient.notified_at = datetime.utcnow()
        recipient.notification_method = notification_method
        recipient.is_delivered = True

        await self.db.commit()
        await self.db.refresh(recipient)
        return recipient

    # ============== Five-Week Review Agent ==============

    async def run_intervention_check(self) -> List[InterventionAlert]:
        """
        Run the five-week review agent.
        Checks all active thresholds and creates alerts for students meeting criteria.
        """
        thresholds = await self.get_all_thresholds(active_only=True)
        created_alerts = []

        for threshold in thresholds:
            alerts = await self._check_threshold(threshold)
            created_alerts.extend(alerts)

        return created_alerts

    async def _check_threshold(
        self,
        threshold: InterventionThreshold
    ) -> List[InterventionAlert]:
        """Check a single threshold against all students."""
        alerts = []

        # Extract threshold attributes BEFORE any other queries to avoid lazy loading
        threshold_data = {
            'id': threshold.id,
            'subject': threshold.subject,
            'min_score_percent': threshold.min_score_percent,
            'weeks_to_review': threshold.weeks_to_review,
            'failures_required': threshold.failures_required,
            'alert_priority': threshold.alert_priority,
            'notify_teacher': threshold.notify_teacher
        }

        # Get all active students
        result = await self.db.execute(
            select(Student)
            .options(joinedload(Student.class_info), joinedload(Student.user))
            .where(Student.status == StudentStatus.ACTIVE)
        )
        students = list(result.scalars().unique().all())

        # Extract student data before the loop
        student_data_list = []
        for s in students:
            student_data_list.append({
                'id': s.id,
                'student_code': s.student_code,
                'full_name': s.user.full_name if s.user else "Unknown",
                'class_id': s.class_id
            })

        for student_data in student_data_list:
            alert = await self._check_student_threshold_data(student_data, threshold_data)
            if alert:
                alerts.append(alert)

        return alerts

    async def _check_student_threshold_data(
        self,
        student_data: dict,
        threshold_data: dict
    ) -> Optional[InterventionAlert]:
        """
        Check if a student triggers a threshold using academic weeks.
        Uses pre-extracted data dictionaries to avoid lazy loading issues.

        Args:
            student_data: Dict with keys: id, student_code, full_name, class_id
            threshold_data: Dict with keys: id, subject, min_score_percent, weeks_to_review,
                           failures_required, alert_priority, notify_teacher
        """
        student_id = student_data['id']
        student_code = student_data['student_code']
        student_full_name = student_data['full_name']
        student_class_id = student_data['class_id']

        threshold_id = threshold_data['id']
        threshold_subject = threshold_data['subject']
        threshold_min_score = threshold_data['min_score_percent']
        threshold_weeks_to_review = threshold_data['weeks_to_review']
        threshold_failures_required = threshold_data['failures_required']
        threshold_alert_priority = threshold_data['alert_priority']
        threshold_notify_teacher = threshold_data['notify_teacher']

        # Get current academic week
        current_week = calendar_service.get_current_week()
        if current_week == 0:
            return None  # Outside academic year

        # Calculate review window (last N academic weeks)
        start_week = max(1, current_week - threshold_weeks_to_review + 1)

        # Get weekly performances for the review period
        result = await self.db.execute(
            select(WeeklyPerformance)
            .where(
                and_(
                    WeeklyPerformance.student_id == student_id,
                    WeeklyPerformance.week_number >= start_week,
                    WeeklyPerformance.week_number <= current_week
                )
            )
            .order_by(WeeklyPerformance.week_number)
        )
        performances = list(result.scalars().all())

        if not performances:
            return None

        # Define the 4 subjects we track
        subjects_to_check = ["Verbal Reasoning", "Non-Verbal Reasoning", "English", "Mathematics"]

        # If threshold is subject-specific, only check that subject
        if threshold_subject:
            subjects_to_check = [threshold_subject]

        # Check each subject
        for subject in subjects_to_check:
            weeks_failing = 0
            weekly_scores = []

            for perf in performances:
                subject_scores = perf.subject_scores or {}
                subject_data_perf = subject_scores.get(subject, {})
                avg = subject_data_perf.get('average')

                if avg is not None:
                    weekly_scores.append({
                        'week': perf.week_number,
                        'subject': subject,
                        'score': avg
                    })
                    if avg < threshold_min_score:
                        weeks_failing += 1

            # Check if threshold is met (e.g., 3 out of 5 weeks failing)
            if weeks_failing >= threshold_failures_required:
                # Check for existing pending/in-progress alert for this subject
                existing = await self.db.execute(
                    select(InterventionAlert)
                    .where(
                        and_(
                            InterventionAlert.student_id == student_id,
                            InterventionAlert.subject == subject,
                            InterventionAlert.status.in_([AlertStatus.PENDING, AlertStatus.IN_PROGRESS])
                        )
                    )
                )
                if existing.scalar_one_or_none():
                    continue  # Already has active alert for this subject

                # Calculate current average from failing weeks
                recent_scores = [s['score'] for s in weekly_scores if s['score'] is not None]
                current_avg = sum(recent_scores) / len(recent_scores) if recent_scores else None

                # Convert weekly_scores list to dict format for schema
                weekly_scores_dict = {
                    str(s['week']): {'subject': s['subject'], 'score': s['score']}
                    for s in weekly_scores
                }

                # Create alert
                alert_data = InterventionAlertCreate(
                    student_id=student_id,
                    threshold_id=threshold_id,
                    subject=subject,
                    alert_type="performance_decline",
                    priority=threshold_alert_priority,
                    title=f"Performance Alert: {student_full_name} - {subject}",
                    description=(
                        f"Student's {subject} performance has fallen below "
                        f"{threshold_min_score}% for {weeks_failing} out of the last "
                        f"{threshold_weeks_to_review} weeks."
                    ),
                    recommended_actions=(
                        f"Review {subject} study habits and provide targeted support. "
                        "Schedule a meeting with the student and guardian to discuss "
                        "improvement strategies."
                    ),
                    current_average=current_avg,
                    weeks_failing=weeks_failing,
                    weekly_scores=weekly_scores_dict
                )

                alert = await self.create_alert(alert_data)

                # Notify teacher (required for approval workflow)
                if threshold_notify_teacher:
                    await self._notify_teacher_by_class(alert, student_class_id, student_full_name)

                logger.info(
                    f"Created intervention alert for student {student_code} "
                    f"in subject {subject} (weeks failing: {weeks_failing})"
                )

                return alert

        return None

    async def _check_student_threshold(
        self,
        student: Student,
        threshold: InterventionThreshold
    ) -> Optional[InterventionAlert]:
        """
        Check if a student triggers a threshold using academic weeks.

        This method:
        1. Gets the current academic week
        2. Looks back 'weeks_to_review' academic weeks
        3. Checks subject-specific performance against threshold
        4. Creates alert if threshold is met
        5. Notifies the assigned teacher
        """
        # Extract threshold attributes upfront to avoid lazy loading issues
        threshold_id = threshold.id
        threshold_subject = threshold.subject
        threshold_min_score = threshold.min_score_percent
        threshold_weeks_to_review = threshold.weeks_to_review
        threshold_failures_required = threshold.failures_required
        threshold_alert_priority = threshold.alert_priority
        threshold_notify_teacher = threshold.notify_teacher

        # Extract student attributes
        student_id = student.id
        student_code = student.student_code
        student_full_name = student.user.full_name if student.user else "Unknown"
        student_class_id = student.class_id

        # Get current academic week
        current_week = calendar_service.get_current_week()
        if current_week == 0:
            return None  # Outside academic year

        # Calculate review window (last N academic weeks)
        start_week = max(1, current_week - threshold_weeks_to_review + 1)

        # Get weekly performances for the review period
        result = await self.db.execute(
            select(WeeklyPerformance)
            .where(
                and_(
                    WeeklyPerformance.student_id == student_id,
                    WeeklyPerformance.week_number >= start_week,
                    WeeklyPerformance.week_number <= current_week
                )
            )
            .order_by(WeeklyPerformance.week_number)
        )
        performances = list(result.scalars().all())

        if not performances:
            return None

        # Define the 4 subjects we track
        subjects_to_check = ["Verbal Reasoning", "Non-Verbal Reasoning", "English", "Mathematics"]

        # If threshold is subject-specific, only check that subject
        if threshold_subject:
            subjects_to_check = [threshold_subject]

        # Check each subject
        for subject in subjects_to_check:
            weeks_failing = 0
            weekly_scores = []

            for perf in performances:
                subject_scores = perf.subject_scores or {}
                subject_data = subject_scores.get(subject, {})
                avg = subject_data.get('average')

                if avg is not None:
                    weekly_scores.append({
                        'week': perf.week_number,
                        'subject': subject,
                        'score': avg
                    })
                    if avg < threshold_min_score:
                        weeks_failing += 1

            # Check if threshold is met (e.g., 3 out of 5 weeks failing)
            if weeks_failing >= threshold_failures_required:
                # Check for existing pending/in-progress alert for this subject
                existing = await self.db.execute(
                    select(InterventionAlert)
                    .where(
                        and_(
                            InterventionAlert.student_id == student_id,
                            InterventionAlert.subject == subject,
                            InterventionAlert.status.in_([AlertStatus.PENDING, AlertStatus.IN_PROGRESS])
                        )
                    )
                )
                if existing.scalar_one_or_none():
                    continue  # Already has active alert for this subject

                # Calculate current average from failing weeks
                recent_scores = [s['score'] for s in weekly_scores if s['score'] is not None]
                current_avg = sum(recent_scores) / len(recent_scores) if recent_scores else None

                # Convert weekly_scores list to dict format for schema
                weekly_scores_dict = {
                    str(s['week']): {'subject': s['subject'], 'score': s['score']}
                    for s in weekly_scores
                }

                # Create alert
                alert_data = InterventionAlertCreate(
                    student_id=student_id,
                    threshold_id=threshold_id,
                    subject=subject,
                    alert_type="performance_decline",
                    priority=threshold_alert_priority,
                    title=f"Performance Alert: {student_full_name} - {subject}",
                    description=(
                        f"Student's {subject} performance has fallen below "
                        f"{threshold_min_score}% for {weeks_failing} out of the last "
                        f"{threshold_weeks_to_review} weeks."
                    ),
                    recommended_actions=(
                        f"Review {subject} study habits and provide targeted support. "
                        "Schedule a meeting with the student and guardian to discuss "
                        "improvement strategies."
                    ),
                    current_average=current_avg,
                    weeks_failing=weeks_failing,
                    weekly_scores=weekly_scores_dict
                )

                alert = await self.create_alert(alert_data)

                # Notify teacher (required for approval workflow)
                if threshold_notify_teacher:
                    await self._notify_teacher_by_class(alert, student_class_id, student_full_name)

                logger.info(
                    f"Created intervention alert for student {student_code} "
                    f"in subject {subject} (weeks failing: {weeks_failing})"
                )

                return alert

        return None

    # ============== Weekly Performance Aggregation ==============

    async def aggregate_weekly_performance(
        self,
        student_id: UUID,
        week_start: date
    ) -> WeeklyPerformance:
        """Aggregate performance data for a student for a specific week."""
        week_end = week_start + timedelta(days=6)

        # Check for existing record
        result = await self.db.execute(
            select(WeeklyPerformance)
            .where(
                and_(
                    WeeklyPerformance.student_id == student_id,
                    WeeklyPerformance.week_start == week_start
                )
            )
        )
        performance = result.scalar_one_or_none()

        if not performance:
            performance = WeeklyPerformance(
                student_id=student_id,
                week_start=week_start,
                week_end=week_end,
                week_number=week_start.isocalendar()[1],
                year=week_start.year
            )
            self.db.add(performance)

        # Aggregate test results
        test_results = await self.db.execute(
            select(TestResult)
            .join(TestAttempt)
            .where(
                and_(
                    TestAttempt.student_id == student_id,
                    TestAttempt.status == AttemptStatus.COMPLETED,
                    func.date(TestAttempt.completed_at) >= week_start,
                    func.date(TestAttempt.completed_at) <= week_end
                )
            )
        )
        results = list(test_results.scalars().all())

        if results:
            scores = [r.score_percentage for r in results if r.score_percentage is not None]
            performance.tests_taken = len(results)
            performance.average_score = sum(scores) / len(scores) if scores else None
            performance.highest_score = max(scores) if scores else None
            performance.lowest_score = min(scores) if scores else None
            performance.total_time_minutes = sum(r.duration_seconds or 0 for r in results) // 60

        # Aggregate attendance
        attendance_result = await self.db.execute(
            select(AttendanceRecord)
            .where(
                and_(
                    AttendanceRecord.student_id == student_id,
                    AttendanceRecord.date >= week_start,
                    AttendanceRecord.date <= week_end
                )
            )
        )
        attendance_records = list(attendance_result.scalars().all())

        performance.days_present = sum(1 for a in attendance_records if a.status == AttendanceStatus.PRESENT)
        performance.days_absent = sum(1 for a in attendance_records if a.status == AttendanceStatus.ABSENT)
        performance.days_late = sum(1 for a in attendance_records if a.status == AttendanceStatus.LATE)

        # Aggregate homework
        homework_result = await self.db.execute(
            select(HomeworkRecord)
            .where(
                and_(
                    HomeworkRecord.student_id == student_id,
                    HomeworkRecord.due_date >= week_start,
                    HomeworkRecord.due_date <= week_end
                )
            )
        )
        homework_records = list(homework_result.scalars().all())

        performance.homework_completed = sum(1 for h in homework_records if h.status == HomeworkStatus.COMPLETE)
        performance.homework_missing = sum(1 for h in homework_records if h.status in [HomeworkStatus.NOT_SUBMITTED, HomeworkStatus.INCOMPLETE])

        # Get previous week for comparison
        prev_week_start = week_start - timedelta(weeks=1)
        prev_result = await self.db.execute(
            select(WeeklyPerformance)
            .where(
                and_(
                    WeeklyPerformance.student_id == student_id,
                    WeeklyPerformance.week_start == prev_week_start
                )
            )
        )
        prev_performance = prev_result.scalar_one_or_none()

        if prev_performance and prev_performance.average_score and performance.average_score:
            performance.previous_week_average = prev_performance.average_score
            performance.change_percent = performance.average_score - prev_performance.average_score

        await self.db.commit()
        await self.db.refresh(performance)
        return performance

    # ============== Analytics ==============

    async def get_student_analytics(self, student_id: UUID) -> Optional[StudentAnalytics]:
        """Get comprehensive analytics for a student."""
        result = await self.db.execute(
            select(Student)
            .options(joinedload(Student.class_info))
            .where(Student.id == student_id)
        )
        student = result.scalar_one_or_none()
        if not student:
            return None

        # Get test results
        test_results = await self.db.execute(
            select(TestResult)
            .join(TestAttempt)
            .where(
                and_(
                    TestAttempt.student_id == student_id,
                    TestAttempt.status == AttemptStatus.COMPLETED
                )
            )
        )
        results = list(test_results.scalars().all())

        scores = [r.score_percentage for r in results if r.score_percentage is not None]
        total_time = sum(r.duration_seconds or 0 for r in results)

        # Get weekly trend (last 8 weeks)
        eight_weeks_ago = date.today() - timedelta(weeks=8)
        weekly_result = await self.db.execute(
            select(WeeklyPerformance)
            .where(
                and_(
                    WeeklyPerformance.student_id == student_id,
                    WeeklyPerformance.week_start >= eight_weeks_ago
                )
            )
            .order_by(WeeklyPerformance.week_start)
        )
        weekly_performances = list(weekly_result.scalars().all())

        weekly_trend = [
            {
                'week': p.week_number,
                'year': p.year,
                'average': p.average_score,
                'tests': p.tests_taken
            }
            for p in weekly_performances
        ]

        # Get attendance summary
        attendance_result = await self.db.execute(
            select(
                func.count(AttendanceRecord.id).label('total'),
                func.sum(func.cast(AttendanceRecord.status == AttendanceStatus.PRESENT, Integer)).label('present'),
                func.sum(func.cast(AttendanceRecord.status == AttendanceStatus.ABSENT, Integer)).label('absent')
            )
            .where(AttendanceRecord.student_id == student_id)
        )
        attendance_row = attendance_result.first()
        total_attendance = attendance_row.total or 0
        present = attendance_row.present or 0
        absent = attendance_row.absent or 0

        # Get alerts
        alerts_result = await self.db.execute(
            select(InterventionAlert)
            .where(InterventionAlert.student_id == student_id)
        )
        alerts = list(alerts_result.scalars().all())
        active_alerts = sum(1 for a in alerts if a.status in [AlertStatus.PENDING, AlertStatus.IN_PROGRESS])
        resolved_alerts = sum(1 for a in alerts if a.status == AlertStatus.RESOLVED)

        # Calculate improvement rate
        improvement_rate = None
        if len(weekly_trend) >= 2:
            first_avg = weekly_trend[0].get('average')
            last_avg = weekly_trend[-1].get('average')
            if first_avg and last_avg:
                improvement_rate = last_avg - first_avg

        return StudentAnalytics(
            student_id=student.id,
            student_name=student.user.full_name,
            student_code=student.student_code,
            class_name=student.class_info.name if student.class_info else None,
            overall_average=sum(scores) / len(scores) if scores else None,
            tests_completed=len(results),
            total_time_hours=total_time / 3600,
            weekly_trend=weekly_trend,
            improvement_rate=improvement_rate,
            attendance_rate=(present / total_attendance * 100) if total_attendance > 0 else None,
            days_present=present,
            days_absent=absent,
            active_alerts=active_alerts,
            resolved_alerts=resolved_alerts
        )

    async def get_dashboard_stats(self) -> DashboardStats:
        """Get admin dashboard statistics."""
        today = date.today()
        week_ago = today - timedelta(days=7)

        # Student counts
        total_students = await self.db.execute(select(func.count(Student.id)))
        active_students = await self.db.execute(
            select(func.count(Student.id)).where(Student.status == 'active')
        )

        # Test counts
        total_tests_result = await self.db.execute(
            select(func.count(TestAttempt.id))
            .where(TestAttempt.status == AttemptStatus.COMPLETED)
        )
        tests_this_week_result = await self.db.execute(
            select(func.count(TestAttempt.id))
            .where(
                and_(
                    TestAttempt.status == AttemptStatus.COMPLETED,
                    func.date(TestAttempt.completed_at) >= week_ago
                )
            )
        )
        tests_today_result = await self.db.execute(
            select(func.count(TestAttempt.id))
            .where(
                and_(
                    TestAttempt.status == AttemptStatus.COMPLETED,
                    func.date(TestAttempt.completed_at) == today
                )
            )
        )

        # Alert counts
        pending_alerts = await self.db.execute(
            select(func.count(InterventionAlert.id))
            .where(InterventionAlert.status == AlertStatus.PENDING)
        )
        resolved_this_week = await self.db.execute(
            select(func.count(InterventionAlert.id))
            .where(
                and_(
                    InterventionAlert.status == AlertStatus.RESOLVED,
                    func.date(InterventionAlert.resolved_at) >= week_ago
                )
            )
        )
        at_risk = await self.db.execute(
            select(func.count(func.distinct(InterventionAlert.student_id)))
            .where(InterventionAlert.status.in_([AlertStatus.PENDING, AlertStatus.IN_PROGRESS]))
        )

        # Attendance today
        attendance_today = await self.db.execute(
            select(
                func.count(AttendanceRecord.id).label('total'),
                func.sum(func.cast(AttendanceRecord.status == AttendanceStatus.PRESENT, Integer)).label('present'),
                func.sum(func.cast(AttendanceRecord.status == AttendanceStatus.ABSENT, Integer)).label('absent')
            )
            .where(AttendanceRecord.date == today)
        )
        att_row = attendance_today.first()
        att_total = att_row.total or 0
        att_present = att_row.present or 0
        att_absent = att_row.absent or 0

        return DashboardStats(
            total_students=total_students.scalar() or 0,
            active_students=active_students.scalar() or 0,
            total_tests=total_tests_result.scalar() or 0,
            tests_this_week=tests_this_week_result.scalar() or 0,
            tests_completed_today=tests_today_result.scalar() or 0,
            pending_alerts=pending_alerts.scalar() or 0,
            resolved_this_week=resolved_this_week.scalar() or 0,
            students_at_risk=at_risk.scalar() or 0,
            attendance_rate_today=(att_present / att_total * 100) if att_total > 0 else None,
            students_absent_today=att_absent
        )

    async def get_flagged_students(
        self,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get students with active intervention alerts."""
        # Get distinct students with pending/in-progress alerts
        query = (
            select(Student)
            .join(InterventionAlert)
            .options(joinedload(Student.class_info))
            .where(
                InterventionAlert.status.in_([AlertStatus.PENDING, AlertStatus.IN_PROGRESS])
            )
            .distinct()
        )

        # Count
        count_query = (
            select(func.count(func.distinct(Student.id)))
            .join(InterventionAlert)
            .where(
                InterventionAlert.status.in_([AlertStatus.PENDING, AlertStatus.IN_PROGRESS])
            )
        )
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Get students
        query = query.offset(offset).limit(limit)
        result = await self.db.execute(query)
        students = list(result.scalars().unique().all())

        flagged = []
        for student in students:
            # Get alert count
            alert_count = await self.db.execute(
                select(func.count(InterventionAlert.id))
                .where(
                    and_(
                        InterventionAlert.student_id == student.id,
                        InterventionAlert.status.in_([AlertStatus.PENDING, AlertStatus.IN_PROGRESS])
                    )
                )
            )

            flagged.append({
                'student_id': str(student.id),
                'student_name': student.user.full_name,
                'student_code': student.student_code,
                'class_name': student.class_info.name if student.class_info else None,
                'active_alerts': alert_count.scalar() or 0
            })

        return flagged, total

    # ============== Teacher Approval Workflow ==============

    async def approve_alert(
        self,
        alert_id: UUID,
        approver_id: UUID,
        approval_notes: Optional[str] = None
    ) -> Optional[InterventionAlert]:
        """
        Teacher approves an intervention alert, triggering parent notification.

        Args:
            alert_id: ID of the alert to approve
            approver_id: ID of the teacher/user approving
            approval_notes: Optional notes from teacher

        Returns:
            Updated alert or None if not found
        """
        alert = await self.get_alert(alert_id)
        if not alert:
            return None

        # Extract alert data BEFORE commit to avoid lazy loading issues
        alert_title = alert.title
        alert_student_id = alert.student_id
        alert_subject = alert.subject
        alert_current_average = alert.current_average
        alert_weeks_failing = alert.weeks_failing
        alert_recommended_actions = alert.recommended_actions

        # Update alert status
        alert.status = AlertStatus.IN_PROGRESS
        approved_time = datetime.utcnow()
        alert.approved_at = approved_time
        alert.approved_by = approver_id

        if approval_notes:
            existing_notes = alert.resolution_notes or ""
            alert.resolution_notes = f"Teacher Approval Notes: {approval_notes}\n{existing_notes}".strip()

        await self.db.commit()

        # Send parent notification using extracted data
        await self._notify_parent_by_data(
            alert_id=alert_id,
            student_id=alert_student_id,
            alert_subject=alert_subject,
            alert_current_average=alert_current_average,
            alert_weeks_failing=alert_weeks_failing,
            alert_recommended_actions=alert_recommended_actions
        )

        # Log audit event
        try:
            from app.services.audit_service import AuditService
            from app.models.intervention import AuditAction

            audit_service = AuditService(self.db)
            await audit_service.create_audit_log(
                user_id=approver_id,
                action=AuditAction.UPDATE,
                entity_type="intervention_alert",
                entity_id=str(alert_id),
                entity_name=alert_title,
                description=f"Teacher approved intervention alert - parent notified",
                new_values={
                    "status": "in_progress",
                    "approved_at": approved_time.isoformat(),
                    "parent_notified": True
                }
            )
        except Exception as e:
            logger.warning(f"Failed to log audit for alert approval: {str(e)}")

        await self.db.refresh(alert)
        logger.info(f"Alert {alert_id} approved by user {approver_id}")
        return alert

    async def dismiss_alert(
        self,
        alert_id: UUID,
        resolver_id: UUID,
        reason: str
    ) -> Optional[InterventionAlert]:
        """
        Dismiss an intervention alert without notifying parents.

        Args:
            alert_id: ID of the alert to dismiss
            resolver_id: ID of the teacher/user dismissing
            reason: Reason for dismissal

        Returns:
            Updated alert or None if not found
        """
        alert = await self.get_alert(alert_id)
        if not alert:
            return None

        # Only allow dismissing pending alerts
        if alert.status not in [AlertStatus.PENDING, AlertStatus.IN_PROGRESS]:
            logger.warning(f"Attempted to dismiss non-pending alert {alert_id}")
            return None

        # Update alert status to resolved (dismissed)
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.utcnow()
        alert.resolved_by = resolver_id
        alert.resolution_notes = f"Dismissed by teacher: {reason}"

        await self.db.commit()

        # Log audit event
        try:
            from app.services.audit_service import AuditService
            from app.models.intervention import AuditAction

            audit_service = AuditService(self.db)
            await audit_service.create_audit_log(
                user_id=resolver_id,
                action=AuditAction.UPDATE,
                entity_type="intervention_alert",
                entity_id=str(alert.id),
                entity_name=alert.title,
                description=f"Teacher dismissed intervention alert - {reason}",
                new_values={
                    "status": "resolved",
                    "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                    "dismissal_reason": reason
                }
            )
        except Exception as e:
            logger.warning(f"Failed to log audit for alert dismissal: {str(e)}")

        await self.db.refresh(alert)
        logger.info(f"Alert {alert_id} dismissed by user {resolver_id}")
        return alert

    async def teacher_has_access_to_alert(
        self,
        teacher_id: UUID,
        alert_id: UUID
    ) -> bool:
        """
        Check if a teacher has access to a specific alert.

        A teacher has access if the alert's student is in one of their assigned classes.

        Args:
            teacher_id: TeacherProfile ID
            alert_id: Alert ID to check

        Returns:
            True if teacher has access, False otherwise
        """
        # Get the alert with student info
        alert = await self.get_alert(alert_id)
        if not alert:
            return False

        # Get class IDs assigned to teacher
        class_result = await self.db.execute(
            select(TeacherClassAssignment.class_id)
            .where(TeacherClassAssignment.teacher_id == teacher_id)
        )
        class_ids = [row[0] for row in class_result.fetchall()]

        if not class_ids:
            return False

        # Get student's class
        student_result = await self.db.execute(
            select(Student.class_id).where(Student.id == alert.student_id)
        )
        student_class = student_result.scalar_one_or_none()

        return student_class in class_ids

    async def get_teacher_alerts(
        self,
        teacher_id: UUID,
        status: Optional[AlertStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[InterventionAlert], int]:
        """
        Get alerts for students in classes assigned to a teacher.

        Args:
            teacher_id: TeacherProfile ID
            status: Optional status filter
            limit: Pagination limit
            offset: Pagination offset

        Returns:
            Tuple of (alerts list, total count)
        """
        # Get class IDs assigned to teacher
        class_result = await self.db.execute(
            select(TeacherClassAssignment.class_id)
            .where(TeacherClassAssignment.teacher_id == teacher_id)
        )
        class_ids = [row[0] for row in class_result.fetchall()]

        if not class_ids:
            return [], 0

        # Get student IDs in those classes
        student_result = await self.db.execute(
            select(Student.id).where(Student.class_id.in_(class_ids))
        )
        student_ids = [row[0] for row in student_result.fetchall()]

        if not student_ids:
            return [], 0

        # Build query - load student with user and class_info for name display
        query = select(InterventionAlert).options(
            selectinload(InterventionAlert.recipients),
            joinedload(InterventionAlert.student).joinedload(Student.user),
            joinedload(InterventionAlert.student).joinedload(Student.class_info)
        ).where(InterventionAlert.student_id.in_(student_ids))

        conditions = [InterventionAlert.student_id.in_(student_ids)]
        if status:
            conditions.append(InterventionAlert.status == status)

        query = query.where(and_(*conditions))

        # Count total
        count_query = select(func.count(InterventionAlert.id)).where(and_(*conditions))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Get results
        query = query.order_by(desc(InterventionAlert.created_at)).offset(offset).limit(limit)
        result = await self.db.execute(query)
        alerts = list(result.scalars().unique().all())

        return alerts, total

    # ============== Notification Helpers ==============

    async def _notify_teacher(
        self,
        alert: InterventionAlert,
        student: Student
    ) -> None:
        """
        Send email and in-app notification to teacher about new alert.

        Args:
            alert: The intervention alert
            student: The student the alert is for
        """
        try:
            # Find primary teacher assigned to student's class
            teacher_assignment = await self.db.execute(
                select(TeacherClassAssignment)
                .options(
                    joinedload(TeacherClassAssignment.teacher).joinedload(TeacherProfile.user)
                )
                .where(
                    and_(
                        TeacherClassAssignment.class_id == student.class_id,
                        TeacherClassAssignment.is_primary == True
                    )
                )
            )
            assignment = teacher_assignment.scalar_one_or_none()

            # Fallback: get any teacher assigned to the class
            if not assignment:
                teacher_assignment = await self.db.execute(
                    select(TeacherClassAssignment)
                    .options(
                        joinedload(TeacherClassAssignment.teacher).joinedload(TeacherProfile.user)
                    )
                    .where(TeacherClassAssignment.class_id == student.class_id)
                    .limit(1)
                )
                assignment = teacher_assignment.scalar_one_or_none()

            if not assignment or not assignment.teacher or not assignment.teacher.user:
                logger.warning(
                    f"No teacher found for student {student.student_code} class {student.class_id}"
                )
                return

            teacher_user = assignment.teacher.user

            # Add recipient record
            await self.add_alert_recipient(
                alert_id=alert.id,
                recipient_type=RecipientType.TEACHER,
                recipient_id=teacher_user.id,
                recipient_name=teacher_user.full_name,
                recipient_email=teacher_user.email
            )

            # Send email
            try:
                from app.services.email_service import EmailService

                email_service = EmailService()
                await email_service.send_teacher_intervention_alert(
                    teacher={
                        "email": teacher_user.email,
                        "full_name": teacher_user.full_name
                    },
                    student={
                        "full_name": student.user.full_name,
                        "student_code": student.student_code,
                        "class_name": student.class_info.name if student.class_info else "N/A"
                    },
                    alert={
                        "subject": alert.subject,
                        "current_average": alert.current_average,
                        "weeks_failing": alert.weeks_failing,
                        "recommended_actions": alert.recommended_actions
                    }
                )
                logger.info(f"Sent teacher notification email to {teacher_user.email}")
            except Exception as e:
                logger.error(f"Failed to send teacher email: {str(e)}")

            # Create in-app notification
            try:
                from app.services.notification_service import NotificationService
                from app.models.notification import NotificationType, NotificationPriority

                notification_service = NotificationService(self.db)
                await notification_service.create_notification(
                    user_id=teacher_user.id,
                    notification_type=NotificationType.ALERT,
                    priority=NotificationPriority.HIGH,
                    title="New Intervention Alert",
                    message=(
                        f"Student {student.user.full_name} ({student.student_code}) "
                        f"requires intervention review for {alert.subject or 'performance'}."
                    ),
                    entity_type="intervention_alert",
                    entity_id=str(alert.id),
                    action_url=f"/teacher/intervention/alerts/{alert.id}"
                )
                logger.info(f"Created in-app notification for teacher {teacher_user.id}")
            except Exception as e:
                logger.error(f"Failed to create in-app notification: {str(e)}")

        except Exception as e:
            logger.error(f"Error notifying teacher for alert {alert.id}: {str(e)}")

    async def _notify_teacher_by_class(
        self,
        alert: InterventionAlert,
        class_id: Optional[UUID],
        student_full_name: str
    ) -> None:
        """
        Send email and in-app notification to teacher about new alert.
        Uses class_id directly to avoid lazy loading issues.

        Args:
            alert: The intervention alert
            class_id: The student's class ID
            student_full_name: The student's full name
        """
        # Extract alert ID upfront to avoid lazy loading
        alert_id = alert.id

        if not class_id:
            logger.warning(f"No class_id for alert {alert_id}, cannot notify teacher")
            return

        try:
            # Find primary teacher assigned to student's class
            teacher_assignment = await self.db.execute(
                select(TeacherClassAssignment)
                .options(
                    joinedload(TeacherClassAssignment.teacher).joinedload(TeacherProfile.user)
                )
                .where(
                    and_(
                        TeacherClassAssignment.class_id == class_id,
                        TeacherClassAssignment.is_primary == True
                    )
                )
            )
            assignment = teacher_assignment.scalar_one_or_none()

            # Fallback: get any teacher assigned to the class
            if not assignment:
                teacher_assignment = await self.db.execute(
                    select(TeacherClassAssignment)
                    .options(
                        joinedload(TeacherClassAssignment.teacher).joinedload(TeacherProfile.user)
                    )
                    .where(TeacherClassAssignment.class_id == class_id)
                    .limit(1)
                )
                assignment = teacher_assignment.scalar_one_or_none()

            if not assignment or not assignment.teacher or not assignment.teacher.user:
                logger.warning(f"No teacher found for class {class_id}")
                return

            # Extract teacher info upfront to avoid lazy loading
            teacher_user_id = assignment.teacher.user.id
            teacher_full_name = assignment.teacher.user.full_name
            teacher_email = assignment.teacher.user.email

            # Add recipient record
            await self.add_alert_recipient(
                alert_id=alert_id,
                recipient_type=RecipientType.TEACHER,
                recipient_id=teacher_user_id,
                recipient_name=teacher_full_name,
                recipient_email=teacher_email
            )

            logger.info(f"Added teacher {teacher_email} as recipient for alert {alert_id}")

        except Exception as e:
            logger.error(f"Error notifying teacher for alert {alert_id}: {str(e)}")

    async def _notify_parent(self, alert: InterventionAlert) -> None:
        """
        Send email notification to parent after teacher approval.

        Args:
            alert: The approved intervention alert
        """
        # Extract alert attributes BEFORE any database operations to avoid lazy loading
        alert_id = alert.id
        alert_student_id = alert.student_id
        alert_subject = alert.subject
        alert_current_average = alert.current_average
        alert_weeks_failing = alert.weeks_failing
        alert_recommended_actions = alert.recommended_actions

        try:
            # Get student with user info
            student_result = await self.db.execute(
                select(Student)
                .options(joinedload(Student.user), joinedload(Student.class_info))
                .where(Student.id == alert_student_id)
            )
            student = student_result.scalar_one_or_none()

            if not student or not student.user:
                logger.warning(f"No student/user found for alert {alert_id}")
                return

            # Extract student info before any more queries
            student_full_name = student.user.full_name
            student_email = student.user.email
            student_code = student.student_code
            student_class_name = student.class_info.name if student.class_info else "N/A"

            # Use student's email (which is parent email per requirements)
            parent_email = student_email
            parent_name = student_full_name

            # Add parent recipient record
            await self.add_alert_recipient(
                alert_id=alert_id,
                recipient_type=RecipientType.PARENT,
                recipient_name=parent_name,
                recipient_email=parent_email
            )

            # Send email
            try:
                from app.services.email_service import EmailService

                email_service = EmailService()
                await email_service.send_parent_intervention_alert(
                    parent_email=parent_email,
                    student={
                        "full_name": student_full_name,
                        "student_code": student_code,
                        "class_name": student_class_name
                    },
                    alert={
                        "subject": alert_subject,
                        "current_average": alert_current_average,
                        "weeks_failing": alert_weeks_failing,
                        "recommended_actions": alert_recommended_actions
                    }
                )
                logger.info(f"Sent parent notification email to {parent_email}")
            except Exception as e:
                logger.error(f"Failed to send parent email: {str(e)}")

            # Mark recipient as notified
            recipient_result = await self.db.execute(
                select(AlertRecipient)
                .where(
                    and_(
                        AlertRecipient.alert_id == alert_id,
                        AlertRecipient.recipient_type == RecipientType.PARENT
                    )
                )
            )
            recipient = recipient_result.scalar_one_or_none()
            if recipient:
                await self.mark_recipient_notified(recipient.id, "email")

        except Exception as e:
            logger.error(f"Error notifying parent for alert {alert_id}: {str(e)}")

    async def _notify_parent_by_data(
        self,
        alert_id: UUID,
        student_id: UUID,
        alert_subject: Optional[str],
        alert_current_average: Optional[float],
        alert_weeks_failing: Optional[int],
        alert_recommended_actions: Optional[str]
    ) -> None:
        """
        Send email notification to parent using pre-extracted data.
        This version avoids lazy loading issues by accepting data directly.

        Args:
            alert_id: The alert ID
            student_id: The student ID
            alert_subject: The subject for the alert
            alert_current_average: Current average score
            alert_weeks_failing: Number of weeks failing
            alert_recommended_actions: Recommended actions text
        """
        try:
            # Get student with user info
            student_result = await self.db.execute(
                select(Student)
                .options(joinedload(Student.user), joinedload(Student.class_info))
                .where(Student.id == student_id)
            )
            student = student_result.scalar_one_or_none()

            if not student or not student.user:
                logger.warning(f"No student/user found for alert {alert_id}")
                return

            # Extract student info before any more queries
            student_full_name = student.user.full_name
            student_email = student.user.email
            student_code = student.student_code
            student_class_name = student.class_info.name if student.class_info else "N/A"

            # Use student's email (which is parent email per requirements)
            parent_email = student_email
            parent_name = student_full_name

            # Add parent recipient record
            await self.add_alert_recipient(
                alert_id=alert_id,
                recipient_type=RecipientType.PARENT,
                recipient_name=parent_name,
                recipient_email=parent_email
            )

            # Send email
            try:
                from app.services.email_service import EmailService

                email_service = EmailService()
                await email_service.send_parent_intervention_alert(
                    parent_email=parent_email,
                    student={
                        "full_name": student_full_name,
                        "student_code": student_code,
                        "class_name": student_class_name
                    },
                    alert={
                        "subject": alert_subject,
                        "current_average": alert_current_average,
                        "weeks_failing": alert_weeks_failing,
                        "recommended_actions": alert_recommended_actions
                    }
                )
                logger.info(f"Sent parent notification email to {parent_email}")
            except Exception as e:
                logger.error(f"Failed to send parent email: {str(e)}")

            # Mark recipient as notified
            recipient_result = await self.db.execute(
                select(AlertRecipient)
                .where(
                    and_(
                        AlertRecipient.alert_id == alert_id,
                        AlertRecipient.recipient_type == RecipientType.PARENT
                    )
                )
            )
            recipient = recipient_result.scalar_one_or_none()
            if recipient:
                await self.mark_recipient_notified(recipient.id, "email")

        except Exception as e:
            logger.error(f"Error notifying parent for alert {alert_id}: {str(e)}")
