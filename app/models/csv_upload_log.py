from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
import enum

from app.core.database import Base


class CSVUploadStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CSVUploadLog(Base):
    __tablename__ = "csv_upload_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=True)
    total_records = Column(Integer, default=0)
    successful_records = Column(Integer, default=0)
    failed_records = Column(Integer, default=0)
    error_details = Column(JSONB, nullable=True)
    upload_date = Column(DateTime(timezone=True), default=func.now())
    status = Column(SQLEnum(CSVUploadStatus), default=CSVUploadStatus.PENDING)

    def __repr__(self):
        return f"<CSVUploadLog(file_name='{self.file_name}', status='{self.status.value}')>"