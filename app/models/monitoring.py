"""
Monitoring Models for Anti-Cheating System

This module contains models for tracking suspicious activities and
monitoring active test sessions in real-time.
"""

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ActivityType(enum.Enum):
    """Types of suspicious activities that can be logged."""
    TAB_SWITCH = "tab_switch"
    TAB_HIDDEN = "tab_hidden"
    RIGHT_CLICK = "right_click"
    KEYBOARD_SHORTCUT = "keyboard_shortcut"
    IDLE_TIMEOUT = "idle_timeout"
    WINDOW_BLUR = "window_blur"
    WINDOW_FOCUS = "window_focus"
    FULLSCREEN_EXIT = "fullscreen_exit"
    DEVTOOLS_OPEN = "devtools_open"
    PRINT_ATTEMPT = "print_attempt"
    SCREENSHOT_ATTEMPT = "screenshot_attempt"
    MULTIPLE_MONITORS = "multiple_monitors"
    BROWSER_RESIZE = "browser_resize"


class AlertSeverity(enum.Enum):
    """Severity levels for alerts."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SessionStatus(enum.Enum):
    """Status of an active test session."""
    ACTIVE = "active"
    IDLE = "idle"
    SUSPICIOUS = "suspicious"
    DISCONNECTED = "disconnected"
    COMPLETED = "completed"


class SuspiciousActivityLog(Base):
    """
    Log of suspicious activities detected during test sessions.

    Records events like tab switches, copy-paste attempts, idle time, etc.
    """
    __tablename__ = "suspicious_activity_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey('test_attempts.id'), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey('students.id'), nullable=False)
    test_id = Column(UUID(as_uuid=True), ForeignKey('tests.id'), nullable=False)

    activity_type = Column(SQLEnum(ActivityType), nullable=False)
    severity = Column(SQLEnum(AlertSeverity), default=AlertSeverity.LOW)

    # Activity details
    description = Column(Text)
    extra_data = Column(JSONB)  # Additional context (e.g., key pressed, duration)

    # Timing
    occurred_at = Column(DateTime(timezone=True), default=func.now())
    duration_seconds = Column(Integer)  # For idle/hidden events

    # Location in test
    question_number = Column(Integer)
    question_id = Column(UUID(as_uuid=True), ForeignKey('questions.id'), nullable=True)

    # Review status
    reviewed = Column(Boolean, default=False)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text)

    created_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    attempt = relationship("TestAttempt", back_populates="suspicious_activities")
    student = relationship("Student")
    test = relationship("Test")
    question = relationship("Question")
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class ActiveTestSession(Base):
    """
    Real-time tracking of active test sessions.

    Updated via heartbeats (every 10 seconds) to monitor student activity.
    """
    __tablename__ = "active_test_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey('test_attempts.id'), nullable=False, unique=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey('students.id'), nullable=False)
    test_id = Column(UUID(as_uuid=True), ForeignKey('tests.id'), nullable=False)
    assignment_id = Column(UUID(as_uuid=True), nullable=True)

    # Session status
    status = Column(SQLEnum(SessionStatus), default=SessionStatus.ACTIVE)

    # Progress tracking
    current_question = Column(Integer, default=1)
    questions_answered = Column(Integer, default=0)
    total_questions = Column(Integer, default=0)
    progress_percentage = Column(Integer, default=0)

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=False)
    last_heartbeat = Column(DateTime(timezone=True), default=func.now())
    last_activity = Column(DateTime(timezone=True), default=func.now())
    time_remaining_seconds = Column(Integer)

    # Activity counters
    tab_switches = Column(Integer, default=0)
    idle_periods = Column(Integer, default=0)
    total_idle_seconds = Column(Integer, default=0)
    warnings_count = Column(Integer, default=0)

    # Browser/device info
    browser_info = Column(JSONB)
    ip_address = Column(String(45))
    user_agent = Column(Text)
    screen_resolution = Column(String(20))

    # Flags
    is_flagged = Column(Boolean, default=False)
    flag_reason = Column(Text)
    requires_attention = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    attempt = relationship("TestAttempt", back_populates="active_session")
    student = relationship("Student")
    test = relationship("Test")


class AlertConfiguration(Base):
    """
    Configurable thresholds for generating alerts.

    Admins can customize when alerts are triggered.
    """
    __tablename__ = "alert_configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text)

    # Thresholds
    activity_type = Column(SQLEnum(ActivityType), nullable=True)  # Null means applies to all
    threshold_count = Column(Integer, default=3)  # Number of occurrences before alert
    threshold_duration_seconds = Column(Integer)  # For time-based activities
    severity = Column(SQLEnum(AlertSeverity), default=AlertSeverity.MEDIUM)

    # Actions
    notify_teacher = Column(Boolean, default=True)
    notify_admin = Column(Boolean, default=False)
    auto_flag_session = Column(Boolean, default=False)

    # Status
    is_active = Column(Boolean, default=True)

    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User")
