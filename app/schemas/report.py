"""
Pydantic schemas for student report generation
"""

from pydantic import BaseModel, Field
from typing import Optional


class ReportGenerationRequest(BaseModel):
    """Schema for report generation request from admin."""
    strengths: str = Field(..., description="Student's strengths and positive areas")
    areas_for_improvement: str = Field(..., description="Areas where the student needs improvement")
    teacher_comment: str = Field(..., description="Teacher's overall comment on student performance")
    intervention_recommendation: str = Field(..., description="Recommended interventions for 5-week review")
    next_steps: str = Field(..., description="Action plan and next steps for the student")

    class Config:
        json_schema_extra = {
            "example": {
                "strengths": "Excellent comprehension skills and strong analytical thinking in mathematics.",
                "areas_for_improvement": "Needs to work on time management during tests and focus on verbal reasoning practice.",
                "teacher_comment": "A dedicated student showing consistent progress. Encourage regular practice in weaker areas.",
                "intervention_recommendation": "Additional tutoring sessions in verbal reasoning, practice with timed test conditions.",
                "next_steps": "Complete weekly practice tests, attend extra help sessions, focus on vocabulary building exercises."
            }
        }


class ReportGenerationResponse(BaseModel):
    """Schema for report generation response."""
    success: bool = Field(..., description="Whether the report was generated and sent successfully")
    message: str = Field(..., description="Status message")
    student_email: str = Field(..., description="Email address where the report was sent")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Report generated and sent successfully",
                "student_email": "student@example.com"
            }
        }
