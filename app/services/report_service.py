"""
Report Generation Service
Generates PDF reports for students based on their performance data.
"""

import io
from datetime import datetime
from typing import Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Frame, PageTemplate
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfgen import canvas

from app.models.student import Student
from app.models.test import Test, TestResult
from app.models.class_model import Class
from app.models.user import User


class ReportService:
    """Service for generating student performance reports."""

    def __init__(self):
        self.page_width, self.page_height = letter
        self.left_margin = 0.75 * inch
        self.right_margin = 0.75 * inch
        self.top_margin = 0.75 * inch
        self.bottom_margin = 0.75 * inch

    async def generate_student_report(
        self,
        db: AsyncSession,
        student_id: str,
        report_data: Dict
    ) -> io.BytesIO:
        """
        Generate a comprehensive PDF report for a student.

        Args:
            db: Database session
            student_id: UUID of the student
            report_data: Dictionary containing:
                - strengths: str
                - areas_for_improvement: str
                - teacher_comment: str
                - intervention_recommendation: str
                - next_steps: str

        Returns:
            BytesIO buffer containing the PDF
        """
        # Fetch student data
        student_data = await self._fetch_student_data(db, student_id)

        # Calculate performance metrics
        performance_data = await self._calculate_performance_metrics(db, student_id)

        # Generate PDF
        pdf_buffer = await self._create_pdf_report(
            student_data=student_data,
            performance_data=performance_data,
            report_data=report_data
        )

        return pdf_buffer

    async def _fetch_student_data(self, db: AsyncSession, student_id: str) -> Dict:
        """Fetch student information from database."""
        stmt = (
            select(Student, User, Class)
            .join(User, Student.user_id == User.id)
            .outerjoin(Class, Student.class_id == Class.id)
            .where(Student.id == student_id)
        )

        result = await db.execute(stmt)
        row = result.first()

        if not row:
            raise ValueError(f"Student with ID {student_id} not found")

        student, user, class_info = row

        return {
            "student_name": user.full_name or "N/A",
            "student_code": student.student_code or "N/A",
            "year_group": f"Year {student.year_group}" if student.year_group else "N/A",
            "class_name": class_info.name if class_info else "Not Assigned",
            "email": user.email
        }

    async def _calculate_performance_metrics(self, db: AsyncSession, student_id: str) -> Dict:
        """Calculate student performance metrics from test results."""
        # Get all test results for the student
        stmt = (
            select(TestResult, Test)
            .join(Test, TestResult.test_id == Test.id)
            .where(TestResult.student_id == student_id)
            .where(TestResult.status.isnot(None))
        )

        result = await db.execute(stmt)
        results = result.all()

        if not results:
            return {
                "english_average": "N/A",
                "mathematics_average": "N/A",
                "verbal_reasoning_average": "N/A",
                "non_verbal_reasoning_average": "N/A",
                "overall_average": "N/A",
                "class_rank": "N/A"
            }

        # Group results by test type
        subject_scores = {
            "English": [],
            "Mathematics": [],
            "Verbal Reasoning": [],
            "Non-Verbal Reasoning": []
        }

        all_scores = []

        for test_result, test in results:
            if test.type in subject_scores:
                subject_scores[test.type].append(test_result.percentage)
                all_scores.append(test_result.percentage)

        # Calculate averages
        def calc_avg(scores):
            return round(sum(scores) / len(scores), 1) if scores else "N/A"

        english_avg = calc_avg(subject_scores["English"])
        math_avg = calc_avg(subject_scores["Mathematics"])
        vr_avg = calc_avg(subject_scores["Verbal Reasoning"])
        nvr_avg = calc_avg(subject_scores["Non-Verbal Reasoning"])
        overall_avg = calc_avg(all_scores)

        # Calculate class rank (simplified - could be enhanced)
        class_rank = await self._calculate_class_rank(db, student_id, overall_avg)

        return {
            "english_average": f"{english_avg}%" if english_avg != "N/A" else "N/A",
            "mathematics_average": f"{math_avg}%" if math_avg != "N/A" else "N/A",
            "verbal_reasoning_average": f"{vr_avg}%" if vr_avg != "N/A" else "N/A",
            "non_verbal_reasoning_average": f"{nvr_avg}%" if nvr_avg != "N/A" else "N/A",
            "overall_average": f"{overall_avg}%" if overall_avg != "N/A" else "N/A",
            "class_rank": class_rank
        }

    async def _calculate_class_rank(self, db: AsyncSession, student_id: str, student_avg: float) -> str:
        """Calculate student's rank within their class."""
        if student_avg == "N/A":
            return "N/A"

        # Get student's class
        stmt = select(Student.class_id).where(Student.id == student_id)
        result = await db.execute(stmt)
        class_id = result.scalar_one_or_none()

        if not class_id:
            return "N/A"

        # Get all students in the same class with their average scores
        stmt = (
            select(Student.id, func.avg(TestResult.percentage).label("avg_score"))
            .join(TestResult, Student.id == TestResult.student_id)
            .where(Student.class_id == class_id)
            .group_by(Student.id)
            .order_by(desc("avg_score"))
        )

        result = await db.execute(stmt)
        class_rankings = result.all()

        if not class_rankings:
            return "N/A"

        # Find student's rank
        rank = 1
        for idx, (sid, avg) in enumerate(class_rankings, 1):
            if str(sid) == str(student_id):
                rank = idx
                break

        total_students = len(class_rankings)
        return f"{rank} of {total_students}"

    async def _create_pdf_report(
        self,
        student_data: Dict,
        performance_data: Dict,
        report_data: Dict
    ) -> io.BytesIO:
        """Create the actual PDF report."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=self.left_margin,
            rightMargin=self.right_margin,
            topMargin=self.top_margin,
            bottomMargin=self.bottom_margin
        )

        # Container for the 'Flowable' objects
        elements = []

        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=20,
            textColor=colors.HexColor('#1e3a8a'),
            spaceAfter=12,
            alignment=TA_LEFT,
            fontName='Helvetica-Bold'
        )

        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1e40af'),
            spaceAfter=8,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        )

        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=10,
            leading=14
        )

        # Title
        title = Paragraph("AE Tuition – Student Progress Report", title_style)
        elements.append(title)
        elements.append(Spacer(1, 0.2 * inch))

        # Student Information Table
        student_info = [
            ['Student Name:', student_data['student_name']],
            ['Student ID:', student_data['student_code']],
            ['Year Group:', student_data['year_group']],
            ['Class:', student_data['class_name']],
            ['Report Period:', datetime.now().strftime('%B %Y')]
        ]

        # Calculate available width: page width - margins
        available_width = self.page_width - self.left_margin - self.right_margin
        info_table = Table(student_info, colWidths=[2.5*inch, available_width - 2.5*inch])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))

        elements.append(info_table)
        elements.append(Spacer(1, 0.3 * inch))

        # Overall Summary
        elements.append(Paragraph("Overall Summary", heading_style))

        summary_data = [
            ['Average Score:', performance_data['overall_average']],
            ['Class Rank:', performance_data['class_rank']],
            ['Teacher Comment:', report_data.get('teacher_comment', 'N/A')]
        ]

        summary_table = Table(summary_data, colWidths=[2.5*inch, available_width - 2.5*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))

        elements.append(summary_table)
        elements.append(Spacer(1, 0.3 * inch))

        # Subject Performance
        elements.append(Paragraph("Subject Performance", heading_style))

        subject_data = [
            ['English', performance_data['english_average']],
            ['Mathematics', performance_data['mathematics_average']],
            ['Verbal Reasoning (VR)', performance_data['verbal_reasoning_average']],
            ['Non-Verbal Reasoning (NVR)', performance_data['non_verbal_reasoning_average']]
        ]

        # Make subject table full width with equal columns
        subject_col_width = available_width / 2
        subject_table = Table(subject_data, colWidths=[subject_col_width, subject_col_width])
        subject_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))

        elements.append(subject_table)
        elements.append(Spacer(1, 0.3 * inch))

        # Strengths
        elements.append(Paragraph("Strengths", heading_style))
        strengths_text = Paragraph(report_data.get('strengths', 'N/A'), normal_style)
        elements.append(strengths_text)
        elements.append(Spacer(1, 0.2 * inch))

        # Areas for Improvement
        elements.append(Paragraph("Areas for Improvement", heading_style))
        improvement_text = Paragraph(report_data.get('areas_for_improvement', 'N/A'), normal_style)
        elements.append(improvement_text)
        elements.append(Spacer(1, 0.2 * inch))

        # Intervention Recommendation
        elements.append(Paragraph("Intervention Recommendation (5-Week Review)", heading_style))
        intervention_text = Paragraph(report_data.get('intervention_recommendation', 'N/A'), normal_style)
        elements.append(intervention_text)
        elements.append(Spacer(1, 0.2 * inch))

        # Next Steps
        elements.append(Paragraph("Next Steps", heading_style))
        next_steps_text = Paragraph(report_data.get('next_steps', 'N/A'), normal_style)
        elements.append(next_steps_text)

        # Build PDF
        doc.build(elements)

        # Get the value of the BytesIO buffer
        buffer.seek(0)
        return buffer
