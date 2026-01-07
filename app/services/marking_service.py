"""
Marking Service for Teacher Assessment System

This service handles:
- Managing the marking queue
- Processing creative writing submissions
- Saving and updating manual marks
- Managing image annotations
- Calculating scores and updating results
"""

from typing import Dict, List, Optional, Any
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_, func, desc
from sqlalchemy.orm import selectinload

from app.models.marking import (
    CreativeWritingSubmission, ImageAnnotation, ManualMark,
    TeacherComment, MarkingQueue, MarkingStatus, AnnotationType,
    StudentCreativeWork, StudentCreativeWorkStatus
)
from app.models.test import TestAttempt, Test, TestAssignment, TestResult, AttemptStatus
from app.models.question import Question, QuestionResponse, QuestionType
from app.models.student import Student
from app.models.user import User
from app.models.class_model import Class
from app.models.teacher import TeacherClassAssignment, TeacherProfile


class MarkingService:
    """Service for managing manual marking workflow."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Creative Writing Submissions ====================

    async def create_submission(
        self,
        attempt_id: UUID,
        question_id: UUID,
        student_id: UUID,
        image_url: str,
        s3_key: str,
        original_filename: str,
        file_size_bytes: int,
        image_width: int,
        image_height: int,
        mime_type: str,
        thumbnail_url: Optional[str] = None
    ) -> CreativeWritingSubmission:
        """
        Create a new creative writing submission.

        Called when a student uploads an image of their work.
        """
        # Check for existing submission (resubmission)
        result = await self.db.execute(
            select(CreativeWritingSubmission).where(and_(
                CreativeWritingSubmission.attempt_id == attempt_id,
                CreativeWritingSubmission.question_id == question_id
            ))
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing submission (resubmission)
            existing.image_url = image_url
            existing.s3_key = s3_key
            existing.thumbnail_url = thumbnail_url
            existing.original_filename = original_filename
            existing.file_size_bytes = file_size_bytes
            existing.image_width = image_width
            existing.image_height = image_height
            existing.mime_type = mime_type
            existing.resubmitted = True
            existing.resubmission_count = (existing.resubmission_count or 0) + 1
            existing.submitted_at = datetime.now(timezone.utc)

            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        submission = CreativeWritingSubmission(
            attempt_id=attempt_id,
            question_id=question_id,
            student_id=student_id,
            image_url=image_url,
            s3_key=s3_key,
            thumbnail_url=thumbnail_url,
            original_filename=original_filename,
            file_size_bytes=file_size_bytes,
            image_width=image_width,
            image_height=image_height,
            mime_type=mime_type
        )

        self.db.add(submission)
        await self.db.commit()
        await self.db.refresh(submission)

        # Create a manual mark entry and add to marking queue
        await self._create_manual_mark_entry(submission)

        return submission

    async def get_submission(self, submission_id: UUID) -> Optional[CreativeWritingSubmission]:
        """Get a creative writing submission by ID."""
        result = await self.db.execute(
            select(CreativeWritingSubmission)
            .options(
                selectinload(CreativeWritingSubmission.annotations),
                selectinload(CreativeWritingSubmission.student).selectinload(Student.user),
                selectinload(CreativeWritingSubmission.question)
            )
            .where(CreativeWritingSubmission.id == submission_id)
        )
        return result.scalar_one_or_none()

    async def get_submissions_for_attempt(
        self,
        attempt_id: UUID
    ) -> List[CreativeWritingSubmission]:
        """Get all creative writing submissions for a test attempt."""
        result = await self.db.execute(
            select(CreativeWritingSubmission)
            .options(selectinload(CreativeWritingSubmission.annotations))
            .where(CreativeWritingSubmission.attempt_id == attempt_id)
            .order_by(CreativeWritingSubmission.submitted_at)
        )
        return list(result.scalars().all())

    # ==================== Image Annotations ====================

    async def add_annotation(
        self,
        submission_id: UUID,
        teacher_id: UUID,
        annotation_type: AnnotationType,
        fabric_data: Dict[str, Any],
        comment_text: Optional[str] = None,
        x_position: Optional[float] = None,
        y_position: Optional[float] = None,
        color: str = "#FF0000",
        stroke_width: int = 2
    ) -> ImageAnnotation:
        """Add an annotation to a creative writing submission."""
        annotation = ImageAnnotation(
            submission_id=submission_id,
            teacher_id=teacher_id,
            annotation_type=annotation_type,
            fabric_data=fabric_data,
            comment_text=comment_text,
            x_position=x_position,
            y_position=y_position,
            color=color,
            stroke_width=stroke_width
        )

        self.db.add(annotation)
        await self.db.commit()
        await self.db.refresh(annotation)

        return annotation

    async def update_annotation(
        self,
        annotation_id: UUID,
        fabric_data: Optional[Dict[str, Any]] = None,
        comment_text: Optional[str] = None,
        color: Optional[str] = None,
        is_visible: Optional[bool] = None
    ) -> Optional[ImageAnnotation]:
        """Update an existing annotation."""
        result = await self.db.execute(
            select(ImageAnnotation).where(ImageAnnotation.id == annotation_id)
        )
        annotation = result.scalar_one_or_none()

        if not annotation:
            return None

        if fabric_data is not None:
            annotation.fabric_data = fabric_data
        if comment_text is not None:
            annotation.comment_text = comment_text
        if color is not None:
            annotation.color = color
        if is_visible is not None:
            annotation.is_visible = is_visible

        await self.db.commit()
        await self.db.refresh(annotation)

        return annotation

    async def delete_annotation(self, annotation_id: UUID) -> bool:
        """Delete an annotation."""
        result = await self.db.execute(
            delete(ImageAnnotation).where(ImageAnnotation.id == annotation_id)
        )
        await self.db.commit()
        return result.rowcount > 0

    async def get_annotations_for_submission(
        self,
        submission_id: UUID
    ) -> List[ImageAnnotation]:
        """Get all annotations for a submission."""
        result = await self.db.execute(
            select(ImageAnnotation)
            .options(selectinload(ImageAnnotation.teacher))
            .where(ImageAnnotation.submission_id == submission_id)
            .order_by(ImageAnnotation.created_at)
        )
        return list(result.scalars().all())

    async def save_annotations_batch(
        self,
        submission_id: UUID,
        teacher_id: UUID,
        annotations: List[Dict[str, Any]]
    ) -> List[ImageAnnotation]:
        """
        Save multiple annotations at once.

        This is more efficient when saving the entire canvas state.
        """
        # Delete existing annotations from this teacher
        await self.db.execute(
            delete(ImageAnnotation).where(and_(
                ImageAnnotation.submission_id == submission_id,
                ImageAnnotation.teacher_id == teacher_id
            ))
        )

        # Create new annotations
        created_annotations = []
        for ann_data in annotations:
            annotation = ImageAnnotation(
                submission_id=submission_id,
                teacher_id=teacher_id,
                annotation_type=AnnotationType(ann_data.get("type", "drawing")),
                fabric_data=ann_data.get("fabric_data", {}),
                comment_text=ann_data.get("comment_text"),
                x_position=ann_data.get("x"),
                y_position=ann_data.get("y"),
                color=ann_data.get("color", "#FF0000"),
                stroke_width=ann_data.get("stroke_width", 2)
            )
            self.db.add(annotation)
            created_annotations.append(annotation)

        await self.db.commit()

        return created_annotations

    # ==================== Manual Marks ====================

    async def _create_manual_mark_entry(
        self,
        submission: CreativeWritingSubmission
    ) -> ManualMark:
        """Create a manual mark entry for a creative writing submission."""
        # Get the question to determine max points
        result = await self.db.execute(
            select(Question).where(Question.id == submission.question_id)
        )
        question = result.scalar_one_or_none()
        max_points = question.points if question else 10

        # Find or create the question response
        response_result = await self.db.execute(
            select(QuestionResponse).where(and_(
                QuestionResponse.attempt_id == submission.attempt_id,
                QuestionResponse.question_id == submission.question_id
            ))
        )
        response = response_result.scalar_one_or_none()

        if not response:
            # Create a response entry
            response = QuestionResponse(
                attempt_id=submission.attempt_id,
                question_id=submission.question_id,
                answer_text=f"Creative writing submission: {submission.original_filename}",
                points_earned=0
            )
            self.db.add(response)
            await self.db.flush()

        # Check for existing manual mark
        existing_result = await self.db.execute(
            select(ManualMark).where(ManualMark.response_id == response.id)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            # Reset existing mark for resubmission
            existing.status = MarkingStatus.PENDING
            existing.creative_submission_id = submission.id
            existing.points_awarded = None
            existing.feedback = None
            existing.marked_by = None
            existing.marked_at = None
            await self.db.commit()
            return existing

        manual_mark = ManualMark(
            response_id=response.id,
            attempt_id=submission.attempt_id,
            question_id=submission.question_id,
            student_id=submission.student_id,
            creative_submission_id=submission.id,
            status=MarkingStatus.PENDING,
            max_points=max_points
        )

        self.db.add(manual_mark)
        await self.db.commit()
        await self.db.refresh(manual_mark)

        # Add to marking queue
        await self._add_to_marking_queue(manual_mark)

        return manual_mark

    async def _add_to_marking_queue(self, manual_mark: ManualMark) -> MarkingQueue:
        """Add a manual mark to the marking queue."""
        # Get test and assignment info
        result = await self.db.execute(
            select(TestAttempt)
            .options(selectinload(TestAttempt.assignment))
            .where(TestAttempt.id == manual_mark.attempt_id)
        )
        attempt = result.scalar_one_or_none()

        test_id = attempt.test_id if attempt else None
        assignment_id = attempt.assignment_id if attempt else None
        class_id = None
        due_date = None

        if attempt and attempt.assignment:
            class_id = attempt.assignment.class_id
            due_date = attempt.assignment.scheduled_end

        queue_item = MarkingQueue(
            manual_mark_id=manual_mark.id,
            test_id=test_id,
            assignment_id=assignment_id,
            class_id=class_id,
            due_date=due_date,
            priority=0
        )

        self.db.add(queue_item)
        await self.db.commit()

        return queue_item

    async def submit_mark(
        self,
        manual_mark_id: UUID,
        teacher_id: UUID,
        points_awarded: float,
        feedback: Optional[str] = None,
        strengths: Optional[str] = None,
        improvements: Optional[str] = None,
        rubric_scores: Optional[Dict[str, Any]] = None,
        time_spent_seconds: Optional[int] = None
    ) -> ManualMark:
        """
        Submit a mark for a creative writing or open-ended question.
        """
        result = await self.db.execute(
            select(ManualMark).where(ManualMark.id == manual_mark_id)
        )
        manual_mark = result.scalar_one_or_none()

        if not manual_mark:
            raise ValueError("Manual mark not found")

        # Calculate percentage
        percentage = (points_awarded / manual_mark.max_points * 100) if manual_mark.max_points > 0 else 0

        # Update manual mark
        manual_mark.points_awarded = points_awarded
        manual_mark.percentage = percentage
        manual_mark.feedback = feedback
        manual_mark.strengths = strengths
        manual_mark.improvements = improvements
        manual_mark.rubric_scores = rubric_scores
        manual_mark.marked_by = teacher_id
        manual_mark.marked_at = datetime.now(timezone.utc)
        manual_mark.status = MarkingStatus.MARKED
        manual_mark.time_spent_seconds = time_spent_seconds

        # Update the question response with the points
        if manual_mark.response_id:
            await self.db.execute(
                update(QuestionResponse)
                .where(QuestionResponse.id == manual_mark.response_id)
                .values(points_earned=points_awarded, is_correct=(percentage >= 50))
            )

        # Remove from marking queue
        await self.db.execute(
            delete(MarkingQueue).where(MarkingQueue.manual_mark_id == manual_mark_id)
        )

        # Update test result if all questions are marked
        await self._update_test_result_if_complete(manual_mark.attempt_id)

        await self.db.commit()
        await self.db.refresh(manual_mark)

        return manual_mark

    async def _update_test_result_if_complete(self, attempt_id: UUID) -> None:
        """Update test result if all manual marks are complete."""
        # Check for pending manual marks
        pending_result = await self.db.execute(
            select(func.count(ManualMark.id))
            .where(and_(
                ManualMark.attempt_id == attempt_id,
                ManualMark.status == MarkingStatus.PENDING
            ))
        )
        pending_count = pending_result.scalar()

        if pending_count > 0:
            return  # Still has pending marks

        # All marks complete - recalculate test result
        # Get all responses for this attempt
        responses_result = await self.db.execute(
            select(QuestionResponse)
            .where(QuestionResponse.attempt_id == attempt_id)
        )
        responses = responses_result.scalars().all()

        total_score = sum(r.points_earned or 0 for r in responses)

        # Update test result
        await self.db.execute(
            update(TestResult)
            .where(TestResult.attempt_id == attempt_id)
            .values(
                total_score=total_score,
                status='pass' if total_score >= 50 else 'fail'  # Simple pass/fail
            )
        )

    # ==================== Marking Queue ====================

    async def get_marking_queue(
        self,
        teacher_id: Optional[UUID] = None,
        test_id: Optional[UUID] = None,
        class_id: Optional[UUID] = None,
        status: Optional[MarkingStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get the marking queue with filters.

        Returns enriched queue items including:
        - Test-based manual marks from MarkingQueue
        - Standalone creative work submissions from StudentCreativeWork
        """
        all_items = []

        # 1. Get test-based marking queue items
        query = (
            select(MarkingQueue)
            .options(
                selectinload(MarkingQueue.manual_mark)
                .selectinload(ManualMark.student)
                .selectinload(Student.user),
                selectinload(MarkingQueue.manual_mark)
                .selectinload(ManualMark.question),
                selectinload(MarkingQueue.manual_mark)
                .selectinload(ManualMark.creative_submission),
                selectinload(MarkingQueue.test)
            )
        )

        # Apply filters for test-based queue
        conditions = []
        if test_id:
            conditions.append(MarkingQueue.test_id == test_id)
        if class_id:
            conditions.append(MarkingQueue.class_id == class_id)
        if teacher_id:
            conditions.append(or_(
                MarkingQueue.assigned_to == teacher_id,
                MarkingQueue.assigned_to.is_(None)
            ))
        if status:
            query = query.join(ManualMark)
            conditions.append(ManualMark.status == status)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(
            desc(MarkingQueue.priority),
            MarkingQueue.due_date,
            MarkingQueue.created_at
        )

        result = await self.db.execute(query)
        queue_items = result.unique().scalars().all()
        all_items.extend([self._queue_item_to_dict(item) for item in queue_items])

        # 2. Get standalone creative work submissions (if not filtering by test_id)
        if not test_id:
            creative_items = await self._get_creative_work_queue(teacher_id, class_id, status)
            all_items.extend(creative_items)

        # Sort combined results by created_at (newest first) and apply pagination
        all_items.sort(key=lambda x: x.get('created_at') or '', reverse=True)

        return all_items[offset:offset + limit]

    async def _get_creative_work_queue(
        self,
        teacher_id: Optional[UUID] = None,
        class_id: Optional[UUID] = None,
        status: Optional[MarkingStatus] = None
    ) -> List[Dict[str, Any]]:
        """
        Get standalone creative work submissions for the teacher's classes.
        """
        # Get teacher's assigned class IDs
        teacher_class_ids = []
        if teacher_id:
            # First get teacher record from user_id
            teacher_result = await self.db.execute(
                select(TeacherProfile).where(TeacherProfile.user_id == teacher_id)
            )
            teacher = teacher_result.scalar_one_or_none()

            if teacher:
                class_result = await self.db.execute(
                    select(TeacherClassAssignment.class_id)
                    .where(TeacherClassAssignment.teacher_id == teacher.id)
                )
                teacher_class_ids = [row[0] for row in class_result.fetchall()]

        # Build query for creative work
        query = (
            select(StudentCreativeWork)
            .options(
                selectinload(StudentCreativeWork.student).selectinload(Student.user),
                selectinload(StudentCreativeWork.student).selectinload(Student.class_info)
            )
        )

        conditions = []

        # Filter by pending status (or match the status filter)
        if status:
            if status == MarkingStatus.PENDING:
                conditions.append(StudentCreativeWork.status == StudentCreativeWorkStatus.PENDING)
            elif status == MarkingStatus.MARKED:
                conditions.append(StudentCreativeWork.status == StudentCreativeWorkStatus.REVIEWED)
        else:
            # Default: show pending items
            conditions.append(StudentCreativeWork.status == StudentCreativeWorkStatus.PENDING)

        # Filter by teacher's assigned classes
        if teacher_class_ids:
            # Join with Student to filter by class
            query = query.join(Student, StudentCreativeWork.student_id == Student.id)
            conditions.append(Student.class_id.in_(teacher_class_ids))
        elif class_id:
            query = query.join(Student, StudentCreativeWork.student_id == Student.id)
            conditions.append(Student.class_id == class_id)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(desc(StudentCreativeWork.submitted_at))

        result = await self.db.execute(query)
        creative_works = result.unique().scalars().all()

        return [self._creative_work_to_queue_dict(work) for work in creative_works]

    def _creative_work_to_queue_dict(self, work: StudentCreativeWork) -> Dict[str, Any]:
        """Convert a standalone creative work to a queue item dictionary."""
        student_name = "Unknown"
        student_email = ""
        if work.student and work.student.user:
            student_name = work.student.user.full_name or work.student.user.username
            student_email = work.student.user.email

        return {
            "id": f"cw_{work.id}",  # Prefix to distinguish from regular queue items
            "manual_mark_id": None,
            "creative_work_id": str(work.id),
            "test_id": None,
            "test_title": "Creative Writing",
            "student_id": str(work.student_id),
            "student_name": student_name,
            "student_email": student_email,
            "question_id": None,
            "question_text": work.title,
            "question_type": "CREATIVE_WORK",
            "max_points": 0,
            "status": work.status.value if work.status else "pending",
            "submission_url": work.image_url,
            "submission_thumbnail": None,
            "priority": 0,
            "due_date": None,
            "is_locked": False,
            "locked_by": None,
            "created_at": work.submitted_at.isoformat() if work.submitted_at else None
        }

    async def get_queue_stats(
        self,
        teacher_id: Optional[UUID] = None,
        test_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Get statistics about the marking queue including standalone creative work."""
        base_conditions = []
        if test_id:
            base_conditions.append(MarkingQueue.test_id == test_id)

        # Total pending from MarkingQueue
        pending_query = select(func.count(MarkingQueue.id))
        if base_conditions:
            pending_query = pending_query.where(and_(*base_conditions))
        pending_result = await self.db.execute(pending_query)
        total_pending = pending_result.scalar() or 0

        # Add standalone creative work pending count (if not filtering by test_id)
        if not test_id and teacher_id:
            creative_pending = await self._get_creative_work_pending_count(teacher_id)
            total_pending += creative_pending

        # Assigned to this teacher
        assigned_count = 0
        if teacher_id:
            assigned_query = select(func.count(MarkingQueue.id)).where(
                MarkingQueue.assigned_to == teacher_id
            )
            if base_conditions:
                assigned_query = assigned_query.where(and_(*base_conditions))
            assigned_result = await self.db.execute(assigned_query)
            assigned_count = assigned_result.scalar() or 0

        # Overdue items
        overdue_query = select(func.count(MarkingQueue.id)).where(
            MarkingQueue.due_date < datetime.now(timezone.utc)
        )
        if base_conditions:
            overdue_query = overdue_query.where(and_(*base_conditions))
        overdue_result = await self.db.execute(overdue_query)
        overdue_count = overdue_result.scalar() or 0

        return {
            "total_pending": total_pending,
            "assigned_to_me": assigned_count,
            "overdue": overdue_count
        }

    async def _get_creative_work_pending_count(self, teacher_id: UUID) -> int:
        """Get count of pending creative work for teacher's assigned classes."""
        # Get teacher record
        teacher_result = await self.db.execute(
            select(TeacherProfile).where(TeacherProfile.user_id == teacher_id)
        )
        teacher = teacher_result.scalar_one_or_none()

        if not teacher:
            return 0

        # Get teacher's assigned class IDs
        class_result = await self.db.execute(
            select(TeacherClassAssignment.class_id)
            .where(TeacherClassAssignment.teacher_id == teacher.id)
        )
        teacher_class_ids = [row[0] for row in class_result.fetchall()]

        if not teacher_class_ids:
            return 0

        # Count pending creative work from students in those classes
        count_query = (
            select(func.count(StudentCreativeWork.id))
            .join(Student, StudentCreativeWork.student_id == Student.id)
            .where(and_(
                StudentCreativeWork.status == StudentCreativeWorkStatus.PENDING,
                Student.class_id.in_(teacher_class_ids)
            ))
        )
        count_result = await self.db.execute(count_query)
        return count_result.scalar() or 0

    async def lock_queue_item(
        self,
        queue_id: UUID,
        teacher_id: UUID
    ) -> bool:
        """Lock a queue item for marking."""
        result = await self.db.execute(
            update(MarkingQueue)
            .where(and_(
                MarkingQueue.id == queue_id,
                or_(
                    MarkingQueue.is_locked == False,
                    MarkingQueue.locked_by == teacher_id
                )
            ))
            .values(
                is_locked=True,
                locked_by=teacher_id,
                locked_at=datetime.now(timezone.utc)
            )
        )
        await self.db.commit()
        return result.rowcount > 0

    async def unlock_queue_item(self, queue_id: UUID) -> bool:
        """Unlock a queue item."""
        result = await self.db.execute(
            update(MarkingQueue)
            .where(MarkingQueue.id == queue_id)
            .values(
                is_locked=False,
                locked_by=None,
                locked_at=None
            )
        )
        await self.db.commit()
        return result.rowcount > 0

    def _queue_item_to_dict(self, item: MarkingQueue) -> Dict[str, Any]:
        """Convert a queue item to a dictionary."""
        manual_mark = item.manual_mark
        student_name = "Unknown"
        student_email = ""
        if manual_mark and manual_mark.student and manual_mark.student.user:
            student_name = manual_mark.student.user.full_name or manual_mark.student.user.username
            student_email = manual_mark.student.user.email

        question_text = ""
        question_type = ""
        if manual_mark and manual_mark.question:
            question_text = manual_mark.question.question_text or ""
            question_type = manual_mark.question.question_type.value if manual_mark.question.question_type else ""

        submission_url = None
        submission_thumbnail = None
        if manual_mark and manual_mark.creative_submission:
            submission_url = manual_mark.creative_submission.image_url
            submission_thumbnail = manual_mark.creative_submission.thumbnail_url

        test_title = item.test.title if item.test else "Unknown Test"

        return {
            "id": str(item.id),
            "manual_mark_id": str(item.manual_mark_id),
            "creative_work_id": None,  # Not a standalone creative work
            "test_id": str(item.test_id) if item.test_id else None,
            "test_title": test_title,
            "student_id": str(manual_mark.student_id) if manual_mark else None,
            "student_name": student_name,
            "student_email": student_email,
            "question_id": str(manual_mark.question_id) if manual_mark else None,
            "question_text": question_text[:100] + "..." if len(question_text) > 100 else question_text,
            "question_type": question_type,
            "max_points": manual_mark.max_points if manual_mark else 0,
            "status": manual_mark.status.value if manual_mark else "pending",
            "submission_url": submission_url,
            "submission_thumbnail": submission_thumbnail,
            "priority": item.priority,
            "due_date": item.due_date.isoformat() if item.due_date else None,
            "is_locked": item.is_locked,
            "locked_by": str(item.locked_by) if item.locked_by else None,
            "created_at": item.created_at.isoformat() if item.created_at else None
        }

    # ==================== Teacher Comments ====================

    async def add_comment(
        self,
        teacher_id: UUID,
        student_id: UUID,
        comment_text: str,
        comment_type: str = "feedback",
        attempt_id: Optional[UUID] = None,
        result_id: Optional[UUID] = None,
        question_id: Optional[UUID] = None,
        visible_to_student: bool = True,
        visible_to_parents: bool = False
    ) -> TeacherComment:
        """Add a comment on student performance."""
        comment = TeacherComment(
            teacher_id=teacher_id,
            student_id=student_id,
            comment_text=comment_text,
            comment_type=comment_type,
            attempt_id=attempt_id,
            result_id=result_id,
            question_id=question_id,
            visible_to_student=visible_to_student,
            visible_to_parents=visible_to_parents
        )

        self.db.add(comment)
        await self.db.commit()
        await self.db.refresh(comment)

        return comment

    async def get_comments_for_student(
        self,
        student_id: UUID,
        visible_to_student_only: bool = False
    ) -> List[TeacherComment]:
        """Get all comments for a student."""
        query = select(TeacherComment).where(TeacherComment.student_id == student_id)

        if visible_to_student_only:
            query = query.where(TeacherComment.visible_to_student == True)

        query = query.order_by(desc(TeacherComment.created_at))

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_comments_for_attempt(
        self,
        attempt_id: UUID
    ) -> List[TeacherComment]:
        """Get all comments for a specific test attempt."""
        result = await self.db.execute(
            select(TeacherComment)
            .options(selectinload(TeacherComment.teacher))
            .where(TeacherComment.attempt_id == attempt_id)
            .order_by(TeacherComment.created_at)
        )
        return list(result.scalars().all())
