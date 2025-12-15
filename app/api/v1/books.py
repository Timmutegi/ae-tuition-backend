"""
API endpoints for managing books.

Books are used in the attendance tracking system for recording
book-related comments (Help in, Incomplete, Unmarked, At home).
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_admin_user, get_current_user
from app.models.user import User
from app.services.book_service import BookService
from app.schemas.book import (
    BookCreate,
    BookUpdate,
    BookResponse,
    BookListResponse,
    BooksBySubject
)

router = APIRouter()


# ========== Admin Endpoints ==========

@router.post("/admin/books", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
async def create_book(
    book_data: BookCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Create a new book. Admin only."""
    book = await BookService.create_book(db, book_data)
    return book


@router.get("/admin/books", response_model=BookListResponse)
async def get_all_books(
    subject: Optional[str] = Query(None, description="Filter by subject (English, VR, NVR, Maths)"),
    is_active: Optional[bool] = Query(True, description="Filter by active status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Get all books with optional filtering. Admin only."""
    books = await BookService.get_all_books(db, subject=subject, is_active=is_active, skip=skip, limit=limit)
    total = await BookService.get_books_count(db, subject=subject, is_active=is_active)
    return BookListResponse(books=books, total=total)


@router.get("/admin/books/{book_id}", response_model=BookResponse)
async def get_book(
    book_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Get a specific book by ID. Admin only."""
    book = await BookService.get_book_by_id(db, book_id)
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    return book


@router.put("/admin/books/{book_id}", response_model=BookResponse)
async def update_book(
    book_id: UUID,
    book_data: BookUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Update a book. Admin only."""
    book = await BookService.update_book(db, book_id, book_data)
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    return book


@router.delete("/admin/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(
    book_id: UUID,
    hard_delete: bool = Query(False, description="Set to true for permanent deletion"),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Delete a book (soft delete by default). Admin only."""
    success = await BookService.delete_book(db, book_id, soft_delete=not hard_delete)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    return None


@router.post("/admin/books/{book_id}/restore", response_model=BookResponse)
async def restore_book(
    book_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """Restore a soft-deleted book. Admin only."""
    book = await BookService.restore_book(db, book_id)
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    return book


# ========== Public Endpoints (for dropdowns) ==========

@router.get("/books", response_model=List[BookResponse])
async def get_active_books(
    subject: Optional[str] = Query(None, description="Filter by subject"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all active books for dropdown selection.
    Available to authenticated users (teachers, supervisors, admins).
    """
    books = await BookService.get_all_books(db, subject=subject, is_active=True, limit=1000)
    return books


@router.get("/books/by-subject", response_model=List[BooksBySubject])
async def get_books_grouped_by_subject(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get active books grouped by subject for easier dropdown organization.
    Available to authenticated users.
    """
    grouped = await BookService.get_books_by_subject(db, is_active=True)
    return [
        BooksBySubject(subject=subject, books=books)
        for subject, books in sorted(grouped.items())
    ]
