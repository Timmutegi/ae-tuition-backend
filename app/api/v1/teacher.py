from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_admin, get_current_teacher
from app.models.user import User
from app.models.intervention import AlertStatus
from app.services.teacher_service import TeacherService
from app.services.intervention_service import InterventionService
from app.schemas.teacher import (
    TeacherCreateRequest,
    TeacherProfileUpdate,
    TeacherProfileResponse,
    TeacherListResponse,
    TeacherClassAssignmentCreate,
    TeacherClassAssignmentResponse,
    BulkClassAssignment,
    AssignedClassInfo
)
from app.schemas.intervention import InterventionAlertResponse


# Request schemas for intervention actions
class AlertApprovalRequest(BaseModel):
    """Request body for approving an alert."""
    approval_notes: Optional[str] = None


class AlertDismissRequest(BaseModel):
    """Request body for dismissing an alert."""
    reason: str

router = APIRouter(prefix="/teachers", tags=["teachers"])


# ============================================================
# Teacher's own endpoints (for teacher portal)
# IMPORTANT: These must be defined BEFORE /{teacher_id} routes
# to avoid FastAPI matching "me" as a teacher_id parameter
# ============================================================

@router.get("/me/profile", response_model=TeacherProfileResponse)
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Get current teacher's profile."""
    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )
    return teacher


@router.get("/me/classes", response_model=List[AssignedClassInfo])
async def get_my_classes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Get current teacher's assigned classes."""
    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )

    classes = await TeacherService.get_teacher_classes(db, teacher.id)
    result = []
    for cls in classes:
        result.append(AssignedClassInfo(
            id=cls.id,
            name=cls.name,
            year_group=cls.year_group,
            academic_year=cls.academic_year,
            student_count=len(cls.students) if cls.students else 0,
            is_primary=False
        ))
    return result


@router.get("/me/students")
async def get_my_students(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Get all students in current teacher's assigned classes."""
    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )

    students = await TeacherService.get_teacher_students(db, teacher.id)
    result = []
    for student in students:
        result.append({
            "id": str(student.id),
            "user_id": str(student.user_id),
            "full_name": student.user.full_name if student.user else None,
            "email": student.user.email if student.user else None,
            "student_code": student.student_code,
            "year_group": student.year_group,
            "class_id": str(student.class_id) if student.class_id else None,
            "class_name": student.class_info.name if student.class_info else None,
            "status": student.status.value if student.status else None
        })
    return result


