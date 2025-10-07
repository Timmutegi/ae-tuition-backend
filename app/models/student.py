from sqlalchemy import Column, String, Integer, Date, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum

from app.core.database import Base


class StudentStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    GRADUATED = "graduated"


class Student(Base):
    __tablename__ = "students"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey('classes.id'), nullable=True)
    year_group = Column(Integer, nullable=False)
    student_code = Column(String(20), unique=True, nullable=True)
    enrollment_date = Column(Date, default=func.current_date())
    status = Column(SQLEnum(StudentStatus), default=StudentStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="student_profile")
    class_info = relationship("Class", back_populates="students")
    student_test_assignments = relationship("StudentTestAssignment", back_populates="student")
    test_attempts = relationship("TestAttempt", back_populates="student")
    test_results = relationship("TestResult", back_populates="student")

    def __repr__(self):
        return f"<Student(user_id='{self.user_id}', student_code='{self.student_code}')>"