"""
Intervention and Analytics models for Phase 6: Advanced Analytics & Intervention System.
Includes intervention alerts, thresholds, reports, and audit logging.
"""

from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Text, Boolean, Integer, Float, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum

from app.core.database import Base


class AlertStatus(enum.Enum):
    """Status of an intervention alert."""
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class AlertPriority(enum.Enum):
    """Priority level for alerts."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecipientType(enum.Enum):
    """Type of alert recipient."""
    PARENT = "parent"
    TEACHER = "teacher"
    SUPERVISOR = "supervisor"
    ADMIN = "admin"


class ReportType(enum.Enum):
    """Type of generated report."""
    STUDENT_PROGRESS = "student_progress"
    CLASS_PERFORMANCE = "class_performance"
    ATTENDANCE_SUMMARY = "attendance_summary"
    INTERVENTION_SUMMARY = "intervention_summary"
    TEACHER_ACTIVITY = "teacher_activity"
    CUSTOM = "custom"


class ReportFormat(enum.Enum):
    """Output format for reports."""
    PDF = "pdf"
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"


class AuditAction(enum.Enum):
    """Type of audited action."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    VIEW = "view"
    LOGIN = "login"
    LOGOUT = "logout"
    EXPORT = "export"
    ASSIGN = "assign"
    SUBMIT = "submit"
    GRADE = "grade"


class InterventionThreshold(Base):
    """Configurable thresholds for triggering intervention alerts."""
    __tablename__ = "intervention_thresholds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Threshold parameters
    subject = Column(String(100), nullable=True)  # Null means all subjects
    min_score_percent = Column(Float, nullable=False, default=50.0)  # Below this triggers alert
    max_score_percent = Column(Float, nullable=False, default=60.0)  # Upper bound of concern range
    weeks_to_review = Column(Integer, nullable=False, default=5)  # Review window
    failures_required = Column(Integer, nullable=False, default=3)  # Failures within window to trigger

    # Alert configuration
    alert_priority = Column(SQLEnum(AlertPriority), default=AlertPriority.MEDIUM)
    notify_parent = Column(Boolean, default=True)
    notify_teacher = Column(Boolean, default=True)
    notify_supervisor = Column(Boolean, default=True)

    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    alerts = relationship("InterventionAlert", back_populates="threshold")

    def __repr__(self):
        return f"<InterventionThreshold(name='{self.name}', min_score={self.min_score_percent}%)>"


class InterventionAlert(Base):
    """Performance decline alerts for students requiring intervention."""
    __tablename__ = "intervention_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    threshold_id = Column(UUID(as_uuid=True), ForeignKey("intervention_thresholds.id", ondelete="SET NULL"), nullable=True)

    # Alert details
    subject = Column(String(100), nullable=True)  # Specific subject or null for overall
    alert_type = Column(String(50), nullable=False)  # e.g., 'performance_decline', 'attendance', 'homework'
    priority = Column(SQLEnum(AlertPriority), nullable=False, default=AlertPriority.MEDIUM)
    status = Column(SQLEnum(AlertStatus), nullable=False, default=AlertStatus.PENDING)

    # Performance data
    current_average = Column(Float, nullable=True)
    previous_average = Column(Float, nullable=True)
    weeks_failing = Column(Integer, nullable=True)
    weekly_scores = Column(JSONB, nullable=True)  # Array of weekly scores

    # Alert message
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    recommended_actions = Column(Text, nullable=True)

    # Resolution
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Teacher Approval (for parent notification workflow)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    student = relationship("Student", backref="intervention_alerts")
    threshold = relationship("InterventionThreshold", back_populates="alerts")
    resolver = relationship("User", foreign_keys=[resolved_by])
    approver = relationship("User", foreign_keys=[approved_by])
    recipients = relationship("AlertRecipient", back_populates="alert", cascade="all, delete-orphan")

    @property
    def student_name(self) -> str:
        """Get student's full name from the user relationship."""
        if self.student and self.student.user:
            return self.student.user.full_name
        return "Unknown Student"

    @property
    def student_code(self) -> str:
        """Get student's code."""
        if self.student:
            return self.student.student_code or ""
        return ""

    @property
    def class_name(self) -> str:
        """Get student's class name."""
        if self.student and self.student.class_info:
            return self.student.class_info.name
        return ""

    def __repr__(self):
        return f"<InterventionAlert(student_id='{self.student_id}', type='{self.alert_type}', status='{self.status}')>"


class AlertRecipient(Base):
    """Recipients of intervention alerts and their notification status."""
    __tablename__ = "alert_recipients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id = Column(UUID(as_uuid=True), ForeignKey("intervention_alerts.id", ondelete="CASCADE"), nullable=False)

    recipient_type = Column(SQLEnum(RecipientType), nullable=False)
    recipient_id = Column(UUID(as_uuid=True), nullable=True)  # User ID if applicable
    recipient_name = Column(String(255), nullable=True)
    recipient_email = Column(String(255), nullable=True)
    recipient_phone = Column(String(50), nullable=True)

    # Notification status
    notified_at = Column(DateTime(timezone=True), nullable=True)
    notification_method = Column(String(50), nullable=True)  # email, sms, in_app
    is_delivered = Column(Boolean, default=False)
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    alert = relationship("InterventionAlert", back_populates="recipients")

    def __repr__(self):
        return f"<AlertRecipient(alert_id='{self.alert_id}', type='{self.recipient_type}')>"


