from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from uuid import UUID

from app.models.student import StudentStatus


class ClassBase(BaseModel):
    name: str = Field(..., max_length=50)
    year_group: int = Field(..., ge=1, le=13)
    academic_year: Optional[str] = Field(None, max_length=20)
    teacher_id: Optional[UUID] = None


class ClassCreate(ClassBase):
    pass


class ClassUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    year_group: Optional[int] = Field(None, ge=1, le=13)
    academic_year: Optional[str] = Field(None, max_length=20)
    teacher_id: Optional[UUID] = None


class ClassResponse(ClassBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    student_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class ClassListResponse(BaseModel):
    classes: List[ClassResponse]
    total: int
    page: int
    pages: int
    limit: int


class StudentBase(BaseModel):
    class_id: Optional[UUID] = None
    year_group: int = Field(..., ge=1, le=13)


class StudentCreate(StudentBase):
    email: EmailStr
    full_name: str = Field(..., min_length=1)
    first_name: Optional[str] = None  # For CSV upload
    surname: Optional[str] = None  # For CSV upload
    student_id: Optional[str] = None  # For CSV upload (external ID)
    class_name: Optional[str] = None  # For CSV upload


class StudentBulkCreate(BaseModel):
    students: List[StudentCreate]


class StudentUpdate(BaseModel):
    full_name: Optional[str] = None
    class_id: Optional[UUID] = None
    year_group: Optional[int] = Field(None, ge=1, le=13)
    status: Optional[StudentStatus] = None


class StudentResponse(StudentBase):
    id: UUID
    user_id: UUID
    student_code: Optional[str] = None
    email: EmailStr
    full_name: Optional[str] = None
    username: str
    enrollment_date: date
    status: StudentStatus
    is_active: bool
    created_at: datetime
    updated_at: datetime
    class_info: Optional[ClassResponse] = None

    model_config = ConfigDict(from_attributes=True)


class StudentListResponse(BaseModel):
    students: List[StudentResponse]
    total: int
    page: int
    pages: int
    limit: int


class CSVUploadPreview(BaseModel):
    data: List[dict]
    errors: List[dict]
    total_rows: int
    valid_rows: int
    invalid_rows: int


class CSVUploadResult(BaseModel):
    file_name: str
    total_records: int
    successful_records: int
    failed_records: int
    errors: Optional[List[dict]] = []
    created_students: Optional[List[StudentResponse]] = []


class PasswordResetResponse(BaseModel):
    message: str
    email_sent: bool


class StudentProfileResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: EmailStr
    username: str
    full_name: str
    student_code: Optional[str] = None
    year_group: int
    enrollment_date: date
    status: StudentStatus
    class_info: Optional[ClassResponse] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StudentProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=50)


class ChangePasswordResponse(BaseModel):
    message: str
    success: bool


class StudentProgressResponse(BaseModel):
    total_tests: int
    completed_tests: int
    average_score: float
    best_score: float
    improvement_percentage: Optional[float] = None
    subject_performance: dict
    recent_trends: List[dict]


class StudentStatsResponse(BaseModel):
    tests_completed: int
    tests_pending: int
    average_score: float
    best_score: float
    total_time_spent: int  # minutes
    streak_days: int
    badges_earned: List[str]
    class_rank: Optional[int] = None
    class_size: Optional[int] = None