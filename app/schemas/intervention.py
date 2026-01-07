"""
Pydantic schemas for Phase 6: Advanced Analytics & Intervention System.
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from uuid import UUID

from app.models.intervention import (
    AlertStatus, AlertPriority, RecipientType,
    ReportType, ReportFormat, AuditAction
)


# ============== Intervention Threshold Schemas ==============

class InterventionThresholdBase(BaseModel):
    """Base schema for intervention thresholds."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    subject: Optional[str] = None  # Null means all subjects
    min_score_percent: float = Field(default=50.0, ge=0, le=100)
    max_score_percent: float = Field(default=60.0, ge=0, le=100)
    weeks_to_review: int = Field(default=5, ge=1, le=52)
    failures_required: int = Field(default=3, ge=1)
    alert_priority: AlertPriority = AlertPriority.MEDIUM
    notify_parent: bool = True
    notify_teacher: bool = True
    notify_supervisor: bool = True
    is_active: bool = True


class InterventionThresholdCreate(InterventionThresholdBase):
    """Schema for creating a threshold."""
    pass


class InterventionThresholdUpdate(BaseModel):
    """Schema for updating a threshold."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    subject: Optional[str] = None
    min_score_percent: Optional[float] = Field(None, ge=0, le=100)
    max_score_percent: Optional[float] = Field(None, ge=0, le=100)
    weeks_to_review: Optional[int] = Field(None, ge=1, le=52)
    failures_required: Optional[int] = Field(None, ge=1)
    alert_priority: Optional[AlertPriority] = None
    notify_parent: Optional[bool] = None
    notify_teacher: Optional[bool] = None
    notify_supervisor: Optional[bool] = None
    is_active: Optional[bool] = None


class InterventionThresholdResponse(InterventionThresholdBase):
    """Response schema for threshold."""
    id: UUID
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============== Intervention Alert Schemas ==============

class AlertRecipientBase(BaseModel):
    """Base schema for alert recipients."""
    recipient_type: RecipientType
    recipient_id: Optional[UUID] = None
    recipient_name: Optional[str] = None
    recipient_email: Optional[str] = None
    recipient_phone: Optional[str] = None


class AlertRecipientCreate(AlertRecipientBase):
    """Schema for creating a recipient."""
    pass


class AlertRecipientResponse(AlertRecipientBase):
    """Response schema for recipient."""
    id: UUID
    alert_id: UUID
    notified_at: Optional[datetime] = None
    notification_method: Optional[str] = None
    is_delivered: bool = False
    is_read: bool = False
    read_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class InterventionAlertBase(BaseModel):
    """Base schema for intervention alerts."""
    subject: Optional[str] = None
    alert_type: str
    priority: AlertPriority = AlertPriority.MEDIUM
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    recommended_actions: Optional[str] = None


class InterventionAlertCreate(InterventionAlertBase):
    """Schema for creating an alert."""
    student_id: UUID
    threshold_id: Optional[UUID] = None
    current_average: Optional[float] = None
    previous_average: Optional[float] = None
    weeks_failing: Optional[int] = None
    weekly_scores: Optional[Dict[str, Any]] = None


class InterventionAlertUpdate(BaseModel):
    """Schema for updating an alert."""
    status: Optional[AlertStatus] = None
    priority: Optional[AlertPriority] = None
    resolution_notes: Optional[str] = None


class InterventionAlertResponse(InterventionAlertBase):
    """Response schema for alert."""
    id: UUID
    student_id: UUID
    threshold_id: Optional[UUID] = None
    status: AlertStatus
    current_average: Optional[float] = None
    previous_average: Optional[float] = None
    weeks_failing: Optional[int] = None
    weekly_scores: Optional[Dict[str, Any]] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[UUID] = None
    resolution_notes: Optional[str] = None
    # Teacher approval fields
    approved_at: Optional[datetime] = None
    approved_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    # Nested data
    student_name: Optional[str] = None
    student_code: Optional[str] = None
    class_name: Optional[str] = None
    recipients: List[AlertRecipientResponse] = []

    class Config:
        from_attributes = True


# ============== Report Configuration Schemas ==============

class ReportConfigurationBase(BaseModel):
    """Base schema for report configurations."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    report_type: ReportType
    filters: Optional[Dict[str, Any]] = None
    columns: Optional[List[str]] = None
    group_by: Optional[List[str]] = None
    sort_by: Optional[List[str]] = None
    is_scheduled: bool = False
    schedule_cron: Optional[str] = None
    recipients: Optional[List[str]] = None
    is_public: bool = False


class ReportConfigurationCreate(ReportConfigurationBase):
    """Schema for creating a report configuration."""
    pass


