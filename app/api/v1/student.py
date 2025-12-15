from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta, timezone
import io

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User, Student, TestAssignment, StudentTestAssignment, Test, TestAttempt, TestResult, Class
from app.models.user import UserRole
from app.models.test import AssignmentStatus, TestStatus, AttemptStatus
from app.models.marking import StudentCreativeWork, StudentCreativeWorkStatus
from app.schemas.test import (
    TestAttemptCreate, TestAttemptResponse, TestSessionResponse,
    QuestionResponseCreate, QuestionResponseUpdate, QuestionResponseDetail,
    TestSubmissionRequest, TestSubmissionResponse, TestResultDetail
)
from app.schemas.student import (
    StudentProfileResponse, StudentProfileUpdate, ChangePasswordRequest, ChangePasswordResponse,
    StudentProgressResponse, StudentStatsResponse, CreativeWorkResponse, CreativeWorkListResponse
)
from app.schemas.analytics import StudentAnalytics
from app.services.test_session_service import TestSessionService
from app.services.analytics_service import AnalyticsService
from app.services.s3_service import s3_service
from app.core.security import get_password_hash, verify_password

router = APIRouter(prefix="/student", tags=["Student"])


@router.get("/dashboard")
async def get_student_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get student dashboard data"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Get upcoming tests (both class assignments and individual assignments, only published tests)
    now = datetime.now(timezone.utc)
    upcoming = []

    # 1. Get class assignments
    if student.class_id:
        class_assignments = await db.execute(
            select(TestAssignment, Test)
            .join(Test, TestAssignment.test_id == Test.id)
            .where(and_(
                TestAssignment.class_id == student.class_id,
                TestAssignment.status.in_([AssignmentStatus.SCHEDULED, AssignmentStatus.ACTIVE]),
                TestAssignment.scheduled_end > now,
                Test.status == TestStatus.PUBLISHED  # Only show published tests
            ))
            .order_by(TestAssignment.scheduled_start)
        )

        for assignment, test in class_assignments:
            # Check if student has an attempt
            attempt_result = await db.execute(
                select(TestAttempt)
                .where(and_(
                    TestAttempt.test_id == test.id,
                    TestAttempt.student_id == student.id
                ))
            )
            attempt = attempt_result.scalar_one_or_none()

            upcoming.append({
                "assignment_id": str(assignment.id),
                "test_id": str(test.id),
                "test_title": test.title,
                "test_type": test.type.value,
                "scheduled_start": assignment.scheduled_start.isoformat(),
                "scheduled_end": assignment.scheduled_end.isoformat(),
                "duration_minutes": test.duration_minutes,
                "status": "completed" if attempt and attempt.status != AttemptStatus.IN_PROGRESS else
                          "in_progress" if attempt else "not_started",
                "attempt_id": str(attempt.id) if attempt else None
            })

    # 2. Get individual student assignments
    student_assignments = await db.execute(
        select(StudentTestAssignment, Test)
        .join(Test, StudentTestAssignment.test_id == Test.id)
        .where(and_(
            StudentTestAssignment.student_id == student.id,
            StudentTestAssignment.status.in_([AssignmentStatus.SCHEDULED, AssignmentStatus.ACTIVE]),
            StudentTestAssignment.scheduled_end > now,
            Test.status == TestStatus.PUBLISHED  # Only show published tests
        ))
        .order_by(StudentTestAssignment.scheduled_start)
    )

    for assignment, test in student_assignments:
        # Check if student has an attempt
        attempt_result = await db.execute(
            select(TestAttempt)
            .where(and_(
                TestAttempt.test_id == test.id,
                TestAttempt.student_id == student.id
            ))
        )
        attempt = attempt_result.scalar_one_or_none()

        upcoming.append({
            "assignment_id": str(assignment.id),
            "test_id": str(test.id),
            "test_title": test.title,
            "test_type": test.type.value,
            "scheduled_start": assignment.scheduled_start.isoformat(),
            "scheduled_end": assignment.scheduled_end.isoformat(),
            "duration_minutes": test.duration_minutes,
            "status": "completed" if attempt and attempt.status != AttemptStatus.IN_PROGRESS else
                      "in_progress" if attempt else "not_started",
            "attempt_id": str(attempt.id) if attempt else None
        })

    # Sort by scheduled_start time
    upcoming.sort(key=lambda x: x["scheduled_start"])

    # Get recent results (only for published tests)
    recent_results = await db.execute(
        select(TestResult, Test)
        .join(Test, TestResult.test_id == Test.id)
        .where(and_(
            TestResult.student_id == student.id,
            Test.status == TestStatus.PUBLISHED  # Only show results for published tests
        ))
        .order_by(TestResult.submitted_at.desc())
        .limit(5)
    )

    results = []
    for result, test in recent_results:
        results.append({
            "result_id": str(result.id),
            "test_title": test.title,
            "score": f"{result.total_score}/{result.max_score}",
            "percentage": float(result.percentage),
            "grade": result.grade,
            "status": result.status.value,
            "submitted_at": result.submitted_at.isoformat() if result.submitted_at else None
        })

    return {
        "student": {
            "id": str(student.id),
            "name": current_user.full_name,
            "email": current_user.email,
            "student_code": student.student_code,
            "year_group": student.year_group
        },
        "upcoming_tests": upcoming,
        "recent_results": results,
        "stats": {
            "tests_completed": len(results),
            "average_score": sum(r["percentage"] for r in results) / len(results) if results else 0
        }
    }


