"""
API endpoints for Phase 6: Advanced Analytics & Intervention System.
Handles intervention alerts, thresholds, reports, and audit logs.
"""

from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, get_current_admin
from app.models.user import User
from app.models.intervention import AlertStatus, AlertPriority, ReportType, ReportFormat, AuditAction
from app.services.intervention_service import InterventionService
from app.services.audit_service import AuditService
from app.schemas.intervention import (
    InterventionThresholdCreate, InterventionThresholdUpdate, InterventionThresholdResponse,
    InterventionAlertCreate, InterventionAlertUpdate, InterventionAlertResponse,
    ReportConfigurationCreate, ReportConfigurationUpdate, ReportConfigurationResponse,
    GenerateReportRequest, GeneratedReportResponse,
    AuditLogResponse, AuditLogFilter,
    WeeklyPerformanceResponse, StudentAnalytics, DashboardStats
)

router = APIRouter(prefix="/interventions")


# ============== Threshold Endpoints ==============

@router.post("/thresholds", response_model=InterventionThresholdResponse)
async def create_threshold(
    data: InterventionThresholdCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Create a new intervention threshold. Admin only."""
    service = InterventionService(db)
    threshold = await service.create_threshold(data, current_user.id)
    return threshold


@router.get("/thresholds", response_model=List[InterventionThresholdResponse])
async def get_thresholds(
    active_only: bool = Query(False, description="Only return active thresholds"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get all intervention thresholds. Admin only."""
    service = InterventionService(db)
    thresholds = await service.get_all_thresholds(active_only=active_only)
    return thresholds


@router.get("/thresholds/{threshold_id}", response_model=InterventionThresholdResponse)
async def get_threshold(
    threshold_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get a specific threshold. Admin only."""
    service = InterventionService(db)
    threshold = await service.get_threshold(threshold_id)
    if not threshold:
        raise HTTPException(status_code=404, detail="Threshold not found")
    return threshold


@router.put("/thresholds/{threshold_id}", response_model=InterventionThresholdResponse)
async def update_threshold(
    threshold_id: UUID,
    data: InterventionThresholdUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update a threshold. Admin only."""
    service = InterventionService(db)
    threshold = await service.update_threshold(threshold_id, data)
    if not threshold:
        raise HTTPException(status_code=404, detail="Threshold not found")
    return threshold


@router.delete("/thresholds/{threshold_id}")
async def delete_threshold(
    threshold_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Delete a threshold. Admin only."""
    service = InterventionService(db)
    deleted = await service.delete_threshold(threshold_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Threshold not found")
    return {"message": "Threshold deleted successfully"}


# ============== Alert Endpoints ==============

@router.post("/alerts", response_model=InterventionAlertResponse)
async def create_alert(
    data: InterventionAlertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Create a new intervention alert manually. Admin only."""
    service = InterventionService(db)
    alert = await service.create_alert(data)
    return alert


@router.get("/alerts")
async def get_alerts(
    student_id: Optional[UUID] = None,
    status: Optional[AlertStatus] = None,
    priority: Optional[AlertPriority] = None,
    subject: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get intervention alerts with filtering."""
    service = InterventionService(db)
    alerts, total = await service.get_alerts(
        student_id=student_id,
        status=status,
        priority=priority,
        subject=subject,
        limit=limit,
        offset=offset
    )

    # Add student info to response
    result = []
    for alert in alerts:
        alert_dict = {
            "id": alert.id,
            "student_id": alert.student_id,
            "threshold_id": alert.threshold_id,
            "subject": alert.subject,
            "alert_type": alert.alert_type,
            "priority": alert.priority,
            "status": alert.status,
            "title": alert.title,
            "description": alert.description,
            "recommended_actions": alert.recommended_actions,
            "current_average": alert.current_average,
            "previous_average": alert.previous_average,
            "weeks_failing": alert.weeks_failing,
            "weekly_scores": alert.weekly_scores,
            "resolved_at": alert.resolved_at,
            "resolved_by": alert.resolved_by,
            "resolution_notes": alert.resolution_notes,
            "created_at": alert.created_at,
            "updated_at": alert.updated_at,
            "student_name": alert.student.student_name if alert.student else None,
            "student_code": alert.student.student_code if alert.student else None,
            "class_name": alert.student.class_rel.name if alert.student and alert.student.class_rel else None,
            "recipients": [
                {
                    "id": r.id,
                    "alert_id": r.alert_id,
                    "recipient_type": r.recipient_type,
                    "recipient_id": r.recipient_id,
                    "recipient_name": r.recipient_name,
                    "recipient_email": r.recipient_email,
                    "notified_at": r.notified_at,
                    "is_delivered": r.is_delivered,
                    "is_read": r.is_read,
                    "created_at": r.created_at
                }
                for r in alert.recipients
            ]
        }
        result.append(alert_dict)

    return {"alerts": result, "total": total}


@router.get("/alerts/{alert_id}", response_model=InterventionAlertResponse)
async def get_alert(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific alert."""
    service = InterventionService(db)
    alert = await service.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {
        "id": alert.id,
        "student_id": alert.student_id,
        "threshold_id": alert.threshold_id,
        "subject": alert.subject,
        "alert_type": alert.alert_type,
        "priority": alert.priority,
        "status": alert.status,
        "title": alert.title,
        "description": alert.description,
        "recommended_actions": alert.recommended_actions,
        "current_average": alert.current_average,
        "previous_average": alert.previous_average,
        "weeks_failing": alert.weeks_failing,
        "weekly_scores": alert.weekly_scores,
        "resolved_at": alert.resolved_at,
        "resolved_by": alert.resolved_by,
        "resolution_notes": alert.resolution_notes,
        "created_at": alert.created_at,
        "updated_at": alert.updated_at,
        "student_name": alert.student.student_name if alert.student else None,
        "student_code": alert.student.student_code if alert.student else None,
        "class_name": alert.student.class_rel.name if alert.student and alert.student.class_rel else None,
        "recipients": []
    }


@router.put("/alerts/{alert_id}", response_model=InterventionAlertResponse)
async def update_alert(
    alert_id: UUID,
    data: InterventionAlertUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an alert status."""
    service = InterventionService(db)
    alert = await service.update_alert(alert_id, data, resolved_by=current_user.id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {
        "id": alert.id,
        "student_id": alert.student_id,
        "threshold_id": alert.threshold_id,
        "subject": alert.subject,
        "alert_type": alert.alert_type,
        "priority": alert.priority,
        "status": alert.status,
        "title": alert.title,
        "description": alert.description,
        "recommended_actions": alert.recommended_actions,
        "current_average": alert.current_average,
        "previous_average": alert.previous_average,
        "weeks_failing": alert.weeks_failing,
        "weekly_scores": alert.weekly_scores,
        "resolved_at": alert.resolved_at,
        "resolved_by": alert.resolved_by,
        "resolution_notes": alert.resolution_notes,
        "created_at": alert.created_at,
        "updated_at": alert.updated_at,
        "student_name": None,
        "student_code": None,
        "class_name": None,
        "recipients": []
    }


@router.post("/run-check")
async def run_intervention_check(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Run the five-week review agent to check for students needing intervention. Admin only."""
    service = InterventionService(db)
    alerts = await service.run_intervention_check()
    return {
        "message": f"Intervention check completed. {len(alerts)} new alerts created.",
        "alerts_created": len(alerts)
    }


@router.get("/flagged-students")
async def get_flagged_students(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get students with active intervention alerts."""
    service = InterventionService(db)
    students, total = await service.get_flagged_students(limit=limit, offset=offset)
    return {"students": students, "total": total}


# ============== Analytics Endpoints ==============

@router.get("/analytics/student/{student_id}", response_model=StudentAnalytics)
async def get_student_analytics(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive analytics for a student."""
    service = InterventionService(db)
    analytics = await service.get_student_analytics(student_id)
    if not analytics:
        raise HTTPException(status_code=404, detail="Student not found")
    return analytics


@router.get("/analytics/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get admin dashboard statistics. Admin only."""
    service = InterventionService(db)
    stats = await service.get_dashboard_stats()
    return stats


# ============== Report Configuration Endpoints ==============

@router.post("/reports/configurations", response_model=ReportConfigurationResponse)
async def create_report_configuration(
    data: ReportConfigurationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Create a new report configuration. Admin only."""
    service = AuditService(db)
    config = await service.create_configuration(data, current_user.id)
    return config


@router.get("/reports/configurations", response_model=List[ReportConfigurationResponse])
async def get_report_configurations(
    report_type: Optional[ReportType] = None,
    include_public: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get report configurations. Admin only."""
    service = AuditService(db)
    configs = await service.get_configurations(
        user_id=current_user.id,
        report_type=report_type,
        include_public=include_public
    )
    return configs


@router.get("/reports/configurations/{config_id}", response_model=ReportConfigurationResponse)
async def get_report_configuration(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get a specific report configuration. Admin only."""
    service = AuditService(db)
    config = await service.get_configuration(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return config


@router.put("/reports/configurations/{config_id}", response_model=ReportConfigurationResponse)
async def update_report_configuration(
    config_id: UUID,
    data: ReportConfigurationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update a report configuration. Admin only."""
    service = AuditService(db)
    config = await service.update_configuration(config_id, data)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return config


@router.delete("/reports/configurations/{config_id}")
async def delete_report_configuration(
    config_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Delete a report configuration. Admin only."""
    service = AuditService(db)
    deleted = await service.delete_configuration(config_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return {"message": "Configuration deleted successfully"}


@router.post("/reports/generate", response_model=GeneratedReportResponse)
async def generate_report(
    data: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Generate a new report. Admin only."""
    service = AuditService(db)
    report = await service.create_report_record(data, current_user.id)
    # Note: Actual report generation would typically be done asynchronously
    # For now, we just create the record
    return report


@router.get("/reports/generated")
async def get_generated_reports(
    report_type: Optional[ReportType] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get generated reports. Admin only."""
    service = AuditService(db)
    reports, total = await service.get_generated_reports(
        user_id=current_user.id,
        report_type=report_type,
        limit=limit,
        offset=offset
    )
    return {"reports": reports, "total": total}


@router.get("/reports/generated/{report_id}", response_model=GeneratedReportResponse)
async def get_generated_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get a specific generated report. Admin only."""
    service = AuditService(db)
    report = await service.get_generated_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


# ============== Audit Log Endpoints ==============

@router.get("/audit-logs")
async def get_audit_logs(
    user_id: Optional[UUID] = None,
    action: Optional[AuditAction] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get audit logs. Admin only."""
    service = AuditService(db)
    filters = AuditLogFilter(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        offset=offset
    )
    logs, total = await service.get_audit_logs(filters)
    return {"logs": logs, "total": total}


@router.get("/audit-logs/recent")
async def get_recent_activity(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get recent activity. Admin only."""
    service = AuditService(db)
    logs = await service.get_recent_activity(limit=limit)
    return {"logs": logs}


@router.get("/audit-logs/user/{user_id}/summary")
async def get_user_activity_summary(
    user_id: UUID,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get activity summary for a user. Admin only."""
    service = AuditService(db)
    summary = await service.get_user_activity_summary(user_id, days=days)
    return summary
