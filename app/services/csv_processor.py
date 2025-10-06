import io
import csv
import logging
from typing import List, Dict, Tuple, Optional
from fastapi import UploadFile, HTTPException
import pandas as pd

from app.core.database import AsyncSessionLocal
from app.models import User


logger = logging.getLogger(__name__)


class CSVProcessorService:
    REQUIRED_COLUMNS = ["Class ID", "Student ID", "Year Group", "First Name", "Surname", "Email Address"]
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    @classmethod
    async def validate_csv_structure(cls, file: UploadFile) -> dict:
        """Validate CSV file type and structure."""
        # Check file type
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be a CSV")

        # Check file size
        file_content = await file.read()
        if len(file_content) > cls.MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")

        await file.seek(0)  # Reset file pointer
        return {"valid": True, "size": len(file_content)}

    @classmethod
    async def parse_csv_file(cls, file: UploadFile) -> List[dict]:
        """Parse CSV file and return list of student data."""
        try:
            content = await file.read()
            decoded = content.decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(decoded))

            students = []
            for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (header is row 1)
                # Clean up column names (remove extra spaces)
                cleaned_row = {k.strip(): v.strip() if v else '' for k, v in row.items()}

                # Skip empty rows (rows where all values are empty)
                if all(not value for value in cleaned_row.values()):
                    continue

                cleaned_row['row_number'] = row_num
                students.append(cleaned_row)

            return students

        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="File encoding error. Please use UTF-8")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"CSV parsing error: {str(e)}")

    @classmethod
    async def validate_student_data(
        cls,
        data: List[dict],
        db_session
    ) -> Tuple[List[dict], List[dict]]:
        """Validate student data and return valid and invalid records."""
        from sqlalchemy import text

        valid_records = []
        errors = []

        # Check for required columns
        if data:
            first_row_keys = set(data[0].keys())
            first_row_keys.discard('row_number')  # Remove row_number from check
            missing_columns = set(cls.REQUIRED_COLUMNS) - first_row_keys
            if missing_columns:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required columns: {', '.join(missing_columns)}"
                )

        # Get existing student codes from database
        existing_student_codes = set()
        result = await db_session.execute(
            text("SELECT student_code FROM students WHERE student_code IS NOT NULL")
        )
        for row in result:
            existing_student_codes.add(row[0].upper())

        # Validate each record
        seen_student_codes = set()
        for record in data:
            row_num = record.get('row_number', 0)
            record_errors = []

            # Validate email format (but allow duplicates for siblings)
            email = record.get('Email Address', '').lower()
            if not email:
                record_errors.append({
                    'field': 'Email Address',
                    'error': 'Email is required'
                })
            elif '@' not in email or '.' not in email:
                record_errors.append({
                    'field': 'Email Address',
                    'error': 'Invalid email format'
                })

            # Validate Student ID (student_code) uniqueness
            student_code = record.get('Student ID', '').strip().upper()
            if not student_code:
                record_errors.append({
                    'field': 'Student ID',
                    'error': 'Student ID is required'
                })
            elif student_code in existing_student_codes:
                record_errors.append({
                    'field': 'Student ID',
                    'error': 'Student ID already exists in system'
                })
            elif student_code in seen_student_codes:
                record_errors.append({
                    'field': 'Student ID',
                    'error': 'Duplicate Student ID in CSV'
                })
            else:
                seen_student_codes.add(student_code)

            # Validate First Name and Surname
            if not record.get('First Name'):
                record_errors.append({
                    'field': 'First Name',
                    'error': 'First Name is required'
                })

            if not record.get('Surname'):
                record_errors.append({
                    'field': 'Surname',
                    'error': 'Surname is required'
                })

            # Validate Year Group
            try:
                year_group = int(record.get('Year Group', 0))
                if year_group < 1 or year_group > 13:
                    record_errors.append({
                        'field': 'Year Group',
                        'error': 'Year Group must be between 1 and 13'
                    })
            except (ValueError, TypeError):
                record_errors.append({
                    'field': 'Year Group',
                    'error': 'Year Group must be a number'
                })

            # Validate Class ID
            if not record.get('Class ID'):
                record_errors.append({
                    'field': 'Class ID',
                    'error': 'Class ID is required'
                })

            if record_errors:
                errors.append({
                    'row': row_num,
                    'data': record,
                    'errors': record_errors
                })
            else:
                valid_records.append(record)

        return valid_records, errors

    @classmethod
    async def check_duplicate_emails(cls, emails: List[str]) -> List[str]:
        """Check for duplicate emails in database."""
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("SELECT email FROM users WHERE LOWER(email) = ANY(:emails)"),
                {"emails": [email.lower() for email in emails]}
            )
            return [row[0] for row in result]

    @classmethod
    def generate_csv_template(cls) -> io.BytesIO:
        """Generate CSV template for student upload."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(cls.REQUIRED_COLUMNS)

        # Write sample data
        # Columns: ["Class ID", "Student ID", "Year Group", "First Name", "Surname", "Email Address"]
        sample_data = [
            ["7A", "STU001", "7", "John", "Doe", "john.doe@example.com"],
            ["7B", "STU002", "7", "Jane", "Smith", "jane.smith@example.com"],
            ["8A", "STU003", "8", "Bob", "Johnson", "bob.johnson@example.com"]
        ]
        writer.writerows(sample_data)

        # Convert to BytesIO
        bytes_output = io.BytesIO()
        bytes_output.write(output.getvalue().encode('utf-8'))
        bytes_output.seek(0)
        return bytes_output