class ReportConfigurationUpdate(BaseModel):
    """Schema for updating a report configuration."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    columns: Optional[List[str]] = None
    group_by: Optional[List[str]] = None
    sort_by: Optional[List[str]] = None
    is_scheduled: Optional[bool] = None
    schedule_cron: Optional[str] = None
    recipients: Optional[List[str]] = None
    is_public: Optional[bool] = None


class ReportConfigurationResponse(ReportConfigurationBase):
    """Response schema for report configuration."""
    id: UUID
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============== Generated Report Schemas ==============

class GenerateReportRequest(BaseModel):
    """Request to generate a report."""
    configuration_id: Optional[UUID] = None
    report_type: Optional[ReportType] = None
    format: ReportFormat = ReportFormat.PDF
    parameters: Optional[Dict[str, Any]] = None
    name: Optional[str] = None


class GeneratedReportResponse(BaseModel):
    """Response schema for generated report."""
    id: UUID
    configuration_id: Optional[UUID] = None
    name: str
    report_type: ReportType
    format: ReportFormat
    file_path: Optional[str] = None
    file_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    parameters: Optional[Dict[str, Any]] = None
    row_count: Optional[int] = None
    is_ready: bool = False
    error_message: Optional[str] = None
    expires_at: Optional[datetime] = None
    generated_by: Optional[UUID] = None
    generated_at: datetime

    class Config:
        from_attributes = True


# ============== Audit Log Schemas ==============

class AuditLogCreate(BaseModel):
    """Schema for creating an audit log entry."""
    action: AuditAction
    entity_type: str
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    description: Optional[str] = None
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    duration_ms: Optional[int] = None


class AuditLogResponse(BaseModel):
    """Response schema for audit log."""
    id: UUID
    user_id: Optional[UUID] = None
    user_email: Optional[str] = None
    user_role: Optional[str] = None
    action: AuditAction
    entity_type: str
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    description: Optional[str] = None
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: datetime
    duration_ms: Optional[int] = None

    class Config:
        from_attributes = True


class AuditLogFilter(BaseModel):
    """Filter parameters for querying audit logs."""
    user_id: Optional[UUID] = None
    action: Optional[AuditAction] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


# ============== Weekly Performance Schemas ==============

class WeeklyPerformanceResponse(BaseModel):
    """Response schema for weekly performance."""
    id: UUID
    student_id: UUID
    week_start: date
    week_end: date
    week_number: int
    year: int

    # Performance metrics
    tests_taken: int = 0
    average_score: Optional[float] = None
    highest_score: Optional[float] = None
    lowest_score: Optional[float] = None
    total_time_minutes: int = 0
    subject_scores: Optional[Dict[str, Any]] = None

    # Attendance
    days_present: int = 0
    days_absent: int = 0
    days_late: int = 0

    # Homework
    homework_completed: int = 0
    homework_missing: int = 0

    # Comparison
    previous_week_average: Optional[float] = None
    change_percent: Optional[float] = None

    # Student info
    student_name: Optional[str] = None
    student_code: Optional[str] = None

    class Config:
        from_attributes = True


# ============== Analytics Schemas ==============

class StudentAnalytics(BaseModel):
    """Comprehensive analytics for a single student."""
    student_id: UUID
    student_name: str
    student_code: str
    class_name: Optional[str] = None

    # Overall performance
    overall_average: Optional[float] = None
    tests_completed: int = 0
    total_time_hours: float = 0

    # Subject breakdown
    subject_performance: Dict[str, Dict[str, Any]] = {}

    # Trends
    weekly_trend: List[Dict[str, Any]] = []
    improvement_rate: Optional[float] = None

    # Attendance
    attendance_rate: Optional[float] = None
    days_present: int = 0
    days_absent: int = 0

    # Alerts
    active_alerts: int = 0
    resolved_alerts: int = 0


class ClassAnalytics(BaseModel):
    """Analytics for a class."""
    class_id: UUID
    class_name: str
    student_count: int = 0

    # Performance
    average_score: Optional[float] = None
    highest_performer: Optional[str] = None
    lowest_performer: Optional[str] = None

    # Distribution
    score_distribution: Dict[str, int] = {}  # A, B, C, D, F counts

    # Subject performance
    subject_averages: Dict[str, float] = {}

    # Trends
    weekly_trend: List[Dict[str, Any]] = []

    # Alerts
    students_needing_intervention: int = 0


class PerformanceComparison(BaseModel):
    """Compare performance between students/classes/periods."""
    comparison_type: str  # 'student', 'class', 'period'
    items: List[Dict[str, Any]] = []
    metrics: List[str] = []


class DashboardStats(BaseModel):
    """Admin dashboard statistics."""
    # Overview
    total_students: int = 0
    active_students: int = 0
    total_tests: int = 0
    tests_this_week: int = 0

    # Performance
    overall_average: Optional[float] = None
    tests_completed_today: int = 0
    average_completion_time_minutes: Optional[float] = None

    # Interventions
    pending_alerts: int = 0
    resolved_this_week: int = 0
    students_at_risk: int = 0

    # Attendance
    attendance_rate_today: Optional[float] = None
    students_absent_today: int = 0

    # Recent activity
    recent_tests: List[Dict[str, Any]] = []
    recent_alerts: List[Dict[str, Any]] = []
