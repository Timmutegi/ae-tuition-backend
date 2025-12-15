"""
Book Model for tracking educational books assigned to students.

Books are used in the attendance tracking system where teachers/supervisors
can record which books students need help with, haven't completed, etc.
"""

from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.core.database import Base


class Book(Base):
    """
    Book model for the attendance tracking system.

    Books are assigned to students weekly and tracked via the comments
    system with categories: Help in (H), Incomplete (I/c), Unmarked (u/m),
    At home (a/h).
    """
    __tablename__ = "books"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    subject = Column(String(50), nullable=False)  # English, VR, NVR, Maths
    is_active = Column(Boolean, default=True, nullable=False)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Book(name='{self.name}', subject='{self.subject}')>"
