"""
Pydantic schemas for Book model.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


# Book Base Schema
class BookBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Name of the book")
    subject: str = Field(..., description="Subject area: English, VR, NVR, Maths")


class BookCreate(BookBase):
    """Schema for creating a new book."""
    pass


class BookUpdate(BaseModel):
    """Schema for updating a book. All fields optional."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    subject: Optional[str] = None
    is_active: Optional[bool] = None


class BookResponse(BookBase):
    """Schema for book response."""
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BookListResponse(BaseModel):
    """Schema for list of books response."""
    books: List[BookResponse]
    total: int


class BooksBySubject(BaseModel):
    """Schema for books grouped by subject."""
    subject: str
    books: List[BookResponse]
