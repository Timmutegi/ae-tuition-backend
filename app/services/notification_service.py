"""
Notification service for managing in-app notifications and user preferences.
Phase 7: Notifications & Polish
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta

from app.models.notification import (
    Notification, NotificationPreference, UserPreferences,
    NotificationType, NotificationPriority
)
from app.schemas.notification import (
    NotificationCreate, NotificationCreateBulk, NotificationUpdate,
    NotificationPreferenceCreate, NotificationPreferenceUpdate,
    UserPreferencesCreate, UserPreferencesUpdate
)


class NotificationService:
    """Service for managing notifications"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Notification CRUD ====================

    async def create_notification(self, data: NotificationCreate) -> Notification:
        """Create a single notification"""
        notification = Notification(
            user_id=data.user_id,
            type=NotificationType(data.type.value),
            priority=NotificationPriority(data.priority.value),
            title=data.title,
            message=data.message,
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            action_url=data.action_url,
            extra_data=data.extra_data,
            expires_at=data.expires_at
        )
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def create_bulk_notifications(self, data: NotificationCreateBulk) -> List[Notification]:
        """Create same notification for multiple users"""
        notifications = []
        for user_id in data.user_ids:
            notification = Notification(
                user_id=user_id,
                type=NotificationType(data.type.value),
                priority=NotificationPriority(data.priority.value),
                title=data.title,
                message=data.message,
                entity_type=data.entity_type,
                entity_id=data.entity_id,
                action_url=data.action_url,
                extra_data=data.extra_data,
                expires_at=data.expires_at
            )
            self.db.add(notification)
            notifications.append(notification)

        await self.db.commit()
        return notifications

    async def get_notification(self, notification_id: UUID) -> Optional[Notification]:
        """Get a single notification by ID"""
        result = await self.db.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def get_user_notifications(
        self,
        user_id: UUID,
        include_read: bool = True,
        include_archived: bool = False,
        notification_type: Optional[NotificationType] = None,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[List[Notification], int, int]:
        """Get notifications for a user with filters"""
        # Build base query
        conditions = [Notification.user_id == user_id]

        if not include_read:
            conditions.append(Notification.is_read == False)

        if not include_archived:
            conditions.append(Notification.is_archived == False)

        if notification_type:
            conditions.append(Notification.type == notification_type)

        # Exclude expired notifications
        conditions.append(
            or_(
                Notification.expires_at.is_(None),
                Notification.expires_at > datetime.utcnow()
            )
        )

        # Get notifications
        result = await self.db.execute(
            select(Notification)
            .where(and_(*conditions))
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        notifications = list(result.scalars().all())

        # Get total count
        count_result = await self.db.execute(
            select(func.count(Notification.id))
            .where(and_(*conditions))
        )
        total = count_result.scalar() or 0

        # Get unread count
        unread_result = await self.db.execute(
            select(func.count(Notification.id))
            .where(
                Notification.user_id == user_id,
                Notification.is_read == False,
                Notification.is_archived == False,
                or_(
                    Notification.expires_at.is_(None),
                    Notification.expires_at > datetime.utcnow()
                )
            )
        )
        unread_count = unread_result.scalar() or 0

        return notifications, total, unread_count

    async def get_notification_summary(self, user_id: UUID) -> Dict[str, Any]:
        """Get notification summary for the bell icon"""
        # Get unread count by type
        type_result = await self.db.execute(
            select(Notification.type, func.count(Notification.id))
            .where(
                Notification.user_id == user_id,
                Notification.is_read == False,
                Notification.is_archived == False,
                or_(
                    Notification.expires_at.is_(None),
                    Notification.expires_at > datetime.utcnow()
                )
            )
            .group_by(Notification.type)
        )
        by_type = {row[0].value: row[1] for row in type_result.all()}

        # Get unread count by priority
        priority_result = await self.db.execute(
            select(Notification.priority, func.count(Notification.id))
            .where(
                Notification.user_id == user_id,
                Notification.is_read == False,
                Notification.is_archived == False,
                or_(
                    Notification.expires_at.is_(None),
                    Notification.expires_at > datetime.utcnow()
                )
            )
            .group_by(Notification.priority)
        )
        by_priority = {row[0].value: row[1] for row in priority_result.all()}

        # Total unread
        total_unread = sum(by_type.values())

        # Get recent notifications (last 5)
        recent_result = await self.db.execute(
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_archived == False,
                or_(
                    Notification.expires_at.is_(None),
                    Notification.expires_at > datetime.utcnow()
                )
            )
            .order_by(Notification.created_at.desc())
            .limit(5)
        )
        recent = list(recent_result.scalars().all())

        return {
            "total_unread": total_unread,
            "by_type": by_type,
            "by_priority": by_priority,
            "recent": recent
        }

    async def mark_as_read(self, notification_id: UUID, user_id: UUID) -> bool:
        """Mark a notification as read"""
        result = await self.db.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.user_id == user_id
            )
            .values(is_read=True, read_at=datetime.utcnow())
        )
        await self.db.commit()
        return result.rowcount > 0

    async def mark_all_as_read(self, user_id: UUID, notification_type: Optional[NotificationType] = None) -> int:
        """Mark all notifications as read for a user"""
        conditions = [
            Notification.user_id == user_id,
            Notification.is_read == False
        ]

        if notification_type:
            conditions.append(Notification.type == notification_type)

        result = await self.db.execute(
            update(Notification)
            .where(and_(*conditions))
            .values(is_read=True, read_at=datetime.utcnow())
        )
        await self.db.commit()
        return result.rowcount

    async def archive_notification(self, notification_id: UUID, user_id: UUID) -> bool:
        """Archive a notification"""
        result = await self.db.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.user_id == user_id
            )
            .values(is_archived=True)
        )
        await self.db.commit()
        return result.rowcount > 0

    async def delete_notification(self, notification_id: UUID, user_id: UUID) -> bool:
        """Delete a notification"""
        result = await self.db.execute(
            delete(Notification)
            .where(
                Notification.id == notification_id,
                Notification.user_id == user_id
            )
        )
        await self.db.commit()
        return result.rowcount > 0

    async def cleanup_expired_notifications(self) -> int:
        """Delete expired notifications (can be run as a scheduled task)"""
        result = await self.db.execute(
            delete(Notification)
            .where(
                Notification.expires_at.isnot(None),
                Notification.expires_at < datetime.utcnow()
            )
        )
        await self.db.commit()
        return result.rowcount

    # ==================== Notification Preferences ====================

    async def get_notification_preferences(self, user_id: UUID) -> Optional[NotificationPreference]:
        """Get notification preferences for a user"""
        result = await self.db.execute(
            select(NotificationPreference)
            .where(NotificationPreference.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_notification_preferences(
        self,
        user_id: UUID,
        data: Optional[NotificationPreferenceCreate] = None
    ) -> NotificationPreference:
        """Create notification preferences with defaults"""
        if data:
            prefs = NotificationPreference(user_id=user_id, **data.model_dump())
        else:
            prefs = NotificationPreference(user_id=user_id)

        self.db.add(prefs)
        await self.db.commit()
        await self.db.refresh(prefs)
        return prefs

    async def update_notification_preferences(
        self,
        user_id: UUID,
        data: NotificationPreferenceUpdate
    ) -> Optional[NotificationPreference]:
        """Update notification preferences"""
        prefs = await self.get_notification_preferences(user_id)

        if not prefs:
            # Create with defaults and then update
            prefs = await self.create_notification_preferences(user_id)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(prefs, key, value)

        await self.db.commit()
        await self.db.refresh(prefs)
        return prefs

    async def should_send_notification(
        self,
        user_id: UUID,
        notification_type: NotificationType
    ) -> bool:
        """Check if user should receive a notification of this type"""
        prefs = await self.get_notification_preferences(user_id)

        if not prefs:
            return True  # Default to enabled

        # Map notification type to preference field
        type_to_field = {
            NotificationType.ALERT: "alert_enabled",
            NotificationType.TEST_ASSIGNED: "test_assigned_enabled",
            NotificationType.TEST_GRADED: "test_graded_enabled",
            NotificationType.TEST_REMINDER: "test_reminder_enabled",
            NotificationType.ATTENDANCE: "attendance_enabled",
            NotificationType.SUPPORT: "support_enabled",
            NotificationType.SYSTEM: "system_enabled",
            NotificationType.MESSAGE: "message_enabled",
            NotificationType.REPORT: "report_enabled",
        }

        field = type_to_field.get(notification_type)
        if field:
            return getattr(prefs, field, True)

        return True


class UserPreferencesService:
    """Service for managing user preferences"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_preferences(self, user_id: UUID) -> Optional[UserPreferences]:
        """Get user preferences"""
        result = await self.db.execute(
            select(UserPreferences)
            .where(UserPreferences.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_preferences(
        self,
        user_id: UUID,
        data: Optional[UserPreferencesCreate] = None
    ) -> UserPreferences:
        """Create user preferences with defaults"""
        if data:
            prefs = UserPreferences(user_id=user_id, **data.model_dump())
        else:
            prefs = UserPreferences(user_id=user_id)

        self.db.add(prefs)
        await self.db.commit()
        await self.db.refresh(prefs)
        return prefs

    async def update_preferences(
        self,
        user_id: UUID,
        data: UserPreferencesUpdate
    ) -> Optional[UserPreferences]:
        """Update user preferences"""
        prefs = await self.get_preferences(user_id)

        if not prefs:
            # Create with defaults and then update
            prefs = await self.create_preferences(user_id)

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(prefs, key, value)

        await self.db.commit()
        await self.db.refresh(prefs)
        return prefs

    async def get_or_create_preferences(self, user_id: UUID) -> UserPreferences:
        """Get preferences, creating defaults if not exists"""
        prefs = await self.get_preferences(user_id)
        if not prefs:
            prefs = await self.create_preferences(user_id)
        return prefs

    async def update_theme(self, user_id: UUID, theme: str) -> UserPreferences:
        """Quick method to update just the theme"""
        prefs = await self.get_or_create_preferences(user_id)
        prefs.theme = theme
        await self.db.commit()
        await self.db.refresh(prefs)
        return prefs
