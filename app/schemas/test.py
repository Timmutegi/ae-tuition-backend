from pydantic import BaseModel, Field, ConfigDict, field_validator, field_serializer
from typing import Optional, List, Any, Dict, TYPE_CHECKING
from datetime import datetime
from uuid import UUID
from enum import Enum

from app.models.test import TestType, TestFormat, TestStatus, QuestionOrder, AssignmentStatus, AttemptStatus, ResultStatus

# Import ClassResponse, StudentResponse and TestQuestionSetResponse directly to avoid forward reference issues
try:
    from app.schemas.student import ClassResponse, StudentResponse
except ImportError:
    ClassResponse = None
    StudentResponse = None

try:
    from app.schemas.question_set import TestQuestionSetResponse
except ImportError:
    TestQuestionSetResponse = None


class TestBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    type: TestType
    test_format: TestFormat = TestFormat.STANDARD
    duration_minutes: int = Field(..., gt=0, le=600)
    warning_intervals: Optional[List[int]] = [10, 5, 1]
    pass_mark: int = Field(default=50, ge=0, le=100)
    instructions: Optional[str] = None
    question_order: QuestionOrder = QuestionOrder.SEQUENTIAL


class TestCreate(TestBase):
    pass


class TestUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    test_format: Optional[TestFormat] = None
    duration_minutes: Optional[int] = Field(None, gt=0, le=600)
    warning_intervals: Optional[List[int]] = None
    pass_mark: Optional[int] = Field(None, ge=0, le=100)
    instructions: Optional[str] = None
    question_order: Optional[QuestionOrder] = None
    status: Optional[TestStatus] = None


