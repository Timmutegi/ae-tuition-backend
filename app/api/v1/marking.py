"""
Marking API Endpoints for Teacher Assessment System

Provides endpoints for:
- Managing the marking queue
- Uploading creative writing submissions
- Saving annotations on student work
- Submitting marks and feedback
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from datetime import datetime
import httpx

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user, get_current_teacher
from app.models.user import User
from app.models.marking import MarkingStatus, AnnotationType
from app.services.marking_service import MarkingService
from app.services.s3_service import S3Service


router = APIRouter()


# ==================== Request/Response Schemas ====================

class SubmissionResponse(BaseModel):
    """Response for a creative writing submission."""
    id: str
    attempt_id: str
    question_id: str
    student_id: str
    image_url: str
    thumbnail_url: Optional[str]
    original_filename: str
    submitted_at: str
    resubmission_count: int

    class Config:
        from_attributes = True


class AnnotationCreate(BaseModel):
    """Request to create an annotation."""
    annotation_type: str = Field(..., description="Type of annotation")
    fabric_data: dict = Field(..., description="Fabric.js object data")
    comment_text: Optional[str] = None
    x_position: Optional[float] = None
    y_position: Optional[float] = None
    color: str = "#FF0000"
    stroke_width: int = 2


class AnnotationBatchSave(BaseModel):
    """Request to save all annotations for a submission."""
    annotations: List[dict] = Field(..., description="List of annotation objects")


class AnnotationResponse(BaseModel):
    """Response for an annotation."""
    id: str
    annotation_type: str
    fabric_data: dict
    comment_text: Optional[str]
    color: str
    teacher_name: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class MarkSubmitRequest(BaseModel):
    """Request to submit a mark."""
    points_awarded: float = Field(..., ge=0, description="Points to award")
    feedback: Optional[str] = None
    strengths: Optional[str] = None
    improvements: Optional[str] = None
    rubric_scores: Optional[dict] = None
    time_spent_seconds: Optional[int] = None


class MarkResponse(BaseModel):
    """Response for a submitted mark."""
    id: str
    status: str
    points_awarded: Optional[float]
    max_points: float
    percentage: Optional[float]
    feedback: Optional[str]
    marked_by: Optional[str]
    marked_at: Optional[str]

    class Config:
        from_attributes = True


class QueueItemResponse(BaseModel):
    """Response for a marking queue item."""
    id: str
    manual_mark_id: Optional[str] = None  # None for standalone creative work
    creative_work_id: Optional[str] = None  # Set for standalone creative work
    test_id: Optional[str] = None
    test_title: str
    student_id: Optional[str] = None
    student_name: str
    student_email: str
    question_id: Optional[str] = None
    question_text: str
    question_type: str
    max_points: float
    status: str
    submission_url: Optional[str] = None
    submission_thumbnail: Optional[str] = None
    priority: int
    due_date: Optional[str] = None
    is_locked: bool
    locked_by: Optional[str] = None
    created_at: Optional[str] = None


class QueueStatsResponse(BaseModel):
    """Response for queue statistics."""
    total_pending: int
    assigned_to_me: int
    overdue: int


class CommentCreate(BaseModel):
    """Request to create a comment."""
    student_id: str
    comment_text: str
    comment_type: str = "feedback"
    attempt_id: Optional[str] = None
    result_id: Optional[str] = None
    question_id: Optional[str] = None
    visible_to_student: bool = True
    visible_to_parents: bool = False


class CommentResponse(BaseModel):
    """Response for a comment."""
    id: str
    comment_text: str
    comment_type: str
    teacher_name: str
    created_at: str
    visible_to_student: bool

    class Config:
        from_attributes = True


# ==================== Student Endpoints (Upload) ====================

@router.post("/submissions/upload", response_model=SubmissionResponse)
async def upload_creative_writing(
    attempt_id: str = Form(...),
    question_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a creative writing submission (image).

    Students upload images of their handwritten work.
    """
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}"
        )

    # Validate file size (max 10MB)
    contents = await file.read()
    file_size = len(contents)
    if file_size > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 10MB"
        )

    # Get student ID from current user
    from app.models.student import Student
    from sqlalchemy import select

    result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = result.scalar_one_or_none()

    if not student:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can upload creative writing"
        )

    # Upload to S3
    s3_service = S3Service()
    s3_key = f"creative-writing/{attempt_id}/{question_id}/{file.filename}"

    try:
        # Reset file pointer
        await file.seek(0)
        upload_result = await s3_service.upload_file(
            file=file,
            s3_key=s3_key,
            content_type=file.content_type
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}"
        )

    # Get image dimensions (optional - would need PIL)
    image_width = 0
    image_height = 0

    # Create submission
    marking_service = MarkingService(db)
    submission = await marking_service.create_submission(
        attempt_id=UUID(attempt_id),
        question_id=UUID(question_id),
        student_id=student.id,
        image_url=upload_result.get("url", ""),
        s3_key=s3_key,
        original_filename=file.filename,
        file_size_bytes=file_size,
        image_width=image_width,
        image_height=image_height,
        mime_type=file.content_type
    )

    return SubmissionResponse(
        id=str(submission.id),
        attempt_id=str(submission.attempt_id),
        question_id=str(submission.question_id),
        student_id=str(submission.student_id),
        image_url=submission.image_url,
        thumbnail_url=submission.thumbnail_url,
        original_filename=submission.original_filename,
        submitted_at=submission.submitted_at.isoformat(),
        resubmission_count=submission.resubmission_count
    )


