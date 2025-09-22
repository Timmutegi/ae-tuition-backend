from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin_user
from app.models import User
from app.schemas.student import (
    StudentCreate, StudentUpdate, StudentResponse, StudentListResponse,
    CSVUploadPreview, CSVUploadResult, PasswordResetResponse,
    ClassCreate, ClassUpdate, ClassResponse
)
from app.schemas.analytics import (
    AdminDashboardOverview, StudentAnalytics, ClassAnalytics, TestAnalytics
)
from app.services.student_service import StudentService
from app.services.csv_processor import CSVProcessorService
from app.services.analytics_service import AnalyticsService


router = APIRouter(prefix="/admin", tags=["admin"])
student_service = StudentService()


# Student Management Endpoints

@router.post("/students/upload", response_model=CSVUploadPreview)
async def upload_students_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Upload and validate CSV file for bulk student creation."""
    # Validate file structure
    await CSVProcessorService.validate_csv_structure(file)

    # Parse CSV data
    students_data = await CSVProcessorService.parse_csv_file(file)

    # Validate student data
    valid_records, errors = await CSVProcessorService.validate_student_data(
        students_data, db
    )

    # Transform valid records to match frontend expectations
    # Map CSV columns to StudentCreate schema
    transformed_records = []
    for record in valid_records:
        # Combine first name and surname for full name
        full_name = f"{record.get('First Name', '')} {record.get('Surname', '')}".strip()

        transformed = {
            'email': record.get('Email Address', ''),
            'full_name': full_name,
            'first_name': record.get('First Name', ''),
            'surname': record.get('Surname', ''),
            'student_id': record.get('Student ID', ''),
            'class_name': record.get('Class ID', ''),
            'year_group': int(record.get('Year Group', 0))
        }
        transformed_records.append(transformed)

    return CSVUploadPreview(
        data=transformed_records,
        errors=errors,
        total_rows=len(students_data),
        valid_rows=len(valid_records),
        invalid_rows=len(errors)
    )


@router.post("/students/bulk-create", response_model=CSVUploadResult)
async def bulk_create_students(
    students: List[StudentCreate],
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Create multiple students from validated data."""
    result = await student_service.create_bulk_students(db, students)

    return CSVUploadResult(
        file_name="bulk_upload",
        total_records=result["total"],
        successful_records=len(result["successful"]),
        failed_records=len(result["failed"]),
        errors=result["failed"]
    )


@router.get("/students", response_model=StudentListResponse)
async def list_students(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
    class_id: Optional[UUID] = Query(None),
    year_group: Optional[int] = Query(None, ge=1, le=13),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Get paginated list of students with optional filters."""
    result = await student_service.get_students(
        db=db,
        page=page,
        limit=limit,
        search=search,
        class_id=class_id,
        year_group=year_group,
        status=status
    )

    # Transform Student objects to StudentResponse objects
    student_responses = []
    for student in result["students"]:
        student_response = StudentResponse(
            id=student.id,
            user_id=student.user_id,
            student_code=student.student_code,
            email=student.user.email,
            full_name=student.user.full_name,
            username=student.user.username,
            class_id=student.class_id,
            year_group=student.year_group,
            enrollment_date=student.enrollment_date,
            status=student.status,
            is_active=student.user.is_active,
            created_at=student.created_at,
            updated_at=student.updated_at,
            class_info=student.class_info
        )
        student_responses.append(student_response)

    return StudentListResponse(
        students=student_responses,
        total=result["total"],
        page=result["page"],
        pages=result["pages"],
        limit=result["limit"]
    )


@router.get("/students/{student_id}", response_model=StudentResponse)
async def get_student(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Get detailed information about a specific student."""
    student = await student_service.get_student(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    return StudentResponse(
        id=student.id,
        user_id=student.user_id,
        student_code=student.student_code,
        email=student.user.email,
        full_name=student.user.full_name,
        username=student.user.username,
        class_id=student.class_id,
        year_group=student.year_group,
        enrollment_date=student.enrollment_date,
        status=student.status,
        is_active=student.user.is_active,
        created_at=student.created_at,
        updated_at=student.updated_at,
        class_info=student.class_info
    )


@router.put("/students/{student_id}", response_model=StudentResponse)
async def update_student(
    student_id: UUID,
    student_data: StudentUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Update student information."""
    student = await student_service.update_student(db, student_id, student_data)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    return StudentResponse(
        id=student.id,
        user_id=student.user_id,
        student_code=student.student_code,
        email=student.user.email,
        full_name=student.user.full_name,
        username=student.user.username,
        class_id=student.class_id,
        year_group=student.year_group,
        enrollment_date=student.enrollment_date,
        status=student.status,
        is_active=student.user.is_active,
        created_at=student.created_at,
        updated_at=student.updated_at,
        class_info=student.class_info
    )


@router.delete("/students/{student_id}")
async def delete_student(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Delete a student account."""
    success = await student_service.delete_student(db, student_id)
    if not success:
        raise HTTPException(status_code=404, detail="Student not found")

    return {"message": "Student deleted successfully"}


@router.post("/students/{student_id}/reset-password", response_model=PasswordResetResponse)
async def reset_student_password(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Reset student password and send email notification."""
    result = await student_service.reset_password(db, student_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    return PasswordResetResponse(
        message=result["message"],
        email_sent=result["email_sent"]
    )


@router.get("/students/template/download")
async def download_csv_template(
    current_admin: User = Depends(get_current_admin_user)
):
    """Download CSV template for student upload."""
    template = CSVProcessorService.generate_csv_template()

    return Response(
        content=template.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=student_upload_template.csv"
        }
    )


# Analytics Endpoints

@router.get("/analytics/dashboard", response_model=AdminDashboardOverview)
async def get_admin_dashboard_analytics(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Get comprehensive analytics overview for admin dashboard."""
    try:
        analytics = await AnalyticsService.get_admin_dashboard_overview(db)
        return AdminDashboardOverview(**analytics)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard analytics: {str(e)}")


@router.get("/analytics/students/{student_id}", response_model=StudentAnalytics)
async def get_student_analytics(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Get detailed analytics for a specific student."""
    try:
        analytics = await AnalyticsService.get_student_analytics(db, student_id)
        return StudentAnalytics(**analytics)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get student analytics: {str(e)}")


@router.get("/analytics/classes/{class_id}", response_model=ClassAnalytics)
async def get_class_analytics(
    class_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Get comprehensive analytics for a specific class."""
    try:
        analytics = await AnalyticsService.get_class_analytics(db, class_id)
        return ClassAnalytics(**analytics)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get class analytics: {str(e)}")


@router.get("/analytics/tests/{test_id}", response_model=TestAnalytics)
async def get_test_analytics(
    test_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Get detailed analytics for a specific test."""
    try:
        analytics = await AnalyticsService.get_test_analytics(db, test_id)
        return TestAnalytics(**analytics)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get test analytics: {str(e)}")