class TestResponse(TestBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    total_marks: Optional[int] = None
    status: TestStatus
    template_id: Optional[UUID] = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    test_question_sets: List[TestQuestionSetResponse] = []


class TestQuestionBase(BaseModel):
    question_id: UUID
    passage_id: Optional[UUID] = None
    order_number: int = Field(..., ge=1)
    question_group: Optional[str] = None
    points: int = Field(default=1, ge=1)


class TestQuestionCreate(TestQuestionBase):
    pass


class TestQuestionResponse(TestQuestionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    test_id: UUID
    created_at: datetime


class TestAssignmentBase(BaseModel):
    class_id: UUID
    scheduled_start: datetime
    scheduled_end: datetime
    buffer_time_minutes: int = Field(default=0, ge=0)
    allow_late_submission: bool = False
    late_submission_grace_minutes: int = Field(default=0, ge=0)
    auto_submit: bool = True
    extended_time_students: Optional[List[UUID]] = None
    custom_instructions: Optional[str] = None


class TestAssignmentCreate(TestAssignmentBase):
    pass


class TestAssignmentUpdate(BaseModel):
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    buffer_time_minutes: Optional[int] = Field(None, ge=0)
    allow_late_submission: Optional[bool] = None
    late_submission_grace_minutes: Optional[int] = Field(None, ge=0)
    auto_submit: Optional[bool] = None
    extended_time_students: Optional[List[UUID]] = None
    custom_instructions: Optional[str] = None
    status: Optional[AssignmentStatus] = None


class TestAssignmentResponse(TestAssignmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    test_id: UUID
    status: AssignmentStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    class_info: Optional[ClassResponse] = None


class StudentTestAssignmentBase(BaseModel):
    student_id: UUID
    scheduled_start: datetime
    scheduled_end: datetime
    buffer_time_minutes: int = Field(default=0, ge=0)
    allow_late_submission: bool = False
    late_submission_grace_minutes: int = Field(default=0, ge=0)
    auto_submit: bool = True
    custom_instructions: Optional[str] = None


class StudentTestAssignmentCreate(StudentTestAssignmentBase):
    pass


class StudentTestAssignmentUpdate(BaseModel):
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    buffer_time_minutes: Optional[int] = Field(None, ge=0)
    allow_late_submission: Optional[bool] = None
    late_submission_grace_minutes: Optional[int] = Field(None, ge=0)
    auto_submit: Optional[bool] = None
    custom_instructions: Optional[str] = None
    status: Optional[AssignmentStatus] = None


class StudentAssignmentInfo(BaseModel):
    """Minimal student info for assignment responses"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    student_code: Optional[str] = None
    year_group: int
    user: Optional[Any] = None  # Contains user info like full_name, email
    class_info: Optional[Any] = None  # Contains class info

    @field_serializer('user')
    def serialize_user(self, user: Any, _info):
        if user is None:
            return None
        if hasattr(user, '__dict__'):
            return {
                'id': str(user.id) if hasattr(user, 'id') else None,
                'email': user.email if hasattr(user, 'email') else None,
                'full_name': user.full_name if hasattr(user, 'full_name') else None,
                'username': user.username if hasattr(user, 'username') else None,
            }
        return user

    @field_serializer('class_info')
    def serialize_class_info(self, class_info: Any, _info):
        if class_info is None:
            return None
        if hasattr(class_info, '__dict__'):
            return {
                'id': str(class_info.id) if hasattr(class_info, 'id') else None,
                'name': class_info.name if hasattr(class_info, 'name') else None,
                'year_group': class_info.year_group if hasattr(class_info, 'year_group') else None,
            }
        return class_info


class StudentTestAssignmentResponse(StudentTestAssignmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    test_id: UUID
    status: AssignmentStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    student: Optional[StudentAssignmentInfo] = None  # Will contain student info


class TestWithDetails(TestResponse):
    model_config = ConfigDict(from_attributes=True)

    test_questions: List[TestQuestionResponse] = []
    test_assignments: List[TestAssignmentResponse] = []
    student_test_assignments: List[StudentTestAssignmentResponse] = []
    test_question_sets: List[TestQuestionSetResponse] = []


class TestFilters(BaseModel):
    type: Optional[TestType] = None
    status: Optional[TestStatus] = None
    created_by: Optional[UUID] = None
    search: Optional[str] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)


class TestPreview(BaseModel):
    test: TestResponse
    questions: List[Dict[str, Any]]
    passages: List[Dict[str, Any]]
    estimated_duration: int
    question_count: int
    total_marks: int


class BulkAssignmentData(BaseModel):
    scheduled_start: datetime
    scheduled_end: datetime
    buffer_time_minutes: int = Field(default=0, ge=0)
    allow_late_submission: bool = False
    late_submission_grace_minutes: int = Field(default=0, ge=0)
    auto_submit: bool = True
    extended_time_students: Optional[List[UUID]] = None
    custom_instructions: Optional[str] = None


class BulkAssignmentRequest(BaseModel):
    class_ids: List[UUID]
    assignment_data: BulkAssignmentData


class BulkStudentAssignmentRequest(BaseModel):
    student_ids: List[UUID]
    assignment_data: BulkAssignmentData


class MixedAssignmentRequest(BaseModel):
    class_ids: List[UUID] = []
    student_ids: List[UUID] = []
    assignment_data: BulkAssignmentData


class TestCloneRequest(BaseModel):
    new_title: str = Field(..., min_length=1, max_length=255)
    copy_assignments: bool = False
    copy_questions: bool = True


class TestStatsResponse(BaseModel):
    total_tests: int
    draft_tests: int
    published_tests: int
    archived_tests: int
    total_assignments: int
    active_assignments: int


class TestListResponse(BaseModel):
    tests: List[TestResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class TestAttemptBase(BaseModel):
    test_id: UUID
    assignment_id: UUID


class TestAttemptCreate(TestAttemptBase):
    browser_info: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None


class TestAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    test_id: UUID
    student_id: UUID
    assignment_id: Optional[UUID] = None  # Can be None for individual student assignments
    student_assignment_id: Optional[UUID] = None  # For individual student assignments
    started_at: datetime
    submitted_at: Optional[datetime] = None
    time_taken: Optional[int] = None
    status: AttemptStatus
    created_at: datetime


class QuestionResponseBase(BaseModel):
    question_id: UUID
    answer_text: Optional[str] = None
    selected_options: Optional[List[UUID]] = None
    dropdown_selections: Optional[Dict[str, Any]] = None
    fill_in_answers: Optional[Dict[str, Any]] = None
    pattern_response: Optional[Dict[str, Any]] = None


class QuestionResponseCreate(QuestionResponseBase):
    pass


class QuestionResponseUpdate(BaseModel):
    answer_text: Optional[str] = None
    selected_options: Optional[List[UUID]] = None
    dropdown_selections: Optional[Dict[str, Any]] = None
    fill_in_answers: Optional[Dict[str, Any]] = None
    pattern_response: Optional[Dict[str, Any]] = None


class QuestionResponseDetail(QuestionResponseBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attempt_id: UUID
    is_correct: Optional[bool] = None
    partial_score: Optional[float] = None
    points_earned: int = 0
    time_spent: Optional[int] = None
    answered_at: Optional[datetime] = None
    created_at: datetime


class TestSessionResponse(BaseModel):
    attempt: TestAttemptResponse
    test: TestResponse
    questions: List[Dict[str, Any]]
    passages: Dict[str, Dict[str, Any]]
    answers: Dict[str, QuestionResponseDetail]
    time_remaining: int
    progress: Dict[str, Any]


class TestSubmissionRequest(BaseModel):
    answers: Dict[str, QuestionResponseCreate]
    submission_type: str = "manual"  # manual, auto_submit, timeout


class TestSubmissionResponse(BaseModel):
    attempt_id: UUID
    result_id: UUID
    total_score: int
    max_score: int
    percentage: float
    status: ResultStatus
    time_taken: int
    submitted_at: datetime


class QuestionAnalysisItem(BaseModel):
    """Individual question analysis for test results"""
    question_number: int
    question_id: UUID
    question_type: str
    question_text: Optional[str] = None
    image_url: Optional[str] = None
    student_answer: Optional[str] = None
    correct_answer: Optional[str] = None
    is_correct: bool
    points_earned: int
    max_points: int
    time_spent: Optional[int] = None


class TestResultDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attempt_id: UUID
    student_id: UUID
    test_id: UUID
    total_score: int
    max_score: int
    percentage: float
    grade: Optional[str] = None
    time_taken: Optional[int] = None
    submitted_at: Optional[datetime] = None
    status: ResultStatus
    question_scores: Optional[Dict[str, Any]] = None
    analytics_data: Optional[Dict[str, Any]] = None
    question_analysis: Optional[List[QuestionAnalysisItem]] = None
    created_at: datetime
    test_title: Optional[str] = None
    test_type: Optional[str] = None