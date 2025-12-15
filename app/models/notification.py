"""
Notification models for in-app notifications and user preferences.
Phase 7: Notifications & Polish
"""
from sqlalchemy import Column, String, Boolean, DateTime, Enum, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum

from app.core.database import Base


class NotificationType(enum.Enum):
    """Types of notifications"""
    ALERT = "alert"                    # Intervention alerts
    TEST_ASSIGNED = "test_assigned"    # New test assigned
    TEST_GRADED = "test_graded"        # Test has been graded
    TEST_REMINDER = "test_reminder"    # Test deadline approaching
    ATTENDANCE = "attendance"          # Attendance-related
    SUPPORT = "support"                # Support session scheduled
    SYSTEM = "system"                  # System announcements
    MESSAGE = "message"                # Direct messages
    REPORT = "report"                  # Report ready


class NotificationPriority(enum.Enum):
    """Notification priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Notification(Base):
    """In-app notifications for users"""
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Recipient
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Notification content
    type = Column(Enum(NotificationType), nullable=False, default=NotificationType.SYSTEM)
    priority = Column(Enum(NotificationPriority), nullable=False, default=NotificationPriority.NORMAL)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)

    # Optional link to related entity
    entity_type = Column(String(50), nullable=True)  # e.g., 'test', 'alert', 'report'
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    action_url = Column(String(500), nullable=True)  # Frontend route to navigate to

    # Additional data as JSON
    extra_data = Column(JSON, nullable=True)

    # Status
    is_read = Column(Boolean, default=False, nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    is_archived = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Auto-delete after expiry

    # Relationships
    user = relationship("User", backref="notifications")

    def __repr__(self):
        return f"<Notification(user_id={self.user_id}, type={self.type.value}, title='{self.title[:30]}...')>"


class NotificationPreference(Base):
    """User preferences for notification delivery"""
    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True)

    # In-app notifications (per type)
    alert_enabled = Column(Boolean, default=True, nullable=False)
    test_assigned_enabled = Column(Boolean, default=True, nullable=False)
    test_graded_enabled = Column(Boolean, default=True, nullable=False)
    test_reminder_enabled = Column(Boolean, default=True, nullable=False)
    attendance_enabled = Column(Boolean, default=True, nullable=False)
    support_enabled = Column(Boolean, default=True, nullable=False)
    system_enabled = Column(Boolean, default=True, nullable=False)
    message_enabled = Column(Boolean, default=True, nullable=False)
    report_enabled = Column(Boolean, default=True, nullable=False)

    # Email notifications
    email_enabled = Column(Boolean, default=True, nullable=False)
    email_digest = Column(Boolean, default=False, nullable=False)  # Daily digest instead of immediate

    # Sound and display
    sound_enabled = Column(Boolean, default=True, nullable=False)
    desktop_enabled = Column(Boolean, default=False, nullable=False)  # Browser notifications

    # Quiet hours
    quiet_hours_enabled = Column(Boolean, default=False, nullable=False)
    quiet_hours_start = Column(String(5), nullable=True)  # HH:MM format
    quiet_hours_end = Column(String(5), nullable=True)    # HH:MM format

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="notification_preferences")

    def __repr__(self):
        return f"<NotificationPreference(user_id={self.user_id})>"


class UserPreferences(Base):
    """General user preferences including theme settings"""
    __tablename__ = "user_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True)

    # Theme settings
    theme = Column(String(20), default="light", nullable=False)  # 'light', 'dark', 'system'

    # UI preferences
    sidebar_collapsed = Column(Boolean, default=False, nullable=False)
    compact_mode = Column(Boolean, default=False, nullable=False)

    # Language and locale
    language = Column(String(10), default="en", nullable=False)
    date_format = Column(String(20), default="DD/MM/YYYY", nullable=False)
    time_format = Column(String(10), default="24h", nullable=False)  # '12h' or '24h'

    # Dashboard preferences
    dashboard_layout = Column(JSON, nullable=True)  # Custom widget arrangement
    default_page_size = Column(String(10), default="20", nullable=False)

    # Accessibility
    high_contrast = Column(Boolean, default=False, nullable=False)
    reduce_motion = Column(Boolean, default=False, nullable=False)
    font_size = Column(String(10), default="medium", nullable=False)  # 'small', 'medium', 'large'

    # Additional preferences as JSON
    custom_settings = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="preferences")

    def __repr__(self):
        return f"<UserPreferences(user_id={self.user_id}, theme={self.theme})>"
