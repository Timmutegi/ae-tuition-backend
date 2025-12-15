from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class Class(Base):
    __tablename__ = "classes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False)
    year_group = Column(Integer, nullable=False)
    academic_year = Column(String(20), nullable=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    students = relationship("Student", back_populates="class_info")
    teacher = relationship("User", foreign_keys=[teacher_id])
    test_assignments = relationship("TestAssignment", back_populates="class_info")
    teacher_assignments = relationship("TeacherClassAssignment", back_populates="class_info")

    def __repr__(self):
        return f"<Class(name='{self.name}', year_group={self.year_group})>"