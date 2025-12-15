"""
Pydantic schemas for the support system (Phase 5).
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from uuid import UUID
from enum import Enum


# Enums matching database enums
class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"
    LEFT_EARLY = "left_early"


class AttendanceSource(str, Enum):
    MANUAL = "manual"
    TEST_SESSION = "test_session"
    SYSTEM = "system"


class SupportSessionType(str, Enum):
    ACADEMIC = "academic"
    BEHAVIORAL = "behavioral"
    WELFARE = "welfare"
    COUNSELING = "counseling"
    PARENT_MEETING = "parent_meeting"
    OTHER = "other"


class HomeworkStatus(str, Enum):
    NOT_SUBMITTED = "not_submitted"
    INCOMPLETE = "incomplete"
    LATE = "late"
    COMPLETE = "complete"
    EXCUSED = "excused"


class CommunicationType(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    PHONE_CALL = "phone_call"
    IN_PERSON = "in_person"
    LETTER = "letter"


# ========== Attendance Schemas ==========

class AttendanceRecordBase(BaseModel):
    student_id: UUID
    date: date
    status: AttendanceStatus = AttendanceStatus.PRESENT
    arrival_time: Optional[datetime] = None
    departure_time: Optional[datetime] = None
    notes: Optional[str] = None


class AttendanceRecordCreate(AttendanceRecordBase):
    pass


class AttendanceRecordUpdate(BaseModel):
    status: Optional[AttendanceStatus] = None
    arrival_time: Optional[datetime] = None
    departure_time: Optional[datetime] = None
    notes: Optional[str] = None


class AttendanceBulkCreate(BaseModel):
    """Bulk create attendance records for multiple students."""
    date: date
    student_ids: List[UUID]
    status: AttendanceStatus = AttendanceStatus.PRESENT
    notes: Optional[str] = None


class AttendanceRecordResponse(AttendanceRecordBase):
    id: UUID
    source: AttendanceSource
    recorded_by: Optional[UUID] = None
    test_attempt_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    # Populated fields
    student_name: Optional[str] = None
    student_code: Optional[str] = None
    class_name: Optional[str] = None

    class Config:
        from_attributes = True


class AttendanceSummary(BaseModel):
    """Summary statistics for attendance."""
    total_students: int
    present: int
    absent: int
    late: int
    excused: int
    left_early: int
    attendance_rate: float


class AttendanceReportRequest(BaseModel):
    """Request for attendance report generation."""
    start_date: date
    end_date: date
    student_ids: Optional[List[UUID]] = None
    class_id: Optional[UUID] = None
    format: str = "csv"  # csv, pdf, excel


# ========== Support Session Schemas ==========

class SupportSessionBase(BaseModel):
    student_id: UUID
    session_type: SupportSessionType
    session_date: datetime
    duration_minutes: Optional[int] = None
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    objectives: Optional[str] = None
    outcomes: Optional[str] = None
    action_items: Optional[str] = None
    follow_up_required: bool = False
    follow_up_date: Optional[date] = None
    follow_up_notes: Optional[str] = None
    is_confidential: bool = False


class SupportSessionCreate(SupportSessionBase):
    pass


class SupportSessionUpdate(BaseModel):
    session_type: Optional[SupportSessionType] = None
    session_date: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    objectives: Optional[str] = None
    outcomes: Optional[str] = None
    action_items: Optional[str] = None
    follow_up_required: Optional[bool] = None
    follow_up_date: Optional[date] = None
    follow_up_notes: Optional[str] = None
    is_confidential: Optional[bool] = None


class SupportSessionResponse(SupportSessionBase):
    id: UUID
    supervisor_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    # Populated fields
    student_name: Optional[str] = None
    student_code: Optional[str] = None
    supervisor_name: Optional[str] = None

    class Config:
        from_attributes = True


# ========== Homework Schemas ==========

class HomeworkRecordBase(BaseModel):
    student_id: UUID
    subject: str = Field(..., min_length=1, max_length=100)
    assignment_title: str = Field(..., min_length=1, max_length=255)
    assigned_date: date
    due_date: date
    status: HomeworkStatus = HomeworkStatus.NOT_SUBMITTED
    submitted_date: Optional[date] = None
    description: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = None


class HomeworkRecordCreate(HomeworkRecordBase):
    pass


class HomeworkRecordUpdate(BaseModel):
    status: Optional[HomeworkStatus] = None
    submitted_date: Optional[date] = None
    reason: Optional[str] = None
    notes: Optional[str] = None


class HomeworkBulkCreate(BaseModel):
    """Create homework record for multiple students at once."""
    student_ids: List[UUID]
    subject: str
    assignment_title: str
    assigned_date: date
    due_date: date
    description: Optional[str] = None


class HomeworkRecordResponse(HomeworkRecordBase):
    id: UUID
    recorded_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    # Populated fields
    student_name: Optional[str] = None
    student_code: Optional[str] = None
    class_name: Optional[str] = None

    class Config:
        from_attributes = True


class HomeworkSummary(BaseModel):
    """Summary of homework status for a student."""
    student_id: UUID
    student_name: str
    total_assignments: int
    completed: int
    incomplete: int
    not_submitted: int
    late: int
    completion_rate: float


# ========== Communication Template Schemas ==========

class CommunicationTemplateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=50)
    subject: str = Field(..., min_length=1, max_length=255)
    body: str
    variables: Optional[dict] = None
    is_active: bool = True


class CommunicationTemplateCreate(CommunicationTemplateBase):
    pass


class CommunicationTemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    variables: Optional[dict] = None
    is_active: Optional[bool] = None


class CommunicationTemplateResponse(CommunicationTemplateBase):
    id: UUID
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ========== Parent Communication Schemas ==========

class ParentCommunicationBase(BaseModel):
    student_id: UUID
    communication_type: CommunicationType
    subject: str = Field(..., min_length=1, max_length=255)
    body: str
    recipient_name: Optional[str] = None
    recipient_email: Optional[str] = None
    recipient_phone: Optional[str] = None


class ParentCommunicationCreate(ParentCommunicationBase):
    template_id: Optional[UUID] = None
    related_attendance_id: Optional[UUID] = None
    related_homework_id: Optional[UUID] = None
    related_session_id: Optional[UUID] = None


class ParentCommunicationFromTemplate(BaseModel):
    """Create communication using a template."""
    student_id: UUID
    template_id: UUID
    communication_type: CommunicationType
    recipient_name: Optional[str] = None
    recipient_email: Optional[str] = None
    recipient_phone: Optional[str] = None
    variable_values: Optional[dict] = None  # Values to fill in template variables
    related_attendance_id: Optional[UUID] = None
    related_homework_id: Optional[UUID] = None
    related_session_id: Optional[UUID] = None


class ParentCommunicationUpdate(BaseModel):
    is_delivered: Optional[bool] = None
    delivery_status: Optional[str] = None
    response_received: Optional[bool] = None
    response_date: Optional[datetime] = None
    response_notes: Optional[str] = None


class ParentCommunicationResponse(ParentCommunicationBase):
    id: UUID
    sent_by: Optional[UUID] = None
    template_id: Optional[UUID] = None
    sent_at: datetime
    is_delivered: bool
    delivery_status: Optional[str] = None
    response_received: bool
    response_date: Optional[datetime] = None
    response_notes: Optional[str] = None
    related_attendance_id: Optional[UUID] = None
    related_homework_id: Optional[UUID] = None
    related_session_id: Optional[UUID] = None

    # Populated fields
    student_name: Optional[str] = None
    student_code: Optional[str] = None
    sender_name: Optional[str] = None
    template_name: Optional[str] = None

    class Config:
        from_attributes = True


# ========== Student Overview Schemas ==========

class StudentOverview(BaseModel):
    """Comprehensive overview of a student for supervisor."""
    student_id: UUID
    student_name: str
    student_code: Optional[str] = None
    class_name: Optional[str] = None
    year_group: int

    # Attendance summary
    attendance_rate: float
    days_present: int
    days_absent: int
    days_late: int

    # Homework summary
    homework_completion_rate: float
    missing_assignments: int
    late_assignments: int

    # Support sessions
    total_support_sessions: int
    recent_sessions: List[SupportSessionResponse]

    # Recent communications
    recent_communications: List[ParentCommunicationResponse]

    # Alerts/flags
    requires_attention: bool
    attention_reasons: List[str]


class SupervisorDashboardStats(BaseModel):
    """Dashboard statistics for supervisor."""
    total_assigned_students: int
    students_present_today: int
    students_absent_today: int
    pending_follow_ups: int
    missing_homework_count: int
    communications_sent_this_week: int
    support_sessions_this_week: int
