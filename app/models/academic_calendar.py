"""
Academic Calendar Configuration Model

Stores academic calendar configuration including break periods.
"""

from sqlalchemy import Column, String, Date, DateTime, Text, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid

from app.core.database import Base


class AcademicCalendarConfig(Base):
    """
    Academic calendar configuration table.

    Stores the academic year configuration including break periods
    and other calendar-related settings.
    """
    __tablename__ = "academic_calendar_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    academic_year = Column(String(20), unique=True, nullable=False)  # e.g., "2025-2026"
    year_start_date = Column(Date, nullable=False)  # First day of academic year
    total_weeks = Column(Integer, default=40, nullable=False)

    # Break periods stored as JSONB for flexibility
    # Format: [{"name": "Christmas Break", "start_date": "2025-12-12", "end_date": "2026-01-02"}, ...]
    break_periods = Column(JSONB, nullable=False, default=list)

    # Additional configuration options
    week_start_day = Column(String(10), default="Friday", nullable=False)  # Day week starts
    week_end_day = Column(String(10), default="Wednesday", nullable=False)  # Day week ends

    # Metadata
    notes = Column(Text)  # Any additional notes about the calendar
    is_active = Column(Boolean, default=True, nullable=False)  # Whether this config is active
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(UUID(as_uuid=True))  # Admin user who created this config

    def __repr__(self):
        return f"<AcademicCalendarConfig(year={self.academic_year}, weeks={self.total_weeks})>"
