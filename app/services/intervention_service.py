"""
Intervention service for Phase 6: Advanced Analytics & Intervention System.
Handles intervention alerts, thresholds, weekly performance tracking, and analytics.
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from sqlalchemy import select, func, and_, or_, desc, asc
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intervention import (
    InterventionThreshold, InterventionAlert, AlertRecipient,
    WeeklyPerformance, AlertStatus, AlertPriority, RecipientType
)
from app.models.student import Student
from app.models.class_model import Class
from app.models.test import TestAttempt, TestResult, AttemptStatus
from app.models.support import AttendanceRecord, HomeworkRecord, AttendanceStatus, HomeworkStatus
from app.schemas.intervention import (
    InterventionThresholdCreate, InterventionThresholdUpdate,
    InterventionAlertCreate, InterventionAlertUpdate,
    StudentAnalytics, ClassAnalytics, DashboardStats
)


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

        # Get all active students
        result = await self.db.execute(
            select(Student)
            .options(joinedload(Student.class_rel))
            .where(Student.status == 'active')
        )
        students = list(result.scalars().unique().all())

        for student in students:
            alert = await self._check_student_threshold(student, threshold)
            if alert:
                alerts.append(alert)

        return alerts

    async def _check_student_threshold(
        self,
        student: Student,
        threshold: InterventionThreshold
    ) -> Optional[InterventionAlert]:
        """Check if a student triggers a threshold."""
        # Calculate date range for review period
        end_date = date.today()
        start_date = end_date - timedelta(weeks=threshold.weeks_to_review)

        # Get weekly performances
        result = await self.db.execute(
            select(WeeklyPerformance)
            .where(
                and_(
                    WeeklyPerformance.student_id == student.id,
                    WeeklyPerformance.week_start >= start_date,
                    WeeklyPerformance.week_end <= end_date
                )
            )
            .order_by(WeeklyPerformance.week_start)
        )
        performances = list(result.scalars().all())

        if not performances:
            return None

        # Check if subject-specific
        weeks_failing = 0
        weekly_scores = []

        for perf in performances:
            if threshold.subject:
                # Subject-specific check
                subject_scores = perf.subject_scores or {}
                subject_data = subject_scores.get(threshold.subject, {})
                avg = subject_data.get('average')
            else:
                # Overall average
                avg = perf.average_score

            if avg is not None:
                weekly_scores.append({
                    'week': perf.week_number,
                    'score': avg
                })
                if avg < threshold.min_score_percent:
                    weeks_failing += 1

        # Check if threshold is met
        if weeks_failing >= threshold.failures_required:
            # Check for existing pending alert
            existing = await self.db.execute(
                select(InterventionAlert)
                .where(
                    and_(
                        InterventionAlert.student_id == student.id,
                        InterventionAlert.threshold_id == threshold.id,
                        InterventionAlert.status.in_([AlertStatus.PENDING, AlertStatus.IN_PROGRESS])
                    )
                )
            )
            if existing.scalar_one_or_none():
                return None  # Already has active alert

            # Calculate averages
            recent_scores = [s['score'] for s in weekly_scores[-threshold.failures_required:] if s['score']]
            current_avg = sum(recent_scores) / len(recent_scores) if recent_scores else None

            # Create alert
            subject_text = threshold.subject or "overall performance"
            alert_data = InterventionAlertCreate(
                student_id=student.id,
                threshold_id=threshold.id,
                subject=threshold.subject,
                alert_type="performance_decline",
                priority=threshold.alert_priority,
                title=f"Performance Alert: {student.student_name}",
                description=f"Student's {subject_text} has fallen below {threshold.min_score_percent}% for {weeks_failing} out of the last {threshold.weeks_to_review} weeks.",
                recommended_actions="Schedule a meeting with the student and guardian. Review study habits and provide additional support.",
                current_average=current_avg,
                weeks_failing=weeks_failing,
                weekly_scores=weekly_scores
            )

            alert = await self.create_alert(alert_data)

            # Add recipients based on threshold settings
            if threshold.notify_parent:
                await self.add_alert_recipient(
                    alert_id=alert.id,
                    recipient_type=RecipientType.PARENT,
                    recipient_name=student.parent_name,
                    recipient_email=student.parent_email,
                    recipient_phone=student.parent_phone
                )

            if threshold.notify_supervisor and student.supervisor_id:
                await self.add_alert_recipient(
                    alert_id=alert.id,
                    recipient_type=RecipientType.SUPERVISOR,
                    recipient_id=student.supervisor_id
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
            .options(joinedload(Student.class_rel))
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
            student_name=student.student_name,
            student_code=student.student_code,
            class_name=student.class_rel.name if student.class_rel else None,
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
            .options(joinedload(Student.class_rel))
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
                'student_name': student.student_name,
                'student_code': student.student_code,
                'class_name': student.class_rel.name if student.class_rel else None,
                'active_alerts': alert_count.scalar() or 0
            })

        return flagged, total
