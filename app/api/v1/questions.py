from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_admin_user
from app.models import User
from app.models.question import Question, AnswerOption
from app.schemas.question import (
    QuestionCreate, QuestionUpdate, QuestionResponse, QuestionWithPassage, QuestionFilters,
    ReadingPassageCreate, ReadingPassageUpdate, ReadingPassageResponse, PassageFilters,
    AnswerOptionCreate, AnswerOptionResponse, QuestionBankStats
)
from app.services.question_service import QuestionService
from app.services.s3_service import s3_service

router = APIRouter(prefix="/questions", tags=["Question Management"])


# Question endpoints
@router.post("/", response_model=QuestionResponse)
async def create_question(
    question_data: QuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Create a new question with answer options"""
    # Use the service method which returns a Pydantic schema
    question_response = await QuestionService.create_question(db, question_data, current_user.id)
    return question_response


@router.get("/", response_model=dict)
async def get_questions(
    question_type: Optional[str] = Query(None),
    question_format: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    passage_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None),
    tags: Optional[List[str]] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get questions with filtering and pagination"""
    from app.models.question import QuestionType, QuestionFormat, Difficulty

    filters = QuestionFilters(
        question_type=QuestionType(question_type) if question_type else None,
        question_format=QuestionFormat(question_format) if question_format else None,
        subject=subject,
        difficulty=Difficulty(difficulty) if difficulty else None,
        passage_id=passage_id,
        search=search,
        tags=tags,
        page=page,
        limit=limit
    )

    result = await QuestionService.get_questions(db, filters)
    return result


# Reading passage endpoints (MUST come before /{question_id} routes)
@router.post("/passages", response_model=ReadingPassageResponse)
async def create_reading_passage(
    passage_data: ReadingPassageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Create a new reading passage"""
    try:
        passage = await QuestionService.create_reading_passage(db, passage_data, current_user.id)
        return passage
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/passages", response_model=dict)
async def get_reading_passages(
    subject: Optional[str] = Query(None),
    genre: Optional[str] = Query(None),
    reading_level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get reading passages with filtering and pagination"""
    filters = PassageFilters(
        subject=subject,
        genre=genre,
        reading_level=reading_level,
        search=search,
        page=page,
        limit=limit
    )

    result = await QuestionService.get_reading_passages(db, filters)
    return result


@router.get("/passages/{passage_id}", response_model=ReadingPassageResponse)
async def get_reading_passage(
    passage_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get reading passage by ID"""
    passage = await QuestionService.get_reading_passage_by_id(db, passage_id)
    if not passage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reading passage not found"
        )
    return passage


@router.put("/passages/{passage_id}", response_model=ReadingPassageResponse)
async def update_reading_passage(
    passage_id: UUID,
    passage_data: ReadingPassageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Update reading passage"""
    passage = await QuestionService.update_reading_passage(db, passage_id, passage_data, current_user.id)
    if not passage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reading passage not found or access denied"
        )
    return passage


@router.delete("/passages/{passage_id}")
async def delete_reading_passage(
    passage_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Delete reading passage"""
    try:
        success = await QuestionService.delete_reading_passage(db, passage_id, current_user.id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reading passage not found or access denied"
            )
        return {"message": "Reading passage deleted successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/passages/{passage_id}/questions", response_model=List[QuestionResponse])
async def get_questions_by_passage(
    passage_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get all questions for a specific passage"""
    questions = await QuestionService.get_questions_by_passage(db, passage_id)
    return questions


@router.get("/stats/overview", response_model=QuestionBankStats)
async def get_question_bank_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get question bank statistics"""
    stats = await QuestionService.get_question_bank_stats(db, current_user.id)
    return stats


# Question CRUD endpoints (come after specific routes like /passages, /stats)
@router.get("/{question_id}", response_model=QuestionWithPassage)
async def get_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get question by ID with all details"""
    question = await QuestionService.get_question_by_id(db, question_id)
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found"
        )
    return question


@router.put("/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: UUID,
    question_data: QuestionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Update question"""
    question = await QuestionService.update_question(db, question_id, question_data, current_user.id)
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found or access denied"
        )
    return question


@router.delete("/{question_id}")
async def delete_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Delete question"""
    try:
        success = await QuestionService.delete_question(db, question_id, current_user.id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question not found or access denied"
            )
        return {"message": "Question deleted successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{question_id}/options", response_model=AnswerOptionResponse)
async def add_answer_option(
    question_id: UUID,
    option_data: AnswerOptionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Add answer option to a question"""
    option = await QuestionService.add_answer_option(db, question_id, option_data, current_user.id)
    if not option:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found or access denied"
        )
    return option


@router.delete("/options/{option_id}")
async def remove_answer_option(
    option_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Remove answer option"""
    success = await QuestionService.remove_answer_option(db, option_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Answer option not found or access denied"
        )
    return {"message": "Answer option removed successfully"}


@router.post("/upload-image")
async def upload_question_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user)
):
    """Upload image for questions"""
    # Validate file
    is_valid, error_message = s3_service.validate_file(file.filename, file.size)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message
        )

    # Upload to S3
    upload_result = await s3_service.upload_file(
        file.file,
        file.filename,
        "questions"
    )

    if not upload_result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload image"
        )

    return {
        "message": "Image uploaded successfully",
        "s3_key": upload_result["s3_key"],
        "public_url": upload_result["public_url"],
        "file_name": upload_result["file_name"]
    }