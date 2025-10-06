from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class QuestionSet(Base):
    __tablename__ = "question_sets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    subject = Column(String(50))
    grade_level = Column(String(20))
    total_points = Column(Integer, default=0)
    question_count = Column(Integer, default=0)
    metadata_json = Column(JSONB)  # Additional metadata
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    question_set_items = relationship("QuestionSetItem", back_populates="question_set", cascade="all, delete-orphan")
    test_question_sets = relationship("TestQuestionSet", back_populates="question_set")

    def __repr__(self):
        return f"<QuestionSet(name='{self.name}', subject='{self.subject}', question_count={self.question_count})>"


class QuestionSetItem(Base):
    __tablename__ = "question_set_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_set_id = Column(UUID(as_uuid=True), ForeignKey('question_sets.id', ondelete='CASCADE'), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey('questions.id'), nullable=False)
    order_number = Column(Integer, nullable=False)
    points_override = Column(Integer)  # Override question's default points if needed
    created_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    question_set = relationship("QuestionSet", back_populates="question_set_items")
    question = relationship("Question")

    def __repr__(self):
        return f"<QuestionSetItem(set_id='{self.question_set_id}', question_id='{self.question_id}', order={self.order_number})>"


class TestQuestionSet(Base):
    __tablename__ = "test_question_sets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_id = Column(UUID(as_uuid=True), ForeignKey('tests.id', ondelete='CASCADE'), nullable=False)
    question_set_id = Column(UUID(as_uuid=True), ForeignKey('question_sets.id'), nullable=False)
    order_number = Column(Integer, nullable=False)  # Order of the set within the test
    created_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    test = relationship("Test", back_populates="test_question_sets")
    question_set = relationship("QuestionSet", back_populates="test_question_sets")

    def __repr__(self):
        return f"<TestQuestionSet(test_id='{self.test_id}', question_set_id='{self.question_set_id}', order={self.order_number})>"