@router.get("/tests")
async def get_available_tests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all tests available to the student (both class assignments and individual assignments)"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    now = datetime.now(timezone.utc)
    available_tests = []

    # 1. Get all test assignments for student's class (only PUBLISHED tests)
    if student.class_id:
        class_assignments = await db.execute(
            select(TestAssignment, Test)
            .join(Test, TestAssignment.test_id == Test.id)
            .where(and_(
                TestAssignment.class_id == student.class_id,
                TestAssignment.status.in_([AssignmentStatus.SCHEDULED, AssignmentStatus.ACTIVE]),
                Test.status == TestStatus.PUBLISHED  # Only show published tests to students
            ))
            .order_by(TestAssignment.scheduled_start)
        )

        for assignment, test in class_assignments:
            # Check if student has an attempt
            attempt_result = await db.execute(
                select(TestAttempt)
                .where(and_(
                    TestAttempt.test_id == test.id,
                    TestAttempt.student_id == student.id
                ))
            )
            attempt = attempt_result.scalar_one_or_none()

            # Determine if test is available for taking
            # Student can start test only if current time is between scheduled_start and scheduled_end
            can_start = False
            if not attempt or attempt.status == AttemptStatus.IN_PROGRESS:
                # Ensure database datetimes are timezone-aware for comparison
                scheduled_start = assignment.scheduled_start
                scheduled_end = assignment.scheduled_end
                if scheduled_start.tzinfo is None:
                    scheduled_start = scheduled_start.replace(tzinfo=timezone.utc)
                if scheduled_end.tzinfo is None:
                    scheduled_end = scheduled_end.replace(tzinfo=timezone.utc)

                can_start = now >= scheduled_start and now <= scheduled_end

            # For completed tests, get the result ID
            result_id = None
            if attempt and attempt.status != AttemptStatus.IN_PROGRESS:
                result_query = await db.execute(
                    select(TestResult)
                    .where(and_(
                        TestResult.test_id == test.id,
                        TestResult.student_id == student.id,
                        TestResult.attempt_id == attempt.id
                    ))
                )
                test_result = result_query.scalar_one_or_none()
                if test_result:
                    result_id = str(test_result.id)

            available_tests.append({
                "assignment_id": str(assignment.id),
                "test_id": str(test.id),
                "title": test.title,
                "description": test.description,
                "type": test.type.value,
                "duration_minutes": test.duration_minutes,
                "total_marks": test.total_marks,
                "pass_mark": test.pass_mark,
                "scheduled_start": assignment.scheduled_start.isoformat(),
                "scheduled_end": assignment.scheduled_end.isoformat(),
                "can_start": can_start,
                "status": "completed" if attempt and attempt.status != AttemptStatus.IN_PROGRESS else
                          "in_progress" if attempt and attempt.status == AttemptStatus.IN_PROGRESS else
                          "not_started",
                "attempt_id": str(attempt.id) if attempt else None,
                "result_id": result_id,
                "custom_instructions": assignment.custom_instructions
            })

    # 2. Get all individual student test assignments (only PUBLISHED tests)
    student_assignments = await db.execute(
        select(StudentTestAssignment, Test)
        .join(Test, StudentTestAssignment.test_id == Test.id)
        .where(and_(
            StudentTestAssignment.student_id == student.id,
            StudentTestAssignment.status.in_([AssignmentStatus.SCHEDULED, AssignmentStatus.ACTIVE]),
            Test.status == TestStatus.PUBLISHED  # Only show published tests to students
        ))
        .order_by(StudentTestAssignment.scheduled_start)
    )

    for assignment, test in student_assignments:
        # Check if student has an attempt
        attempt_result = await db.execute(
            select(TestAttempt)
            .where(and_(
                TestAttempt.test_id == test.id,
                TestAttempt.student_id == student.id
            ))
        )
        attempt = attempt_result.scalar_one_or_none()

        # Determine if test is available for taking
        # Student can start test only if current time is between scheduled_start and scheduled_end
        can_start = False
        if not attempt or attempt.status == AttemptStatus.IN_PROGRESS:
            # Ensure database datetimes are timezone-aware for comparison
            scheduled_start = assignment.scheduled_start
            scheduled_end = assignment.scheduled_end
            if scheduled_start.tzinfo is None:
                scheduled_start = scheduled_start.replace(tzinfo=timezone.utc)
            if scheduled_end.tzinfo is None:
                scheduled_end = scheduled_end.replace(tzinfo=timezone.utc)

            can_start = now >= scheduled_start and now <= scheduled_end

        # For completed tests, get the result ID
        result_id = None
        if attempt and attempt.status != AttemptStatus.IN_PROGRESS:
            result_query = await db.execute(
                select(TestResult)
                .where(and_(
                    TestResult.test_id == test.id,
                    TestResult.student_id == student.id,
                    TestResult.attempt_id == attempt.id
                ))
            )
            test_result = result_query.scalar_one_or_none()
            if test_result:
                result_id = str(test_result.id)

        available_tests.append({
            "assignment_id": str(assignment.id),
            "test_id": str(test.id),
            "title": test.title,
            "description": test.description,
            "type": test.type.value,
            "duration_minutes": test.duration_minutes,
            "total_marks": test.total_marks,
            "pass_mark": test.pass_mark,
            "scheduled_start": assignment.scheduled_start.isoformat(),
            "scheduled_end": assignment.scheduled_end.isoformat(),
            "can_start": can_start,
            "status": "completed" if attempt and attempt.status != AttemptStatus.IN_PROGRESS else
                      "in_progress" if attempt and attempt.status == AttemptStatus.IN_PROGRESS else
                      "not_started",
            "attempt_id": str(attempt.id) if attempt else None,
            "result_id": result_id,
            "custom_instructions": assignment.custom_instructions
        })

    # Sort by scheduled_start time
    available_tests.sort(key=lambda x: x["scheduled_start"])

    return available_tests


@router.post("/tests/{test_id}/start")
async def start_test(
    test_id: UUID,
    request: Request,
    assignment_id: UUID = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> TestSessionResponse:
    """Start or resume a test attempt"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Cache student.id to avoid lazy loading issues
    student_id = student.id

    # Get browser info
    browser_info = {
        "user_agent": request.headers.get("user-agent", ""),
        "referer": request.headers.get("referer", ""),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    # Get IP address
    ip_address = request.client.host if request.client else "unknown"

    try:
        # Start or resume test attempt
        attempt = await TestSessionService.start_test_attempt(
            db=db,
            test_id=test_id,
            student_id=student_id,
            assignment_id=assignment_id,
            browser_info=browser_info,
            ip_address=ip_address
        )

        # Get full session details
        session = await TestSessionService.get_test_session(
            db=db,
            attempt_id=attempt.id,
            student_id=student_id
        )

        return session

    except ValueError as e:
        import traceback
        print(f"ValueError starting test: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        print(f"Error starting test: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to start test")


@router.get("/tests/{test_id}/session")
async def get_test_session(
    test_id: UUID,
    attempt_id: UUID = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> TestSessionResponse:
    """Get current test session details"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    try:
        session = await TestSessionService.get_test_session(
            db=db,
            attempt_id=attempt_id,
            student_id=student.id
        )
        return session

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get test session")


@router.post("/attempts/{attempt_id}/answers/{question_id}")
async def save_answer(
    attempt_id: UUID,
    question_id: UUID,
    answer_data: QuestionResponseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> QuestionResponseDetail:
    """Save or update an answer for a question"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    try:
        response = await TestSessionService.save_answer(
            db=db,
            attempt_id=attempt_id,
            question_id=question_id,
            answer_data=answer_data,
            student_id=student.id
        )

        return QuestionResponseDetail.model_validate(response)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to save answer")


@router.post("/attempts/{attempt_id}/answers")
async def save_multiple_answers(
    attempt_id: UUID,
    answers: Dict[str, QuestionResponseCreate],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[QuestionResponseDetail]:
    """Save multiple answers at once (for auto-save)"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    try:
        responses = await TestSessionService.bulk_save_answers(
            db=db,
            attempt_id=attempt_id,
            answers=answers,
            student_id=student.id
        )

        return [QuestionResponseDetail.model_validate(r) for r in responses]

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to save answers")


@router.post("/attempts/{attempt_id}/submit")
async def submit_test(
    attempt_id: UUID,
    submission_data: TestSubmissionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> TestSubmissionResponse:
    """Submit test and get results"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    try:
        result = await TestSessionService.submit_test(
            db=db,
            attempt_id=attempt_id,
            submission_data=submission_data,
            student_id=student.id
        )

        return result

    except ValueError as e:
        print(f"ValueError submitting test: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Exception submitting test: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to submit test: {str(e)}")


@router.get("/results")
async def get_my_results(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[TestResultDetail]:
    """Get all test results for the current student"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    results = await TestSessionService.get_student_test_results(
        db=db,
        student_id=student.id,
        limit=limit,
        offset=offset
    )

    return results


@router.get("/results/{result_id}")
async def get_result_details(
    result_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> TestResultDetail:
    """Get detailed test result"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    result = await TestSessionService.get_test_result(
        db=db,
        result_id=result_id,
        student_id=student.id
    )

    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    return result


@router.get("/profile")
async def get_student_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> StudentProfileResponse:
    """Get current student's profile information"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record with class info
    from sqlalchemy.orm import selectinload
    student_result = await db.execute(
        select(Student)
        .options(selectinload(Student.class_info))
        .where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Build response
    profile_data = {
        "id": student.id,
        "user_id": student.user_id,
        "email": current_user.email,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "student_code": student.student_code,
        "year_group": student.year_group,
        "enrollment_date": student.enrollment_date,
        "status": student.status,
        "class_info": student.class_info,
        "created_at": student.created_at,
        "updated_at": student.updated_at
    }

    return StudentProfileResponse(**profile_data)


@router.put("/profile")
async def update_student_profile(
    profile_data: StudentProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> StudentProfileResponse:
    """Update current student's profile information"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        # Get student record
        from sqlalchemy.orm import selectinload
        student_result = await db.execute(
            select(Student)
            .options(selectinload(Student.class_info))
            .where(Student.user_id == current_user.id)
        )
        student = student_result.scalar_one_or_none()
        if not student:
            raise HTTPException(status_code=404, detail="Student profile not found")

        # Update allowed fields
        if profile_data.full_name is not None:
            current_user.full_name = profile_data.full_name

        await db.commit()

        # Return updated profile
        updated_profile_data = {
            "id": student.id,
            "user_id": student.user_id,
            "email": current_user.email,
            "username": current_user.username,
            "full_name": current_user.full_name,
            "student_code": student.student_code,
            "year_group": student.year_group,
            "enrollment_date": student.enrollment_date,
            "status": student.status,
            "class_info": student.class_info,
            "created_at": student.created_at,
            "updated_at": student.updated_at
        }

        return StudentProfileResponse(**updated_profile_data)

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")


@router.post("/change-password")
async def change_password(
    password_data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> ChangePasswordResponse:
    """Change current student's password"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        # Verify current password
        if not verify_password(password_data.current_password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

        # Update password
        current_user.password_hash = get_password_hash(password_data.new_password)
        await db.commit()

        return ChangePasswordResponse(
            message="Password changed successfully",
            success=True
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to change password: {str(e)}")


@router.get("/progress")
async def get_student_progress(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> StudentProgressResponse:
    """Get current student's progress and performance analytics"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Get all test results for this student
    results = await db.execute(
        select(TestResult, Test)
        .join(Test, TestResult.test_id == Test.id)
        .where(TestResult.student_id == student.id)
        .order_by(TestResult.submitted_at.desc())
    )

    all_results = results.fetchall()

    if not all_results:
        # No results yet
        return StudentProgressResponse(
            total_tests=0,
            completed_tests=0,
            average_score=0.0,
            best_score=0.0,
            improvement_percentage=None,
            subject_performance={},
            recent_trends=[]
        )

    # Calculate basic stats
    total_tests = len(all_results)
    percentages = [float(result.TestResult.percentage) for result in all_results]
    average_score = sum(percentages) / len(percentages)
    best_score = max(percentages)

    # Calculate improvement (comparing first half to second half)
    improvement_percentage = None
    if len(percentages) >= 4:
        mid_point = len(percentages) // 2
        first_half_avg = sum(percentages[mid_point:]) / mid_point  # Earlier tests (reversed order)
        second_half_avg = sum(percentages[:mid_point]) / mid_point  # Recent tests
        improvement_percentage = second_half_avg - first_half_avg

    # Calculate subject performance
    subject_performance = {}
    for result in all_results:
        subject = result.Test.type.value
        if subject not in subject_performance:
            subject_performance[subject] = []
        subject_performance[subject].append(float(result.TestResult.percentage))

    # Average by subject
    for subject in subject_performance:
        scores = subject_performance[subject]
        subject_performance[subject] = {
            "average": sum(scores) / len(scores),
            "tests_taken": len(scores),
            "best_score": max(scores)
        }

    # Recent trends (last 5 tests)
    recent_trends = []
    for result in all_results[:5]:  # Already ordered by submitted_at desc
        recent_trends.append({
            "test_title": result.Test.title,
            "score": float(result.TestResult.percentage),
            "submitted_at": result.TestResult.submitted_at.isoformat() if result.TestResult.submitted_at else None,
            "subject": result.Test.type.value
        })

    return StudentProgressResponse(
        total_tests=total_tests,
        completed_tests=total_tests,
        average_score=average_score,
        best_score=best_score,
        improvement_percentage=improvement_percentage,
        subject_performance=subject_performance,
        recent_trends=recent_trends
    )


@router.get("/statistics")
async def get_student_statistics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> StudentStatsResponse:
    """Get current student's comprehensive statistics"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Get completed tests count and stats (only for published tests)
    results = await db.execute(
        select(TestResult, Test)
        .join(Test, TestResult.test_id == Test.id)
        .where(and_(
            TestResult.student_id == student.id,
            Test.status == TestStatus.PUBLISHED  # Only include published tests
        ))
        .order_by(TestResult.submitted_at.desc())
    )

    all_results = results.fetchall()

    # Get pending tests count (only for published tests)
    now = datetime.now(timezone.utc)
    pending_tests = await db.execute(
        select(func.count(TestAssignment.id))
        .join(Test, TestAssignment.test_id == Test.id)
        .outerjoin(TestAttempt, and_(
            TestAttempt.test_id == Test.id,
            TestAttempt.student_id == student.id
        ))
        .where(and_(
            TestAssignment.class_id == student.class_id,
            TestAssignment.status.in_([AssignmentStatus.SCHEDULED, AssignmentStatus.ACTIVE]),
            TestAssignment.scheduled_end > now,
            or_(TestAttempt.id.is_(None), TestAttempt.status == AttemptStatus.IN_PROGRESS),
            Test.status == TestStatus.PUBLISHED  # Only count published tests
        ))
    )

    pending_count = pending_tests.scalar()

    # Calculate stats
    tests_completed = len(all_results)
    percentages = [float(result.TestResult.percentage) for result in all_results]
    average_score = sum(percentages) / len(percentages) if percentages else 0.0
    best_score = max(percentages) if percentages else 0.0

    # Calculate total time spent (in minutes)
    total_time_minutes = 0
    for result in all_results:
        if result.TestResult.time_taken:
            total_time_minutes += result.TestResult.time_taken // 60  # Convert seconds to minutes

    # Calculate streak (simplified - tests completed in consecutive days)
    streak_days = 0
    if all_results:
        # This is a simplified calculation - in a real system you'd want more sophisticated logic
        recent_dates = set()
        for result in all_results[:10]:  # Check last 10 tests
            if result.TestResult.submitted_at:
                date_str = result.TestResult.submitted_at.date()
                recent_dates.add(date_str)
        streak_days = len(recent_dates)

    # Simple badges based on performance
    badges_earned = []
    if tests_completed >= 1:
        badges_earned.append("First Test Completed")
    if tests_completed >= 5:
        badges_earned.append("Regular Tester")
    if tests_completed >= 10:
        badges_earned.append("Test Master")
    if average_score >= 90:
        badges_earned.append("High Achiever")
    if average_score >= 80:
        badges_earned.append("Good Performer")
    if best_score == 100:
        badges_earned.append("Perfect Score")

    # Get class rank (optional)
    class_rank = None
    class_size = None
    if student.class_id:
        # Get all students in class with their average scores (only for published tests)
        class_students = await db.execute(
            select(Student.id, func.avg(TestResult.percentage).label('avg_score'))
            .outerjoin(TestResult, TestResult.student_id == Student.id)
            .outerjoin(Test, TestResult.test_id == Test.id)
            .where(and_(
                Student.class_id == student.class_id,
                or_(Test.status == TestStatus.PUBLISHED, Test.id.is_(None))  # Include students with no tests
            ))
            .group_by(Student.id)
            .order_by(func.avg(TestResult.percentage).desc().nulls_last())
        )

        class_results = class_students.fetchall()
        class_size = len(class_results)

        for idx, (student_id, avg_score) in enumerate(class_results):
            if student_id == student.id:
                class_rank = idx + 1
                break

    return StudentStatsResponse(
        tests_completed=tests_completed,
        tests_pending=pending_count,
        average_score=average_score,
        best_score=best_score,
        total_time_spent=total_time_minutes,
        streak_days=streak_days,
        badges_earned=badges_earned,
        class_rank=class_rank,
        class_size=class_size
    )


@router.get("/analytics")
async def get_student_analytics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> StudentAnalytics:
    """Get comprehensive analytics for the current student"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    try:
        analytics = await AnalyticsService.get_student_analytics(db, student.id)
        return StudentAnalytics(**analytics)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get analytics: {str(e)}")


# ============================================================
# Creative Writing Endpoints
# ============================================================


@router.get("/creative-writing")
async def get_creative_writing_submissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> CreativeWorkListResponse:
    """Get all creative writing submissions for the current student"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Get all submissions for this student
    submissions_result = await db.execute(
        select(StudentCreativeWork)
        .where(StudentCreativeWork.student_id == student.id)
        .order_by(StudentCreativeWork.submitted_at.desc())
    )
    submissions = submissions_result.scalars().all()

    return CreativeWorkListResponse(
        submissions=[
            CreativeWorkResponse(
                id=sub.id,
                title=sub.title,
                description=sub.description,
                image_url=sub.image_url,
                status=sub.status.value,
                feedback=sub.feedback,
                submitted_at=sub.submitted_at,
                reviewed_at=sub.reviewed_at
            )
            for sub in submissions
        ],
        total=len(submissions)
    )


@router.post("/creative-writing/upload")
async def upload_creative_writing(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> CreativeWorkResponse:
    """Upload a new creative writing submission"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Validate file
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Only image files are allowed")

    # Read file content
    file_content = await file.read()
    file_size = len(file_content)

    # Validate file size (max 10MB)
    if file_size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size must be less than 10MB")

    # Reset file pointer for upload
    file_obj = io.BytesIO(file_content)

    # Upload to S3
    upload_result = await s3_service.upload_file(
        file=file_obj,
        file_name=file.filename or "creative_work.jpg",
        folder="creative-writing"
    )

    if not upload_result:
        raise HTTPException(status_code=500, detail="Failed to upload file")

    # Create database record
    creative_work = StudentCreativeWork(
        student_id=student.id,
        title=title,
        description=description,
        image_url=upload_result["public_url"],
        s3_key=upload_result["s3_key"],
        original_filename=file.filename,
        file_size_bytes=file_size,
        mime_type=file.content_type
    )

    db.add(creative_work)
    await db.commit()
    await db.refresh(creative_work)

    return CreativeWorkResponse(
        id=creative_work.id,
        title=creative_work.title,
        description=creative_work.description,
        image_url=creative_work.image_url,
        status=creative_work.status.value,
        feedback=creative_work.feedback,
        submitted_at=creative_work.submitted_at,
        reviewed_at=creative_work.reviewed_at
    )


@router.delete("/creative-writing/{submission_id}")
async def delete_creative_writing(
    submission_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a creative writing submission (only if pending)"""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get student record
    student_result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Get submission
    submission_result = await db.execute(
        select(StudentCreativeWork).where(
            StudentCreativeWork.id == submission_id,
            StudentCreativeWork.student_id == student.id
        )
    )
    submission = submission_result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != StudentCreativeWorkStatus.PENDING:
        raise HTTPException(status_code=400, detail="Can only delete pending submissions")

    # Delete from S3
    if submission.s3_key:
        await s3_service.delete_file(submission.s3_key)

    # Delete from database
    await db.delete(submission)
    await db.commit()

    return {"message": "Submission deleted successfully"}