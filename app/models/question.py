from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Boolean, DECIMAL
from sqlalchemy.dialects.postgresql import UUID, ENUM, JSONB, ARRAY
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum

from app.core.database import Base


class QuestionType(enum.Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    DROPDOWN_SELECT = "dropdown_select"
    PATTERN_RECOGNITION = "pattern_recognition"
    READING_COMPREHENSION = "reading_comprehension"
    WORD_COMPLETION = "word_completion"
    SENTENCE_COMPLETION = "sentence_completion"
    CLOZE_TEST = "cloze_test"


class QuestionFormat(enum.Enum):
    STANDARD = "standard"
    PASSAGE_BASED = "passage_based"
    VISUAL_PATTERN = "visual_pattern"
    SEQUENCE = "sequence"


class ReadingPassage(Base):
    __tablename__ = "reading_passages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255))
    content = Column(Text, nullable=True)
    image_url = Column(String(500))
    s3_key = Column(String(255))
    word_count = Column(Integer)
    reading_level = Column(String(20))
    source = Column(String(255))
    author = Column(String(255))
    genre = Column(String(50))
    subject = Column(String(50))
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    questions = relationship("Question", back_populates="passage")
    test_questions = relationship("TestQuestion", back_populates="passage")

    def __repr__(self):
        return f"<ReadingPassage(title='{self.title}', subject='{self.subject}', reading_level='{self.reading_level}')>"


class Question(Base):
    __tablename__ = "questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_text = Column(Text, nullable=True)
    question_type = Column(ENUM(QuestionType), nullable=False)
    question_format = Column(ENUM(QuestionFormat), default=QuestionFormat.STANDARD)
    passage_id = Column(UUID(as_uuid=True), ForeignKey('reading_passages.id'), nullable=True)
    passage_reference_lines = Column(String(50))
    subject = Column(String(50))
    points = Column(Integer, default=1)
    image_url = Column(Text)
    s3_key = Column(String(255))
    explanation = Column(Text)
    instruction_text = Column(Text)
    pattern_sequence = Column(JSONB)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    passage = relationship("ReadingPassage", back_populates="questions")
    answer_options = relationship("AnswerOption", back_populates="question", cascade="all, delete-orphan")
    test_questions = relationship("TestQuestion", back_populates="question")
    question_responses = relationship("QuestionResponse", back_populates="question")

    def __repr__(self):
        return f"<Question(type='{self.question_type.value}', subject='{self.subject}')>"


class OptionType(enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    DROPDOWN_ITEM = "dropdown_item"
    PATTERN_SHAPE = "pattern_shape"


class AnswerOption(Base):
    __tablename__ = "answer_options"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id = Column(UUID(as_uuid=True), ForeignKey('questions.id', ondelete='CASCADE'), nullable=False)
    option_text = Column(Text, nullable=False)
    option_type = Column(ENUM(OptionType), default=OptionType.TEXT)
    option_group = Column(String(20))
    is_correct = Column(Boolean, default=False)
    order_number = Column(Integer)
    image_url = Column(Text)
    s3_key = Column(String(255))
    pattern_data = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    question = relationship("Question", back_populates="answer_options")

    def __repr__(self):
        return f"<AnswerOption(question_id='{self.question_id}', option_text='{self.option_text[:50]}...', is_correct={self.is_correct})>"


class QuestionResponse(Base):
    __tablename__ = "question_responses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey('test_attempts.id', ondelete='CASCADE'), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey('questions.id'), nullable=False)
    answer_text = Column(Text)
    selected_options = Column(ARRAY(UUID))
    dropdown_selections = Column(JSONB)
    fill_in_answers = Column(JSONB)
    pattern_response = Column(JSONB)
    is_correct = Column(Boolean)
    partial_score = Column(DECIMAL(5, 2))
    points_earned = Column(Integer, default=0)
    time_spent = Column(Integer)
    answered_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    attempt = relationship("TestAttempt", back_populates="question_responses")
    question = relationship("Question", back_populates="question_responses")

    def __repr__(self):
        return f"<QuestionResponse(attempt_id='{self.attempt_id}', question_id='{self.question_id}', is_correct={self.is_correct})>"