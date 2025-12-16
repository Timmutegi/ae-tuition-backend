from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class TeacherProfile(Base):
    """Teacher profile with additional information linked to User."""
    __tablename__ = "teacher_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="teacher_profile")
    class_assignments = relationship("TeacherClassAssignment", back_populates="teacher", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TeacherProfile(user_id='{self.user_id}')>"


class TeacherClassAssignment(Base):
    """Many-to-many relationship between teachers and classes."""
    __tablename__ = "teacher_class_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teacher_profiles.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    is_primary = Column(Boolean, default=False)  # Primary teacher for the class
    assigned_at = Column(DateTime(timezone=True), default=func.now())
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    teacher = relationship("TeacherProfile", back_populates="class_assignments")
    class_info = relationship("Class", back_populates="teacher_assignments")
    assigner = relationship("User", foreign_keys=[assigned_by])

    # Unique constraint to prevent duplicate assignments
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )

    def __repr__(self):
        return f"<TeacherClassAssignment(teacher_id='{self.teacher_id}', class_id='{self.class_id}')>"
