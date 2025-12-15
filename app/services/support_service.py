"""
Support service for Phase 5: Supervisor Portal & Support System.
Handles attendance, support sessions, homework tracking, and parent communications.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime, date, timedelta
from uuid import UUID
import re

from app.models.support import (
    AttendanceRecord, SupportSession, HomeworkRecord,
    CommunicationTemplate, ParentCommunication,
    AttendanceStatus, AttendanceSource, SupportSessionType,
    HomeworkStatus, CommunicationType
)
from app.models.student import Student
from app.models.supervisor import SupervisorProfile, SupervisorStudentAssignment
from app.models.user import User
from app.models.class_model import Class
from app.schemas.support import (
    AttendanceRecordCreate, AttendanceRecordUpdate, AttendanceBulkCreate,
    SupportSessionCreate, SupportSessionUpdate,
    HomeworkRecordCreate, HomeworkRecordUpdate, HomeworkBulkCreate,
    CommunicationTemplateCreate, CommunicationTemplateUpdate,
    ParentCommunicationCreate, ParentCommunicationFromTemplate,
    AttendanceSummary, HomeworkSummary, StudentOverview, SupervisorDashboardStats
)


class SupportService:
    """Service class for support system operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ========== Attendance Methods ==========

    async def create_attendance_record(
        self,
        data: AttendanceRecordCreate,
        recorded_by: UUID
    ) -> AttendanceRecord:
        """Create a single attendance record."""
        record = AttendanceRecord(
            student_id=data.student_id,
            date=data.date,
            status=AttendanceStatus(data.status.value),
            source=AttendanceSource.MANUAL,
            recorded_by=recorded_by,
            arrival_time=data.arrival_time,
            departure_time=data.departure_time,
            notes=data.notes
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def create_bulk_attendance(
        self,
        data: AttendanceBulkCreate,
        recorded_by: UUID
    ) -> List[AttendanceRecord]:
        """Create attendance records for multiple students."""
        records = []
        for student_id in data.student_ids:
            record = AttendanceRecord(
                student_id=student_id,
                date=data.date,
                status=AttendanceStatus(data.status.value),
                source=AttendanceSource.MANUAL,
                recorded_by=recorded_by,
                notes=data.notes
            )
            self.db.add(record)
            records.append(record)

        await self.db.commit()
        for record in records:
            await self.db.refresh(record)
        return records

    async def update_attendance_record(
        self,
        record_id: UUID,
        data: AttendanceRecordUpdate
    ) -> Optional[AttendanceRecord]:
        """Update an attendance record."""
        result = await self.db.execute(
            select(AttendanceRecord).where(AttendanceRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field == 'status' and value:
                value = AttendanceStatus(value.value)
            setattr(record, field, value)

        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def get_attendance_by_date(
        self,
        target_date: date,
        class_id: Optional[UUID] = None,
        supervisor_id: Optional[UUID] = None
    ) -> List[dict]:
        """Get attendance records for a specific date."""
        query = (
            select(AttendanceRecord, Student, User, Class)
            .join(Student, AttendanceRecord.student_id == Student.id)
            .join(User, Student.user_id == User.id)
            .outerjoin(Class, Student.class_id == Class.id)
            .where(AttendanceRecord.date == target_date)
        )

        if class_id:
            query = query.where(Student.class_id == class_id)

        if supervisor_id:
            query = query.join(
                SupervisorStudentAssignment,
                SupervisorStudentAssignment.student_id == Student.id
            ).where(SupervisorStudentAssignment.supervisor_id == supervisor_id)

        result = await self.db.execute(query.order_by(User.full_name))
        rows = result.all()

        return [
            {
                'id': str(record.id),
                'student_id': str(record.student_id),
                'date': str(record.date),
                'status': record.status.value,
                'source': record.source.value if record.source else None,
                'arrival_time': str(record.arrival_time) if record.arrival_time else None,
                'departure_time': str(record.departure_time) if record.departure_time else None,
                'notes': record.notes,
                'student_name': user.full_name or 'Unknown',
                'student_code': student.student_code,
                'class_name': cls.name if cls else None
            }
            for record, student, user, cls in rows
        ]

    async def get_attendance_summary(
        self,
        target_date: date,
        class_id: Optional[UUID] = None,
        supervisor_id: Optional[UUID] = None
    ) -> AttendanceSummary:
        """Get attendance summary for a date."""
        query = (
            select(
                func.count(AttendanceRecord.id).label('total'),
                func.count().filter(AttendanceRecord.status == AttendanceStatus.PRESENT).label('present'),
                func.count().filter(AttendanceRecord.status == AttendanceStatus.ABSENT).label('absent'),
                func.count().filter(AttendanceRecord.status == AttendanceStatus.LATE).label('late'),
                func.count().filter(AttendanceRecord.status == AttendanceStatus.EXCUSED).label('excused'),
                func.count().filter(AttendanceRecord.status == AttendanceStatus.LEFT_EARLY).label('left_early')
            )
            .select_from(AttendanceRecord)
            .join(Student, AttendanceRecord.student_id == Student.id)
            .where(AttendanceRecord.date == target_date)
        )

        if class_id:
            query = query.where(Student.class_id == class_id)

        if supervisor_id:
            query = query.join(
                SupervisorStudentAssignment,
                SupervisorStudentAssignment.student_id == Student.id
            ).where(SupervisorStudentAssignment.supervisor_id == supervisor_id)

        result = await self.db.execute(query)
        row = result.one()

        total = row.total or 0
        present = row.present or 0

        return AttendanceSummary(
            total_students=total,
            present=present,
            absent=row.absent or 0,
            late=row.late or 0,
            excused=row.excused or 0,
            left_early=row.left_early or 0,
            attendance_rate=round((present / total * 100) if total > 0 else 0, 2)
        )

    async def get_student_attendance_history(
        self,
        student_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[AttendanceRecord]:
        """Get attendance history for a student."""
        query = select(AttendanceRecord).where(AttendanceRecord.student_id == student_id)

        if start_date:
            query = query.where(AttendanceRecord.date >= start_date)
        if end_date:
            query = query.where(AttendanceRecord.date <= end_date)

        result = await self.db.execute(query.order_by(AttendanceRecord.date.desc()))
        return list(result.scalars().all())

    # ========== Support Session Methods ==========

    async def create_support_session(
        self,
        data: SupportSessionCreate,
        supervisor_id: UUID
    ) -> SupportSession:
        """Create a support session record."""
        session = SupportSession(
            student_id=data.student_id,
            supervisor_id=supervisor_id,
            session_type=SupportSessionType(data.session_type.value),
            session_date=data.session_date,
            duration_minutes=data.duration_minutes,
            title=data.title,
            description=data.description,
            objectives=data.objectives,
            outcomes=data.outcomes,
            action_items=data.action_items,
            follow_up_required=data.follow_up_required,
            follow_up_date=data.follow_up_date,
            follow_up_notes=data.follow_up_notes,
            is_confidential=data.is_confidential
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def update_support_session(
        self,
        session_id: UUID,
        data: SupportSessionUpdate
    ) -> Optional[SupportSession]:
        """Update a support session."""
        result = await self.db.execute(
            select(SupportSession).where(SupportSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field == 'session_type' and value:
                value = SupportSessionType(value.value)
            setattr(session, field, value)

        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_support_sessions(
        self,
        supervisor_id: Optional[UUID] = None,
        student_id: Optional[UUID] = None,
        session_type: Optional[SupportSessionType] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        follow_up_required: Optional[bool] = None
    ) -> List[dict]:
        """Get support sessions with filters."""
        query = (
            select(SupportSession, Student, User)
            .join(Student, SupportSession.student_id == Student.id)
            .join(User, Student.user_id == User.id)
        )

        if supervisor_id:
            query = query.where(SupportSession.supervisor_id == supervisor_id)
        if student_id:
            query = query.where(SupportSession.student_id == student_id)
        if session_type:
            query = query.where(SupportSession.session_type == session_type)
        if start_date:
            query = query.where(func.date(SupportSession.session_date) >= start_date)
        if end_date:
            query = query.where(func.date(SupportSession.session_date) <= end_date)
        if follow_up_required is not None:
            query = query.where(SupportSession.follow_up_required == follow_up_required)

        result = await self.db.execute(query.order_by(SupportSession.session_date.desc()))
        rows = result.all()

        return [
            {
                'id': str(session.id),
                'student_id': str(session.student_id),
                'supervisor_id': str(session.supervisor_id) if session.supervisor_id else None,
                'session_type': session.session_type.value,
                'session_date': session.session_date.isoformat() if session.session_date else None,
                'duration_minutes': session.duration_minutes,
                'title': session.title,
                'description': session.description,
                'objectives': session.objectives,
                'outcomes': session.outcomes,
                'action_items': session.action_items,
                'follow_up_required': session.follow_up_required,
                'follow_up_date': str(session.follow_up_date) if session.follow_up_date else None,
                'follow_up_notes': session.follow_up_notes,
                'is_confidential': session.is_confidential,
                'student_name': user.full_name or 'Unknown',
                'student_code': student.student_code
            }
            for session, student, user in rows
        ]

    async def get_pending_follow_ups(self, supervisor_id: UUID) -> List[dict]:
        """Get sessions that require follow-up."""
        today = date.today()
        query = (
            select(SupportSession, Student, User)
            .join(Student, SupportSession.student_id == Student.id)
            .join(User, Student.user_id == User.id)
            .where(
                and_(
                    SupportSession.supervisor_id == supervisor_id,
                    SupportSession.follow_up_required == True,
                    or_(
                        SupportSession.follow_up_date <= today,
                        SupportSession.follow_up_date.is_(None)
                    )
                )
            )
            .order_by(SupportSession.follow_up_date.asc().nullsfirst())
        )

        result = await self.db.execute(query)
        rows = result.all()

        return [
            {
                'id': str(session.id),
                'student_id': str(session.student_id),
                'supervisor_id': str(session.supervisor_id) if session.supervisor_id else None,
                'session_type': session.session_type.value,
                'session_date': session.session_date.isoformat() if session.session_date else None,
                'duration_minutes': session.duration_minutes,
                'title': session.title,
                'description': session.description,
                'objectives': session.objectives,
                'outcomes': session.outcomes,
                'action_items': session.action_items,
                'follow_up_required': session.follow_up_required,
                'follow_up_date': str(session.follow_up_date) if session.follow_up_date else None,
                'follow_up_notes': session.follow_up_notes,
                'is_confidential': session.is_confidential,
                'student_name': user.full_name or 'Unknown',
                'student_code': student.student_code
            }
            for session, student, user in rows
        ]

    # ========== Homework Methods ==========

    async def create_homework_record(
        self,
        data: HomeworkRecordCreate,
        recorded_by: UUID
    ) -> HomeworkRecord:
        """Create a homework record."""
        record = HomeworkRecord(
            student_id=data.student_id,
            subject=data.subject,
            assignment_title=data.assignment_title,
            assigned_date=data.assigned_date,
            due_date=data.due_date,
            status=HomeworkStatus(data.status.value),
            submitted_date=data.submitted_date,
            description=data.description,
            reason=data.reason,
            notes=data.notes,
            recorded_by=recorded_by
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def create_bulk_homework(
        self,
        data: HomeworkBulkCreate,
        recorded_by: UUID
    ) -> List[HomeworkRecord]:
        """Create homework records for multiple students."""
        records = []
        for student_id in data.student_ids:
            record = HomeworkRecord(
                student_id=student_id,
                subject=data.subject,
                assignment_title=data.assignment_title,
                assigned_date=data.assigned_date,
                due_date=data.due_date,
                status=HomeworkStatus.NOT_SUBMITTED,
                description=data.description,
                recorded_by=recorded_by
            )
            self.db.add(record)
            records.append(record)

        await self.db.commit()
        for record in records:
            await self.db.refresh(record)
        return records

    async def update_homework_record(
        self,
        record_id: UUID,
        data: HomeworkRecordUpdate
    ) -> Optional[HomeworkRecord]:
        """Update a homework record."""
        result = await self.db.execute(
            select(HomeworkRecord).where(HomeworkRecord.id == record_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field == 'status' and value:
                value = HomeworkStatus(value.value)
            setattr(record, field, value)

        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def get_homework_records(
        self,
        student_id: Optional[UUID] = None,
        class_id: Optional[UUID] = None,
        subject: Optional[str] = None,
        status: Optional[HomeworkStatus] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[dict]:
        """Get homework records with filters."""
        query = (
            select(HomeworkRecord, Student, User, Class)
            .join(Student, HomeworkRecord.student_id == Student.id)
            .join(User, Student.user_id == User.id)
            .outerjoin(Class, Student.class_id == Class.id)
        )

        if student_id:
            query = query.where(HomeworkRecord.student_id == student_id)
        if class_id:
            query = query.where(Student.class_id == class_id)
        if subject:
            query = query.where(HomeworkRecord.subject.ilike(f"%{subject}%"))
        if status:
            query = query.where(HomeworkRecord.status == status)
        if start_date:
            query = query.where(HomeworkRecord.due_date >= start_date)
        if end_date:
            query = query.where(HomeworkRecord.due_date <= end_date)

        result = await self.db.execute(query.order_by(HomeworkRecord.due_date.desc()))
        rows = result.all()

        return [
            {
                **record.__dict__,
                'student_name': user.full_name or 'Unknown',
                'student_code': student.student_code,
                'class_name': cls.name if cls else None
            }
            for record, student, user, cls in rows
        ]

    async def get_missing_homework(
        self,
        class_id: Optional[UUID] = None,
        supervisor_id: Optional[UUID] = None
    ) -> List[dict]:
        """Get all missing/incomplete homework."""
        query = (
            select(HomeworkRecord, Student, User, Class)
            .join(Student, HomeworkRecord.student_id == Student.id)
            .join(User, Student.user_id == User.id)
            .outerjoin(Class, Student.class_id == Class.id)
            .where(
                HomeworkRecord.status.in_([
                    HomeworkStatus.NOT_SUBMITTED,
                    HomeworkStatus.INCOMPLETE
                ])
            )
        )

        if class_id:
            query = query.where(Student.class_id == class_id)

        if supervisor_id:
            query = query.join(
                SupervisorStudentAssignment,
                SupervisorStudentAssignment.student_id == Student.id
            ).where(SupervisorStudentAssignment.supervisor_id == supervisor_id)

        result = await self.db.execute(query.order_by(HomeworkRecord.due_date.asc()))
        rows = result.all()

        return [
            {
                **record.__dict__,
                'student_name': user.full_name or 'Unknown',
                'student_code': student.student_code,
                'class_name': cls.name if cls else None
            }
            for record, student, user, cls in rows
        ]

    # ========== Communication Template Methods ==========

    async def create_template(
        self,
        data: CommunicationTemplateCreate,
        created_by: UUID
    ) -> CommunicationTemplate:
        """Create a communication template."""
        template = CommunicationTemplate(
            name=data.name,
            category=data.category,
            subject=data.subject,
            body=data.body,
            variables=data.variables,
            is_active=data.is_active,
            created_by=created_by
        )
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def get_templates(
        self,
        category: Optional[str] = None,
        is_active: bool = True
    ) -> List[CommunicationTemplate]:
        """Get communication templates."""
        query = select(CommunicationTemplate).where(
            CommunicationTemplate.is_active == is_active
        )

        if category:
            query = query.where(CommunicationTemplate.category == category)

        result = await self.db.execute(query.order_by(CommunicationTemplate.name))
        return list(result.scalars().all())

    async def update_template(
        self,
        template_id: UUID,
        data: CommunicationTemplateUpdate
    ) -> Optional[CommunicationTemplate]:
        """Update a communication template."""
        result = await self.db.execute(
            select(CommunicationTemplate).where(CommunicationTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(template, field, value)

        await self.db.commit()
        await self.db.refresh(template)
        return template

    # ========== Parent Communication Methods ==========

    async def create_communication(
        self,
        data: ParentCommunicationCreate,
        sent_by: UUID
    ) -> ParentCommunication:
        """Create a parent communication record."""
        communication = ParentCommunication(
            student_id=data.student_id,
            sent_by=sent_by,
            communication_type=CommunicationType(data.communication_type.value),
            template_id=data.template_id,
            subject=data.subject,
            body=data.body,
            recipient_name=data.recipient_name,
            recipient_email=data.recipient_email,
            recipient_phone=data.recipient_phone,
            related_attendance_id=data.related_attendance_id,
            related_homework_id=data.related_homework_id,
            related_session_id=data.related_session_id
        )
        self.db.add(communication)
        await self.db.commit()
        await self.db.refresh(communication)
        return communication

    async def create_communication_from_template(
        self,
        data: ParentCommunicationFromTemplate,
        sent_by: UUID
    ) -> ParentCommunication:
        """Create a communication using a template."""
        # Get template
        result = await self.db.execute(
            select(CommunicationTemplate).where(CommunicationTemplate.id == data.template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise ValueError("Template not found")

        # Get student info for variable substitution
        student_result = await self.db.execute(
            select(Student, User)
            .join(User, Student.user_id == User.id)
            .where(Student.id == data.student_id)
        )
        student_row = student_result.one_or_none()
        if not student_row:
            raise ValueError("Student not found")

        student, user = student_row

        # Prepare variable values
        # Parse full_name into first and last name for template variables
        full_name = user.full_name or 'Student'
        name_parts = full_name.split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        variables = {
            'student_name': full_name,
            'student_first_name': first_name,
            'student_last_name': last_name,
            'date': date.today().strftime('%B %d, %Y'),
            **(data.variable_values or {})
        }

        # Substitute variables in subject and body
        subject = self._substitute_variables(template.subject, variables)
        body = self._substitute_variables(template.body, variables)

        communication = ParentCommunication(
            student_id=data.student_id,
            sent_by=sent_by,
            communication_type=CommunicationType(data.communication_type.value),
            template_id=data.template_id,
            subject=subject,
            body=body,
            recipient_name=data.recipient_name,
            recipient_email=data.recipient_email,
            recipient_phone=data.recipient_phone,
            related_attendance_id=data.related_attendance_id,
            related_homework_id=data.related_homework_id,
            related_session_id=data.related_session_id
        )
        self.db.add(communication)
        await self.db.commit()
        await self.db.refresh(communication)
        return communication

    def _substitute_variables(self, text: str, variables: dict) -> str:
        """Replace {{variable}} placeholders with values."""
        for key, value in variables.items():
            text = text.replace(f"{{{{{key}}}}}", str(value))
        return text

    async def get_communications(
        self,
        student_id: Optional[UUID] = None,
        sent_by: Optional[UUID] = None,
        communication_type: Optional[CommunicationType] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[dict]:
        """Get parent communications with filters."""
        query = (
            select(ParentCommunication, Student, User)
            .join(Student, ParentCommunication.student_id == Student.id)
            .join(User, Student.user_id == User.id)
        )

        if student_id:
            query = query.where(ParentCommunication.student_id == student_id)
        if sent_by:
            query = query.where(ParentCommunication.sent_by == sent_by)
        if communication_type:
            query = query.where(ParentCommunication.communication_type == communication_type)
        if start_date:
            query = query.where(func.date(ParentCommunication.sent_at) >= start_date)
        if end_date:
            query = query.where(func.date(ParentCommunication.sent_at) <= end_date)

        result = await self.db.execute(query.order_by(ParentCommunication.sent_at.desc()))
        rows = result.all()

        return [
            {
                **comm.__dict__,
                'student_name': user.full_name or 'Unknown',
                'student_code': student.student_code
            }
            for comm, student, user in rows
        ]

    # ========== Student Overview Methods ==========

    async def get_student_overview(self, student_id: UUID) -> Optional[StudentOverview]:
        """Get comprehensive overview of a student."""
        # Get student info
        student_result = await self.db.execute(
            select(Student, User, Class)
            .join(User, Student.user_id == User.id)
            .outerjoin(Class, Student.class_id == Class.id)
            .where(Student.id == student_id)
        )
        student_row = student_result.one_or_none()
        if not student_row:
            return None

        student, user, cls = student_row

        # Calculate attendance stats (last 30 days)
        thirty_days_ago = date.today() - timedelta(days=30)
        attendance_result = await self.db.execute(
            select(
                func.count(AttendanceRecord.id).label('total'),
                func.count().filter(AttendanceRecord.status == AttendanceStatus.PRESENT).label('present'),
                func.count().filter(AttendanceRecord.status == AttendanceStatus.ABSENT).label('absent'),
                func.count().filter(AttendanceRecord.status == AttendanceStatus.LATE).label('late')
            )
            .where(
                and_(
                    AttendanceRecord.student_id == student_id,
                    AttendanceRecord.date >= thirty_days_ago
                )
            )
        )
        att_row = attendance_result.one()

        # Calculate homework stats
        homework_result = await self.db.execute(
            select(
                func.count(HomeworkRecord.id).label('total'),
                func.count().filter(HomeworkRecord.status == HomeworkStatus.COMPLETE).label('complete'),
                func.count().filter(HomeworkRecord.status == HomeworkStatus.NOT_SUBMITTED).label('missing'),
                func.count().filter(HomeworkRecord.status == HomeworkStatus.LATE).label('late')
            )
            .where(HomeworkRecord.student_id == student_id)
        )
        hw_row = homework_result.one()

        # Get recent support sessions
        sessions_result = await self.db.execute(
            select(SupportSession)
            .where(SupportSession.student_id == student_id)
            .order_by(SupportSession.session_date.desc())
            .limit(5)
        )
        recent_sessions = list(sessions_result.scalars().all())

        # Get recent communications
        comms_result = await self.db.execute(
            select(ParentCommunication)
            .where(ParentCommunication.student_id == student_id)
            .order_by(ParentCommunication.sent_at.desc())
            .limit(5)
        )
        recent_comms = list(comms_result.scalars().all())

        # Determine if attention is needed
        attention_reasons = []
        requires_attention = False

        att_total = att_row.total or 0
        att_present = att_row.present or 0
        attendance_rate = (att_present / att_total * 100) if att_total > 0 else 100

        if attendance_rate < 80:
            attention_reasons.append(f"Low attendance rate: {attendance_rate:.1f}%")
            requires_attention = True

        hw_total = hw_row.total or 0
        hw_complete = hw_row.complete or 0
        hw_missing = hw_row.missing or 0
        homework_rate = (hw_complete / hw_total * 100) if hw_total > 0 else 100

        if hw_missing > 3:
            attention_reasons.append(f"{hw_missing} missing homework assignments")
            requires_attention = True

        return StudentOverview(
            student_id=student_id,
            student_name=user.full_name or 'Unknown',
            student_code=student.student_code,
            class_name=cls.name if cls else None,
            year_group=student.year_group,
            attendance_rate=round(attendance_rate, 2),
            days_present=att_present,
            days_absent=att_row.absent or 0,
            days_late=att_row.late or 0,
            homework_completion_rate=round(homework_rate, 2),
            missing_assignments=hw_missing,
            late_assignments=hw_row.late or 0,
            total_support_sessions=len(recent_sessions),
            recent_sessions=[],  # Would need to convert to response objects
            recent_communications=[],  # Would need to convert to response objects
            requires_attention=requires_attention,
            attention_reasons=attention_reasons
        )

    async def get_supervisor_dashboard_stats(self, supervisor_id: UUID) -> SupervisorDashboardStats:
        """Get dashboard statistics for a supervisor."""
        today = date.today()
        week_ago = today - timedelta(days=7)

        # Get assigned students count
        students_result = await self.db.execute(
            select(func.count(SupervisorStudentAssignment.id))
            .where(SupervisorStudentAssignment.supervisor_id == supervisor_id)
        )
        total_students = students_result.scalar() or 0

        # Get today's attendance
        attendance_result = await self.db.execute(
            select(
                func.count().filter(AttendanceRecord.status == AttendanceStatus.PRESENT).label('present'),
                func.count().filter(AttendanceRecord.status == AttendanceStatus.ABSENT).label('absent')
            )
            .select_from(AttendanceRecord)
            .join(SupervisorStudentAssignment, SupervisorStudentAssignment.student_id == AttendanceRecord.student_id)
            .where(
                and_(
                    SupervisorStudentAssignment.supervisor_id == supervisor_id,
                    AttendanceRecord.date == today
                )
            )
        )
        att_row = attendance_result.one()

        # Get pending follow-ups count
        followups_result = await self.db.execute(
            select(func.count(SupportSession.id))
            .where(
                and_(
                    SupportSession.supervisor_id == supervisor_id,
                    SupportSession.follow_up_required == True,
                    or_(
                        SupportSession.follow_up_date <= today,
                        SupportSession.follow_up_date.is_(None)
                    )
                )
            )
        )
        pending_followups = followups_result.scalar() or 0

        # Get missing homework count
        homework_result = await self.db.execute(
            select(func.count(HomeworkRecord.id))
            .select_from(HomeworkRecord)
            .join(SupervisorStudentAssignment, SupervisorStudentAssignment.student_id == HomeworkRecord.student_id)
            .where(
                and_(
                    SupervisorStudentAssignment.supervisor_id == supervisor_id,
                    HomeworkRecord.status.in_([HomeworkStatus.NOT_SUBMITTED, HomeworkStatus.INCOMPLETE])
                )
            )
        )
        missing_homework = homework_result.scalar() or 0

        # Get communications sent this week
        comms_result = await self.db.execute(
            select(func.count(ParentCommunication.id))
            .where(
                and_(
                    ParentCommunication.sent_by == supervisor_id,
                    func.date(ParentCommunication.sent_at) >= week_ago
                )
            )
        )
        comms_this_week = comms_result.scalar() or 0

        # Get support sessions this week
        sessions_result = await self.db.execute(
            select(func.count(SupportSession.id))
            .where(
                and_(
                    SupportSession.supervisor_id == supervisor_id,
                    func.date(SupportSession.session_date) >= week_ago
                )
            )
        )
        sessions_this_week = sessions_result.scalar() or 0

        return SupervisorDashboardStats(
            total_assigned_students=total_students,
            students_present_today=att_row.present or 0,
            students_absent_today=att_row.absent or 0,
            pending_follow_ups=pending_followups,
            missing_homework_count=missing_homework,
            communications_sent_this_week=comms_this_week,
            support_sessions_this_week=sessions_this_week
        )

    async def get_assigned_students(self, supervisor_id: UUID) -> List[dict]:
        """Get list of students assigned to a supervisor."""
        query = (
            select(Student, User, Class, SupervisorStudentAssignment)
            .join(SupervisorStudentAssignment, SupervisorStudentAssignment.student_id == Student.id)
            .join(User, Student.user_id == User.id)
            .outerjoin(Class, Student.class_id == Class.id)
            .where(SupervisorStudentAssignment.supervisor_id == supervisor_id)
            .order_by(User.full_name)
        )

        result = await self.db.execute(query)
        rows = result.all()

        return [
            {
                'student_id': student.id,
                'student_name': user.full_name or 'Unknown',
                'student_code': student.student_code,
                'class_name': cls.name if cls else None,
                'year_group': student.year_group,
                'assigned_at': assignment.assigned_at
            }
            for student, user, cls, assignment in rows
        ]
