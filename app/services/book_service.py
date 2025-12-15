"""
Service for managing books in the attendance tracking system.
"""

import logging
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.book import Book
from app.schemas.book import BookCreate, BookUpdate

logger = logging.getLogger(__name__)


class BookService:
    """Service for managing educational books."""

    @staticmethod
    async def create_book(
        db: AsyncSession,
        book_data: BookCreate
    ) -> Book:
        """Create a new book."""
        book = Book(
            name=book_data.name,
            subject=book_data.subject,
            is_active=True
        )
        db.add(book)
        await db.commit()
        await db.refresh(book)
        logger.info(f"Created book: {book.name} ({book.subject})")
        return book

    @staticmethod
    async def get_book_by_id(
        db: AsyncSession,
        book_id: UUID
    ) -> Optional[Book]:
        """Get a book by its ID."""
        result = await db.execute(
            select(Book).where(Book.id == book_id)
        )
        return result.scalars().first()

    @staticmethod
    async def get_all_books(
        db: AsyncSession,
        subject: Optional[str] = None,
        is_active: Optional[bool] = True,
        skip: int = 0,
        limit: int = 100
    ) -> List[Book]:
        """Get all books with optional filtering by subject and active status."""
        query = select(Book)

        if is_active is not None:
            query = query.where(Book.is_active == is_active)

        if subject:
            query = query.where(Book.subject == subject)

        query = query.order_by(Book.subject, Book.name)
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_books_count(
        db: AsyncSession,
        subject: Optional[str] = None,
        is_active: Optional[bool] = True
    ) -> int:
        """Get total count of books with optional filtering."""
        query = select(func.count(Book.id))

        if is_active is not None:
            query = query.where(Book.is_active == is_active)

        if subject:
            query = query.where(Book.subject == subject)

        result = await db.execute(query)
        return result.scalar() or 0

    @staticmethod
    async def get_books_by_subject(
        db: AsyncSession,
        is_active: bool = True
    ) -> dict:
        """Get books grouped by subject."""
        books = await BookService.get_all_books(db, is_active=is_active, limit=1000)

        grouped = {}
        for book in books:
            if book.subject not in grouped:
                grouped[book.subject] = []
            grouped[book.subject].append(book)

        return grouped

    @staticmethod
    async def update_book(
        db: AsyncSession,
        book_id: UUID,
        book_data: BookUpdate
    ) -> Optional[Book]:
        """Update a book."""
        result = await db.execute(
            select(Book).where(Book.id == book_id)
        )
        book = result.scalars().first()

        if not book:
            return None

        # Update only provided fields
        update_data = book_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(book, field, value)

        await db.commit()
        await db.refresh(book)
        logger.info(f"Updated book: {book.name}")
        return book

    @staticmethod
    async def delete_book(
        db: AsyncSession,
        book_id: UUID,
        soft_delete: bool = True
    ) -> bool:
        """Delete a book (soft delete by default)."""
        result = await db.execute(
            select(Book).where(Book.id == book_id)
        )
        book = result.scalars().first()

        if not book:
            return False

        if soft_delete:
            book.is_active = False
            await db.commit()
            logger.info(f"Soft deleted book: {book.name}")
        else:
            await db.delete(book)
            await db.commit()
            logger.info(f"Hard deleted book: {book.name}")

        return True

    @staticmethod
    async def restore_book(
        db: AsyncSession,
        book_id: UUID
    ) -> Optional[Book]:
        """Restore a soft-deleted book."""
        result = await db.execute(
            select(Book).where(Book.id == book_id)
        )
        book = result.scalars().first()

        if not book:
            return None

        book.is_active = True
        await db.commit()
        await db.refresh(book)
        logger.info(f"Restored book: {book.name}")
        return book
