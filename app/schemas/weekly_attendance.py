"""
Pydantic schemas for Weekly Attendance model.

Includes schemas for:
- Weekly attendance records with book comments
- Combined attendance with test scores
- Overall performance summaries
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict
from datetime import datetime
from uuid import UUID


def to_camel(string: str) -> str:
    """Convert snake_case to camelCase."""
    components = string.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


# Book Comments Schema
class BookComments(BaseModel):
    """Schema for book-based comments in attendance records."""
    help_in: List[str] = Field(default_factory=list, description="Book IDs student needs help with (H)")
    incomplete: List[str] = Field(default_factory=list, description="Book IDs not completed (I/c)")
    unmarked: List[str] = Field(default_factory=list, description="Book IDs not marked (u/m)")
    at_home: List[str] = Field(default_factory=list, description="Book IDs left at home (a/h)")


# Weekly Attendance Base
class WeeklyAttendanceBase(BaseModel):
    week_number: int = Field(..., ge=1, le=52, description="Week number (1-52)")
    academic_year: str = Field(..., description="Academic year e.g. '2025-2026'")
    is_present: Optional[bool] = Field(None, description="True=present, False=absent, None=not marked")
    comments: BookComments = Field(default_factory=BookComments)
    notes: Optional[str] = None


class WeeklyAttendanceCreate(BaseModel):
    """Schema for creating/updating weekly attendance."""
    student_id: UUID
    week_number: int = Field(..., ge=1, le=52)
    academic_year: str
    is_present: Optional[bool] = None
    comments: Optional[BookComments] = None
    notes: Optional[str] = None


class WeeklyAttendanceUpdate(BaseModel):
    """Schema for updating weekly attendance. All fields optional."""
    is_present: Optional[bool] = None
    comments: Optional[BookComments] = None
    notes: Optional[str] = None


class WeeklyAttendanceCommentsUpdate(BaseModel):
    """Schema for updating only the comments field."""
    student_id: UUID
    week_number: int = Field(..., ge=1, le=52)
    academic_year: str
    comments: BookComments


class WeeklyAttendanceResponse(WeeklyAttendanceBase):
    """Schema for weekly attendance response."""
    id: UUID
    student_id: UUID
    recorded_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Subject Score (for integrating test results)
class SubjectScore(BaseModel):
    """Schema for a single subject's test score."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    subject: str
    mark: Optional[int] = None
    max_mark: Optional[int] = None
    percentage: Optional[float] = None
    test_id: Optional[str] = None
    test_title: Optional[str] = None
    submitted_at: Optional[datetime] = None


# Student Weekly Attendance with Test Scores
class StudentWeeklyAttendanceRecord(BaseModel):
    """Schema for a student's weekly attendance with integrated test scores."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    student_id: str
    student_code: str
    first_name: str
    surname: str
    full_name: str
    class_id: str
    class_name: str
    year_group: int

    # Attendance
    attendance_id: Optional[str] = None
    is_present: Optional[bool] = None

    # Book comments
    comments: BookComments = Field(default_factory=BookComments)
    notes: Optional[str] = None

    # Test scores by subject
    scores: Dict[str, SubjectScore] = Field(default_factory=dict)


# Week Info
class AcademicWeekInfo(BaseModel):
    """Schema for academic week information."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    week_number: int
    start_date: str
    end_date: str
    is_break: bool = False
    break_name: Optional[str] = None
    week_label: str


# Weekly Attendance Data Response
class WeeklyAttendanceDataResponse(BaseModel):
    """Schema for the complete weekly attendance data response."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    week_info: AcademicWeekInfo
    students: List[StudentWeeklyAttendanceRecord]
    total_students: int
    subjects: List[str] = ["English", "VR GL", "NVR", "Maths"]


# Overall Performance
class StudentOverallPerformance(BaseModel):
    """Schema for a student's overall performance across all weeks."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    student_id: str
    student_code: str
    first_name: str
    surname: str
    full_name: str
    class_id: str
    class_name: str
    year_group: int

    # Attendance stats
    total_weeks: int
    weeks_present: int
    weeks_absent: int
    attendance_rate: float

    # Average scores by subject - Note: inner dict keys stay as-is (average_mark, average_percentage)
    average_scores: Dict[str, Dict[str, Optional[float]]] = Field(
        default_factory=dict,
        description="Subject -> {averageMark, averagePercentage}"
    )


class OverallPerformanceResponse(BaseModel):
    """Schema for overall performance data response."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    academic_year: str
    total_weeks_completed: int
    students: List[StudentOverallPerformance]
    total_students: int
    subjects: List[str] = ["English", "VR GL", "NVR", "Maths"]


# Bulk Operations
class BulkAttendanceCreate(BaseModel):
    """Schema for creating attendance for multiple students at once."""
    week_number: int = Field(..., ge=1, le=52)
    academic_year: str
    student_attendance: List[Dict] = Field(
        ...,
        description="List of {student_id, is_present, comments?, notes?}"
    )


class BulkAttendanceResponse(BaseModel):
    """Response for bulk attendance creation."""
    created: int
    updated: int
    errors: List[Dict] = Field(default_factory=list)
