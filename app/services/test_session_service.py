from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, update, delete
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
from decimal import Decimal
from datetime import timezone

from app.models import (
    Test, TestQuestion, TestAssignment, StudentTestAssignment, TestAttempt, TestResult,
    Question, AnswerOption, QuestionResponse, Student, User,
    AttemptStatus, ResultStatus, AssignmentStatus, TestStatus,
    QuestionType, ReadingPassage, TestQuestionSet, QuestionSet, QuestionSetItem
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

        # Check if assignment exists and is active (check both class and individual assignments)
        assignment_result = await db.execute(
            select(TestAssignment)
            .where(and_(
                TestAssignment.id == assignment_id,
                TestAssignment.test_id == test_id,
                TestAssignment.status.in_([AssignmentStatus.SCHEDULED, AssignmentStatus.ACTIVE])
            ))
        )
        assignment = assignment_result.scalar_one_or_none()
        is_student_assignment = False

        # If not found in class assignments, check individual student assignments
        if not assignment:
            student_assignment_result = await db.execute(
                select(StudentTestAssignment)
                .where(and_(
                    StudentTestAssignment.id == assignment_id,
                    StudentTestAssignment.test_id == test_id,
                    StudentTestAssignment.status.in_([AssignmentStatus.SCHEDULED, AssignmentStatus.ACTIVE])
                ))
            )
            assignment = student_assignment_result.scalar_one_or_none()
            is_student_assignment = True

        if not assignment:
            raise ValueError("Test assignment not found or not active")

        # Check if within scheduled time window (student can start as long as end time hasn't been reached)
        now = datetime.now(timezone.utc)

        # Ensure assignment times are timezone-aware
        scheduled_end = assignment.scheduled_end
        if scheduled_end.tzinfo is None:
            scheduled_end = scheduled_end.replace(tzinfo=timezone.utc)

        if now > scheduled_end:
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

        # Create new attempt with correct foreign key column based on assignment type
        if is_student_assignment:
            # For individual student assignments, use student_assignment_id column
            attempt = TestAttempt(
                test_id=test_id,
                student_id=student_id,
                assignment_id=None,
                student_assignment_id=assignment_id,
                started_at=now,
                status=AttemptStatus.IN_PROGRESS,
                browser_info=browser_info,
                ip_address=ip_address,
                answers={}
            )
        else:
            # For class assignments, use assignment_id column
            attempt = TestAttempt(
                test_id=test_id,
                student_id=student_id,
                assignment_id=assignment_id,
                student_assignment_id=None,
                started_at=now,
                status=AttemptStatus.IN_PROGRESS,
                browser_info=browser_info,
                ip_address=ip_address,
                answers={}
            )
        db.add(attempt)

        # Update assignment status to ACTIVE when first student starts
        if assignment.status == AssignmentStatus.SCHEDULED:
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
                joinedload(TestAttempt.test)
                .selectinload(Test.test_question_sets)
                .selectinload(TestQuestionSet.question_set)
                .selectinload(QuestionSet.question_set_items)
                .selectinload(QuestionSetItem.question)
                .selectinload(Question.answer_options),
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

        # Store test_id and all test attributes locally to avoid session issues
        test_id = attempt.test_id
        test_title = attempt.test.title
        test_description = attempt.test.description
        test_type = attempt.test.type
        test_format = attempt.test.test_format
        test_duration_minutes = attempt.test.duration_minutes
        test_warning_intervals = attempt.test.warning_intervals
        test_pass_mark = attempt.test.pass_mark
        test_total_marks = attempt.test.total_marks
        test_instructions = attempt.test.instructions
        test_question_order = attempt.test.question_order
        test_status = attempt.test.status
        test_template_id = attempt.test.template_id
        test_created_by = attempt.test.created_by
        test_created_at = attempt.test.created_at
        test_updated_at = attempt.test.updated_at

        # Calculate time remaining
        now = datetime.now(timezone.utc)

        # Ensure started_at is timezone-aware
        started_at = attempt.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

        time_elapsed = int((now - started_at).total_seconds())
        time_remaining = max(0, (test_duration_minutes * 60) - time_elapsed)

        # Prepare questions data
        questions = []
        passages = {}

        # Fetch test questions separately to avoid lazy loading issues
        test_questions_result = await db.execute(
            select(TestQuestion)
            .options(
                selectinload(TestQuestion.question).selectinload(Question.answer_options),
                selectinload(TestQuestion.question).selectinload(Question.passage),
                selectinload(TestQuestion.passage)
            )
            .where(TestQuestion.test_id == test_id)
            .order_by(TestQuestion.order_number)
        )
        test_questions = test_questions_result.scalars().all()

        # Check if test has direct questions or uses question sets
        if test_questions:
            # Handle direct test questions
            for tq in test_questions:
                question = tq.question

                # Add passage if exists (check both TestQuestion.passage and Question.passage)
                passage = None
                passage_id = None

                if tq.passage_id and tq.passage:
                    passage = tq.passage
                    passage_id = tq.passage_id
                elif question.passage_id and question.passage:
                    passage = question.passage
                    passage_id = question.passage_id

                if passage_id and passage:
                    passages[str(passage_id)] = {
                        "id": str(passage_id),
                        "title": passage.title,
                        "content": passage.content,
                        "image_url": passage.image_url,
                        "s3_key": passage.s3_key,
                        "author": passage.author,
                        "source": passage.source
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
                    "passage_id": str(passage_id) if passage_id else None,
                    "passage_reference_lines": question.passage_reference_lines,
                    "instruction_text": question.instruction_text,
                    "image_url": question.image_url,
                    "pattern_sequence": question.pattern_sequence,
                    "points": tq.points,
                    "answer_options": options,
                    # Include additional fields for verbal reasoning questions
                    "given_word": question.given_word,
                    "letter_template": question.letter_template,
                    "word_bank": question.word_bank
                })
        else:
            # Try fetching question sets if no direct questions
            test_question_sets_result = await db.execute(
                select(TestQuestionSet)
                .options(
                    selectinload(TestQuestionSet.question_set).selectinload(QuestionSet.question_set_items).selectinload(QuestionSetItem.question).selectinload(Question.answer_options),
                    selectinload(TestQuestionSet.question_set).selectinload(QuestionSet.question_set_items).selectinload(QuestionSetItem.question).selectinload(Question.passage)
                )
                .where(TestQuestionSet.test_id == test_id)
                .order_by(TestQuestionSet.order_number)
            )
            test_question_sets = test_question_sets_result.scalars().all()

            # Handle question sets if they exist
            if test_question_sets:
                overall_order = 1
                for tqs in test_question_sets:
                    question_set = tqs.question_set
                    if question_set and question_set.question_set_items:
                        for qsi in sorted(question_set.question_set_items, key=lambda x: x.order_number):
                            question = qsi.question

                            # Add passage if exists (for questions in question sets)
                            if question.passage_id and question.passage:
                                passages[str(question.passage_id)] = {
                                    "id": str(question.passage_id),
                                    "title": question.passage.title,
                                    "content": question.passage.content,
                                    "image_url": question.passage.image_url,
                                    "s3_key": question.passage.s3_key,
                                    "author": question.passage.author,
                                    "source": question.passage.source
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
                                "order_number": overall_order,
                                "question_text": question.question_text,
                                "question_type": question.question_type.value,
                                "question_format": question.question_format.value if question.question_format else None,
                                "passage_id": str(question.passage_id) if question.passage_id else None,
                                "passage_reference_lines": question.passage_reference_lines,
                                "instruction_text": question.instruction_text,
                                "image_url": question.image_url,
                                "pattern_sequence": question.pattern_sequence,
                                "points": qsi.points_override if qsi.points_override else question.points,
                                "answer_options": options,
                                # Include additional fields for verbal reasoning questions
                                "given_word": question.given_word,
                                "letter_template": question.letter_template,
                                "word_bank": question.word_bank
                            })
                            overall_order += 1

        # Prepare answers data
        answers = {}
        for response in attempt.question_responses:
            answers[str(response.question_id)] = QuestionResponseDetail(
                id=response.id,
                attempt_id=response.attempt_id,
                question_id=response.question_id,
                answer_text=response.answer_text,
                selected_options=response.selected_options,
                dropdown_selections=response.dropdown_selections,
                fill_in_answers=response.fill_in_answers,
                pattern_response=response.pattern_response,
                is_correct=response.is_correct,
                partial_score=response.partial_score,
                points_earned=response.points_earned,
                time_spent=response.time_spent,
                answered_at=response.answered_at,
                created_at=response.created_at
            )

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
            attempt=TestAttemptResponse(
                id=attempt.id,
                test_id=test_id,
                student_id=attempt.student_id,
                assignment_id=attempt.assignment_id,
                started_at=attempt.started_at,
                submitted_at=attempt.submitted_at,
                time_taken=attempt.time_taken,
                status=attempt.status,
                browser_info=attempt.browser_info,
                ip_address=attempt.ip_address,
                created_at=attempt.created_at
            ),
            test=TestResponse(
                id=test_id,
                title=test_title,
                description=test_description,
                type=test_type,
                test_format=test_format,
                duration_minutes=test_duration_minutes,
                warning_intervals=test_warning_intervals,
                pass_mark=test_pass_mark,
                total_marks=test_total_marks,
                instructions=test_instructions,
                question_order=test_question_order,
                status=test_status,
                template_id=test_template_id,
                created_by=test_created_by,
                created_at=test_created_at,
                updated_at=test_updated_at,
                test_question_sets=[]
            ),
            questions=questions,
            passages=passages,
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
            answer_dict = answer_data.model_dump(exclude_unset=True, mode='json')
            for field, value in answer_dict.items():
                if field != 'question_id':  # Don't update question_id
                    setattr(response, field, value)
            response.answered_at = datetime.now(timezone.utc)
        else:
            # Create new response
            answer_dict = answer_data.model_dump(mode='json', exclude={'question_id'})
            response = QuestionResponse(
                attempt_id=attempt_id,
                question_id=question_id,
                answer_text=answer_dict.get('answer_text'),
                selected_options=answer_dict.get('selected_options'),
                dropdown_selections=answer_dict.get('dropdown_selections'),
                fill_in_answers=answer_dict.get('fill_in_answers'),
                pattern_response=answer_dict.get('pattern_response'),
                answered_at=datetime.now(timezone.utc)
            )
            db.add(response)

        # Update attempt's answers JSON
        if not attempt.answers:
            attempt.answers = {}

        # Create a clean JSON-serializable dict without nested UUID objects
        answer_json = answer_data.model_dump(mode='json')

        # Recursively convert all UUIDs to strings
        def convert_uuids_to_strings(obj):
            if isinstance(obj, UUID):
                return str(obj)
            elif isinstance(obj, dict):
                return {k: convert_uuids_to_strings(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_uuids_to_strings(item) for item in obj]
            else:
                return obj

        answer_json = convert_uuids_to_strings(answer_json)
        attempt.answers[str(question_id)] = answer_json

        await db.commit()
        await db.refresh(response)

        return response

    @staticmethod
    async def bulk_save_answers(
        db: AsyncSession,
        attempt_id: UUID,
        answers: Dict[str, QuestionResponseCreate],  # Changed to expect string keys
        student_id: UUID
    ) -> List[QuestionResponse]:
        """Save multiple answers at once (for auto-save)"""

        responses = []
        for question_id_str, answer_data in answers.items():
            # Convert string question_id back to UUID
            question_id = UUID(question_id_str)
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

        # Get attempt with all related data (including both test_questions and question_sets)
        attempt_result = await db.execute(
            select(TestAttempt)
            .options(
                joinedload(TestAttempt.test)
                .selectinload(Test.test_questions)
                .selectinload(TestQuestion.question)
                .selectinload(Question.answer_options),
                joinedload(TestAttempt.test)
                .selectinload(Test.test_question_sets)
                .selectinload(TestQuestionSet.question_set)
                .selectinload(QuestionSet.question_set_items)
                .selectinload(QuestionSetItem.question)
                .selectinload(Question.answer_options)
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

        # Store attempt attributes locally to avoid session issues and lazy loading
        test_id = attempt.test_id
        student_id_from_attempt = attempt.student_id
        attempt_started_at = attempt.started_at
        attempt_test_pass_mark = attempt.test.pass_mark

        # Save any final answers
        if submission_data.answers:
            try:
                await TestSessionService.bulk_save_answers(
                    db, attempt_id, submission_data.answers, student_id
                )
            except Exception as e:
                print(f"Error in bulk_save_answers: {str(e)}")
                raise

        # Calculate score
        total_score = 0
        max_score = 0
        question_scores = {}

        # Get all questions (from both direct test_questions and question_sets)
        all_questions = []

        # Fetch test questions separately to avoid lazy loading
        test_questions_result = await db.execute(
            select(TestQuestion)
            .options(selectinload(TestQuestion.question).selectinload(Question.answer_options))
            .where(TestQuestion.test_id == test_id)
            .order_by(TestQuestion.order_number)
        )
        test_questions = test_questions_result.scalars().all()

        if test_questions:
            # Add direct test questions
            for tq in test_questions:
                all_questions.append((tq.question, tq.points))
        else:
            # Try question sets if no direct questions
            test_question_sets_result = await db.execute(
                select(TestQuestionSet)
                .options(
                    selectinload(TestQuestionSet.question_set)
                    .selectinload(QuestionSet.question_set_items)
                    .selectinload(QuestionSetItem.question)
                    .selectinload(Question.answer_options)
                )
                .where(TestQuestionSet.test_id == test_id)
                .order_by(TestQuestionSet.order_number)
            )
            test_question_sets = test_question_sets_result.scalars().all()

            for tqs in test_question_sets:
                for qsi in tqs.question_set.question_set_items:
                    points = qsi.points_override if qsi.points_override is not None else qsi.question.points
                    all_questions.append((qsi.question, points))

        # Create a lookup dictionary for question responses to avoid lazy loading
        # Get all question responses for this attempt using a separate query
        responses_result = await db.execute(
            select(QuestionResponse)
            .where(QuestionResponse.attempt_id == attempt_id)
        )
        responses = responses_result.scalars().all()
        response_lookup = {r.question_id: r for r in responses}

        # Create lookup dictionaries for answer options to avoid lazy loading
        question_ids = [q[0].id for q in all_questions]
        options_result = await db.execute(
            select(AnswerOption)
            .where(AnswerOption.question_id.in_(question_ids))
        )
        all_options = options_result.scalars().all()

        # Group options by question_id for quick lookup
        options_by_question = {}
        for option in all_options:
            if option.question_id not in options_by_question:
                options_by_question[option.question_id] = []
            options_by_question[option.question_id].append(option)

        for question, points in all_questions:
            max_score += points

            # Find the response for this question using the lookup dictionary
            response = response_lookup.get(question.id)

            if response:
                is_correct = False
                points_earned = 0

                # Check answer based on question type
                if question.question_type == QuestionType.MULTIPLE_CHOICE:
                    # Find correct option
                    question_options = options_by_question.get(question.id, [])
                    correct_option = next(
                        (opt for opt in question_options if opt.is_correct),
                        None
                    )
                    if correct_option and response.selected_options:
                        is_correct = str(correct_option.id) in [str(opt) for opt in response.selected_options]

                elif question.question_type == QuestionType.TRUE_FALSE:
                    question_options = options_by_question.get(question.id, [])
                    correct_option = next(
                        (opt for opt in question_options if opt.is_correct),
                        None
                    )
                    if correct_option and response.selected_options:
                        is_correct = str(correct_option.id) in [str(opt) for opt in response.selected_options]

                elif question.question_type in [QuestionType.FILL_BLANK, QuestionType.WORD_COMPLETION, QuestionType.TEXT_ENTRY]:
                    # For fill-in-blank, check if answer matches correct option text or correct_answer field
                    correct_answer = question.correct_answer
                    if not correct_answer:
                        question_options = options_by_question.get(question.id, [])
                        correct_option = next(
                            (opt for opt in question_options if opt.is_correct),
                            None
                        )
                        if correct_option:
                            correct_answer = correct_option.option_text

                    if correct_answer and response.answer_text:
                        case_sensitive = getattr(question, 'case_sensitive', False)
                        if case_sensitive:
                            is_correct = response.answer_text.strip() == correct_answer.strip()
                        else:
                            is_correct = response.answer_text.strip().lower() == correct_answer.strip().lower()

                elif question.question_type in [QuestionType.SYNONYM_COMPLETION, QuestionType.ANTONYM_COMPLETION]:
                    # For synonym/antonym completion (letter boxes), check against correct_answer
                    correct_answer = question.correct_answer
                    if not correct_answer and question.letter_template:
                        correct_answer = question.letter_template.get("answer")

                    if correct_answer and response.answer_text:
                        case_sensitive = getattr(question, 'case_sensitive', False)
                        if case_sensitive:
                            is_correct = response.answer_text.strip() == correct_answer.strip()
                        else:
                            is_correct = response.answer_text.strip().lower() == correct_answer.strip().lower()

                elif question.question_type in [QuestionType.SYNONYM_SELECTION, QuestionType.ANTONYM_SELECTION,
                                                  QuestionType.ODD_ONE_OUT, QuestionType.DOUBLE_MEANING_MATCH,
                                                  QuestionType.READING_COMPREHENSION]:
                    # These all use multiple choice style - check selected option
                    question_options = options_by_question.get(question.id, [])
                    correct_option = next(
                        (opt for opt in question_options if opt.is_correct),
                        None
                    )
                    if correct_option and response.selected_options:
                        is_correct = str(correct_option.id) in [str(opt) for opt in response.selected_options]

                elif question.question_type == QuestionType.SENTENCE_REARRANGEMENT:
                    # Check if the identified "wrong" word matches correct_answer
                    correct_answer = question.correct_answer
                    if correct_answer and response.answer_text:
                        case_sensitive = getattr(question, 'case_sensitive', False)
                        if case_sensitive:
                            is_correct = response.answer_text.strip() == correct_answer.strip()
                        else:
                            is_correct = response.answer_text.strip().lower() == correct_answer.strip().lower()

                elif question.question_type in [QuestionType.CLOZE_SELECT, QuestionType.WORD_BANK_CLOZE,
                                                  QuestionType.FILL_MISSING_LETTERS]:
                    # For multiple blank questions, check each answer
                    correct_answers = question.correct_answers
                    if correct_answers:
                        user_answers = response.fill_in_answers or response.dropdown_selections or {}
                        all_correct = True
                        total_blanks = len(correct_answers)
                        correct_count = 0

                        for blank_id, expected in correct_answers.items():
                            user_answer = user_answers.get(str(blank_id), "")
                            case_sensitive = getattr(question, 'case_sensitive', False)

                            if case_sensitive:
                                if str(user_answer).strip() == str(expected).strip():
                                    correct_count += 1
                                else:
                                    all_correct = False
                            else:
                                if str(user_answer).strip().lower() == str(expected).strip().lower():
                                    correct_count += 1
                                else:
                                    all_correct = False

                        # Check if partial credit is allowed
                        allow_partial = getattr(question, 'allow_partial_credit', False)
                        if allow_partial and total_blanks > 0:
                            points_earned = int(points * (correct_count / total_blanks))
                            is_correct = all_correct
                        else:
                            is_correct = all_correct

                elif question.question_type == QuestionType.CLOZE_TEST and response.dropdown_selections:
                    # For cloze tests, check each dropdown selection
                    all_correct = True
                    for blank_id, selected_option_id in response.dropdown_selections.items():
                        question_options = options_by_question.get(question.id, [])
                        correct_option = next(
                            (opt for opt in question_options
                             if opt.is_correct and opt.option_group == blank_id),
                            None
                        )
                        if not correct_option or str(correct_option.id) != str(selected_option_id):
                            all_correct = False
                            break
                    is_correct = all_correct

                if is_correct:
                    points_earned = points
                    total_score += points_earned

                # Update response with scoring
                response.is_correct = is_correct
                response.points_earned = points_earned

                question_scores[str(question.id)] = {
                    "points_earned": points_earned,
                    "max_points": points,
                    "is_correct": is_correct
                }
            else:
                question_scores[str(question.id)] = {
                    "points_earned": 0,
                    "max_points": points,
                    "is_correct": False
                }

        # Update attempt status
        now = datetime.now(timezone.utc)
        attempt.submitted_at = now
        time_taken_seconds = int((now - attempt_started_at).total_seconds())
        attempt.time_taken = time_taken_seconds

        if submission_data.submission_type == "auto_submit":
            attempt.status = AttemptStatus.AUTO_SUBMITTED
        else:
            attempt.status = AttemptStatus.SUBMITTED

        # Calculate percentage and determine pass/fail
        percentage = (total_score / max_score * 100) if max_score > 0 else 0
        status = ResultStatus.PASS if attempt_test_pass_mark and percentage >= attempt_test_pass_mark else ResultStatus.FAIL

        # Create test result
        result = TestResult(
            attempt_id=attempt_id,
            student_id=student_id,
            test_id=test_id,
            total_score=total_score,
            max_score=max_score,
            percentage=Decimal(str(round(percentage, 2))),
            grade=TestSessionService._calculate_grade(percentage),
            time_taken=time_taken_seconds,
            submitted_at=now,
            status=status,
            question_scores=question_scores,
            analytics_data={
                "submission_type": submission_data.submission_type,
                "questions_answered": len([s for s in question_scores.values() if s["points_earned"] > 0]),
                "questions_skipped": len([s for s in question_scores.values() if s["points_earned"] == 0]),
                "time_per_question": time_taken_seconds / len(question_scores) if question_scores else 0
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
            time_taken=time_taken_seconds,
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
        """Get test result details with question analysis"""
        from app.schemas.test import QuestionAnalysisItem

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

        if not result:
            return None

        # Get question_scores which contains the authoritative list of question IDs
        # that were actually used in this test attempt
        question_scores = result.question_scores or {}
        question_ids_from_scores = [UUID(qid) for qid in question_scores.keys()]

        # Get question responses for this attempt
        responses_result = await db.execute(
            select(QuestionResponse)
            .options(selectinload(QuestionResponse.question).selectinload(Question.answer_options))
            .where(QuestionResponse.attempt_id == result.attempt_id)
        )
        responses = responses_result.scalars().all()

        # Create a lookup dictionary for responses by question_id
        response_lookup = {r.question_id: r for r in responses}

        # Collect all question IDs we need to load (from both sources)
        all_question_ids = set(question_ids_from_scores)
        all_question_ids.update(r.question_id for r in responses)

        # Load all questions by ID directly (this handles cases where question IDs
        # in responses/scores differ from what's in TestQuestion/TestQuestionSet)
        questions_result = await db.execute(
            select(Question)
            .options(selectinload(Question.answer_options))
            .where(Question.id.in_(all_question_ids))
        )
        questions_by_id = {q.id: q for q in questions_result.scalars().all()}

        # Build all_questions list from question_scores (authoritative order)
        all_questions = []
        for idx, (qid_str, score_data) in enumerate(question_scores.items(), start=1):
            qid = UUID(qid_str)
            question = questions_by_id.get(qid)
            if question:
                all_questions.append({
                    "question": question,
                    "order_number": idx,
                    "points": score_data.get("max_points", question.points or 1)
                })

        # Create a fallback lookup from question_scores stored in TestResult
        # This ensures we have scoring data even if QuestionResponse records aren't found
        question_scores_lookup = result.question_scores or {}

        # Build question analysis list for ALL questions
        question_analysis = []

        for q_data in sorted(all_questions, key=lambda x: x["order_number"]):
            question = q_data["question"]
            order_number = q_data["order_number"]
            max_points = q_data["points"] or question.points or 1

            if not question:
                continue

            # Check if student answered this question
            response = response_lookup.get(question.id)

            # Also check question_scores for fallback data (uses string key)
            score_data = question_scores_lookup.get(str(question.id), {})

            # Determine student's answer
            student_answer = None
            is_correct = False
            points_earned = 0
            time_spent = None

            if response:
                if response.answer_text:
                    student_answer = response.answer_text
                elif response.selected_options and question.answer_options:
                    selected_option = next(
                        (opt for opt in question.answer_options if opt.id in response.selected_options),
                        None
                    )
                    if selected_option:
                        student_answer = selected_option.option_text
                elif response.dropdown_selections:
                    # For cloze/dropdown questions, format the selections
                    student_answer = ", ".join([str(v) for v in response.dropdown_selections.values()])
                elif response.fill_in_answers:
                    # For fill-in-blank questions
                    student_answer = ", ".join([str(v) for v in response.fill_in_answers.values()])

                is_correct = response.is_correct or False
                points_earned = response.points_earned or 0
                time_spent = response.time_spent
            elif score_data:
                # Fallback to question_scores data when QuestionResponse not found
                # This happens when responses were processed during submission but
                # the QuestionResponse query returned empty results
                is_correct = score_data.get("is_correct", False)
                points_earned = score_data.get("points_earned", 0)
                # We can infer if student answered based on points_earned or is_correct
                if is_correct or points_earned > 0:
                    student_answer = "(Answer recorded)"  # Placeholder when actual answer not available

            # Determine correct answer - for multiple choice, use the option text not the letter
            correct_answer = None
            if question.answer_options:
                # For questions with answer options, get the text of the correct option
                correct_option = next(
                    (opt for opt in question.answer_options if opt.is_correct),
                    None
                )
                if correct_option:
                    correct_answer = correct_option.option_text

            # Fall back to question.correct_answer only if no answer options
            if not correct_answer:
                correct_answer = question.correct_answer

            analysis_item = QuestionAnalysisItem(
                question_number=order_number,
                question_id=question.id,
                question_type=question.question_type.value if question.question_type else "unknown",
                question_text=question.question_text,
                image_url=question.image_url,
                student_answer=student_answer,
                correct_answer=correct_answer,
                is_correct=is_correct,
                points_earned=points_earned,
                max_points=max_points,
                time_spent=time_spent
            )
            question_analysis.append(analysis_item)

        # Build result detail
        result_detail = TestResultDetail(
            id=result.id,
            attempt_id=result.attempt_id,
            student_id=result.student_id,
            test_id=result.test_id,
            total_score=result.total_score,
            max_score=result.max_score,
            percentage=float(result.percentage) if result.percentage else 0.0,
            grade=result.grade,
            time_taken=result.time_taken,
            submitted_at=result.submitted_at,
            status=result.status,
            question_scores=result.question_scores,
            analytics_data=result.analytics_data,
            question_analysis=question_analysis if question_analysis else None,
            created_at=result.created_at,
            test_title=result.test.title if result.test else None,
            test_type=result.test.type.value if result.test and result.test.type else None
        )

        return result_detail

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

        result_details = []
        for r in results.unique().scalars().all():
            result_detail = TestResultDetail(
                id=r.id,
                attempt_id=r.attempt_id,
                student_id=r.student_id,
                test_id=r.test_id,
                total_score=r.total_score,
                max_score=r.max_score,
                percentage=float(r.percentage) if r.percentage else 0.0,
                grade=r.grade,
                time_taken=r.time_taken,
                submitted_at=r.submitted_at,
                status=r.status,
                question_scores=r.question_scores,
                analytics_data=r.analytics_data,
                question_analysis=None,  # Don't include detailed analysis in list view
                created_at=r.created_at,
                test_title=r.test.title if r.test else None,
                test_type=r.test.type.value if r.test and r.test.type else None
            )
            result_details.append(result_detail)

        return result_details

    @staticmethod
    async def check_and_auto_submit_expired_tests(db: AsyncSession):
        """Check for expired test attempts and auto-submit them"""

        # Find all in-progress attempts that have exceeded their time limit
        now = datetime.now(timezone.utc)

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