@router.get("/me/tests")
async def get_my_tests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Get tests assigned to the current teacher's classes or students in those classes."""
    from app.models.test import Test, TestAssignment, StudentTestAssignment, TestStatus
    from app.models.teacher import TeacherClassAssignment
    from app.models.student import Student

    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )

    # Get class IDs assigned to this teacher
    class_result = await db.execute(
        select(TeacherClassAssignment.class_id)
        .where(TeacherClassAssignment.teacher_id == teacher.id)
    )
    class_ids = [row[0] for row in class_result.fetchall()]

    if not class_ids:
        return {"tests": []}

    # Get student IDs in those classes
    student_result = await db.execute(
        select(Student.id)
        .where(Student.class_id.in_(class_ids))
    )
    student_ids = [row[0] for row in student_result.fetchall()]

    # Get tests assigned to those classes (with assignment info)
    class_test_result = await db.execute(
        select(Test, TestAssignment)
        .join(TestAssignment, Test.id == TestAssignment.test_id)
        .where(TestAssignment.class_id.in_(class_ids))
    )
    class_tests = class_test_result.fetchall()

    # Get tests assigned to students in those classes (if any students exist)
    student_tests = []
    if student_ids:
        student_test_result = await db.execute(
            select(Test, StudentTestAssignment)
            .join(StudentTestAssignment, Test.id == StudentTestAssignment.test_id)
            .where(StudentTestAssignment.student_id.in_(student_ids))
        )
        student_tests = student_test_result.fetchall()

    # Combine and deduplicate tests, keeping track of assignments
    tests_dict = {}

    for test, assignment in class_tests:
        if str(test.id) not in tests_dict:
            tests_dict[str(test.id)] = {
                "id": str(test.id),
                "title": test.title,
                "description": test.description,
                "subject": test.type.value if test.type else None,
                "duration_minutes": test.duration_minutes,
                "total_points": test.total_marks or 0,
                "is_active": test.status == TestStatus.PUBLISHED,
                "start_date": assignment.scheduled_start.isoformat() if assignment.scheduled_start else None,
                "end_date": assignment.scheduled_end.isoformat() if assignment.scheduled_end else None,
                "created_at": test.created_at.isoformat() if test.created_at else None,
                "status": test.status.value if test.status else None,
                "test_type": test.type.value if test.type else None,
                "assignment_type": "class"
            }

    for test, assignment in student_tests:
        if str(test.id) not in tests_dict:
            tests_dict[str(test.id)] = {
                "id": str(test.id),
                "title": test.title,
                "description": test.description,
                "subject": test.type.value if test.type else None,
                "duration_minutes": test.duration_minutes,
                "total_points": test.total_marks or 0,
                "is_active": test.status == TestStatus.PUBLISHED,
                "start_date": assignment.scheduled_start.isoformat() if assignment.scheduled_start else None,
                "end_date": assignment.scheduled_end.isoformat() if assignment.scheduled_end else None,
                "created_at": test.created_at.isoformat() if test.created_at else None,
                "status": test.status.value if test.status else None,
                "test_type": test.type.value if test.type else None,
                "assignment_type": "student"
            }

    return {"tests": list(tests_dict.values())}


# ============================================================
# Teacher Test Results Endpoints
# ============================================================

@router.get("/me/tests/{test_id}/results")
async def get_test_results(
    test_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Get all student results for a specific test.
    Only returns results for students in the teacher's assigned classes.
    """
    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )

    try:
        results = await TeacherService.get_test_results_for_teacher(
            db=db,
            teacher_id=teacher.id,
            test_id=test_id
        )
        return results
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/me/results/{result_id}")
async def get_result_detail(
    result_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Get detailed result for a specific student's test attempt.
    Only accessible if the student is in one of the teacher's assigned classes.
    """
    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )

    result = await TeacherService.get_result_detail_for_teacher(
        db=db,
        teacher_id=teacher.id,
        result_id=result_id
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not found or access denied"
        )

    return result


# ============================================================
# Teacher Intervention Endpoints
# ============================================================

@router.get("/me/intervention/alerts")
async def get_my_intervention_alerts(
    status_filter: Optional[AlertStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Get intervention alerts for students in the current teacher's assigned classes.

    Teachers only see alerts for students in classes they are assigned to.
    """
    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )

    intervention_service = InterventionService(db)
    alerts, total = await intervention_service.get_teacher_alerts(
        teacher_id=teacher.id,
        status=status_filter,
        limit=limit,
        offset=offset
    )

    # Manually serialize alerts to include computed properties
    alerts_data = []
    for alert in alerts:
        alert_dict = {
            "id": str(alert.id),
            "student_id": str(alert.student_id),
            "threshold_id": str(alert.threshold_id) if alert.threshold_id else None,
            "subject": alert.subject,
            "alert_type": alert.alert_type,
            "priority": alert.priority.value if alert.priority else None,
            "status": alert.status.value if alert.status else None,
            "current_average": alert.current_average,
            "previous_average": alert.previous_average,
            "weeks_failing": alert.weeks_failing,
            "weekly_scores": alert.weekly_scores,
            "title": alert.title,
            "description": alert.description,
            "recommended_actions": alert.recommended_actions,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "resolved_by": str(alert.resolved_by) if alert.resolved_by else None,
            "resolution_notes": alert.resolution_notes,
            "approved_at": alert.approved_at.isoformat() if alert.approved_at else None,
            "approved_by": str(alert.approved_by) if alert.approved_by else None,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "updated_at": alert.updated_at.isoformat() if alert.updated_at else None,
            # Computed properties for student info
            "student_name": alert.student_name,
            "student_code": alert.student_code,
            "class_name": alert.class_name,
            "recipients": []
        }
        alerts_data.append(alert_dict)

    return {
        "alerts": alerts_data,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/me/intervention/alerts/{alert_id}")
async def get_intervention_alert_detail(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Get detailed information about a specific intervention alert.

    Teachers can only view alerts for students in their assigned classes.
    """
    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )

    intervention_service = InterventionService(db)

    # Verify the alert belongs to a student in the teacher's classes
    alert = await intervention_service.get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )

    # Check if teacher has access to this alert
    has_access = await intervention_service.teacher_has_access_to_alert(teacher.id, alert_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this alert"
        )

    return alert


