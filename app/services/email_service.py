import os
import logging
import asyncio
import base64
from typing import Dict, List, Optional
import resend
from pathlib import Path

from app.core.config import settings


logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        resend.api_key = settings.RESEND_API_KEY
        self.from_email = settings.FROM_EMAIL
        self.frontend_url = settings.FRONTEND_URL
        self.templates_dir = Path(__file__).parent.parent / "emails" / "templates"

    def _load_template(self, template_name: str) -> str:
        """Load email template from file."""
        template_path = self.templates_dir / template_name
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"Template {template_name} not found")
            raise ValueError(f"Email template {template_name} not found")

    def _render_template(self, template_content: str, variables: Dict[str, str]) -> str:
        """Replace template variables with actual values."""
        content = template_content
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            content = content.replace(placeholder, str(value))
        return content

    async def send_welcome_email(self, student: dict, password: str) -> bool:
        """Send welcome email to newly created student."""
        try:
            template = self._load_template("student_welcome.html")

            variables = {
                "student_name": student.get("full_name", "Student"),
                "student_code": student.get("student_code", "N/A"),
                "email": student["email"],
                "password": password,
                "frontend_url": self.frontend_url,
                "contact_email": "support@ae-tuition.com"
            }

            html_content = self._render_template(template, variables)

            email_data = {
                "from": self.from_email,
                "to": [student["email"]],
                "subject": "Welcome to AE Tuition - Your Account Details",
                "html": html_content
            }

            # Use sync call since resend doesn't have async support - but don't await it to avoid greenlet issues
            try:
                response = resend.Emails.send(email_data)
            except Exception as e:
                logger.error(f"Email send failed: {str(e)}")
                return False
            logger.info(f"Welcome email sent to {student['email']}: {response}")
            return True

        except Exception as e:
            logger.error(f"Failed to send welcome email to {student['email']}: {str(e)}")
            return False

    async def send_password_reset(self, student: dict, new_password: str) -> bool:
        """Send password reset email to student."""
        try:
            template = self._load_template("password_reset.html")

            variables = {
                "student_name": student.get("full_name", "Student"),
                "new_password": new_password,
                "frontend_url": self.frontend_url,
                "contact_email": "support@ae-tuition.com"
            }

            html_content = self._render_template(template, variables)

            email_data = {
                "from": self.from_email,
                "to": [student["email"]],
                "subject": "AE Tuition - Password Reset",
                "html": html_content
            }

            # Use sync call since resend doesn't have async support - but don't await it to avoid greenlet issues
            try:
                response = resend.Emails.send(email_data)
            except Exception as e:
                logger.error(f"Email send failed: {str(e)}")
                return False
            logger.info(f"Password reset email sent to {student['email']}: {response}")
            return True

        except Exception as e:
            logger.error(f"Failed to send password reset email to {student['email']}: {str(e)}")
            return False

    async def send_bulk_emails(self, email_data: List[dict]) -> dict:
        """Send emails to multiple recipients."""
        results = {
            "sent": 0,
            "failed": 0,
            "errors": []
        }

        for data in email_data:
            try:
                success = await self.send_welcome_email(
                    data["student"],
                    data["password"]
                )
                if success:
                    results["sent"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append({
                        "email": data["student"]["email"],
                        "error": "Failed to send"
                    })
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({
                    "email": data["student"]["email"],
                    "error": str(e)
                })

        return results

    async def send_teacher_welcome_email(self, teacher: dict, password: str) -> bool:
        """Send welcome email to newly created teacher with login credentials."""
        try:
            template = self._load_template("teacher_welcome.html")

            variables = {
                "teacher_name": teacher.get("full_name", "Teacher"),
                "username": teacher.get("username", ""),
                "email": teacher["email"],
                "password": password,
                "frontend_url": self.frontend_url,
                "contact_email": "support@ae-tuition.com"
            }

            html_content = self._render_template(template, variables)

            email_data = {
                "from": self.from_email,
                "to": [teacher["email"]],
                "subject": "Welcome to AE Tuition - Your Teacher Account Details",
                "html": html_content
            }

            try:
                response = resend.Emails.send(email_data)
            except Exception as e:
                logger.error(f"Email send failed: {str(e)}")
                return False
            logger.info(f"Teacher welcome email sent to {teacher['email']}: {response}")
            return True

        except Exception as e:
            logger.error(f"Failed to send teacher welcome email to {teacher['email']}: {str(e)}")
            return False

    async def send_supervisor_welcome_email(self, supervisor: dict, password: str) -> bool:
        """Send welcome email to newly created supervisor with login credentials."""
        try:
            template = self._load_template("supervisor_welcome.html")

            variables = {
                "supervisor_name": supervisor.get("full_name", "Supervisor"),
                "username": supervisor.get("username", ""),
                "email": supervisor["email"],
                "password": password,
                "frontend_url": self.frontend_url,
                "contact_email": "support@ae-tuition.com"
            }

            html_content = self._render_template(template, variables)

            email_data = {
                "from": self.from_email,
                "to": [supervisor["email"]],
                "subject": "Welcome to AE Tuition - Your Supervisor Account Details",
                "html": html_content
            }

            try:
                response = resend.Emails.send(email_data)
            except Exception as e:
                logger.error(f"Email send failed: {str(e)}")
                return False
            logger.info(f"Supervisor welcome email sent to {supervisor['email']}: {response}")
            return True

        except Exception as e:
            logger.error(f"Failed to send supervisor welcome email to {supervisor['email']}: {str(e)}")
            return False

    async def send_student_report(self, student: dict, report_data: dict, pdf_buffer) -> bool:
        """
        Send student performance report email with PDF attachment.

        Args:
            student: Dictionary containing student information (email, full_name, etc.)
            report_data: Dictionary containing report metadata (period, class, averages)
            pdf_buffer: BytesIO buffer containing the PDF report

        Returns:
            Boolean indicating success/failure
        """
        try:
            template = self._load_template("student_report.html")

            from datetime import datetime
            report_period = report_data.get("report_period", datetime.now().strftime("%B %Y"))

            variables = {
                "student_name": student.get("full_name", "Student"),
                "report_period": report_period,
                "class_name": report_data.get("class_name", "N/A"),
                "year_group": report_data.get("year_group", "N/A"),
                "overall_average": report_data.get("overall_average", "N/A"),
                "class_rank": report_data.get("class_rank", "N/A"),
                "frontend_url": self.frontend_url,
                "contact_email": "support@ae-tuition.com"
            }

            html_content = self._render_template(template, variables)

            # Read PDF content and encode as base64
            pdf_content = pdf_buffer.read()
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')

            # Generate filename
            student_name_safe = student.get("full_name", "Student").replace(" ", "_")
            filename = f"Performance_Report_{student_name_safe}_{report_period.replace(' ', '_')}.pdf"

            email_data = {
                "from": self.from_email,
                "to": [student["email"]],
                "subject": f"Your Performance Report - {report_period}",
                "html": html_content,
                "attachments": [
                    {
                        "filename": filename,
                        "content": pdf_base64
                    }
                ]
            }

            try:
                response = resend.Emails.send(email_data)
            except Exception as e:
                logger.error(f"Email send failed: {str(e)}")
                return False

            logger.info(f"Student report email sent to {student['email']}: {response}")
            return True

        except Exception as e:
            logger.error(f"Failed to send report email to {student['email']}: {str(e)}")
            return False