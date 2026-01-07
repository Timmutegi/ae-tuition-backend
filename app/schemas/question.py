from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import Optional, List, Any, Dict
from datetime import datetime
from uuid import UUID

from app.models.question import QuestionType, QuestionFormat, OptionType


class ReadingPassageBase(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    content: Optional[str] = None
    image_url: Optional[str] = None
    s3_key: Optional[str] = Field(None, max_length=255)
    word_count: Optional[int] = Field(None, ge=1)
    reading_level: Optional[str] = Field(None, max_length=20)
    source: Optional[str] = Field(None, max_length=255)
    author: Optional[str] = Field(None, max_length=255)
    genre: Optional[str] = Field(None, max_length=50)
    subject: Optional[str] = Field(None, max_length=50)


class ReadingPassageCreate(ReadingPassageBase):
    @model_validator(mode='after')
    def validate_passage_content(self):
        """Validate that either content or image_url is provided"""
        # Treat empty strings as None
        content = self.content.strip() if self.content else None
        image_url = self.image_url

        if not content and not image_url:
            raise ValueError('Either content (text) or image_url must be provided for the passage')

        # Update content to None if it was empty string
        self.content = content if content else None
        return self


class ReadingPassageUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    content: Optional[str] = None
    image_url: Optional[str] = None
    s3_key: Optional[str] = Field(None, max_length=255)
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
    question_text: Optional[str] = None
    question_type: QuestionType
    question_format: QuestionFormat = QuestionFormat.STANDARD
    passage_id: Optional[UUID] = None
    passage_reference_lines: Optional[str] = Field(None, max_length=50)
    subject: Optional[str] = Field(None, max_length=50)
    points: int = Field(default=1, ge=1)
    image_url: Optional[str] = None
    s3_key: Optional[str] = Field(None, max_length=255)
    explanation: Optional[str] = None
    instruction_text: Optional[str] = None
    pattern_sequence: Optional[Dict[str, Any]] = None

    # Auto-marking fields
    correct_answer: Optional[str] = None  # For text-based answers
    correct_answers: Optional[Dict[str, str]] = None  # For multiple blanks {"1": "answer1", "2": "answer2"}
    case_sensitive: bool = False
    allow_partial_credit: bool = False
    word_bank: Optional[List[str]] = None  # For word bank cloze questions
    letter_template: Optional[Dict[str, Any]] = None  # For letter box questions
    given_word: Optional[str] = Field(None, max_length=100)  # The word to find synonym/antonym for


class QuestionCreate(QuestionBase):
    answer_options: List[AnswerOptionCreate] = []

    @field_validator('passage_id', mode='before')
    @classmethod
    def validate_passage_id(cls, v):
        """Convert empty strings to None for passage_id"""
        if v == '' or v is None:
            return None
        return v

    @field_validator('subject', 'passage_reference_lines', 'explanation', 'instruction_text', 's3_key', mode='before')
    @classmethod
    def validate_optional_strings(cls, v):
        """Convert empty strings to None for optional string fields"""
        if v == '' or (isinstance(v, str) and not v.strip()):
            return None
        return v

    @field_validator('question_text')
    @classmethod
    def validate_question_content(cls, v, info):
        """Validate that either question_text or image_url is provided"""
        # Treat empty strings as None
        question_text = v.strip() if v else None

        # Get the image_url value from the data being validated
        image_url = info.data.get('image_url')

        # Check if both are missing
        if not question_text and not image_url:
            raise ValueError('Either question_text or image_url must be provided')

        # Return None instead of empty string if no text provided
        return question_text if question_text else None


class QuestionUpdate(BaseModel):
    question_text: Optional[str] = None
    question_format: Optional[QuestionFormat] = None
    passage_id: Optional[UUID] = None
    passage_reference_lines: Optional[str] = Field(None, max_length=50)
    subject: Optional[str] = Field(None, max_length=50)
    points: Optional[int] = Field(None, ge=1)
    image_url: Optional[str] = None
    s3_key: Optional[str] = Field(None, max_length=255)
    explanation: Optional[str] = None
    instruction_text: Optional[str] = None
    pattern_sequence: Optional[Dict[str, Any]] = None

    # Auto-marking fields
    correct_answer: Optional[str] = None
    correct_answers: Optional[Dict[str, str]] = None
    case_sensitive: Optional[bool] = None
    allow_partial_credit: Optional[bool] = None
    word_bank: Optional[List[str]] = None
    letter_template: Optional[Dict[str, Any]] = None
    given_word: Optional[str] = Field(None, max_length=100)


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
    passage_id: Optional[UUID] = None
    search: Optional[str] = None
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
    total_passages: int
    passages_by_subject: Dict[str, int]