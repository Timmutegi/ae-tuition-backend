"""
Notification API endpoints.
Phase 7: Notifications & Polish
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.notification import NotificationType
from app.services.notification_service import NotificationService, UserPreferencesService
from app.schemas.notification import (
    NotificationCreate, NotificationCreateBulk, NotificationUpdate,
    NotificationResponse, NotificationListResponse, NotificationSummary,
    NotificationPreferenceUpdate, NotificationPreferenceResponse,
    UserPreferencesUpdate, UserPreferencesResponse, UserSettingsResponse
)

router = APIRouter(prefix="/notifications")


# ==================== Notification Endpoints ====================

@router.get("", response_model=NotificationListResponse)
async def get_notifications(
    include_read: bool = Query(True, description="Include read notifications"),
    include_archived: bool = Query(False, description="Include archived notifications"),
    notification_type: Optional[str] = Query(None, description="Filter by notification type"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get notifications for the current user"""
    service = NotificationService(db)

    # Parse notification type if provided
    n_type = None
    if notification_type:
        try:
            n_type = NotificationType(notification_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid notification type: {notification_type}")

    notifications, total, unread_count = await service.get_user_notifications(
        user_id=current_user.id,
        include_read=include_read,
        include_archived=include_archived,
        notification_type=n_type,
        limit=limit,
        offset=offset
    )

    return NotificationListResponse(
        notifications=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        unread_count=unread_count
    )


@router.get("/summary", response_model=NotificationSummary)
async def get_notification_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get notification summary for the bell icon"""
    service = NotificationService(db)
    summary = await service.get_notification_summary(current_user.id)

    return NotificationSummary(
        total_unread=summary["total_unread"],
        by_type=summary["by_type"],
        by_priority=summary["by_priority"],
        recent=[NotificationResponse.model_validate(n) for n in summary["recent"]]
    )


@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific notification"""
    service = NotificationService(db)
    notification = await service.get_notification(notification_id)

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    if notification.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this notification")

    return NotificationResponse.model_validate(notification)


@router.put("/{notification_id}/read")
async def mark_notification_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark a notification as read"""
    service = NotificationService(db)
    success = await service.mark_as_read(notification_id, current_user.id)

    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")

    return {"message": "Notification marked as read"}


@router.put("/read-all")
async def mark_all_notifications_read(
    notification_type: Optional[str] = Query(None, description="Only mark this type as read"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark all notifications as read"""
    service = NotificationService(db)

    n_type = None
    if notification_type:
        try:
            n_type = NotificationType(notification_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid notification type: {notification_type}")

    count = await service.mark_all_as_read(current_user.id, n_type)

    return {"message": f"{count} notifications marked as read"}


@router.put("/{notification_id}/archive")
async def archive_notification(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Archive a notification"""
    service = NotificationService(db)
    success = await service.archive_notification(notification_id, current_user.id)

    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")

    return {"message": "Notification archived"}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a notification"""
    service = NotificationService(db)
    success = await service.delete_notification(notification_id, current_user.id)

    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")

    return {"message": "Notification deleted"}


# ==================== Notification Preferences Endpoints ====================

@router.get("/preferences/notification", response_model=NotificationPreferenceResponse)
async def get_notification_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get notification preferences for the current user"""
    service = NotificationService(db)
    prefs = await service.get_notification_preferences(current_user.id)

    if not prefs:
        # Create defaults
        prefs = await service.create_notification_preferences(current_user.id)

    return NotificationPreferenceResponse.model_validate(prefs)


@router.put("/preferences/notification", response_model=NotificationPreferenceResponse)
async def update_notification_preferences(
    data: NotificationPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update notification preferences"""
    service = NotificationService(db)
    prefs = await service.update_notification_preferences(current_user.id, data)

    return NotificationPreferenceResponse.model_validate(prefs)


# ==================== User Preferences Endpoints ====================

@router.get("/preferences/user", response_model=UserPreferencesResponse)
async def get_user_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user preferences (theme, UI settings, etc.)"""
    service = UserPreferencesService(db)
    prefs = await service.get_or_create_preferences(current_user.id)

    return UserPreferencesResponse.model_validate(prefs)


@router.put("/preferences/user", response_model=UserPreferencesResponse)
async def update_user_preferences(
    data: UserPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user preferences"""
    service = UserPreferencesService(db)
    prefs = await service.update_preferences(current_user.id, data)

    return UserPreferencesResponse.model_validate(prefs)


@router.put("/preferences/theme")
async def update_theme(
    theme: str = Query(..., description="Theme: 'light', 'dark', or 'system'"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Quick endpoint to update just the theme"""
    if theme not in ["light", "dark", "system"]:
        raise HTTPException(status_code=400, detail="Invalid theme. Must be 'light', 'dark', or 'system'")

    service = UserPreferencesService(db)
    prefs = await service.update_theme(current_user.id, theme)

    return {"theme": prefs.theme}


@router.get("/preferences/all", response_model=UserSettingsResponse)
async def get_all_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all user settings (preferences + notification preferences)"""
    notification_service = NotificationService(db)
    user_prefs_service = UserPreferencesService(db)

    user_prefs = await user_prefs_service.get_or_create_preferences(current_user.id)
    notification_prefs = await notification_service.get_notification_preferences(current_user.id)

    if not notification_prefs:
        notification_prefs = await notification_service.create_notification_preferences(current_user.id)

    return UserSettingsResponse(
        preferences=UserPreferencesResponse.model_validate(user_prefs),
        notification_preferences=NotificationPreferenceResponse.model_validate(notification_prefs)
    )
