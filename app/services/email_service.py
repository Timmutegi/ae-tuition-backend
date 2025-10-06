import os
import logging
import asyncio
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