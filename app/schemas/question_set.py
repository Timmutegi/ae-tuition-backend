from pydantic import BaseModel, Field, UUID4
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class QuestionSetItemBase(BaseModel):
    question_id: UUID4
    order_number: int
    points_override: Optional[int] = None


class QuestionSetItemCreate(QuestionSetItemBase):
    pass


class QuestionSetItemResponse(QuestionSetItemBase):
    id: UUID4
    question_set_id: UUID4
    created_at: datetime

    # Include question details
    question: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class QuestionSetBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    subject: Optional[str] = Field(None, max_length=50)
    grade_level: Optional[str] = Field(None, max_length=20)
    metadata_json: Optional[Dict[str, Any]] = None


class QuestionSetCreate(QuestionSetBase):
    question_items: List[QuestionSetItemCreate] = Field(default_factory=list)


class QuestionSetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    subject: Optional[str] = Field(None, max_length=50)
    grade_level: Optional[str] = Field(None, max_length=20)
    metadata_json: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class QuestionSetResponse(QuestionSetBase):
    id: UUID4
    total_points: int
    question_count: int
    is_active: bool
    created_by: UUID4
    created_at: datetime
    updated_at: datetime

    # Include creator details
    creator_name: Optional[str] = None

    class Config:
        from_attributes = True


class QuestionSetWithItems(QuestionSetResponse):
    question_set_items: List[QuestionSetItemResponse] = Field(default_factory=list)


class QuestionSetListResponse(BaseModel):
    question_sets: List[QuestionSetResponse]
    total: int
    page: int
    pages: int
    limit: int


class QuestionSetFilters(BaseModel):
    subject: Optional[str] = None
    grade_level: Optional[str] = None
    search: Optional[str] = None
    is_active: Optional[bool] = True
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=100)


class TestQuestionSetBase(BaseModel):
    question_set_id: UUID4
    order_number: int


class TestQuestionSetCreate(TestQuestionSetBase):
    pass


class TestQuestionSetResponse(TestQuestionSetBase):
    id: UUID4
    test_id: UUID4
    created_at: datetime

    # Include question set details
    question_set: Optional[QuestionSetResponse] = None

    class Config:
        from_attributes = True


class BulkQuestionSetAssignment(BaseModel):
    question_set_ids: List[UUID4]


class AddQuestionsToSetRequest(BaseModel):
    question_ids: List[UUID4]


class RemoveQuestionsFromSetRequest(BaseModel):
    question_ids: List[UUID4]


class ReorderQuestionsInSetRequest(BaseModel):
    question_orders: List[Dict[str, Any]]  # List of {question_id: UUID, order_number: int}