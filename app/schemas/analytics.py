from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from uuid import UUID


class DashboardTotals(BaseModel):
    students: int
    tests: int
    results: int
    active_assignments: int


class DashboardActivity(BaseModel):
    recent_submissions: int
    average_performance: float


class RecentResult(BaseModel):
    student_name: str
    test_title: str
    score: str
    percentage: float
    submitted_at: Optional[str] = None


class AdminDashboardOverview(BaseModel):
    totals: DashboardTotals
    activity: DashboardActivity
    recent_results: List[RecentResult]


class StudentInfo(BaseModel):
    name: str
    email: str
    class_name: Optional[str] = None
    year_group: int


class StudentPerformance(BaseModel):
    tests_completed: int
    average_score: float
    best_score: float
    total_time_spent: int  # minutes


class ProgressTrendItem(BaseModel):
    date: Optional[str] = None
    score: float
    test_title: str
    subject: str


class ClassComparison(BaseModel):
    class_average: float
    student_rank: Optional[int] = None
    class_size: int
    above_average: bool


class StudentAnalytics(BaseModel):
    student_info: StudentInfo
    performance: StudentPerformance
    subject_breakdown: Dict[str, Any]
    progress_trend: List[ProgressTrendItem]
    class_comparison: Optional[ClassComparison] = None


class ClassInfo(BaseModel):
    name: str
    year_group: int
    student_count: int


class ClassPerformance(BaseModel):
    class_average: float
    highest_score: float
    lowest_score: float
    tests_completed: int


class StudentPerformanceItem(BaseModel):
    student_id: str
    name: str
    email: str
    average: float
    best_score: float
    tests_completed: int


class TestStatistic(BaseModel):
    test_id: str
    title: str
    type: str
    class_average: float
    highest_score: float
    lowest_score: float
    completion_count: int


class ClassAnalytics(BaseModel):
    class_info: ClassInfo
    performance: ClassPerformance
    student_performance: List[StudentPerformanceItem]
    subject_breakdown: Dict[str, Any]
    test_statistics: List[TestStatistic]


class TestInfo(BaseModel):
    title: str
    type: str
    duration_minutes: int
    total_marks: Optional[int] = None
    pass_mark: int


class TestStatistics(BaseModel):
    completion_count: int
    average_score: float
    highest_score: float
    lowest_score: float
    pass_rate: float
    average_time: float  # minutes


class StudentResult(BaseModel):
    student_id: str
    name: str
    class_name: Optional[str] = None
    score: str
    percentage: float
    grade: Optional[str] = None
    time_taken: Optional[int] = None  # seconds
    submitted_at: Optional[str] = None
    status: str  # Pass/Fail


class TestAnalytics(BaseModel):
    test_info: TestInfo
    statistics: TestStatistics
    score_distribution: Dict[str, int]
    student_results: List[StudentResult]


class SubjectAnalytics(BaseModel):
    subject: str
    total_tests: int
    average_score: float
    highest_score: float
    lowest_score: float
    completion_rate: float
    difficulty_level: str  # Easy, Medium, Hard


class AnalyticsFilter(BaseModel):
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    class_ids: Optional[List[UUID]] = None
    test_types: Optional[List[str]] = None
    student_ids: Optional[List[UUID]] = None


class PerformanceMetric(BaseModel):
    metric_name: str
    value: float
    change_from_previous: Optional[float] = None
    trend: str  # up, down, stable


class AnalyticsReport(BaseModel):
    title: str
    generated_at: datetime
    filters: AnalyticsFilter
    metrics: List[PerformanceMetric]
    data: Dict[str, Any]
    summary: str


# Weekly Results Schemas

def to_camel(string: str) -> str:
    """Convert snake_case to camelCase."""
    components = string.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


class AcademicWeekInfo(BaseModel):
    """Information about an academic week."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    week_number: int
    start_date: str  # ISO format date
    end_date: str  # ISO format date
    is_break: bool
    break_name: Optional[str] = None
    week_label: str  # e.g., "Week1", "Week2"


class SubjectScore(BaseModel):
    """Score for a single subject."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    subject: str  # English, VR GL, NVR, Maths
    mark: Optional[int] = None
    max_mark: Optional[int] = None
    percentage: Optional[float] = None
    test_id: Optional[str] = None
    test_title: Optional[str] = None
    submitted_at: Optional[str] = None


class StudentWeeklyScores(BaseModel):
    """All scores for a student in a specific week."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    student_id: str
    student_code: str
    first_name: str
    surname: str
    full_name: str
    class_id: str
    class_name: str
    year_group: int
    scores: Dict[str, SubjectScore]  # Key: subject name (e.g., "English")


class WeeklyResultsSummary(BaseModel):
    """Results for all students in a specific week."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    week_info: AcademicWeekInfo
    students: List[StudentWeeklyScores]
    total_students: int
    subjects: List[str]  # List of all subjects


class AllWeeksResults(BaseModel):
    """Results for all 40 weeks."""
    academic_year: str
    current_week: int
    weeks: List[WeeklyResultsSummary]  # All 40 weeks
    total_weeks: int


class AcademicCalendarConfigSchema(BaseModel):
    """Academic calendar configuration."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    academic_year: str
    year_start_date: str
    total_weeks: int
    break_periods: List[Dict[str, str]]  # List of break period dicts
    week_start_day: str
    week_end_day: str
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AcademicCalendarConfigCreate(BaseModel):
    """Schema for creating academic calendar configuration."""
    academic_year: str
    year_start_date: str
    total_weeks: int = 40
    break_periods: List[Dict[str, str]]
    week_start_day: str = "Friday"
    week_end_day: str = "Wednesday"
    notes: Optional[str] = None


class AcademicCalendarConfigUpdate(BaseModel):
    """Schema for updating academic calendar configuration."""
    break_periods: Optional[List[Dict[str, str]]] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None