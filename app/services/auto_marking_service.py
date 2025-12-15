"""
Auto-Marking Service for AE Tuition

This service handles automatic marking of test submissions based on question types
and correct answers specified by admins when creating questions.
"""

from typing import Dict, List, Optional, Any, Tuple
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import re

from app.models.question import Question, QuestionType, AnswerOption, QuestionResponse
from app.models.test import TestAttempt, TestQuestion


class AutoMarkingService:
    """Service for automatically marking test responses."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def mark_test_attempt(self, attempt_id: UUID) -> Dict[str, Any]:
        """
        Mark all responses in a test attempt and calculate the final score.

        Args:
            attempt_id: The ID of the test attempt to mark

        Returns:
            Dictionary containing marking results and score
        """
        # Get the test attempt with responses
        result = await self.db.execute(
            select(TestAttempt)
            .options(selectinload(TestAttempt.question_responses))
            .where(TestAttempt.id == attempt_id)
        )
        attempt = result.scalar_one_or_none()

        if not attempt:
            raise ValueError(f"Test attempt {attempt_id} not found")

        total_points = 0
        earned_points = 0
        marking_results = []

        for response in attempt.question_responses:
            # Get the question with answer options
            q_result = await self.db.execute(
                select(Question)
                .options(selectinload(Question.answer_options))
                .where(Question.id == response.question_id)
            )
            question = q_result.scalar_one_or_none()

            if not question:
                continue

            total_points += question.points

            # Mark the response based on question type
            is_correct, points_earned, partial_score = await self._mark_response(
                question, response
            )

            # Update the response
            response.is_correct = is_correct
            response.points_earned = points_earned
            response.partial_score = partial_score

            earned_points += points_earned

            marking_results.append({
                "question_id": str(question.id),
                "question_type": question.question_type.value,
                "is_correct": is_correct,
                "points_earned": points_earned,
                "max_points": question.points,
                "partial_score": float(partial_score) if partial_score else None
            })

        # Calculate percentage
        percentage = (earned_points / total_points * 100) if total_points > 0 else 0

        # Update the attempt
        attempt.score = earned_points
        attempt.percentage = round(percentage, 2)

        await self.db.commit()

        return {
            "attempt_id": str(attempt_id),
            "total_points": total_points,
            "earned_points": earned_points,
            "percentage": round(percentage, 2),
            "marking_results": marking_results
        }

    async def _mark_response(
        self,
        question: Question,
        response: QuestionResponse
    ) -> Tuple[bool, int, Optional[float]]:
        """
        Mark a single question response.

        Returns:
            Tuple of (is_correct, points_earned, partial_score)
        """
        question_type = question.question_type

        # Route to appropriate marking method based on question type
        marking_methods = {
            QuestionType.MULTIPLE_CHOICE: self._mark_multiple_choice,
            QuestionType.TRUE_FALSE: self._mark_multiple_choice,
            QuestionType.READING_COMPREHENSION: self._mark_multiple_choice,
            QuestionType.SYNONYM_SELECTION: self._mark_multiple_choice,
            QuestionType.ANTONYM_SELECTION: self._mark_multiple_choice,
            QuestionType.ODD_ONE_OUT: self._mark_multiple_choice,
            QuestionType.DOUBLE_MEANING_MATCH: self._mark_multiple_choice,
            QuestionType.FILL_BLANK: self._mark_text_entry,
            QuestionType.TEXT_ENTRY: self._mark_text_entry,
            QuestionType.SYNONYM_COMPLETION: self._mark_letter_completion,
            QuestionType.ANTONYM_COMPLETION: self._mark_letter_completion,
            QuestionType.FILL_MISSING_LETTERS: self._mark_fill_missing_letters,
            QuestionType.CLOZE_SELECT: self._mark_cloze_select,
            QuestionType.WORD_BANK_CLOZE: self._mark_word_bank_cloze,
            QuestionType.SENTENCE_REARRANGEMENT: self._mark_sentence_rearrangement,
            QuestionType.DROPDOWN_SELECT: self._mark_dropdown_select,
            QuestionType.CLOZE_TEST: self._mark_cloze_test,
            QuestionType.WORD_COMPLETION: self._mark_letter_completion,
            QuestionType.SENTENCE_COMPLETION: self._mark_text_entry,
            QuestionType.PATTERN_RECOGNITION: self._mark_pattern_recognition,
        }

        marking_method = marking_methods.get(question_type)

        if marking_method:
            return await marking_method(question, response)

        # Default: no auto-marking, return as incorrect with 0 points
        return False, 0, None

    async def _mark_multiple_choice(
        self,
        question: Question,
        response: QuestionResponse
    ) -> Tuple[bool, int, Optional[float]]:
        """Mark multiple choice questions (including variants like synonym/antonym selection)."""
        if not response.selected_options:
            return False, 0, None

        # Get correct answer options
        correct_options = [opt for opt in question.answer_options if opt.is_correct]
        correct_option_ids = {opt.id for opt in correct_options}

        # Check if selected options match correct options
        selected_ids = set(response.selected_options)

        if selected_ids == correct_option_ids:
            return True, question.points, 1.0

        # Partial credit if enabled
        if question.allow_partial_credit and correct_option_ids:
            correct_selected = len(selected_ids & correct_option_ids)
            total_correct = len(correct_option_ids)
            partial = correct_selected / total_correct
            points = int(question.points * partial)
            return False, points, partial

        return False, 0, 0.0

    async def _mark_text_entry(
        self,
        question: Question,
        response: QuestionResponse
    ) -> Tuple[bool, int, Optional[float]]:
        """Mark free text entry questions."""
        if not response.answer_text:
            return False, 0, None

        correct_answer = question.correct_answer
        if not correct_answer:
            # Check answer options for correct answer
            correct_options = [opt for opt in question.answer_options if opt.is_correct]
            if correct_options:
                correct_answer = correct_options[0].option_text

        if not correct_answer:
            return False, 0, None

        user_answer = response.answer_text.strip()
        expected = correct_answer.strip()

        if question.case_sensitive:
            is_correct = user_answer == expected
        else:
            is_correct = user_answer.lower() == expected.lower()

        return is_correct, question.points if is_correct else 0, 1.0 if is_correct else 0.0

    async def _mark_letter_completion(
        self,
        question: Question,
        response: QuestionResponse
    ) -> Tuple[bool, int, Optional[float]]:
        """
        Mark synonym/antonym completion questions with letter boxes.

        Example: smart -> _n_t_e_l_l_i_g_e_n_t (answer: intelligent)
        """
        if not response.answer_text:
            return False, 0, None

        correct_answer = question.correct_answer

        # Try to get from letter_template if not directly set
        if not correct_answer and question.letter_template:
            correct_answer = question.letter_template.get("answer")

        if not correct_answer:
            return False, 0, None

        user_answer = response.answer_text.strip()
        expected = correct_answer.strip()

        if question.case_sensitive:
            is_correct = user_answer == expected
        else:
            is_correct = user_answer.lower() == expected.lower()

        return is_correct, question.points if is_correct else 0, 1.0 if is_correct else 0.0

    async def _mark_fill_missing_letters(
        self,
        question: Question,
        response: QuestionResponse
    ) -> Tuple[bool, int, Optional[float]]:
        """
        Mark fill-in-the-missing-letters questions in passages.

        Response format: {"11": "vessel", "12": "structures", ...}
        Correct answers format: {"11": "vessel", "12": "structures", ...}
        """
        if not response.fill_in_answers:
            return False, 0, None

        correct_answers = question.correct_answers
        if not correct_answers:
            return False, 0, None

        total_blanks = len(correct_answers)
        correct_count = 0

        for blank_id, expected in correct_answers.items():
            user_answer = response.fill_in_answers.get(str(blank_id), "")

            if question.case_sensitive:
                if user_answer.strip() == expected.strip():
                    correct_count += 1
            else:
                if user_answer.strip().lower() == expected.strip().lower():
                    correct_count += 1

        partial = correct_count / total_blanks if total_blanks > 0 else 0

        if question.allow_partial_credit:
            points = int(question.points * partial)
            return correct_count == total_blanks, points, partial
        else:
            is_correct = correct_count == total_blanks
            return is_correct, question.points if is_correct else 0, partial

    async def _mark_cloze_select(
        self,
        question: Question,
        response: QuestionResponse
    ) -> Tuple[bool, int, Optional[float]]:
        """
        Mark cloze questions where students select from word options.

        Example: "There are 11) [roughly/roguishly/roundly] 1,240 species of bat..."
        Response format: {"11": "roughly", "12": "gliding", ...}
        """
        if not response.dropdown_selections:
            return False, 0, None

        correct_answers = question.correct_answers
        if not correct_answers:
            return False, 0, None

        total_blanks = len(correct_answers)
        correct_count = 0

        for blank_id, expected in correct_answers.items():
            user_answer = response.dropdown_selections.get(str(blank_id), "")

            if question.case_sensitive:
                if user_answer.strip() == expected.strip():
                    correct_count += 1
            else:
                if user_answer.strip().lower() == expected.strip().lower():
                    correct_count += 1

        partial = correct_count / total_blanks if total_blanks > 0 else 0

        if question.allow_partial_credit:
            points = int(question.points * partial)
            return correct_count == total_blanks, points, partial
        else:
            is_correct = correct_count == total_blanks
            return is_correct, question.points if is_correct else 0, partial

    async def _mark_word_bank_cloze(
        self,
        question: Question,
        response: QuestionResponse
    ) -> Tuple[bool, int, Optional[float]]:
        """
        Mark cloze questions using a word bank.

        Word bank: ["exceeded", "realms", "monarch", "prime", "state", ...]
        Response format: {"11": "G", "12": "C", ...} or {"11": "reign", "12": "monarch", ...}
        """
        if not response.fill_in_answers:
            return False, 0, None

        correct_answers = question.correct_answers
        if not correct_answers:
            return False, 0, None

        total_blanks = len(correct_answers)
        correct_count = 0

        for blank_id, expected in correct_answers.items():
            user_answer = response.fill_in_answers.get(str(blank_id), "")

            if question.case_sensitive:
                if user_answer.strip() == expected.strip():
                    correct_count += 1
            else:
                if user_answer.strip().lower() == expected.strip().lower():
                    correct_count += 1

        partial = correct_count / total_blanks if total_blanks > 0 else 0

        if question.allow_partial_credit:
            points = int(question.points * partial)
            return correct_count == total_blanks, points, partial
        else:
            is_correct = correct_count == total_blanks
            return is_correct, question.points if is_correct else 0, partial

    async def _mark_sentence_rearrangement(
        self,
        question: Question,
        response: QuestionResponse
    ) -> Tuple[bool, int, Optional[float]]:
        """
        Mark sentence rearrangement questions.

        The student identifies which word doesn't fit in the sentence.
        """
        if not response.answer_text:
            return False, 0, None

        correct_answer = question.correct_answer
        if not correct_answer:
            return False, 0, None

        user_answer = response.answer_text.strip()
        expected = correct_answer.strip()

        if question.case_sensitive:
            is_correct = user_answer == expected
        else:
            is_correct = user_answer.lower() == expected.lower()

        return is_correct, question.points if is_correct else 0, 1.0 if is_correct else 0.0

    async def _mark_dropdown_select(
        self,
        question: Question,
        response: QuestionResponse
    ) -> Tuple[bool, int, Optional[float]]:
        """Mark questions with dropdown selections (similar to cloze_select)."""
        return await self._mark_cloze_select(question, response)

    async def _mark_cloze_test(
        self,
        question: Question,
        response: QuestionResponse
    ) -> Tuple[bool, int, Optional[float]]:
        """Mark general cloze test questions."""
        return await self._mark_fill_missing_letters(question, response)

    async def _mark_pattern_recognition(
        self,
        question: Question,
        response: QuestionResponse
    ) -> Tuple[bool, int, Optional[float]]:
        """Mark pattern recognition questions."""
        if not response.pattern_response:
            return False, 0, None

        # Compare pattern response with expected pattern
        expected = question.pattern_sequence
        if not expected:
            return False, 0, None

        # Simple comparison - can be made more sophisticated
        if response.pattern_response == expected:
            return True, question.points, 1.0

        return False, 0, 0.0


async def mark_test_on_submission(db: AsyncSession, attempt_id: UUID) -> Dict[str, Any]:
    """
    Convenience function to mark a test immediately on submission.

    Args:
        db: Database session
        attempt_id: The test attempt ID

    Returns:
        Marking results dictionary
    """
    service = AutoMarkingService(db)
    return await service.mark_test_attempt(attempt_id)
