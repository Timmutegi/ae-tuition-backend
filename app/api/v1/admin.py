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
    ClassCreate, ClassUpdate, ClassResponse, ClassListResponse
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
    limit: int = Query(50, ge=1, le=1000),
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


# Class Management Endpoints

@router.get("/classes", response_model=ClassListResponse)
async def list_classes(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
    year_group: Optional[int] = Query(None, ge=1, le=13),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Get paginated list of classes with optional filters."""
    result = await student_service.get_classes(
        db=db,
        page=page,
        limit=limit,
        search=search,
        year_group=year_group
    )

    return ClassListResponse(
        classes=result["classes"],
        total=result["total"],
        page=result["page"],
        pages=result["pages"],
        limit=result["limit"]
    )


@router.get("/classes/{class_id}/students", response_model=StudentListResponse)
async def get_students_by_class(
    class_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Get all students in a specific class."""
    from sqlalchemy import select, func
    from app.models.student import Student
    from app.models.user import User as UserModel
    from app.models.class_model import Class
    from sqlalchemy.orm import selectinload

    # Verify class exists
    class_result = await db.execute(select(Class).where(Class.id == class_id))
    class_obj = class_result.scalar_one_or_none()

    if not class_obj:
        raise HTTPException(status_code=404, detail="Class not found")

    # Count total students in class
    count_query = select(func.count()).select_from(Student).where(Student.class_id == class_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Get students
    offset = (page - 1) * limit
    query = (
        select(Student)
        .options(
            selectinload(Student.user),
            selectinload(Student.class_info)
        )
        .where(Student.class_id == class_id)
        .offset(offset)
        .limit(limit)
        .order_by(UserModel.full_name)
    )

    result = await db.execute(query)
    students = result.scalars().all()

    # Format response
    student_responses = []
    for student in students:
        student_responses.append({
            "id": str(student.id),
            "user_id": str(student.user_id),
            "student_code": student.student_code,
            "email": student.user.email,
            "full_name": student.user.full_name,
            "username": student.user.username,
            "class_id": str(student.class_id) if student.class_id else None,
            "year_group": student.year_group,
            "enrollment_date": student.enrollment_date.isoformat() if student.enrollment_date else None,
            "status": student.status.value,
            "is_active": student.user.is_active,
            "created_at": student.created_at.isoformat() if student.created_at else None,
            "updated_at": student.updated_at.isoformat() if student.updated_at else None,
            "class_info": {
                "id": str(student.class_info.id),
                "name": student.class_info.name,
                "year_group": student.class_info.year_group,
                "academic_year": student.class_info.academic_year
            } if student.class_info else None
        })

    pages = (total + limit - 1) // limit

    return StudentListResponse(
        students=student_responses,
        total=total,
        page=page,
        pages=pages,
        limit=limit
    )


@router.get("/results/export")
async def export_results(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Export all test results with student details to Excel file."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from datetime import datetime
    from sqlalchemy import select
    from app.models.test import TestResult, Test
    from app.models.student import Student

    # Fetch all results with student and test details
    from sqlalchemy.orm import selectinload
    from app.models.user import User
    from app.models.class_model import Class

    query = (
        select(TestResult)
        .options(
            selectinload(TestResult.student).selectinload(Student.user),
            selectinload(TestResult.student).selectinload(Student.class_info),
            selectinload(TestResult.test)
        )
        .order_by(TestResult.submitted_at.desc())
    )

    result = await db.execute(query)
    results = result.scalars().all()

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Test Results"

    # Header style
    header_fill = PatternFill(start_color="1C2536", end_color="1C2536", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=12)
    header_alignment = Alignment(horizontal="center", vertical="center")

    # Headers
    headers = [
        "Student ID", "Student Name", "Student Email", "Class",
        "Test Title", "Test Type", "Score", "Total Marks",
        "Percentage", "Pass/Fail", "Time Taken (minutes)",
        "Submitted At", "Status"
    ]

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment

    # Data rows
    for row_num, test_result in enumerate(results, 2):
        student = test_result.student
        test = test_result.test

        if not student or not test:
            continue

        # Calculate pass/fail
        pass_fail = "Pass" if test_result.percentage >= test.pass_mark else "Fail"

        # Format time taken
        time_taken = ""
        if test_result.time_taken:
            time_taken = f"{test_result.time_taken // 60}"

        # Format submitted at
        submitted_at = ""
        if test_result.submitted_at:
            submitted_at = test_result.submitted_at.strftime("%Y-%m-%d %H:%M:%S")

        # Get student name, email, and class
        student_name = student.user.full_name if student.user else "N/A"
        student_email = student.user.email if student.user else "N/A"
        class_name = student.class_info.name if student.class_info else "N/A"

        row_data = [
            str(student.id),
            student_name,
            student_email,
            class_name,
            test.title,
            test.type.value if hasattr(test.type, 'value') else str(test.type),
            test_result.total_score if test_result.total_score else 0,
            test_result.max_score if test_result.max_score else 0,
            f"{test_result.percentage:.2f}" if test_result.percentage else "0.00",
            pass_fail,
            time_taken,
            submitted_at,
            test_result.status.value if hasattr(test_result.status, 'value') else str(test_result.status)
        ]

        for col_num, value in enumerate(row_data, 1):
            ws.cell(row=row_num, column=col_num, value=value)

    # Adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width

    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    # Generate filename with current date
    filename = f"test-results-{datetime.now().strftime('%Y-%m-%d')}.xlsx"

    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )