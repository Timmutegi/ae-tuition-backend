from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class SupervisorProfile(Base):
    """Supervisor profile for academic supervisors and support staff."""
    __tablename__ = "supervisor_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="supervisor_profile")
    student_assignments = relationship("SupervisorStudentAssignment", back_populates="supervisor", cascade="all, delete-orphan")
    class_assignments = relationship("SupervisorClassAssignment", back_populates="supervisor", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SupervisorProfile(user_id='{self.user_id}')>"


class SupervisorStudentAssignment(Base):
    """Supervisors assigned to specific students for welfare tracking."""
    __tablename__ = "supervisor_student_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supervisor_id = Column(UUID(as_uuid=True), ForeignKey("supervisor_profiles.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), default=func.now())
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    supervisor = relationship("SupervisorProfile", back_populates="student_assignments")
    student = relationship("Student", back_populates="supervisor_assignments")
    assigner = relationship("User", foreign_keys=[assigned_by])

    def __repr__(self):
        return f"<SupervisorStudentAssignment(supervisor_id='{self.supervisor_id}', student_id='{self.student_id}')>"


class SupervisorClassAssignment(Base):
    """Supervisors assigned to classes - allows supervisor to view all students in class."""
    __tablename__ = "supervisor_class_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supervisor_id = Column(UUID(as_uuid=True), ForeignKey("supervisor_profiles.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    is_primary = Column(Boolean, default=False)  # Primary supervisor for the class
    assigned_at = Column(DateTime(timezone=True), default=func.now())
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    supervisor = relationship("SupervisorProfile", back_populates="class_assignments")
    class_info = relationship("Class", backref="supervisor_assignments")
    assigner = relationship("User", foreign_keys=[assigned_by])

    def __repr__(self):
        return f"<SupervisorClassAssignment(supervisor_id='{self.supervisor_id}', class_id='{self.class_id}')>"
