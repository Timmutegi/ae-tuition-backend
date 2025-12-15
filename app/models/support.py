"""
Support system models for Phase 5: Supervisor Portal & Support System.
Includes attendance tracking, support sessions, homework records, and parent communications.
"""

from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Text, Boolean, Integer, Float, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum

from app.core.database import Base


class AttendanceStatus(enum.Enum):
    """Attendance status options."""
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"
    LEFT_EARLY = "left_early"


class AttendanceSource(enum.Enum):
    """How attendance was recorded."""
    MANUAL = "manual"
    TEST_SESSION = "test_session"
    SYSTEM = "system"


class SupportSessionType(enum.Enum):
    """Type of support session."""
    ACADEMIC = "academic"
    BEHAVIORAL = "behavioral"
    WELFARE = "welfare"
    COUNSELING = "counseling"
    PARENT_MEETING = "parent_meeting"
    OTHER = "other"


class HomeworkStatus(enum.Enum):
    """Homework completion status."""
    NOT_SUBMITTED = "not_submitted"
    INCOMPLETE = "incomplete"
    LATE = "late"
    COMPLETE = "complete"
    EXCUSED = "excused"


class CommunicationType(enum.Enum):
    """Type of parent communication."""
    EMAIL = "email"
    SMS = "sms"
    PHONE_CALL = "phone_call"
    IN_PERSON = "in_person"
    LETTER = "letter"


class AttendanceRecord(Base):
    """Student attendance tracking - auto-recorded from tests or manual entry."""
    __tablename__ = "attendance_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    status = Column(SQLEnum(AttendanceStatus), nullable=False, default=AttendanceStatus.PRESENT)
    source = Column(SQLEnum(AttendanceSource), nullable=False, default=AttendanceSource.MANUAL)

    # Optional references
    test_attempt_id = Column(UUID(as_uuid=True), ForeignKey("test_attempts.id", ondelete="SET NULL"), nullable=True)
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Additional info
    arrival_time = Column(DateTime(timezone=True), nullable=True)
    departure_time = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    student = relationship("Student", back_populates="attendance_records")
    recorder = relationship("User", foreign_keys=[recorded_by])

    def __repr__(self):
        return f"<AttendanceRecord(student_id='{self.student_id}', date='{self.date}', status='{self.status}')>"


class SupportSession(Base):
    """Support session logs for tracking student support interactions."""
    __tablename__ = "support_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    supervisor_id = Column(UUID(as_uuid=True), ForeignKey("supervisor_profiles.id", ondelete="SET NULL"), nullable=True)

    session_type = Column(SQLEnum(SupportSessionType), nullable=False)
    session_date = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, nullable=True)

    # Session details
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    objectives = Column(Text, nullable=True)
    outcomes = Column(Text, nullable=True)
    action_items = Column(Text, nullable=True)

    # Follow-up
    follow_up_required = Column(Boolean, default=False)
    follow_up_date = Column(Date, nullable=True)
    follow_up_notes = Column(Text, nullable=True)

    # Privacy
    is_confidential = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    student = relationship("Student", back_populates="support_sessions")
    supervisor = relationship("SupervisorProfile", backref="support_sessions")

    def __repr__(self):
        return f"<SupportSession(student_id='{self.student_id}', type='{self.session_type}', date='{self.session_date}')>"


class HomeworkRecord(Base):
    """Homework tracking - missing/incomplete homework records."""
    __tablename__ = "homework_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)

    # Assignment info
    subject = Column(String(100), nullable=False)
    assignment_title = Column(String(255), nullable=False)
    assigned_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)

    # Status tracking
    status = Column(SQLEnum(HomeworkStatus), nullable=False, default=HomeworkStatus.NOT_SUBMITTED)
    submitted_date = Column(Date, nullable=True)

    # Details
    description = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)  # Reason for missing/late
    notes = Column(Text, nullable=True)

    # Recorded by
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    student = relationship("Student", back_populates="homework_records")
    recorder = relationship("User", foreign_keys=[recorded_by])

    def __repr__(self):
        return f"<HomeworkRecord(student_id='{self.student_id}', subject='{self.subject}', status='{self.status}')>"


class CommunicationTemplate(Base):
    """Predefined templates for parent communications."""
    __tablename__ = "communication_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)  # e.g., 'attendance', 'academic', 'behavioral'
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)

    # Template variables (e.g., {{student_name}}, {{date}})
    variables = Column(JSONB, nullable=True)

    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<CommunicationTemplate(name='{self.name}', category='{self.category}')>"


class ParentCommunication(Base):
    """Log of communications sent to parents/guardians."""
    __tablename__ = "parent_communications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    sent_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Communication details
    communication_type = Column(SQLEnum(CommunicationType), nullable=False)
    template_id = Column(UUID(as_uuid=True), ForeignKey("communication_templates.id", ondelete="SET NULL"), nullable=True)

    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)

    # Recipient info
    recipient_name = Column(String(255), nullable=True)
    recipient_email = Column(String(255), nullable=True)
    recipient_phone = Column(String(50), nullable=True)

    # Status
    sent_at = Column(DateTime(timezone=True), default=func.now())
    is_delivered = Column(Boolean, default=False)
    delivery_status = Column(String(50), nullable=True)  # e.g., 'sent', 'delivered', 'failed', 'bounced'

    # Response tracking
    response_received = Column(Boolean, default=False)
    response_date = Column(DateTime(timezone=True), nullable=True)
    response_notes = Column(Text, nullable=True)

    # Related records
    related_attendance_id = Column(UUID(as_uuid=True), ForeignKey("attendance_records.id", ondelete="SET NULL"), nullable=True)
    related_homework_id = Column(UUID(as_uuid=True), ForeignKey("homework_records.id", ondelete="SET NULL"), nullable=True)
    related_session_id = Column(UUID(as_uuid=True), ForeignKey("support_sessions.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    student = relationship("Student", back_populates="parent_communications")
    sender = relationship("User", foreign_keys=[sent_by])
    template = relationship("CommunicationTemplate")

    def __repr__(self):
        return f"<ParentCommunication(student_id='{self.student_id}', type='{self.communication_type}', sent_at='{self.sent_at}')>"
