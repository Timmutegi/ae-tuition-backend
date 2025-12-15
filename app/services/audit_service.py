"""
Audit and Report Configuration service for Phase 6: Advanced Analytics & Intervention System.
Handles report configurations, generation tracking, and audit logging.
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
import json
import csv
import io
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intervention import (
    ReportConfiguration, GeneratedReport, AuditLog,
    ReportType, ReportFormat, AuditAction
)
from app.models.student import Student
from app.models.class_model import Class
from app.models.test import TestAttempt, TestResult, Test, AttemptStatus
from app.models.support import AttendanceRecord, AttendanceStatus
from app.models.user import User
from app.schemas.intervention import (
    ReportConfigurationCreate, ReportConfigurationUpdate,
    GenerateReportRequest, AuditLogCreate, AuditLogFilter
)


class AuditService:
    """Service for audit logging and report configuration management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============== Report Configuration ==============

    async def create_configuration(
        self,
        data: ReportConfigurationCreate,
        created_by: UUID
    ) -> ReportConfiguration:
        """Create a new report configuration."""
        config = ReportConfiguration(
            **data.model_dump(),
            created_by=created_by
        )
        self.db.add(config)
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def get_configuration(self, config_id: UUID) -> Optional[ReportConfiguration]:
        """Get a configuration by ID."""
        result = await self.db.execute(
            select(ReportConfiguration).where(ReportConfiguration.id == config_id)
        )
        return result.scalar_one_or_none()

    async def get_configurations(
        self,
        user_id: Optional[UUID] = None,
        report_type: Optional[ReportType] = None,
        include_public: bool = True
    ) -> List[ReportConfiguration]:
        """Get report configurations."""
        query = select(ReportConfiguration)

        conditions = []
        if user_id:
            if include_public:
                conditions.append(
                    or_(
                        ReportConfiguration.created_by == user_id,
                        ReportConfiguration.is_public == True
                    )
                )
            else:
                conditions.append(ReportConfiguration.created_by == user_id)

        if report_type:
            conditions.append(ReportConfiguration.report_type == report_type)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(ReportConfiguration.name)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_configuration(
        self,
        config_id: UUID,
        data: ReportConfigurationUpdate
    ) -> Optional[ReportConfiguration]:
        """Update a configuration."""
        config = await self.get_configuration(config_id)
        if not config:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(config, field, value)

        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def delete_configuration(self, config_id: UUID) -> bool:
        """Delete a configuration."""
        config = await self.get_configuration(config_id)
        if not config:
            return False

        await self.db.delete(config)
        await self.db.commit()
        return True

    # ============== Report Generation Tracking ==============

    async def create_report_record(
        self,
        request: GenerateReportRequest,
        generated_by: UUID,
        name: Optional[str] = None
    ) -> GeneratedReport:
        """Create a record for a generated report."""
        config = None
        report_type = request.report_type
        parameters = request.parameters or {}

        if request.configuration_id:
            config = await self.get_configuration(request.configuration_id)
            if config:
                report_type = config.report_type
                parameters = {**(config.filters or {}), **parameters}
                name = name or config.name

        if not report_type:
            raise ValueError("Report type is required")

        if not name:
            name = f"{report_type.value.replace('_', ' ').title()} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        report = GeneratedReport(
            configuration_id=request.configuration_id,
            name=name,
            report_type=report_type,
            format=request.format,
            parameters=parameters,
            generated_by=generated_by,
            is_ready=False
        )
        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)
        return report

    async def update_report_status(
        self,
        report_id: UUID,
        is_ready: bool,
        row_count: Optional[int] = None,
        file_path: Optional[str] = None,
        file_url: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> Optional[GeneratedReport]:
        """Update a report's status after generation."""
        result = await self.db.execute(
            select(GeneratedReport).where(GeneratedReport.id == report_id)
        )
        report = result.scalar_one_or_none()
        if not report:
            return None

        report.is_ready = is_ready
        if row_count is not None:
            report.row_count = row_count
        if file_path:
            report.file_path = file_path
        if file_url:
            report.file_url = file_url
        if file_size_bytes is not None:
            report.file_size_bytes = file_size_bytes
        if error_message:
            report.error_message = error_message

        await self.db.commit()
        await self.db.refresh(report)
        return report

    async def get_generated_reports(
        self,
        user_id: Optional[UUID] = None,
        report_type: Optional[ReportType] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[GeneratedReport], int]:
        """Get generated reports."""
        query = select(GeneratedReport)

        conditions = []
        if user_id:
            conditions.append(GeneratedReport.generated_by == user_id)
        if report_type:
            conditions.append(GeneratedReport.report_type == report_type)

        if conditions:
            query = query.where(and_(*conditions))

        # Count
        count_query = select(func.count(GeneratedReport.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Get results
        query = query.order_by(desc(GeneratedReport.generated_at)).offset(offset).limit(limit)
        result = await self.db.execute(query)
        reports = list(result.scalars().all())

        return reports, total

    async def get_generated_report(self, report_id: UUID) -> Optional[GeneratedReport]:
        """Get a specific generated report."""
        result = await self.db.execute(
            select(GeneratedReport).where(GeneratedReport.id == report_id)
        )
        return result.scalar_one_or_none()

    # ============== Audit Logging ==============

    async def create_audit_log(
        self,
        user_id: Optional[UUID],
        data: AuditLogCreate,
        user_email: Optional[str] = None,
        user_role: Optional[str] = None
    ) -> AuditLog:
        """Create an audit log entry."""
        log = AuditLog(
            user_id=user_id,
            user_email=user_email,
            user_role=user_role,
            **data.model_dump()
        )
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def get_audit_logs(
        self,
        filters: AuditLogFilter
    ) -> Tuple[List[AuditLog], int]:
        """Get audit logs with filtering."""
        query = select(AuditLog)

        conditions = []
        if filters.user_id:
            conditions.append(AuditLog.user_id == filters.user_id)
        if filters.action:
            conditions.append(AuditLog.action == filters.action)
        if filters.entity_type:
            conditions.append(AuditLog.entity_type == filters.entity_type)
        if filters.entity_id:
            conditions.append(AuditLog.entity_id == filters.entity_id)
        if filters.start_date:
            conditions.append(AuditLog.timestamp >= filters.start_date)
        if filters.end_date:
            conditions.append(AuditLog.timestamp <= filters.end_date)

        if conditions:
            query = query.where(and_(*conditions))

        # Count
        count_query = select(func.count(AuditLog.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Get results
        query = query.order_by(desc(AuditLog.timestamp)).offset(filters.offset).limit(filters.limit)
        result = await self.db.execute(query)
        logs = list(result.scalars().all())

        return logs, total

    async def log_action(
        self,
        user: Optional[User],
        action: AuditAction,
        entity_type: str,
        entity_id: Optional[str] = None,
        entity_name: Optional[str] = None,
        description: Optional[str] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        request_info: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """Convenience method to log an action."""
        data = AuditLogCreate(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            description=description,
            old_values=old_values,
            new_values=new_values,
            ip_address=request_info.get('ip_address') if request_info else None,
            user_agent=request_info.get('user_agent') if request_info else None,
            session_id=request_info.get('session_id') if request_info else None
        )

        return await self.create_audit_log(
            user_id=user.id if user else None,
            data=data,
            user_email=user.email if user else None,
            user_role=user.role.value if user else None
        )

    async def get_recent_activity(
        self,
        limit: int = 20,
        entity_types: Optional[List[str]] = None
    ) -> List[AuditLog]:
        """Get recent activity for dashboard."""
        query = select(AuditLog)

        if entity_types:
            query = query.where(AuditLog.entity_type.in_(entity_types))

        query = query.order_by(desc(AuditLog.timestamp)).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_user_activity_summary(
        self,
        user_id: UUID,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get activity summary for a user."""
        start_date = datetime.utcnow() - timedelta(days=days)

        # Count by action type
        action_counts = await self.db.execute(
            select(AuditLog.action, func.count(AuditLog.id))
            .where(
                and_(
                    AuditLog.user_id == user_id,
                    AuditLog.timestamp >= start_date
                )
            )
            .group_by(AuditLog.action)
        )

        counts = {row[0].value: row[1] for row in action_counts}

        # Count by entity type
        entity_counts = await self.db.execute(
            select(AuditLog.entity_type, func.count(AuditLog.id))
            .where(
                and_(
                    AuditLog.user_id == user_id,
                    AuditLog.timestamp >= start_date
                )
            )
            .group_by(AuditLog.entity_type)
        )

        entities = {row[0]: row[1] for row in entity_counts}

        return {
            'period_days': days,
            'action_counts': counts,
            'entity_counts': entities,
            'total_actions': sum(counts.values())
        }
