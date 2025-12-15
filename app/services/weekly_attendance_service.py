"""
Service for managing weekly attendance with integrated test scores.

This service handles:
- Weekly attendance records with book-based comments
- Integration with test scores from the existing test system
- Overall performance calculations
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, time
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from sqlalchemy.orm import selectinload

from app.models.weekly_attendance import WeeklyAttendance
from app.models.student import Student
from app.models.user import User
from app.models.class_model import Class
from app.models.test import TestResult, Test
from app.models.supervisor import SupervisorStudentAssignment, SupervisorClassAssignment
from app.models.teacher import TeacherClassAssignment
from app.schemas.weekly_attendance import (
    WeeklyAttendanceCreate,
    WeeklyAttendanceUpdate,
    WeeklyAttendanceCommentsUpdate,
    BookComments,
    StudentWeeklyAttendanceRecord,
    SubjectScore,
    AcademicWeekInfo,
    WeeklyAttendanceDataResponse,
    StudentOverallPerformance,
    OverallPerformanceResponse
)

logger = logging.getLogger(__name__)


class WeeklyAttendanceService:
    """Service for weekly attendance and test score integration."""

    SUBJECTS = ["English", "VR GL", "NVR", "Maths"]
    SUBJECT_MAP = {
        "English": "English",
        "Verbal Reasoning": "VR GL",
        "Non-Verbal Reasoning": "NVR",
        "Mathematics": "Maths"
    }

    @staticmethod
    async def get_weekly_attendance_with_scores(
        db: AsyncSession,
        week_number: int,
        academic_year: str,
        class_id: Optional[UUID] = None,
        student_code: Optional[str] = None,
        supervisor_id: Optional[UUID] = None,
        teacher_id: Optional[UUID] = None
    ) -> WeeklyAttendanceDataResponse:
        """
        Get weekly attendance data with integrated test scores.

        Args:
            db: Database session
            week_number: Week number (1-40)
            academic_year: Academic year string e.g., "2025-2026"
            class_id: Optional class filter
            student_code: Optional student code filter
            supervisor_id: Optional supervisor filter (gets assigned students)
            teacher_id: Optional teacher filter (gets students from assigned classes)
        """
        from app.services.academic_calendar_service import calendar_service

        # Get week date range
        week_info = calendar_service.get_week_info(week_number)
        start_date = week_info.start_date
        end_date = week_info.end_date
        end_datetime = datetime.combine(end_date, time(23, 59, 59))

        # Build student query with filters
        student_query = (
            select(Student)
            .options(
                selectinload(Student.user),
                selectinload(Student.class_info)
            )
            .join(User, Student.user_id == User.id)
            .where(User.is_active == True)
        )

        # Apply filters
        if class_id:
            student_query = student_query.where(Student.class_id == class_id)

        if student_code:
            student_query = student_query.where(Student.student_code == student_code)

        if supervisor_id:
            # Get students either directly assigned OR in classes assigned to the supervisor
            # First, get the class IDs assigned to this supervisor
            supervisor_class_ids_query = (
                select(SupervisorClassAssignment.class_id)
                .where(SupervisorClassAssignment.supervisor_id == supervisor_id)
            )
            supervisor_class_result = await db.execute(supervisor_class_ids_query)
            supervisor_class_ids = [row[0] for row in supervisor_class_result.fetchall()]

            # Get direct student assignments
            direct_student_ids_query = (
                select(SupervisorStudentAssignment.student_id)
                .where(SupervisorStudentAssignment.supervisor_id == supervisor_id)
            )
            direct_student_result = await db.execute(direct_student_ids_query)
            direct_student_ids = [row[0] for row in direct_student_result.fetchall()]

            # Apply filter: students in assigned classes OR directly assigned students
            if supervisor_class_ids and direct_student_ids:
                student_query = student_query.where(
                    or_(
                        Student.class_id.in_(supervisor_class_ids),
                        Student.id.in_(direct_student_ids)
                    )
                )
            elif supervisor_class_ids:
                student_query = student_query.where(Student.class_id.in_(supervisor_class_ids))
            elif direct_student_ids:
                student_query = student_query.where(Student.id.in_(direct_student_ids))
            else:
                # No assignments at all - return empty
                return WeeklyAttendanceDataResponse(
                    week_info=AcademicWeekInfo(
                        week_number=week_info.week_number,
                        start_date=week_info.start_date.isoformat(),
                        end_date=week_info.end_date.isoformat(),
                        is_break=week_info.is_break,
                        break_name=week_info.break_name,
                        week_label=calendar_service.get_week_label(week_number)
                    ),
                    students=[],
                    total_students=0
                )

        if teacher_id:
            student_query = student_query.join(
                TeacherClassAssignment,
                TeacherClassAssignment.class_id == Student.class_id
            ).where(TeacherClassAssignment.teacher_id == teacher_id)

        student_query = student_query.order_by(User.full_name)
        student_result = await db.execute(student_query)
        students = list(student_result.scalars().all())

        if not students:
            return WeeklyAttendanceDataResponse(
                week_info=AcademicWeekInfo(
                    week_number=week_info.week_number,
                    start_date=week_info.start_date.isoformat(),
                    end_date=week_info.end_date.isoformat(),
                    is_break=week_info.is_break,
                    break_name=week_info.break_name,
                    week_label=calendar_service.get_week_label(week_number)
                ),
                students=[],
                total_students=0
            )

        student_ids = [s.id for s in students]

        # Get attendance records for these students for this week
        attendance_query = (
            select(WeeklyAttendance)
            .where(
                and_(
                    WeeklyAttendance.student_id.in_(student_ids),
                    WeeklyAttendance.week_number == week_number,
                    WeeklyAttendance.academic_year == academic_year
                )
            )
        )
        attendance_result = await db.execute(attendance_query)
        attendance_records = {str(r.student_id): r for r in attendance_result.scalars().all()}

        # Get test results for this week
        test_results_query = (
            select(TestResult)
            .options(selectinload(TestResult.test))
            .where(
                and_(
                    TestResult.student_id.in_(student_ids),
                    TestResult.submitted_at >= start_date,
                    TestResult.submitted_at <= end_datetime
                )
            )
        )
        test_results_result = await db.execute(test_results_query)
        test_results = list(test_results_result.scalars().all())

        # Organize test results by student
        scores_by_student: Dict[str, Dict[str, SubjectScore]] = defaultdict(dict)
        for tr in test_results:
            if not tr.test:
                continue
            student_id = str(tr.student_id)
            test_type = tr.test.type.value if hasattr(tr.test.type, 'value') else str(tr.test.type)
            subject_name = WeeklyAttendanceService.SUBJECT_MAP.get(test_type, test_type)

            # Store latest result per subject (in case of multiple submissions)
            scores_by_student[student_id][subject_name] = SubjectScore(
                subject=subject_name,
                mark=tr.total_score,
                max_mark=tr.max_score,
                percentage=round(tr.percentage, 2) if tr.percentage else None,
                test_id=str(tr.test.id),
                test_title=tr.test.title,
                submitted_at=tr.submitted_at
            )

        # Build student records
        student_records = []
        for student in students:
            student_id = str(student.id)
            full_name = student.user.full_name if student.user else ""
            name_parts = full_name.strip().split(maxsplit=1)
            first_name = name_parts[0] if len(name_parts) > 0 else ""
            surname = name_parts[1] if len(name_parts) > 1 else ""

            # Get attendance record
            attendance = attendance_records.get(student_id)

            # Get scores for all subjects
            student_scores = scores_by_student.get(student_id, {})
            all_scores = {}
            for subject in WeeklyAttendanceService.SUBJECTS:
                if subject in student_scores:
                    all_scores[subject] = student_scores[subject]
                else:
                    all_scores[subject] = SubjectScore(
                        subject=subject,
                        mark=None,
                        max_mark=None,
                        percentage=None,
                        test_id=None,
                        test_title=None,
                        submitted_at=None
                    )

            # Get comments from attendance record
            comments = BookComments()
            if attendance and attendance.comments:
                comments = BookComments(
                    help_in=attendance.comments.get('help_in', []),
                    incomplete=attendance.comments.get('incomplete', []),
                    unmarked=attendance.comments.get('unmarked', []),
                    at_home=attendance.comments.get('at_home', [])
                )

            student_records.append(StudentWeeklyAttendanceRecord(
                student_id=student_id,
                student_code=student.student_code or "N/A",
                first_name=first_name,
                surname=surname,
                full_name=full_name,
                class_id=str(student.class_id) if student.class_id else "",
                class_name=student.class_info.name if student.class_info else "N/A",
                year_group=student.year_group,
                attendance_id=str(attendance.id) if attendance else None,
                is_present=attendance.is_present if attendance else None,
                comments=comments,
                notes=attendance.notes if attendance else None,
                scores=all_scores
            ))

        return WeeklyAttendanceDataResponse(
            week_info=AcademicWeekInfo(
                week_number=week_info.week_number,
                start_date=week_info.start_date.isoformat(),
                end_date=week_info.end_date.isoformat(),
                is_break=week_info.is_break,
                break_name=week_info.break_name,
                week_label=calendar_service.get_week_label(week_number)
            ),
            students=student_records,
            total_students=len(student_records)
        )

    @staticmethod
    async def create_or_update_attendance(
        db: AsyncSession,
        data: WeeklyAttendanceCreate,
        recorded_by: UUID
    ) -> WeeklyAttendance:
        """Create or update weekly attendance record."""
        # Check if record exists
        existing = await db.execute(
            select(WeeklyAttendance).where(
                and_(
                    WeeklyAttendance.student_id == data.student_id,
                    WeeklyAttendance.week_number == data.week_number,
                    WeeklyAttendance.academic_year == data.academic_year
                )
            )
        )
        record = existing.scalars().first()

        if record:
            # Update existing record
            if data.is_present is not None:
                record.is_present = data.is_present
            if data.comments:
                record.comments = data.comments.model_dump()
            if data.notes is not None:
                record.notes = data.notes
            record.recorded_by = recorded_by
        else:
            # Create new record
            comments_dict = data.comments.model_dump() if data.comments else {
                'help_in': [],
                'incomplete': [],
                'unmarked': [],
                'at_home': []
            }
            record = WeeklyAttendance(
                student_id=data.student_id,
                week_number=data.week_number,
                academic_year=data.academic_year,
                is_present=data.is_present,
                comments=comments_dict,
                notes=data.notes,
                recorded_by=recorded_by
            )
            db.add(record)

        await db.commit()
        await db.refresh(record)
        return record

    @staticmethod
    async def update_attendance(
        db: AsyncSession,
        attendance_id: UUID,
        data: WeeklyAttendanceUpdate,
        recorded_by: UUID
    ) -> Optional[WeeklyAttendance]:
        """Update an existing attendance record."""
        result = await db.execute(
            select(WeeklyAttendance).where(WeeklyAttendance.id == attendance_id)
        )
        record = result.scalars().first()

        if not record:
            return None

        if data.is_present is not None:
            record.is_present = data.is_present
        if data.comments is not None:
            record.comments = data.comments.model_dump()
        if data.notes is not None:
            record.notes = data.notes
        record.recorded_by = recorded_by

        await db.commit()
        await db.refresh(record)
        return record

    @staticmethod
    async def update_comments(
        db: AsyncSession,
        data: WeeklyAttendanceCommentsUpdate,
        recorded_by: UUID
    ) -> WeeklyAttendance:
        """Update only the comments for a student's weekly attendance."""
        # Get or create attendance record
        existing = await db.execute(
            select(WeeklyAttendance).where(
                and_(
                    WeeklyAttendance.student_id == data.student_id,
                    WeeklyAttendance.week_number == data.week_number,
                    WeeklyAttendance.academic_year == data.academic_year
                )
            )
        )
        record = existing.scalars().first()

        if record:
            record.comments = data.comments.model_dump()
            record.recorded_by = recorded_by
        else:
            record = WeeklyAttendance(
                student_id=data.student_id,
                week_number=data.week_number,
                academic_year=data.academic_year,
                is_present=None,
                comments=data.comments.model_dump(),
                recorded_by=recorded_by
            )
            db.add(record)

        await db.commit()
        await db.refresh(record)
        return record

    @staticmethod
    async def get_overall_performance(
        db: AsyncSession,
        academic_year: str,
        class_id: Optional[UUID] = None,
        student_code: Optional[str] = None,
        supervisor_id: Optional[UUID] = None,
        teacher_id: Optional[UUID] = None
    ) -> OverallPerformanceResponse:
        """
        Get overall performance (average scores across all weeks).
        """
        from app.services.academic_calendar_service import calendar_service

        # Build student query
        student_query = (
            select(Student)
            .options(
                selectinload(Student.user),
                selectinload(Student.class_info)
            )
            .join(User, Student.user_id == User.id)
            .where(User.is_active == True)
        )

        if class_id:
            student_query = student_query.where(Student.class_id == class_id)

        if student_code:
            student_query = student_query.where(Student.student_code == student_code)

        if supervisor_id:
            # Get students either directly assigned OR in classes assigned to the supervisor
            supervisor_class_ids_query = (
                select(SupervisorClassAssignment.class_id)
                .where(SupervisorClassAssignment.supervisor_id == supervisor_id)
            )
            supervisor_class_result = await db.execute(supervisor_class_ids_query)
            supervisor_class_ids = [row[0] for row in supervisor_class_result.fetchall()]

            direct_student_ids_query = (
                select(SupervisorStudentAssignment.student_id)
                .where(SupervisorStudentAssignment.supervisor_id == supervisor_id)
            )
            direct_student_result = await db.execute(direct_student_ids_query)
            direct_student_ids = [row[0] for row in direct_student_result.fetchall()]

            if supervisor_class_ids and direct_student_ids:
                student_query = student_query.where(
                    or_(
                        Student.class_id.in_(supervisor_class_ids),
                        Student.id.in_(direct_student_ids)
                    )
                )
            elif supervisor_class_ids:
                student_query = student_query.where(Student.class_id.in_(supervisor_class_ids))
            elif direct_student_ids:
                student_query = student_query.where(Student.id.in_(direct_student_ids))
            else:
                return OverallPerformanceResponse(
                    academic_year=academic_year,
                    total_weeks_completed=0,
                    students=[],
                    total_students=0
                )

        if teacher_id:
            student_query = student_query.join(
                TeacherClassAssignment,
                TeacherClassAssignment.class_id == Student.class_id
            ).where(TeacherClassAssignment.teacher_id == teacher_id)

        student_query = student_query.order_by(User.full_name)
        student_result = await db.execute(student_query)
        students = list(student_result.scalars().all())

        if not students:
            return OverallPerformanceResponse(
                academic_year=academic_year,
                total_weeks_completed=0,
                students=[],
                total_students=0
            )

        student_ids = [s.id for s in students]
        current_week = calendar_service.get_current_week()

        # Get all attendance records for these students
        attendance_query = (
            select(WeeklyAttendance)
            .where(
                and_(
                    WeeklyAttendance.student_id.in_(student_ids),
                    WeeklyAttendance.academic_year == academic_year
                )
            )
        )
        attendance_result = await db.execute(attendance_query)
        attendance_records = list(attendance_result.scalars().all())

        # Organize attendance by student
        attendance_by_student: Dict[str, List[WeeklyAttendance]] = defaultdict(list)
        for record in attendance_records:
            attendance_by_student[str(record.student_id)].append(record)

        # Get all test results for this academic year
        year_start, year_end = calendar_service.get_academic_year_dates()
        test_results_query = (
            select(TestResult)
            .options(selectinload(TestResult.test))
            .where(
                and_(
                    TestResult.student_id.in_(student_ids),
                    TestResult.submitted_at >= year_start,
                    TestResult.submitted_at <= year_end
                )
            )
        )
        test_results_result = await db.execute(test_results_query)
        test_results = list(test_results_result.scalars().all())

        # Organize test results by student and subject
        scores_by_student: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        for tr in test_results:
            if not tr.test or tr.percentage is None:
                continue
            student_id = str(tr.student_id)
            test_type = tr.test.type.value if hasattr(tr.test.type, 'value') else str(tr.test.type)
            subject_name = WeeklyAttendanceService.SUBJECT_MAP.get(test_type, test_type)
            scores_by_student[student_id][subject_name].append(float(tr.percentage))

        # Build student performance records
        student_performances = []
        for student in students:
            student_id = str(student.id)
            full_name = student.user.full_name if student.user else ""
            name_parts = full_name.strip().split(maxsplit=1)
            first_name = name_parts[0] if len(name_parts) > 0 else ""
            surname = name_parts[1] if len(name_parts) > 1 else ""

            # Calculate attendance stats
            student_attendance = attendance_by_student.get(student_id, [])
            weeks_present = sum(1 for a in student_attendance if a.is_present == True)
            weeks_absent = sum(1 for a in student_attendance if a.is_present == False)
            total_weeks_marked = weeks_present + weeks_absent
            attendance_rate = round((weeks_present / total_weeks_marked * 100) if total_weeks_marked > 0 else 0, 2)

            # Calculate average scores by subject
            student_scores = scores_by_student.get(student_id, {})
            average_scores = {}
            for subject in WeeklyAttendanceService.SUBJECTS:
                subject_scores = student_scores.get(subject, [])
                if subject_scores:
                    avg_percentage = round(sum(subject_scores) / len(subject_scores), 2)
                    average_scores[subject] = {
                        "averageMark": None,  # Could calculate if we stored marks
                        "averagePercentage": avg_percentage
                    }
                else:
                    average_scores[subject] = {
                        "averageMark": None,
                        "averagePercentage": None
                    }

            student_performances.append(StudentOverallPerformance(
                student_id=student_id,
                student_code=student.student_code or "N/A",
                first_name=first_name,
                surname=surname,
                full_name=full_name,
                class_id=str(student.class_id) if student.class_id else "",
                class_name=student.class_info.name if student.class_info else "N/A",
                year_group=student.year_group,
                total_weeks=current_week,
                weeks_present=weeks_present,
                weeks_absent=weeks_absent,
                attendance_rate=attendance_rate,
                average_scores=average_scores
            ))

        return OverallPerformanceResponse(
            academic_year=academic_year,
            total_weeks_completed=current_week,
            students=student_performances,
            total_students=len(student_performances)
        )

    @staticmethod
    async def bulk_create_attendance(
        db: AsyncSession,
        week_number: int,
        academic_year: str,
        student_attendance: List[Dict],
        recorded_by: UUID
    ) -> Dict[str, Any]:
        """
        Create or update attendance for multiple students at once.

        Args:
            student_attendance: List of {student_id, is_present, comments?, notes?}
        """
        created = 0
        updated = 0
        errors = []

        for item in student_attendance:
            try:
                student_id = UUID(item['student_id'])
                is_present = item.get('is_present')
                comments_data = item.get('comments')
                notes = item.get('notes')

                # Check if record exists
                existing = await db.execute(
                    select(WeeklyAttendance).where(
                        and_(
                            WeeklyAttendance.student_id == student_id,
                            WeeklyAttendance.week_number == week_number,
                            WeeklyAttendance.academic_year == academic_year
                        )
                    )
                )
                record = existing.scalars().first()

                if record:
                    if is_present is not None:
                        record.is_present = is_present
                    if comments_data:
                        record.comments = comments_data
                    if notes is not None:
                        record.notes = notes
                    record.recorded_by = recorded_by
                    updated += 1
                else:
                    comments = comments_data if comments_data else {
                        'help_in': [],
                        'incomplete': [],
                        'unmarked': [],
                        'at_home': []
                    }
                    record = WeeklyAttendance(
                        student_id=student_id,
                        week_number=week_number,
                        academic_year=academic_year,
                        is_present=is_present,
                        comments=comments,
                        notes=notes,
                        recorded_by=recorded_by
                    )
                    db.add(record)
                    created += 1

            except Exception as e:
                errors.append({
                    'student_id': item.get('student_id'),
                    'error': str(e)
                })

        await db.commit()

        return {
            'created': created,
            'updated': updated,
            'errors': errors
        }
