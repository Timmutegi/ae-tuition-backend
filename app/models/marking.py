"""
Marking Models for Teacher Assessment System

This module contains models for:
- Manual marks for open-ended questions
- Creative writing submissions with image uploads
- Image annotations (highlights, comments, drawings)
- Teacher feedback and comments
"""

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class MarkingStatus(enum.Enum):
    """Status of a response requiring manual marking."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    MARKED = "marked"
    REVIEWED = "reviewed"  # Double-checked by another teacher
    RETURNED = "returned"  # Returned for re-marking


class AnnotationType(enum.Enum):
    """Types of annotations that can be made on creative writing."""
    HIGHLIGHT = "highlight"
    UNDERLINE = "underline"
    STRIKETHROUGH = "strikethrough"
    COMMENT = "comment"
    DRAWING = "drawing"  # Freehand drawing
    TEXT = "text"  # Text annotation
    STAMP = "stamp"  # Predefined stamps (checkmark, X, star, etc.)
    ARROW = "arrow"
    CIRCLE = "circle"
    RECTANGLE = "rectangle"


class CreativeWritingSubmission(Base):
    """
    Student submissions for creative writing questions.

    Students upload images of their handwritten work which teachers
    can then annotate and grade.
    """
    __tablename__ = "creative_writing_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey('test_attempts.id'), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey('questions.id'), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey('students.id'), nullable=False)

    # Image storage
    image_url = Column(String(500))  # CloudFront URL
    s3_key = Column(String(255))  # S3 key for the image
    thumbnail_url = Column(String(500))  # Thumbnail for preview

    # Image metadata
    original_filename = Column(String(255))
    file_size_bytes = Column(Integer)
    image_width = Column(Integer)
    image_height = Column(Integer)
    mime_type = Column(String(50))

    # Submission info
    submitted_at = Column(DateTime(timezone=True), default=func.now())
    resubmitted = Column(Boolean, default=False)
    resubmission_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    attempt = relationship("TestAttempt")
    question = relationship("Question")
    student = relationship("Student")
    annotations = relationship("ImageAnnotation", back_populates="submission", cascade="all, delete-orphan")
    manual_mark = relationship("ManualMark", back_populates="creative_submission", uselist=False)


class ImageAnnotation(Base):
    """
    Annotations made by teachers on creative writing submissions.

    Stores the annotation data in a format compatible with Fabric.js
    for rendering on the frontend.
    """
    __tablename__ = "image_annotations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id = Column(UUID(as_uuid=True), ForeignKey('creative_writing_submissions.id'), nullable=False)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)

    # Annotation type and data
    annotation_type = Column(SQLEnum(AnnotationType), nullable=False)

    # Fabric.js object data (position, size, style, etc.)
    fabric_data = Column(JSONB, nullable=False)

    # For comment annotations
    comment_text = Column(Text)

    # Position (for quick filtering/sorting)
    x_position = Column(Float)
    y_position = Column(Float)

    # Styling
    color = Column(String(20), default="#FF0000")  # Red by default
    stroke_width = Column(Integer, default=2)

    # Status
    is_visible = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    submission = relationship("CreativeWritingSubmission", back_populates="annotations")
    teacher = relationship("User")


class ManualMark(Base):
    """
    Manual marks assigned by teachers for open-ended questions.

    Used for creative writing, essay questions, and any response
    that requires human evaluation.
    """
    __tablename__ = "manual_marks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    response_id = Column(UUID(as_uuid=True), ForeignKey('question_responses.id'), nullable=False, unique=True)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey('test_attempts.id'), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey('questions.id'), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey('students.id'), nullable=False)

    # For creative writing submissions
    creative_submission_id = Column(UUID(as_uuid=True), ForeignKey('creative_writing_submissions.id'), nullable=True)

    # Marking status
    status = Column(SQLEnum(MarkingStatus), default=MarkingStatus.PENDING)

    # Marks
    points_awarded = Column(Float)
    max_points = Column(Float, nullable=False)
    percentage = Column(Float)  # Calculated from points_awarded / max_points

    # Teacher feedback
    feedback = Column(Text)
    strengths = Column(Text)  # What the student did well
    improvements = Column(Text)  # Areas for improvement

    # Rubric-based marking (optional)
    rubric_scores = Column(JSONB)  # {"criterion1": score, "criterion2": score, ...}

    # Marking workflow
    marked_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    marked_at = Column(DateTime(timezone=True), nullable=True)

    # Review workflow (for double-checking)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text)

    # Time tracking
    marking_started_at = Column(DateTime(timezone=True), nullable=True)
    time_spent_seconds = Column(Integer)  # Time spent marking

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    response = relationship("QuestionResponse")
    attempt = relationship("TestAttempt")
    question = relationship("Question")
    student = relationship("Student")
    creative_submission = relationship("CreativeWritingSubmission", back_populates="manual_mark")
    marker = relationship("User", foreign_keys=[marked_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class TeacherComment(Base):
    """
    General comments from teachers on student performance.

    Can be attached to attempts, results, or specific questions.
    """
    __tablename__ = "teacher_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey('students.id'), nullable=False)

    # What this comment is about (one of these should be set)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey('test_attempts.id'), nullable=True)
    result_id = Column(UUID(as_uuid=True), ForeignKey('test_results.id'), nullable=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey('questions.id'), nullable=True)

    # Comment content
    comment_text = Column(Text, nullable=False)
    comment_type = Column(String(50))  # 'feedback', 'encouragement', 'concern', 'general'

    # Visibility
    visible_to_student = Column(Boolean, default=True)
    visible_to_parents = Column(Boolean, default=False)

    # Status
    is_pinned = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    teacher = relationship("User")
    student = relationship("Student")
    attempt = relationship("TestAttempt")
    result = relationship("TestResult")
    question = relationship("Question")


class StudentCreativeWorkStatus(enum.Enum):
    """Status of standalone creative writing submissions."""
    PENDING = "pending"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class StudentCreativeWork(Base):
    """
    Standalone creative writing submissions from students.

    Unlike CreativeWritingSubmission (which is tied to test questions),
    this model is for independent creative work uploads that students
    can submit at any time for teacher review.
    """
    __tablename__ = "student_creative_works"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey('students.id'), nullable=False)

    # Submission details
    title = Column(String(255), nullable=False)
    description = Column(Text)

    # Image storage
    image_url = Column(String(500), nullable=False)  # CloudFront URL
    s3_key = Column(String(255), nullable=False)  # S3 key for the image

    # Image metadata
    original_filename = Column(String(255))
    file_size_bytes = Column(Integer)
    mime_type = Column(String(50))

    # Status and feedback
    status = Column(SQLEnum(StudentCreativeWorkStatus), default=StudentCreativeWorkStatus.PENDING)
    feedback = Column(Text)  # Teacher feedback

    # Review info
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    submitted_at = Column(DateTime(timezone=True), default=func.now())
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    student = relationship("Student")
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class MarkingQueue(Base):
    """
    Queue of items awaiting manual marking.

    Provides a centralized view of all pending marking work
    with priority and assignment tracking.
    """
    __tablename__ = "marking_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    manual_mark_id = Column(UUID(as_uuid=True), ForeignKey('manual_marks.id'), nullable=False, unique=True)

    # Assignment info
    test_id = Column(UUID(as_uuid=True), ForeignKey('tests.id'), nullable=False)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey('test_assignments.id'), nullable=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey('classes.id'), nullable=True)

    # Priority and ordering
    priority = Column(Integer, default=0)  # Higher = more urgent
    due_date = Column(DateTime(timezone=True))  # When marking should be completed

    # Assignment to teacher
    assigned_to = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)

    # Status tracking
    is_locked = Column(Boolean, default=False)  # Locked when someone is marking
    locked_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    manual_mark = relationship("ManualMark")
    test = relationship("Test")
    assignment = relationship("TestAssignment")
    student_class = relationship("Class")
    assigned_teacher = relationship("User", foreign_keys=[assigned_to])
    locked_by_user = relationship("User", foreign_keys=[locked_by])