@router.get("/submissions/{submission_id}", response_model=SubmissionResponse)
async def get_submission(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a creative writing submission."""
    service = MarkingService(db)
    submission = await service.get_submission(submission_id)

    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found"
        )

    return SubmissionResponse(
        id=str(submission.id),
        attempt_id=str(submission.attempt_id),
        question_id=str(submission.question_id),
        student_id=str(submission.student_id),
        image_url=submission.image_url,
        thumbnail_url=submission.thumbnail_url,
        original_filename=submission.original_filename,
        submitted_at=submission.submitted_at.isoformat(),
        resubmission_count=submission.resubmission_count
    )


# ==================== Teacher Endpoints (Marking) ====================

@router.get("/queue", response_model=List[QueueItemResponse])
async def get_marking_queue(
    test_id: Optional[UUID] = None,
    class_id: Optional[UUID] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Get the marking queue.

    Teachers see items assigned to them or unassigned.
    """
    marking_status = None
    if status:
        try:
            marking_status = MarkingStatus(status)
        except ValueError:
            pass

    service = MarkingService(db)
    items = await service.get_marking_queue(
        teacher_id=current_user.id,
        test_id=test_id,
        class_id=class_id,
        status=marking_status,
        limit=limit,
        offset=offset
    )

    return items


@router.get("/queue/stats", response_model=QueueStatsResponse)
async def get_queue_stats(
    test_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Get marking queue statistics."""
    service = MarkingService(db)
    stats = await service.get_queue_stats(
        teacher_id=current_user.id,
        test_id=test_id
    )
    return stats


@router.post("/queue/{queue_id}/lock")
async def lock_queue_item(
    queue_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Lock a queue item for marking."""
    service = MarkingService(db)
    success = await service.lock_queue_item(queue_id, current_user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Item is already locked by another teacher"
        )

    return {"status": "locked"}


@router.post("/queue/{queue_id}/unlock")
async def unlock_queue_item(
    queue_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Unlock a queue item."""
    service = MarkingService(db)
    await service.unlock_queue_item(queue_id)
    return {"status": "unlocked"}


# ==================== Annotation Endpoints ====================

@router.get("/submissions/{submission_id}/annotations", response_model=List[AnnotationResponse])
async def get_annotations(
    submission_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all annotations for a submission."""
    service = MarkingService(db)
    annotations = await service.get_annotations_for_submission(submission_id)

    return [
        AnnotationResponse(
            id=str(ann.id),
            annotation_type=ann.annotation_type.value,
            fabric_data=ann.fabric_data,
            comment_text=ann.comment_text,
            color=ann.color,
            teacher_name=ann.teacher.full_name if ann.teacher else None,
            created_at=ann.created_at.isoformat()
        )
        for ann in annotations
    ]


@router.post("/submissions/{submission_id}/annotations", response_model=AnnotationResponse)
async def add_annotation(
    submission_id: UUID,
    request: AnnotationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Add an annotation to a submission."""
    try:
        annotation_type = AnnotationType(request.annotation_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid annotation type: {request.annotation_type}"
        )

    service = MarkingService(db)
    annotation = await service.add_annotation(
        submission_id=submission_id,
        teacher_id=current_user.id,
        annotation_type=annotation_type,
        fabric_data=request.fabric_data,
        comment_text=request.comment_text,
        x_position=request.x_position,
        y_position=request.y_position,
        color=request.color,
        stroke_width=request.stroke_width
    )

    return AnnotationResponse(
        id=str(annotation.id),
        annotation_type=annotation.annotation_type.value,
        fabric_data=annotation.fabric_data,
        comment_text=annotation.comment_text,
        color=annotation.color,
        teacher_name=current_user.full_name,
        created_at=annotation.created_at.isoformat()
    )


@router.post("/submissions/{submission_id}/annotations/batch")
async def save_annotations_batch(
    submission_id: UUID,
    request: AnnotationBatchSave,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Save all annotations for a submission at once.

    Replaces existing annotations from this teacher.
    """
    service = MarkingService(db)
    annotations = await service.save_annotations_batch(
        submission_id=submission_id,
        teacher_id=current_user.id,
        annotations=request.annotations
    )

    return {"saved_count": len(annotations)}


@router.delete("/annotations/{annotation_id}")
async def delete_annotation(
    annotation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Delete an annotation."""
    service = MarkingService(db)
    success = await service.delete_annotation(annotation_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Annotation not found"
        )

    return {"status": "deleted"}


# ==================== Mark Submission Endpoints ====================

@router.post("/marks/{manual_mark_id}/submit", response_model=MarkResponse)
async def submit_mark(
    manual_mark_id: UUID,
    request: MarkSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """
    Submit a mark for a creative writing or open-ended question.
    """
    service = MarkingService(db)

    try:
        mark = await service.submit_mark(
            manual_mark_id=manual_mark_id,
            teacher_id=current_user.id,
            points_awarded=request.points_awarded,
            feedback=request.feedback,
            strengths=request.strengths,
            improvements=request.improvements,
            rubric_scores=request.rubric_scores,
            time_spent_seconds=request.time_spent_seconds
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    return MarkResponse(
        id=str(mark.id),
        status=mark.status.value,
        points_awarded=mark.points_awarded,
        max_points=mark.max_points,
        percentage=mark.percentage,
        feedback=mark.feedback,
        marked_by=str(mark.marked_by) if mark.marked_by else None,
        marked_at=mark.marked_at.isoformat() if mark.marked_at else None
    )


# ==================== Comment Endpoints ====================

@router.post("/comments", response_model=CommentResponse)
async def add_comment(
    request: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Add a comment on student performance."""
    service = MarkingService(db)
    comment = await service.add_comment(
        teacher_id=current_user.id,
        student_id=UUID(request.student_id),
        comment_text=request.comment_text,
        comment_type=request.comment_type,
        attempt_id=UUID(request.attempt_id) if request.attempt_id else None,
        result_id=UUID(request.result_id) if request.result_id else None,
        question_id=UUID(request.question_id) if request.question_id else None,
        visible_to_student=request.visible_to_student,
        visible_to_parents=request.visible_to_parents
    )

    return CommentResponse(
        id=str(comment.id),
        comment_text=comment.comment_text,
        comment_type=comment.comment_type,
        teacher_name=current_user.full_name or current_user.username,
        created_at=comment.created_at.isoformat(),
        visible_to_student=comment.visible_to_student
    )


@router.get("/comments/attempt/{attempt_id}", response_model=List[CommentResponse])
async def get_comments_for_attempt(
    attempt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all comments for a test attempt."""
    service = MarkingService(db)
    comments = await service.get_comments_for_attempt(attempt_id)

    return [
        CommentResponse(
            id=str(c.id),
            comment_text=c.comment_text,
            comment_type=c.comment_type,
            teacher_name=c.teacher.full_name if c.teacher else "Teacher",
            created_at=c.created_at.isoformat(),
            visible_to_student=c.visible_to_student
        )
        for c in comments
    ]


@router.get("/comments/student/{student_id}", response_model=List[CommentResponse])
async def get_comments_for_student(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all comments for a student."""
    # Check if current user is the student or a teacher
    from app.models.student import Student
    from sqlalchemy import select

    result = await db.execute(
        select(Student).where(Student.user_id == current_user.id)
    )
    student = result.scalar_one_or_none()

    # If student, only show visible comments for their own account
    visible_only = student is not None and str(student.id) == str(student_id)

    service = MarkingService(db)
    comments = await service.get_comments_for_student(
        student_id,
        visible_to_student_only=visible_only
    )

    return [
        CommentResponse(
            id=str(c.id),
            comment_text=c.comment_text,
            comment_type=c.comment_type,
            teacher_name=c.teacher.full_name if c.teacher else "Teacher",
            created_at=c.created_at.isoformat(),
            visible_to_student=c.visible_to_student
        )
        for c in comments
    ]


# ==================== Standalone Creative Work Endpoints ====================

class CreativeWorkDetailResponse(BaseModel):
    """Response for standalone creative work."""
    id: str
    student_id: str
    student_name: str
    student_email: str
    title: str
    description: Optional[str] = None
    image_url: str
    annotated_image_url: Optional[str] = None
    status: str
    feedback: Optional[str] = None
    submitted_at: str
    reviewed_at: Optional[str] = None


class CreativeWorkReviewRequest(BaseModel):
    """Request to review creative work."""
    feedback: str = Field(..., min_length=1)
    status: str = Field(default="reviewed")  # "reviewed" or "rejected"
    annotated_image: Optional[str] = None  # Base64 encoded annotated image


@router.get("/creative-work/{work_id}", response_model=CreativeWorkDetailResponse)
async def get_creative_work(
    work_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Get a standalone creative work submission."""
    from app.models.marking import StudentCreativeWork
    from app.models.student import Student
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(StudentCreativeWork)
        .options(
            selectinload(StudentCreativeWork.student).selectinload(Student.user)
        )
        .where(StudentCreativeWork.id == work_id)
    )
    work = result.scalar_one_or_none()

    if not work:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creative work not found"
        )

    student_name = "Unknown"
    student_email = ""
    if work.student and work.student.user:
        student_name = work.student.user.full_name or work.student.user.username
        student_email = work.student.user.email

    return CreativeWorkDetailResponse(
        id=str(work.id),
        student_id=str(work.student_id),
        student_name=student_name,
        student_email=student_email,
        title=work.title,
        description=work.description,
        image_url=work.image_url,
        annotated_image_url=work.annotated_image_url,
        status=work.status.value if work.status else "pending",
        feedback=work.feedback,
        submitted_at=work.submitted_at.isoformat() if work.submitted_at else "",
        reviewed_at=work.reviewed_at.isoformat() if work.reviewed_at else None
    )


@router.post("/creative-work/{work_id}/review", response_model=CreativeWorkDetailResponse)
async def review_creative_work(
    work_id: UUID,
    request: CreativeWorkReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Submit a review for standalone creative work."""
    from app.models.marking import StudentCreativeWork, StudentCreativeWorkStatus
    from app.models.student import Student
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from datetime import datetime, timezone
    import base64
    import io

    result = await db.execute(
        select(StudentCreativeWork)
        .options(
            selectinload(StudentCreativeWork.student).selectinload(Student.user)
        )
        .where(StudentCreativeWork.id == work_id)
    )
    work = result.scalar_one_or_none()

    if not work:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Creative work not found"
        )

    # Handle annotated image upload if provided
    if request.annotated_image:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Received annotated image for work {work_id}, size: {len(request.annotated_image)}")

        try:
            # Remove data URL prefix if present (e.g., "data:image/png;base64,")
            image_data = request.annotated_image
            if ',' in image_data:
                image_data = image_data.split(',')[1]
                logger.info(f"Stripped data URL prefix, base64 size: {len(image_data)}")

            # Decode base64 image
            image_bytes = base64.b64decode(image_data)
            logger.info(f"Decoded image bytes, size: {len(image_bytes)}")

            # Generate S3 key for annotated image
            annotated_s3_key = f"creative-writing/annotated/{work_id}.png"

            # Upload to S3
            s3_service = S3Service()
            upload_result = await s3_service.upload_bytes(
                data=image_bytes,
                s3_key=annotated_s3_key,
                content_type="image/png"
            )

            if upload_result:
                # Update work with annotated image URL
                work.annotated_image_url = upload_result.get("url", "")
                work.annotated_s3_key = annotated_s3_key
                logger.info(f"Successfully uploaded annotated image: {work.annotated_image_url}")
            else:
                logger.error(f"S3 upload returned None for work {work_id}")

        except Exception as e:
            # Log error but don't fail the review
            import logging
            logging.error(f"Failed to upload annotated image: {str(e)}", exc_info=True)

    # Update the work with feedback
    work.feedback = request.feedback
    work.reviewed_by = current_user.id
    work.reviewed_at = datetime.now(timezone.utc)

    if request.status == "rejected":
        work.status = StudentCreativeWorkStatus.REJECTED
    else:
        work.status = StudentCreativeWorkStatus.REVIEWED

    await db.commit()
    await db.refresh(work)

    student_name = "Unknown"
    student_email = ""
    if work.student and work.student.user:
        student_name = work.student.user.full_name or work.student.user.username
        student_email = work.student.user.email

    return CreativeWorkDetailResponse(
        id=str(work.id),
        student_id=str(work.student_id),
        student_name=student_name,
        student_email=student_email,
        title=work.title,
        description=work.description,
        image_url=work.image_url,
        annotated_image_url=work.annotated_image_url,
        status=work.status.value if work.status else "pending",
        feedback=work.feedback,
        submitted_at=work.submitted_at.isoformat() if work.submitted_at else "",
        reviewed_at=work.reviewed_at.isoformat() if work.reviewed_at else None
    )


# ==================== Image Proxy Endpoint ====================

@router.get("/image-proxy/{path:path}")
async def proxy_image(
    path: str,
    current_user: User = Depends(get_current_user)
):
    """
    Proxy images from CloudFront/S3 to avoid CORS issues when loading into canvas.

    The path should be the S3 key (e.g., creative-writing/uuid.png)
    """
    cloudfront_url = settings.CLOUDFRONT_URL
    if not cloudfront_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CloudFront URL not configured"
        )

    # Build the full URL
    base_url = cloudfront_url.rstrip('/')
    image_url = f"{base_url}/{path}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(image_url, timeout=30.0)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "image/png")

            return Response(
                content=response.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=3600"
                }
            )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail="Failed to fetch image"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to connect to image server: {str(e)}"
        )