@router.post("/me/intervention/alerts/{alert_id}/approve")
async def approve_intervention_alert(
    alert_id: UUID,
    approval_data: AlertApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Approve an intervention alert and trigger parent notification.

    When approved:
    1. Alert status changes to IN_PROGRESS
    2. Parent is notified via email about the student's performance
    3. Audit log is created
    """
    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )

    intervention_service = InterventionService(db)

    # Verify access
    has_access = await intervention_service.teacher_has_access_to_alert(teacher.id, alert_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this alert"
        )

    # Approve the alert
    alert = await intervention_service.approve_alert(
        alert_id=alert_id,
        approver_id=current_user.id,
        approval_notes=approval_data.approval_notes
    )

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to approve alert. Alert may already be resolved or not found."
        )

    return {
        "message": "Alert approved successfully. Parent has been notified.",
        "alert_id": str(alert_id),
        "status": alert.status.value
    }


@router.post("/me/intervention/alerts/{alert_id}/dismiss")
async def dismiss_intervention_alert(
    alert_id: UUID,
    dismiss_data: AlertDismissRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Dismiss an intervention alert without notifying parents.

    A reason must be provided explaining why parent notification is not needed.
    The dismissal is logged for audit purposes.
    """
    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )

    intervention_service = InterventionService(db)

    # Verify access
    has_access = await intervention_service.teacher_has_access_to_alert(teacher.id, alert_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this alert"
        )

    # Dismiss the alert
    alert = await intervention_service.dismiss_alert(
        alert_id=alert_id,
        resolver_id=current_user.id,
        reason=dismiss_data.reason
    )

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to dismiss alert. Alert may already be resolved or not found."
        )

    return {
        "message": "Alert dismissed successfully.",
        "alert_id": str(alert_id),
        "status": alert.status.value
    }


@router.get("/me/intervention/stats")
async def get_my_intervention_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Get intervention statistics for the current teacher's classes.
    """
    teacher = await TeacherService.get_teacher_by_user_id(db, current_user.id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher profile not found"
        )

    intervention_service = InterventionService(db)

    # Get counts by status
    pending_alerts, pending_total = await intervention_service.get_teacher_alerts(
        teacher_id=teacher.id,
        status=AlertStatus.PENDING,
        limit=1,
        offset=0
    )

    in_progress_alerts, in_progress_total = await intervention_service.get_teacher_alerts(
        teacher_id=teacher.id,
        status=AlertStatus.IN_PROGRESS,
        limit=1,
        offset=0
    )

    resolved_alerts, resolved_total = await intervention_service.get_teacher_alerts(
        teacher_id=teacher.id,
        status=AlertStatus.RESOLVED,
        limit=1,
        offset=0
    )

    return {
        "pending_count": pending_total,
        "in_progress_count": in_progress_total,
        "resolved_count": resolved_total,
        "total_alerts": pending_total + in_progress_total + resolved_total
    }


# ============================================================
# Admin-only endpoints for teacher management
# ============================================================

@router.post("", response_model=TeacherProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_teacher(
    teacher_data: TeacherCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Create a new teacher account. Admin only."""
    try:
        teacher = await TeacherService.create_teacher(db, teacher_data, current_user.id)
        return teacher
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create teacher: {str(e)}"
        )


@router.get("", response_model=List[TeacherListResponse])
async def get_all_teachers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get all teachers. Admin only."""
    teachers = await TeacherService.get_all_teachers(db, skip, limit, is_active)
    result = []
    for teacher in teachers:
        result.append(TeacherListResponse(
            id=teacher.id,
            user_id=teacher.user_id,
            full_name=teacher.user.full_name if teacher.user else None,
            email=teacher.user.email if teacher.user else "",
            is_active=teacher.user.is_active if teacher.user else False,
            assigned_classes_count=len(teacher.class_assignments) if teacher.class_assignments else 0
        ))
    return result


@router.get("/count")
async def get_teachers_count(
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get total count of teachers. Admin only."""
    count = await TeacherService.count_teachers(db, is_active)
    return {"count": count}


@router.get("/{teacher_id}", response_model=TeacherProfileResponse)
async def get_teacher(
    teacher_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get teacher by ID. Admin only."""
    teacher = await TeacherService.get_teacher_by_id(db, teacher_id)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )
    return teacher


@router.put("/{teacher_id}", response_model=TeacherProfileResponse)
async def update_teacher(
    teacher_id: UUID,
    teacher_data: TeacherProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update teacher profile. Admin only."""
    teacher = await TeacherService.update_teacher(db, teacher_id, teacher_data)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )
    return teacher


@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_teacher(
    teacher_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Delete teacher. Admin only."""
    success = await TeacherService.delete_teacher(db, teacher_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )


# Class assignment endpoints
@router.post("/{teacher_id}/classes", response_model=TeacherClassAssignmentResponse)
async def assign_class_to_teacher(
    teacher_id: UUID,
    class_id: UUID,
    is_primary: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Assign a class to a teacher. Admin only."""
    assignment_data = TeacherClassAssignmentCreate(
        teacher_id=teacher_id,
        class_id=class_id,
        is_primary=is_primary
    )
    try:
        assignment = await TeacherService.assign_class(db, assignment_data, current_user.id)
        return assignment
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to assign class: {str(e)}"
        )


@router.post("/{teacher_id}/classes/bulk", response_model=List[TeacherClassAssignmentResponse])
async def bulk_assign_classes(
    teacher_id: UUID,
    bulk_data: BulkClassAssignment,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Assign multiple classes to a teacher. Admin only."""
    bulk_data.teacher_id = teacher_id
    assignments = await TeacherService.bulk_assign_classes(db, bulk_data, current_user.id)
    return assignments


@router.delete("/{teacher_id}/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_class_from_teacher(
    teacher_id: UUID,
    class_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Remove a class assignment from a teacher. Admin only."""
    success = await TeacherService.remove_class_assignment(db, teacher_id, class_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class assignment not found"
        )


@router.get("/{teacher_id}/classes", response_model=List[AssignedClassInfo])
async def get_teacher_classes(
    teacher_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get all classes assigned to a teacher. Admin only."""
    classes = await TeacherService.get_teacher_classes(db, teacher_id)
    result = []
    for cls in classes:
        result.append(AssignedClassInfo(
            id=cls.id,
            name=cls.name,
            year_group=cls.year_group,
            academic_year=cls.academic_year,
            student_count=len(cls.students) if cls.students else 0,
            is_primary=False  # TODO: Add is_primary from assignment
        ))
    return result


@router.get("/{teacher_id}/students")
async def get_teacher_students(
    teacher_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Get all students from classes assigned to a teacher. Admin only."""
    students = await TeacherService.get_teacher_students(db, teacher_id)
    result = []
    for student in students:
        result.append({
            "id": str(student.id),
            "user_id": str(student.user_id),
            "full_name": student.user.full_name if student.user else None,
            "email": student.user.email if student.user else None,
            "student_code": student.student_code,
            "year_group": student.year_group,
            "class_name": student.class_info.name if student.class_info else None,
            "status": student.status.value if student.status else None
        })
    return result
