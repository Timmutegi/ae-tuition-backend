"""
Weekly Attendance Model for tracking student attendance and book comments.

This model stores weekly attendance records with integrated book-based comments
for tracking which books students need help with, haven't completed, etc.
"""

from sqlalchemy import Column, String, DateTime, Boolean, Integer, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class WeeklyAttendance(Base):
    """
    Weekly attendance record with book comments.

    Each student has one record per week per academic year.
    The comments JSONB field stores book IDs for each category:
    - help_in: Books the student needs help with (H)
    - incomplete: Books not completed that week (I/c)
    - unmarked: Books not marked (u/m)
    - at_home: Books left at home or lost (a/h)
    """
    __tablename__ = "weekly_attendance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    week_number = Column(Integer, nullable=False)  # 1-40
    academic_year = Column(String(20), nullable=False)  # e.g., "2025-2026"

    # Attendance
    is_present = Column(Boolean, nullable=True)  # null = not yet marked

    # Book comments - JSONB storing arrays of book UUIDs
    # Format: {"help_in": ["uuid1", "uuid2"], "incomplete": [], "unmarked": [], "at_home": []}
    comments = Column(JSONB, nullable=False, default=dict)

    # Additional notes
    notes = Column(Text, nullable=True)

    # Who recorded this attendance
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    student = relationship("Student", backref="weekly_attendance_records")
    recorder = relationship("User", foreign_keys=[recorded_by])

    # Ensure one record per student per week per academic year
    __table_args__ = (
        UniqueConstraint('student_id', 'week_number', 'academic_year', name='unique_student_week_year'),
    )

    def __repr__(self):
        return f"<WeeklyAttendance(student_id='{self.student_id}', week={self.week_number}, present={self.is_present})>"

    @property
    def help_in_books(self):
        """Get list of book IDs the student needs help with."""
        return self.comments.get('help_in', []) if self.comments else []

    @property
    def incomplete_books(self):
        """Get list of incomplete book IDs."""
        return self.comments.get('incomplete', []) if self.comments else []

    @property
    def unmarked_books(self):
        """Get list of unmarked book IDs."""
        return self.comments.get('unmarked', []) if self.comments else []

    @property
    def at_home_books(self):
        """Get list of book IDs left at home."""
        return self.comments.get('at_home', []) if self.comments else []
