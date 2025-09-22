from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any, Dict
from datetime import datetime
from uuid import UUID

from app.models.question import QuestionType, QuestionFormat, Difficulty, OptionType


class ReadingPassageBase(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    content: str = Field(..., min_length=1)
    word_count: Optional[int] = Field(None, ge=1)
    reading_level: Optional[str] = Field(None, max_length=20)
    source: Optional[str] = Field(None, max_length=255)
    author: Optional[str] = Field(None, max_length=255)
    genre: Optional[str] = Field(None, max_length=50)
    subject: Optional[str] = Field(None, max_length=50)


class ReadingPassageCreate(ReadingPassageBase):
    pass


class ReadingPassageUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    content: Optional[str] = Field(None, min_length=1)
    word_count: Optional[int] = Field(None, ge=1)
    reading_level: Optional[str] = Field(None, max_length=20)
    source: Optional[str] = Field(None, max_length=255)
    author: Optional[str] = Field(None, max_length=255)
    genre: Optional[str] = Field(None, max_length=50)
    subject: Optional[str] = Field(None, max_length=50)


class ReadingPassageResponse(ReadingPassageBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class AnswerOptionBase(BaseModel):
    option_text: str = Field(..., min_length=1)
    option_type: OptionType = OptionType.TEXT
    option_group: Optional[str] = Field(None, max_length=20)
    is_correct: bool = False
    order_number: Optional[int] = Field(None, ge=1)
    image_url: Optional[str] = None
    s3_key: Optional[str] = Field(None, max_length=255)
    pattern_data: Optional[Dict[str, Any]] = None


class AnswerOptionCreate(AnswerOptionBase):
    pass


class AnswerOptionUpdate(BaseModel):
    option_text: Optional[str] = Field(None, min_length=1)
    option_type: Optional[OptionType] = None
    option_group: Optional[str] = Field(None, max_length=20)
    is_correct: Optional[bool] = None
    order_number: Optional[int] = Field(None, ge=1)
    image_url: Optional[str] = None
    s3_key: Optional[str] = Field(None, max_length=255)
    pattern_data: Optional[Dict[str, Any]] = None


class AnswerOptionResponse(AnswerOptionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_id: UUID
    created_at: datetime


class QuestionBase(BaseModel):
    question_text: str = Field(..., min_length=1)
    question_type: QuestionType
    question_format: QuestionFormat = QuestionFormat.STANDARD
    passage_id: Optional[UUID] = None
    passage_reference_lines: Optional[str] = Field(None, max_length=50)
    subject: Optional[str] = Field(None, max_length=50)
    topic: Optional[str] = Field(None, max_length=100)
    difficulty: Difficulty = Difficulty.MEDIUM
    points: int = Field(default=1, ge=1)
    image_url: Optional[str] = None
    s3_key: Optional[str] = Field(None, max_length=255)
    explanation: Optional[str] = None
    instruction_text: Optional[str] = None
    pattern_sequence: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class QuestionCreate(QuestionBase):
    answer_options: List[AnswerOptionCreate] = []


class QuestionUpdate(BaseModel):
    question_text: Optional[str] = Field(None, min_length=1)
    question_format: Optional[QuestionFormat] = None
    passage_id: Optional[UUID] = None
    passage_reference_lines: Optional[str] = Field(None, max_length=50)
    subject: Optional[str] = Field(None, max_length=50)
    topic: Optional[str] = Field(None, max_length=100)
    difficulty: Optional[Difficulty] = None
    points: Optional[int] = Field(None, ge=1)
    image_url: Optional[str] = None
    s3_key: Optional[str] = Field(None, max_length=255)
    explanation: Optional[str] = None
    instruction_text: Optional[str] = None
    pattern_sequence: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class QuestionResponse(QuestionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    answer_options: List[AnswerOptionResponse] = []


class QuestionWithPassage(QuestionResponse):
    passage: Optional[ReadingPassageResponse] = None


class QuestionFilters(BaseModel):
    question_type: Optional[QuestionType] = None
    question_format: Optional[QuestionFormat] = None
    subject: Optional[str] = None
    difficulty: Optional[Difficulty] = None
    passage_id: Optional[UUID] = None
    search: Optional[str] = None
    tags: Optional[List[str]] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)


class PassageFilters(BaseModel):
    subject: Optional[str] = None
    genre: Optional[str] = None
    reading_level: Optional[str] = None
    search: Optional[str] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)


class QuestionBankStats(BaseModel):
    total_questions: int
    questions_by_type: Dict[str, int]
    questions_by_subject: Dict[str, int]
    questions_by_difficulty: Dict[str, int]
    total_passages: int
    passages_by_subject: Dict[str, int]