class ReportConfiguration(Base):
    """Saved report configurations for generating custom reports."""
    __tablename__ = "report_configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    report_type = Column(SQLEnum(ReportType), nullable=False)

    # Filter parameters
    filters = Column(JSONB, nullable=True)  # class_ids, student_ids, date_range, subjects, etc.

    # Column/field selection
    columns = Column(JSONB, nullable=True)  # Which fields to include

    # Grouping and sorting
    group_by = Column(ARRAY(String), nullable=True)
    sort_by = Column(ARRAY(String), nullable=True)

    # Scheduling (optional)
    is_scheduled = Column(Boolean, default=False)
    schedule_cron = Column(String(50), nullable=True)  # Cron expression
    recipients = Column(JSONB, nullable=True)  # Email recipients for scheduled reports

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_public = Column(Boolean, default=False)  # Shared with other admins

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    generated_reports = relationship("GeneratedReport", back_populates="configuration")

    def __repr__(self):
        return f"<ReportConfiguration(name='{self.name}', type='{self.report_type}')>"


class GeneratedReport(Base):
    """Archive of generated reports with file storage links."""
    __tablename__ = "generated_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    configuration_id = Column(UUID(as_uuid=True), ForeignKey("report_configurations.id", ondelete="SET NULL"), nullable=True)

    name = Column(String(255), nullable=False)
    report_type = Column(SQLEnum(ReportType), nullable=False)
    format = Column(SQLEnum(ReportFormat), nullable=False)

    # File storage
    file_path = Column(String(500), nullable=True)  # S3 key or local path
    file_url = Column(String(500), nullable=True)  # Presigned URL or CDN URL
    file_size_bytes = Column(Integer, nullable=True)

    # Generation details
    parameters = Column(JSONB, nullable=True)  # Parameters used to generate
    row_count = Column(Integer, nullable=True)  # Number of records in report

    # Status
    is_ready = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    generated_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    configuration = relationship("ReportConfiguration", back_populates="generated_reports")
    generator = relationship("User", foreign_keys=[generated_by])

    def __repr__(self):
        return f"<GeneratedReport(name='{self.name}', format='{self.format}')>"


class AuditLog(Base):
    """Comprehensive audit trail for all system activities."""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Who
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_email = Column(String(255), nullable=True)  # Stored for historical reference
    user_role = Column(String(50), nullable=True)

    # What
    action = Column(SQLEnum(AuditAction), nullable=False)
    entity_type = Column(String(100), nullable=False)  # e.g., 'student', 'test', 'question'
    entity_id = Column(String(100), nullable=True)  # UUID as string
    entity_name = Column(String(255), nullable=True)  # Human-readable identifier

    # Details
    description = Column(Text, nullable=True)
    old_values = Column(JSONB, nullable=True)  # Previous state for updates
    new_values = Column(JSONB, nullable=True)  # New state for creates/updates

    # Context
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    session_id = Column(String(100), nullable=True)

    # Timing
    timestamp = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    duration_ms = Column(Integer, nullable=True)  # For tracking slow operations

    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<AuditLog(user='{self.user_email}', action='{self.action}', entity='{self.entity_type}')>"


class WeeklyPerformance(Base):
    """Aggregated weekly performance data for intervention analysis."""
    __tablename__ = "weekly_performance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)

    # Time period
    week_start = Column(Date, nullable=False)
    week_end = Column(Date, nullable=False)
    week_number = Column(Integer, nullable=False)  # Week of year
    year = Column(Integer, nullable=False)

    # Performance metrics (overall)
    tests_taken = Column(Integer, default=0)
    average_score = Column(Float, nullable=True)
    highest_score = Column(Float, nullable=True)
    lowest_score = Column(Float, nullable=True)
    total_time_minutes = Column(Integer, default=0)

    # Subject-wise breakdown (stored as JSON)
    subject_scores = Column(JSONB, nullable=True)  # {subject: {avg, count, tests}}

    # Attendance metrics
    days_present = Column(Integer, default=0)
    days_absent = Column(Integer, default=0)
    days_late = Column(Integer, default=0)

    # Homework metrics
    homework_completed = Column(Integer, default=0)
    homework_missing = Column(Integer, default=0)

    # Comparison
    previous_week_average = Column(Float, nullable=True)
    change_percent = Column(Float, nullable=True)  # Week-over-week change

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    student = relationship("Student", backref="weekly_performances")

    def __repr__(self):
        return f"<WeeklyPerformance(student_id='{self.student_id}', week={self.week_number}/{self.year})>"
