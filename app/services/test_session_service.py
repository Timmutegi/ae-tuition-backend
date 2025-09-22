from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, update, delete
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
from decimal import Decimal

from app.models import (
    Test, TestQuestion, TestAssignment, TestAttempt, TestResult,
    Question, AnswerOption, QuestionResponse, Student, User,
    AttemptStatus, ResultStatus, AssignmentStatus, TestStatus,
    QuestionType, ReadingPassage
)
from app.schemas.test import (
    TestAttemptCreate, TestAttemptResponse, QuestionResponseCreate,
    QuestionResponseUpdate, QuestionResponseDetail, TestSessionResponse,
    TestSubmissionRequest, TestSubmissionResponse, TestResultDetail
)


class TestSessionService:
    @staticmethod
    async def start_test_attempt(
        db: AsyncSession,
        test_id: UUID,
        student_id: UUID,
        assignment_id: UUID,
        browser_info: Dict[str, Any],
        ip_address: str
    ) -> TestAttempt:
        """Start a new test attempt for a student"""

        # Check if test and assignment exist and are valid
        test_result = await db.execute(
            select(Test)
            .where(and_(Test.id == test_id, Test.status == TestStatus.PUBLISHED))
        )
        test = test_result.scalar_one_or_none()
        if not test:
            raise ValueError("Test not found or not published")

        # Check if assignment exists and is active
        assignment_result = await db.execute(
            select(TestAssignment)
            .where(and_(
                TestAssignment.id == assignment_id,
                TestAssignment.test_id == test_id,
                TestAssignment.status.in_([AssignmentStatus.SCHEDULED, AssignmentStatus.ACTIVE])
            ))
        )
        assignment = assignment_result.scalar_one_or_none()
        if not assignment:
            raise ValueError("Test assignment not found or not active")

        # Check if within scheduled time window
        now = datetime.utcnow()
        buffer_start = assignment.scheduled_start - timedelta(minutes=assignment.buffer_time_minutes)
        buffer_end = assignment.scheduled_end + timedelta(
            minutes=assignment.late_submission_grace_minutes if assignment.allow_late_submission else 0
        )

        if now < buffer_start:
            raise ValueError("Test has not started yet")
        if now > buffer_end:
            raise ValueError("Test time window has expired")

        # Check if student already has an attempt for this test
        existing_attempt = await db.execute(
            select(TestAttempt)
            .where(and_(
                TestAttempt.test_id == test_id,
                TestAttempt.student_id == student_id
            ))
        )
        attempt = existing_attempt.scalar_one_or_none()

        if attempt:
            # If attempt exists and is in progress, return it (resume)
            if attempt.status == AttemptStatus.IN_PROGRESS:
                return attempt
            else:
                raise ValueError("Test has already been completed")

        # Create new attempt
        attempt = TestAttempt(
            test_id=test_id,
            student_id=student_id,
            assignment_id=assignment_id,
            started_at=now,
            status=AttemptStatus.IN_PROGRESS,
            browser_info=browser_info,
            ip_address=ip_address,
            answers={}
        )
        db.add(attempt)

        # Update assignment status if needed
        if assignment.status == AssignmentStatus.SCHEDULED and now >= assignment.scheduled_start:
            assignment.status = AssignmentStatus.ACTIVE

        await db.commit()
        await db.refresh(attempt)

        return attempt

    @staticmethod
    async def get_test_session(
        db: AsyncSession,
        attempt_id: UUID,
        student_id: UUID
    ) -> TestSessionResponse:
        """Get current test session details"""

        # Get attempt with related data
        attempt_result = await db.execute(
            select(TestAttempt)
            .options(
                joinedload(TestAttempt.test)
                .selectinload(Test.test_questions)
                .selectinload(TestQuestion.question)
                .selectinload(Question.answer_options),
                joinedload(TestAttempt.test)
                .selectinload(Test.test_questions)
                .selectinload(TestQuestion.passage),
                joinedload(TestAttempt.assignment),
                selectinload(TestAttempt.question_responses)
            )
            .where(and_(
                TestAttempt.id == attempt_id,
                TestAttempt.student_id == student_id
            ))
        )
        attempt = attempt_result.unique().scalar_one_or_none()

        if not attempt:
            raise ValueError("Test attempt not found")

        if attempt.status != AttemptStatus.IN_PROGRESS:
            raise ValueError("Test has already been completed")

        # Calculate time remaining
        now = datetime.utcnow()
        time_elapsed = int((now - attempt.started_at).total_seconds())
        time_remaining = max(0, (attempt.test.duration_minutes * 60) - time_elapsed)

        # Prepare questions data
        questions = []
        passages = {}
        for tq in sorted(attempt.test.test_questions, key=lambda x: x.order_number):
            question = tq.question

            # Add passage if exists
            if tq.passage_id and tq.passage:
                passages[str(tq.passage_id)] = {
                    "id": str(tq.passage_id),
                    "title": tq.passage.title,
                    "content": tq.passage.content,
                    "author": tq.passage.author,
                    "source": tq.passage.source
                }

            # Prepare answer options
            options = []
            for option in question.answer_options:
                options.append({
                    "id": str(option.id),
                    "option_text": option.option_text,
                    "option_type": option.option_type.value if hasattr(option.option_type, 'value') else option.option_type,
                    "option_group": option.option_group,
                    "image_url": option.image_url,
                    "pattern_data": option.pattern_data,
                    "order_number": option.order_number
                })

            questions.append({
                "id": str(question.id),
                "order_number": tq.order_number,
                "question_text": question.question_text,
                "question_type": question.question_type.value,
                "question_format": question.question_format.value if question.question_format else None,
                "passage_id": str(tq.passage_id) if tq.passage_id else None,
                "passage_reference_lines": question.passage_reference_lines,
                "instruction_text": question.instruction_text,
                "image_url": question.image_url,
                "pattern_sequence": question.pattern_sequence,
                "points": tq.points,
                "answer_options": options
            })

        # Prepare answers data
        answers = {}
        for response in attempt.question_responses:
            answers[str(response.question_id)] = QuestionResponseDetail.model_validate(response)

        # Calculate progress
        total_questions = len(questions)
        answered_questions = len(answers)
        progress = {
            "total_questions": total_questions,
            "answered_questions": answered_questions,
            "percentage": round((answered_questions / total_questions * 100) if total_questions > 0 else 0, 2),
            "time_elapsed": time_elapsed,
            "time_remaining": time_remaining
        }

        from app.schemas.test import TestResponse

        return TestSessionResponse(
            attempt=TestAttemptResponse.model_validate(attempt),
            test=TestResponse.model_validate(attempt.test),
            questions=questions,
            answers=answers,
            time_remaining=time_remaining,
            progress=progress
        )

    @staticmethod
    async def save_answer(
        db: AsyncSession,
        attempt_id: UUID,
        question_id: UUID,
        answer_data: QuestionResponseCreate,
        student_id: UUID
    ) -> QuestionResponse:
        """Save or update an answer for a question"""

        # Verify attempt ownership and status
        attempt = await db.execute(
            select(TestAttempt)
            .where(and_(
                TestAttempt.id == attempt_id,
                TestAttempt.student_id == student_id,
                TestAttempt.status == AttemptStatus.IN_PROGRESS
            ))
        )
        attempt = attempt.scalar_one_or_none()

        if not attempt:
            raise ValueError("Active test attempt not found")

        # Check if answer already exists
        existing = await db.execute(
            select(QuestionResponse)
            .where(and_(
                QuestionResponse.attempt_id == attempt_id,
                QuestionResponse.question_id == question_id
            ))
        )
        response = existing.scalar_one_or_none()

        if response:
            # Update existing response
            for field, value in answer_data.model_dump(exclude_unset=True).items():
                setattr(response, field, value)
            response.answered_at = datetime.utcnow()
        else:
            # Create new response
            response = QuestionResponse(
                attempt_id=attempt_id,
                question_id=question_id,
                **answer_data.model_dump(),
                answered_at=datetime.utcnow()
            )
            db.add(response)

        # Update attempt's answers JSON
        if not attempt.answers:
            attempt.answers = {}
        attempt.answers[str(question_id)] = answer_data.model_dump()

        await db.commit()
        await db.refresh(response)

        return response

    @staticmethod
    async def bulk_save_answers(
        db: AsyncSession,
        attempt_id: UUID,
        answers: Dict[UUID, QuestionResponseCreate],
        student_id: UUID
    ) -> List[QuestionResponse]:
        """Save multiple answers at once (for auto-save)"""

        responses = []
        for question_id, answer_data in answers.items():
            response = await TestSessionService.save_answer(
                db, attempt_id, question_id, answer_data, student_id
            )
            responses.append(response)

        return responses

    @staticmethod
    async def submit_test(
        db: AsyncSession,
        attempt_id: UUID,
        submission_data: TestSubmissionRequest,
        student_id: UUID
    ) -> TestSubmissionResponse:
        """Submit test and calculate results"""

        # Get attempt with all related data
        attempt_result = await db.execute(
            select(TestAttempt)
            .options(
                joinedload(TestAttempt.test)
                .selectinload(Test.test_questions)
                .selectinload(TestQuestion.question)
                .selectinload(Question.answer_options),
                selectinload(TestAttempt.question_responses)
            )
            .where(and_(
                TestAttempt.id == attempt_id,
                TestAttempt.student_id == student_id
            ))
        )
        attempt = attempt_result.unique().scalar_one_or_none()

        if not attempt:
            raise ValueError("Test attempt not found")

        if attempt.status != AttemptStatus.IN_PROGRESS:
            raise ValueError("Test has already been submitted")

        # Save any final answers
        if submission_data.answers:
            await TestSessionService.bulk_save_answers(
                db, attempt_id, submission_data.answers, student_id
            )

        # Calculate score
        total_score = 0
        max_score = 0
        question_scores = {}

        for tq in attempt.test.test_questions:
            question = tq.question
            max_score += tq.points

            # Find the response for this question
            response = next(
                (r for r in attempt.question_responses if r.question_id == question.id),
                None
            )

            if response:
                is_correct = False
                points_earned = 0

                # Check answer based on question type
                if question.question_type == QuestionType.MULTIPLE_CHOICE:
                    # Find correct option
                    correct_option = next(
                        (opt for opt in question.answer_options if opt.is_correct),
                        None
                    )
                    if correct_option and response.selected_options:
                        is_correct = str(correct_option.id) in [str(opt) for opt in response.selected_options]

                elif question.question_type == QuestionType.TRUE_FALSE:
                    correct_option = next(
                        (opt for opt in question.answer_options if opt.is_correct),
                        None
                    )
                    if correct_option and response.selected_options:
                        is_correct = str(correct_option.id) in [str(opt) for opt in response.selected_options]

                elif question.question_type in [QuestionType.FILL_BLANK, QuestionType.WORD_COMPLETION]:
                    # For fill-in-blank, check if answer matches correct option text
                    correct_option = next(
                        (opt for opt in question.answer_options if opt.is_correct),
                        None
                    )
                    if correct_option and response.answer_text:
                        is_correct = response.answer_text.strip().lower() == correct_option.option_text.strip().lower()

                elif question.question_type == QuestionType.CLOZE_TEST and response.dropdown_selections:
                    # For cloze tests, check each dropdown selection
                    all_correct = True
                    for blank_id, selected_option_id in response.dropdown_selections.items():
                        correct_option = next(
                            (opt for opt in question.answer_options
                             if opt.is_correct and opt.option_group == blank_id),
                            None
                        )
                        if not correct_option or str(correct_option.id) != str(selected_option_id):
                            all_correct = False
                            break
                    is_correct = all_correct

                if is_correct:
                    points_earned = tq.points
                    total_score += points_earned

                # Update response with scoring
                response.is_correct = is_correct
                response.points_earned = points_earned

                question_scores[str(question.id)] = {
                    "points_earned": points_earned,
                    "max_points": tq.points,
                    "is_correct": is_correct
                }
            else:
                question_scores[str(question.id)] = {
                    "points_earned": 0,
                    "max_points": tq.points,
                    "is_correct": False
                }

        # Update attempt status
        now = datetime.utcnow()
        attempt.submitted_at = now
        attempt.time_taken = int((now - attempt.started_at).total_seconds())

        if submission_data.submission_type == "auto_submit":
            attempt.status = AttemptStatus.AUTO_SUBMITTED
        else:
            attempt.status = AttemptStatus.SUBMITTED

        # Calculate percentage and determine pass/fail
        percentage = (total_score / max_score * 100) if max_score > 0 else 0
        status = ResultStatus.PASS if percentage >= attempt.test.pass_mark else ResultStatus.FAIL

        # Create test result
        result = TestResult(
            attempt_id=attempt_id,
            student_id=student_id,
            test_id=attempt.test_id,
            total_score=total_score,
            max_score=max_score,
            percentage=Decimal(str(round(percentage, 2))),
            grade=TestSessionService._calculate_grade(percentage),
            time_taken=attempt.time_taken,
            submitted_at=now,
            status=status,
            question_scores=question_scores,
            analytics_data={
                "submission_type": submission_data.submission_type,
                "questions_answered": len([s for s in question_scores.values() if s["points_earned"] > 0]),
                "questions_skipped": len([s for s in question_scores.values() if s["points_earned"] == 0]),
                "time_per_question": attempt.time_taken / len(question_scores) if question_scores else 0
            }
        )
        db.add(result)

        await db.commit()
        await db.refresh(result)

        return TestSubmissionResponse(
            attempt_id=attempt_id,
            result_id=result.id,
            total_score=total_score,
            max_score=max_score,
            percentage=float(percentage),
            status=status,
            time_taken=attempt.time_taken,
            submitted_at=now
        )

    @staticmethod
    def _calculate_grade(percentage: float) -> str:
        """Calculate grade based on percentage"""
        if percentage >= 90:
            return "A+"
        elif percentage >= 85:
            return "A"
        elif percentage >= 80:
            return "A-"
        elif percentage >= 75:
            return "B+"
        elif percentage >= 70:
            return "B"
        elif percentage >= 65:
            return "B-"
        elif percentage >= 60:
            return "C+"
        elif percentage >= 55:
            return "C"
        elif percentage >= 50:
            return "C-"
        elif percentage >= 45:
            return "D"
        else:
            return "F"

    @staticmethod
    async def get_test_result(
        db: AsyncSession,
        result_id: UUID,
        student_id: UUID
    ) -> Optional[TestResultDetail]:
        """Get test result details"""

        result = await db.execute(
            select(TestResult)
            .options(
                joinedload(TestResult.attempt),
                joinedload(TestResult.test),
                joinedload(TestResult.student)
            )
            .where(and_(
                TestResult.id == result_id,
                TestResult.student_id == student_id
            ))
        )
        result = result.unique().scalar_one_or_none()

        if result:
            return TestResultDetail.model_validate(result)

        return None

    @staticmethod
    async def get_student_test_results(
        db: AsyncSession,
        student_id: UUID,
        limit: int = 20,
        offset: int = 0
    ) -> List[TestResultDetail]:
        """Get all test results for a student"""

        results = await db.execute(
            select(TestResult)
            .options(
                joinedload(TestResult.test),
                joinedload(TestResult.attempt)
            )
            .where(TestResult.student_id == student_id)
            .order_by(TestResult.submitted_at.desc())
            .limit(limit)
            .offset(offset)
        )

        return [TestResultDetail.model_validate(r) for r in results.unique().scalars().all()]

    @staticmethod
    async def check_and_auto_submit_expired_tests(db: AsyncSession):
        """Check for expired test attempts and auto-submit them"""

        # Find all in-progress attempts that have exceeded their time limit
        now = datetime.utcnow()

        expired_attempts = await db.execute(
            select(TestAttempt)
            .join(TestAttempt.test)
            .join(TestAttempt.assignment)
            .where(and_(
                TestAttempt.status == AttemptStatus.IN_PROGRESS,
                TestAttempt.started_at + timedelta(minutes=Test.duration_minutes) < now
            ))
        )

        for attempt in expired_attempts.scalars().all():
            # Auto-submit the test
            submission_request = TestSubmissionRequest(
                answers={},
                submission_type="timeout"
            )

            try:
                await TestSessionService.submit_test(
                    db, attempt.id, submission_request, attempt.student_id
                )
            except Exception as e:
                # Log error but continue with other attempts
                print(f"Error auto-submitting test attempt {attempt.id}: {str(e)}")
                continue