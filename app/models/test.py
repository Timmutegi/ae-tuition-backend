from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Boolean, DECIMAL
from sqlalchemy.dialects.postgresql import UUID, ENUM, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum

from app.core.database import Base


class TestType(enum.Enum):
    VERBAL_REASONING = "Verbal Reasoning"
    NON_VERBAL_REASONING = "Non-Verbal Reasoning"
    ENGLISH = "English"
    MATHEMATICS = "Mathematics"


class TestFormat(enum.Enum):
    STANDARD = "standard"
    PASSAGE_BASED = "passage_based"
    MIXED_FORMAT = "mixed_format"
    VISUAL_PATTERN = "visual_pattern"


class TestStatus(enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    ARCHIVED = "archived"


class QuestionOrder(enum.Enum):
    SEQUENTIAL = "sequential"
    RANDOM = "random"
    GROUPED = "grouped"


class Test(Base):
    __tablename__ = "tests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    type = Column(ENUM(TestType), nullable=False)
    test_format = Column(ENUM(TestFormat), default=TestFormat.STANDARD)
    duration_minutes = Column(Integer, nullable=False)
    warning_intervals = Column(JSONB, default=[10, 5, 1])
    pass_mark = Column(Integer, default=50)
    total_marks = Column(Integer)
    instructions = Column(Text)
    question_order = Column(ENUM(QuestionOrder), default=QuestionOrder.SEQUENTIAL)
    status = Column(ENUM(TestStatus), default=TestStatus.DRAFT)
    template_id = Column(UUID(as_uuid=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    test_questions = relationship("TestQuestion", back_populates="test", cascade="all, delete-orphan")
    test_question_sets = relationship("TestQuestionSet", back_populates="test", cascade="all, delete-orphan")
    test_assignments = relationship("TestAssignment", back_populates="test", cascade="all, delete-orphan")
    student_test_assignments = relationship("StudentTestAssignment", back_populates="test", cascade="all, delete-orphan")
    test_attempts = relationship("TestAttempt", back_populates="test")
    test_results = relationship("TestResult", back_populates="test")

    def __repr__(self):
        return f"<Test(title='{self.title}', type='{self.type.value}', status='{self.status.value}')>"


class TestQuestion(Base):
    __tablename__ = "test_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id = Column(UUID(as_uuid=True), ForeignKey('tests.id', ondelete='CASCADE'), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey('questions.id'), nullable=False)
    passage_id = Column(UUID(as_uuid=True), ForeignKey('reading_passages.id'), nullable=True)
    order_number = Column(Integer, nullable=False)
    question_group = Column(String(50))
    points = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    test = relationship("Test", back_populates="test_questions")
    question = relationship("Question", back_populates="test_questions")
    passage = relationship("ReadingPassage", back_populates="test_questions")

    def __repr__(self):
        return f"<TestQuestion(test_id='{self.test_id}', question_id='{self.question_id}', order={self.order_number})>"


class AssignmentStatus(enum.Enum):
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TestAssignment(Base):
    __tablename__ = "test_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id = Column(UUID(as_uuid=True), ForeignKey('tests.id', ondelete='CASCADE'), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey('classes.id'), nullable=False)
    scheduled_start = Column(DateTime(timezone=True), nullable=False)
    scheduled_end = Column(DateTime(timezone=True), nullable=False)
    buffer_time_minutes = Column(Integer, default=0)
    allow_late_submission = Column(Boolean, default=False)
    late_submission_grace_minutes = Column(Integer, default=0)
    auto_submit = Column(Boolean, default=True)
    extended_time_students = Column(JSONB)
    custom_instructions = Column(Text)
    status = Column(ENUM(AssignmentStatus), default=AssignmentStatus.SCHEDULED)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    test = relationship("Test", back_populates="test_assignments")
    class_info = relationship("Class", back_populates="test_assignments")
    creator = relationship("User", foreign_keys=[created_by])
    test_attempts = relationship("TestAttempt", back_populates="assignment")

    def __repr__(self):
        return f"<TestAssignment(test_id='{self.test_id}', class_id='{self.class_id}', status='{self.status.value}')>"


class StudentTestAssignment(Base):
    __tablename__ = "student_test_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id = Column(UUID(as_uuid=True), ForeignKey('tests.id', ondelete='CASCADE'), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey('students.id'), nullable=False)
    scheduled_start = Column(DateTime(timezone=True), nullable=False)
    scheduled_end = Column(DateTime(timezone=True), nullable=False)
    buffer_time_minutes = Column(Integer, default=0)
    allow_late_submission = Column(Boolean, default=False)
    late_submission_grace_minutes = Column(Integer, default=0)
    auto_submit = Column(Boolean, default=True)
    custom_instructions = Column(Text)
    status = Column(ENUM(AssignmentStatus), default=AssignmentStatus.SCHEDULED)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    test = relationship("Test", back_populates="student_test_assignments")
    student = relationship("Student", back_populates="student_test_assignments")
    creator = relationship("User", foreign_keys=[created_by])
    student_test_attempts = relationship("TestAttempt", back_populates="student_assignment", foreign_keys="[TestAttempt.student_assignment_id]")

    def __repr__(self):
        return f"<StudentTestAssignment(test_id='{self.test_id}', student_id='{self.student_id}', status='{self.status.value}')>"


class AttemptStatus(enum.Enum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    AUTO_SUBMITTED = "auto_submitted"
    CANCELLED = "cancelled"


class TestAttempt(Base):
    __tablename__ = "test_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id = Column(UUID(as_uuid=True), ForeignKey('tests.id'), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey('students.id'), nullable=False)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey('test_assignments.id'), nullable=True)
    student_assignment_id = Column(UUID(as_uuid=True), ForeignKey('student_test_assignments.id'), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    submitted_at = Column(DateTime(timezone=True))
    time_taken = Column(Integer)
    status = Column(ENUM(AttemptStatus), default=AttemptStatus.IN_PROGRESS)
    answers = Column(JSONB)
    browser_info = Column(JSONB)
    ip_address = Column(String(45))
    created_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    test = relationship("Test", back_populates="test_attempts")
    student = relationship("Student", back_populates="test_attempts")
    assignment = relationship("TestAssignment", back_populates="test_attempts", foreign_keys=[assignment_id])
    student_assignment = relationship("StudentTestAssignment", back_populates="student_test_attempts", foreign_keys=[student_assignment_id])
    question_responses = relationship("QuestionResponse", back_populates="attempt", cascade="all, delete-orphan")
    test_result = relationship("TestResult", back_populates="attempt", uselist=False)

    # Anti-cheating relationships
    suspicious_activities = relationship("SuspiciousActivityLog", back_populates="attempt", cascade="all, delete-orphan")
    active_session = relationship("ActiveTestSession", back_populates="attempt", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TestAttempt(test_id='{self.test_id}', student_id='{self.student_id}', status='{self.status.value}')>"


class ResultStatus(enum.Enum):
    PASS = "pass"
    FAIL = "fail"


class TestResult(Base):
    __tablename__ = "test_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey('test_attempts.id', ondelete='CASCADE'), nullable=False, unique=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey('students.id'), nullable=False)
    test_id = Column(UUID(as_uuid=True), ForeignKey('tests.id'), nullable=False)
    total_score = Column(Integer, nullable=False)
    max_score = Column(Integer, nullable=False)
    percentage = Column(DECIMAL(5, 2))
    grade = Column(String(2))
    time_taken = Column(Integer)
    submitted_at = Column(DateTime(timezone=True))
    status = Column(ENUM(ResultStatus))
    question_scores = Column(JSONB)
    analytics_data = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    attempt = relationship("TestAttempt", back_populates="test_result")
    student = relationship("Student", back_populates="test_results")
    test = relationship("Test", back_populates="test_results")

    def __repr__(self):
        return f"<TestResult(test_id='{self.test_id}', student_id='{self.student_id}', score={self.total_score}/{self.max_score})>"