"""
Pydantic schemas for notifications and user preferences.
Phase 7: Notifications & Polish
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


# Enums matching database models
class NotificationType(str, Enum):
    ALERT = "alert"
    TEST_ASSIGNED = "test_assigned"
    TEST_GRADED = "test_graded"
    TEST_REMINDER = "test_reminder"
    ATTENDANCE = "attendance"
    SUPPORT = "support"
    SYSTEM = "system"
    MESSAGE = "message"
    REPORT = "report"


class NotificationPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# ==================== Notification Schemas ====================

class NotificationBase(BaseModel):
    type: NotificationType = NotificationType.SYSTEM
    priority: NotificationPriority = NotificationPriority.NORMAL
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1)
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    action_url: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None
    expires_at: Optional[datetime] = None


class NotificationCreate(NotificationBase):
    user_id: UUID


class NotificationCreateBulk(NotificationBase):
    """Create same notification for multiple users"""
    user_ids: List[UUID]


class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None
    is_archived: Optional[bool] = None


class NotificationResponse(NotificationBase):
    id: UUID
    user_id: UUID
    is_read: bool
    read_at: Optional[datetime]
    is_archived: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse]
    total: int
    unread_count: int


class NotificationSummary(BaseModel):
    """Summary counts for notification bell"""
    total_unread: int
    by_type: Dict[str, int]
    by_priority: Dict[str, int]
    recent: List[NotificationResponse]


# ==================== Notification Preference Schemas ====================

class NotificationPreferenceBase(BaseModel):
    # Per-type settings
    alert_enabled: bool = True
    test_assigned_enabled: bool = True
    test_graded_enabled: bool = True
    test_reminder_enabled: bool = True
    attendance_enabled: bool = True
    support_enabled: bool = True
    system_enabled: bool = True
    message_enabled: bool = True
    report_enabled: bool = True

    # Email settings
    email_enabled: bool = True
    email_digest: bool = False

    # Sound and display
    sound_enabled: bool = True
    desktop_enabled: bool = False

    # Quiet hours
    quiet_hours_enabled: bool = False
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


class NotificationPreferenceCreate(NotificationPreferenceBase):
    pass


class NotificationPreferenceUpdate(BaseModel):
    alert_enabled: Optional[bool] = None
    test_assigned_enabled: Optional[bool] = None
    test_graded_enabled: Optional[bool] = None
    test_reminder_enabled: Optional[bool] = None
    attendance_enabled: Optional[bool] = None
    support_enabled: Optional[bool] = None
    system_enabled: Optional[bool] = None
    message_enabled: Optional[bool] = None
    report_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    email_digest: Optional[bool] = None
    sound_enabled: Optional[bool] = None
    desktop_enabled: Optional[bool] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


class NotificationPreferenceResponse(NotificationPreferenceBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== User Preference Schemas ====================

class UserPreferencesBase(BaseModel):
    # Theme
    theme: str = "light"

    # UI
    sidebar_collapsed: bool = False
    compact_mode: bool = False

    # Locale
    language: str = "en"
    date_format: str = "DD/MM/YYYY"
    time_format: str = "24h"

    # Dashboard
    dashboard_layout: Optional[Dict[str, Any]] = None
    default_page_size: str = "20"

    # Accessibility
    high_contrast: bool = False
    reduce_motion: bool = False
    font_size: str = "medium"

    # Custom
    custom_settings: Optional[Dict[str, Any]] = None


class UserPreferencesCreate(UserPreferencesBase):
    pass


class UserPreferencesUpdate(BaseModel):
    theme: Optional[str] = None
    sidebar_collapsed: Optional[bool] = None
    compact_mode: Optional[bool] = None
    language: Optional[str] = None
    date_format: Optional[str] = None
    time_format: Optional[str] = None
    dashboard_layout: Optional[Dict[str, Any]] = None
    default_page_size: Optional[str] = None
    high_contrast: Optional[bool] = None
    reduce_motion: Optional[bool] = None
    font_size: Optional[str] = None
    custom_settings: Optional[Dict[str, Any]] = None


class UserPreferencesResponse(UserPreferencesBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== Combined Response ====================

class UserSettingsResponse(BaseModel):
    """Combined user settings response"""
    preferences: Optional[UserPreferencesResponse]
    notification_preferences: Optional[NotificationPreferenceResponse]
