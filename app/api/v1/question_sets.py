from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_admin_user
from app.models import User
from app.schemas.question_set import (
    QuestionSetCreate, QuestionSetUpdate, QuestionSetResponse, QuestionSetWithItems,
    QuestionSetListResponse, QuestionSetFilters, TestQuestionSetCreate,
    BulkQuestionSetAssignment, AddQuestionsToSetRequest, RemoveQuestionsFromSetRequest,
    ReorderQuestionsInSetRequest
)
from app.services.question_set_service import QuestionSetService

router = APIRouter(prefix="/question-sets", tags=["Question Sets"])


@router.post("", response_model=QuestionSetWithItems)
async def create_question_set(
    question_set_data: QuestionSetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Create a new question set"""
    try:
        question_set = await QuestionSetService.create_question_set(
            db, question_set_data, current_user.id
        )
        return question_set
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create question set: {str(e)}"
        )


@router.get("", response_model=QuestionSetListResponse)
async def get_question_sets(
    subject: Optional[str] = Query(None),
    grade_level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(True),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get question sets with filtering and pagination"""
    filters = QuestionSetFilters(
        subject=subject,
        grade_level=grade_level,
        search=search,
        is_active=is_active,
        page=page,
        limit=limit
    )

    try:
        result = await QuestionSetService.get_question_sets(db, filters)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch question sets: {str(e)}"
        )


@router.get("/{question_set_id}", response_model=QuestionSetWithItems)
async def get_question_set(
    question_set_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get a single question set with all its questions"""
    try:
        question_set = await QuestionSetService.get_question_set(db, question_set_id)
        return question_set
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch question set: {str(e)}"
        )


@router.put("/{question_set_id}", response_model=QuestionSetResponse)
async def update_question_set(
    question_set_id: UUID,
    update_data: QuestionSetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Update a question set"""
    try:
        question_set = await QuestionSetService.update_question_set(
            db, question_set_id, update_data
        )
        return question_set
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update question set: {str(e)}"
        )


@router.delete("/{question_set_id}")
async def delete_question_set(
    question_set_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Delete a question set"""
    try:
        await QuestionSetService.delete_question_set(db, question_set_id)
        return {"message": "Question set deleted successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete question set: {str(e)}"
        )


@router.post("/{question_set_id}/questions", response_model=QuestionSetWithItems)
async def add_questions_to_set(
    question_set_id: UUID,
    request: AddQuestionsToSetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Add questions to an existing question set"""
    try:
        question_set = await QuestionSetService.add_questions_to_set(
            db, question_set_id, request
        )
        return question_set
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add questions to set: {str(e)}"
        )


@router.delete("/{question_set_id}/questions", response_model=QuestionSetWithItems)
async def remove_questions_from_set(
    question_set_id: UUID,
    request: RemoveQuestionsFromSetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Remove questions from a question set"""
    try:
        question_set = await QuestionSetService.remove_questions_from_set(
            db, question_set_id, request
        )
        return question_set
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove questions from set: {str(e)}"
        )


@router.put("/{question_set_id}/questions/reorder", response_model=QuestionSetWithItems)
async def reorder_questions_in_set(
    question_set_id: UUID,
    request: ReorderQuestionsInSetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Reorder questions within a question set"""
    try:
        question_set = await QuestionSetService.reorder_questions_in_set(
            db, question_set_id, request
        )
        return question_set
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reorder questions in set: {str(e)}"
        )