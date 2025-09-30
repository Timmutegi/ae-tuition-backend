from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_admin_user
from app.models import User
from app.schemas.test import (
    TestCreate, TestUpdate, TestResponse, TestWithDetails, TestFilters,
    TestQuestionCreate, TestAssignmentCreate, TestAssignmentUpdate, TestAssignmentResponse,
    BulkAssignmentRequest, TestCloneRequest, TestStatsResponse, TestListResponse
)
from app.schemas.question_set import BulkQuestionSetAssignment
from app.services.test_service import TestService

router = APIRouter(prefix="/tests", tags=["Test Management"])


@router.post("/", response_model=TestResponse)
async def create_test(
    test_data: TestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Create a new test"""
    try:
        test = await TestService.create_test(db, test_data, current_user.id)
        return test
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/", response_model=TestListResponse)
async def get_tests(
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get tests with filtering and pagination"""
    from app.models.test import TestType, TestStatus

    filters = TestFilters(
        type=TestType(type) if type else None,
        status=TestStatus(status) if status else None,
        search=search,
        page=page,
        limit=limit
    )

    result = await TestService.get_tests(db, filters)
    return result


@router.get("/{test_id}", response_model=TestWithDetails)
async def get_test(
    test_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get test by ID with full details"""
    test = await TestService.get_test_by_id(db, test_id)
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test not found"
        )
    return test


@router.put("/{test_id}", response_model=TestResponse)
async def update_test(
    test_id: UUID,
    test_data: TestUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Update test"""
    try:
        test = await TestService.update_test(db, test_id, test_data, current_user.id)
        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found or access denied"
            )
        return test
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{test_id}")
async def delete_test(
    test_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Delete test"""
    try:
        success = await TestService.delete_test(db, test_id, current_user.id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found or access denied"
            )
        return {"message": "Test deleted successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{test_id}/clone", response_model=TestResponse)
async def clone_test(
    test_id: UUID,
    clone_data: TestCloneRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Clone an existing test"""
    test = await TestService.clone_test(db, test_id, clone_data, current_user.id)
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test not found"
        )
    return test


@router.post("/{test_id}/questions")
async def assign_questions_to_test(
    test_id: UUID,
    questions: List[TestQuestionCreate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Assign questions to a test"""
    success = await TestService.assign_questions_to_test(db, test_id, questions, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test not found or access denied"
        )
    return {"message": "Questions assigned successfully"}


@router.post("/{test_id}/assign", response_model=List[TestAssignmentResponse])
async def assign_test_to_classes(
    test_id: UUID,
    assignment_data: BulkAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Assign test to multiple classes"""
    try:
        assignments = await TestService.assign_test_to_classes(db, test_id, assignment_data, current_user.id)
        return assignments
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{test_id}/assignments", response_model=List[TestAssignmentResponse])
async def get_test_assignments(
    test_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get all assignments for a test"""
    assignments = await TestService.get_test_assignments(db, test_id)
    return assignments


@router.put("/assignments/{assignment_id}", response_model=TestAssignmentResponse)
async def update_test_assignment(
    assignment_id: UUID,
    assignment_data: TestAssignmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Update a test assignment"""
    assignment = await TestService.update_test_assignment(db, assignment_id, assignment_data, current_user.id)
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found or access denied"
        )
    return assignment


@router.delete("/{test_id}/assignments/{class_id}")
async def remove_test_assignment(
    test_id: UUID,
    class_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Remove test assignment for a specific class"""
    try:
        success = await TestService.remove_test_assignment(db, test_id, class_id, current_user.id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found"
            )
        return {"message": "Assignment removed successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{test_id}/publish", response_model=TestResponse)
async def publish_test(
    test_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Publish a draft test"""
    try:
        test = await TestService.publish_test(db, test_id, current_user.id)
        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found or access denied"
            )
        return test
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{test_id}/unpublish", response_model=TestResponse)
async def unpublish_test(
    test_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Unpublish a test to allow editing"""
    try:
        test = await TestService.unpublish_test(db, test_id, current_user.id)
        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found or access denied"
            )
        return test
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{test_id}/archive", response_model=TestResponse)
async def archive_test(
    test_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Archive a test"""
    test = await TestService.archive_test(db, test_id, current_user.id)
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test not found or access denied"
        )
    return test


@router.post("/{test_id}/question-sets")
async def assign_question_sets_to_test(
    test_id: UUID,
    assignment_data: BulkQuestionSetAssignment,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Assign question sets to a test"""
    from app.services.question_set_service import QuestionSetService

    try:
        await QuestionSetService.assign_question_sets_to_test(db, test_id, assignment_data.question_set_ids)
        return {"message": "Question sets assigned successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign question sets: {str(e)}"
        )


@router.get("/stats/overview", response_model=TestStatsResponse)
async def get_test_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get test statistics"""
    stats = await TestService.get_test_stats(db, current_user.id)
    return stats