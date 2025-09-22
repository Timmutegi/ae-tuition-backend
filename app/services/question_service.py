from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from uuid import UUID

from app.models import (
    Question, ReadingPassage, AnswerOption, User,
    QuestionType, QuestionFormat, Difficulty, OptionType
)
from app.schemas.question import (
    QuestionCreate, QuestionUpdate, QuestionFilters, QuestionResponse,
    ReadingPassageCreate, ReadingPassageUpdate, ReadingPassageResponse, PassageFilters,
    AnswerOptionCreate, AnswerOptionResponse, QuestionBankStats
)


class QuestionService:
    @staticmethod
    async def create_question(db: AsyncSession, question_data: QuestionCreate, creator_id: UUID) -> QuestionResponse:
        """Create a new question with answer options"""
        question = Question(
            **question_data.model_dump(exclude={'answer_options'}),
            created_by=creator_id
        )
        db.add(question)
        await db.flush()

        # Add answer options and collect response data
        answer_option_responses = []
        for option_data in question_data.answer_options:
            option = AnswerOption(
                question_id=question.id,
                **option_data.model_dump()
            )
            db.add(option)

        await db.commit()
        await db.refresh(question)

        # Query the answer options to get their IDs and timestamps
        from sqlalchemy import select
        result = await db.execute(
            select(AnswerOption).where(AnswerOption.question_id == question.id)
        )
        answer_options = result.scalars().all()

        # Convert to Pydantic schema manually
        answer_option_responses = []
        for option in answer_options:
            answer_option_responses.append(AnswerOptionResponse(
                id=option.id,
                question_id=option.question_id,
                option_text=option.option_text,
                option_type=option.option_type,
                option_group=option.option_group,
                is_correct=option.is_correct,
                order_number=option.order_number,
                image_url=option.image_url,
                s3_key=option.s3_key,
                pattern_data=option.pattern_data,
                created_at=option.created_at
            ))

        return QuestionResponse(
            id=question.id,
            question_text=question.question_text,
            question_type=question.question_type,
            question_format=question.question_format,
            passage_id=question.passage_id,
            passage_reference_lines=question.passage_reference_lines,
            subject=question.subject,
            topic=question.topic,
            difficulty=question.difficulty,
            points=question.points,
            image_url=question.image_url,
            s3_key=question.s3_key,
            explanation=question.explanation,
            instruction_text=question.instruction_text,
            pattern_sequence=question.pattern_sequence,
            tags=question.tags,
            created_by=question.created_by,
            created_at=question.created_at,
            updated_at=question.updated_at,
            answer_options=answer_option_responses
        )

    @staticmethod
    async def get_question_by_id(db: AsyncSession, question_id: UUID) -> Optional[dict]:
        """Get question by ID with all details"""
        result = await db.execute(
            select(Question)
            .options(
                selectinload(Question.answer_options),
                selectinload(Question.passage),
                selectinload(Question.creator)
            )
            .where(Question.id == question_id)
        )
        question = result.scalar_one_or_none()

        if not question:
            return None

        # Convert to Pydantic schema manually
        answer_option_responses = []
        for option in question.answer_options:
            answer_option_responses.append(AnswerOptionResponse(
                id=option.id,
                question_id=option.question_id,
                option_text=option.option_text,
                option_type=option.option_type,
                option_group=option.option_group,
                is_correct=option.is_correct,
                order_number=option.order_number,
                image_url=option.image_url,
                s3_key=option.s3_key,
                pattern_data=option.pattern_data,
                created_at=option.created_at
            ))

        question_response = QuestionResponse(
            id=question.id,
            question_text=question.question_text,
            question_type=question.question_type,
            question_format=question.question_format,
            passage_id=question.passage_id,
            passage_reference_lines=question.passage_reference_lines,
            subject=question.subject,
            topic=question.topic,
            difficulty=question.difficulty,
            points=question.points,
            image_url=question.image_url,
            s3_key=question.s3_key,
            explanation=question.explanation,
            instruction_text=question.instruction_text,
            pattern_sequence=question.pattern_sequence,
            tags=question.tags,
            created_by=question.created_by,
            created_at=question.created_at,
            updated_at=question.updated_at,
            answer_options=answer_option_responses
        )

        # Add passage if present
        if question.passage:
            from app.schemas.question import QuestionWithPassage
            passage_response = ReadingPassageResponse(
                id=question.passage.id,
                title=question.passage.title,
                content=question.passage.content,
                word_count=question.passage.word_count,
                reading_level=question.passage.reading_level,
                source=question.passage.source,
                author=question.passage.author,
                genre=question.passage.genre,
                subject=question.passage.subject,
                created_by=question.passage.created_by,
                created_at=question.passage.created_at,
                updated_at=question.passage.updated_at
            )
            return QuestionWithPassage(
                **question_response.model_dump(),
                passage=passage_response
            )

        return question_response

    @staticmethod
    async def get_questions(db: AsyncSession, filters: QuestionFilters) -> Dict[str, Any]:
        """Get questions with filtering and pagination"""
        query = select(Question).options(
            selectinload(Question.answer_options),
            selectinload(Question.passage),
            selectinload(Question.creator)
        )

        # Apply filters
        if filters.question_type:
            query = query.where(Question.question_type == filters.question_type)
        if filters.question_format:
            query = query.where(Question.question_format == filters.question_format)
        if filters.subject:
            query = query.where(Question.subject.ilike(f"%{filters.subject}%"))
        if filters.difficulty:
            query = query.where(Question.difficulty == filters.difficulty)
        if filters.passage_id:
            query = query.where(Question.passage_id == filters.passage_id)
        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.where(
                or_(
                    Question.question_text.ilike(search_pattern),
                    Question.topic.ilike(search_pattern),
                    Question.subject.ilike(search_pattern)
                )
            )
        if filters.tags:
            for tag in filters.tags:
                query = query.where(Question.tags.any(tag))

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (filters.page - 1) * filters.limit
        query = query.offset(offset).limit(filters.limit).order_by(Question.created_at.desc())

        result = await db.execute(query)
        questions = result.scalars().all()

        # Convert SQLAlchemy models to Pydantic schemas manually
        question_responses = []
        for question in questions:
            # Convert answer options
            answer_option_responses = []
            for option in question.answer_options:
                answer_option_responses.append(AnswerOptionResponse(
                    id=option.id,
                    question_id=option.question_id,
                    option_text=option.option_text,
                    option_type=option.option_type,
                    option_group=option.option_group,
                    is_correct=option.is_correct,
                    order_number=option.order_number,
                    image_url=option.image_url,
                    s3_key=option.s3_key,
                    pattern_data=option.pattern_data,
                    created_at=option.created_at
                ))

            question_responses.append(QuestionResponse(
                id=question.id,
                question_text=question.question_text,
                question_type=question.question_type,
                question_format=question.question_format,
                passage_id=question.passage_id,
                passage_reference_lines=question.passage_reference_lines,
                subject=question.subject,
                topic=question.topic,
                difficulty=question.difficulty,
                points=question.points,
                image_url=question.image_url,
                s3_key=question.s3_key,
                explanation=question.explanation,
                instruction_text=question.instruction_text,
                pattern_sequence=question.pattern_sequence,
                tags=question.tags,
                created_by=question.created_by,
                created_at=question.created_at,
                updated_at=question.updated_at,
                answer_options=answer_option_responses
            ))

        return {
            "questions": question_responses,
            "total": total,
            "page": filters.page,
            "limit": filters.limit,
            "total_pages": (total + filters.limit - 1) // filters.limit
        }

    @staticmethod
    async def update_question(db: AsyncSession, question_id: UUID, question_data: QuestionUpdate, user_id: UUID) -> Optional[QuestionResponse]:
        """Update question (only if user is creator)"""
        # Get the question first
        result = await db.execute(
            select(Question)
            .options(selectinload(Question.answer_options))
            .where(Question.id == question_id)
        )
        question = result.scalar_one_or_none()

        if not question or question.created_by != user_id:
            return None

        update_data = question_data.model_dump(exclude_unset=True)
        if update_data:
            for field, value in update_data.items():
                setattr(question, field, value)

            await db.commit()
            await db.refresh(question)

            # Reload with relationships
            result = await db.execute(
                select(Question)
                .options(selectinload(Question.answer_options))
                .where(Question.id == question_id)
            )
            question = result.scalar_one_or_none()

        # Convert to Pydantic schema
        answer_option_responses = []
        for option in question.answer_options:
            answer_option_responses.append(AnswerOptionResponse(
                id=option.id,
                question_id=option.question_id,
                option_text=option.option_text,
                option_type=option.option_type,
                option_group=option.option_group,
                is_correct=option.is_correct,
                order_number=option.order_number,
                image_url=option.image_url,
                s3_key=option.s3_key,
                pattern_data=option.pattern_data,
                created_at=option.created_at
            ))

        return QuestionResponse(
            id=question.id,
            question_text=question.question_text,
            question_type=question.question_type,
            question_format=question.question_format,
            passage_id=question.passage_id,
            passage_reference_lines=question.passage_reference_lines,
            subject=question.subject,
            topic=question.topic,
            difficulty=question.difficulty,
            points=question.points,
            image_url=question.image_url,
            s3_key=question.s3_key,
            explanation=question.explanation,
            instruction_text=question.instruction_text,
            pattern_sequence=question.pattern_sequence,
            tags=question.tags,
            created_by=question.created_by,
            created_at=question.created_at,
            updated_at=question.updated_at,
            answer_options=answer_option_responses
        )

    @staticmethod
    async def delete_question(db: AsyncSession, question_id: UUID, user_id: UUID) -> bool:
        """Delete question (only if user is creator and not used in tests)"""
        result = await db.execute(
            select(Question).where(Question.id == question_id)
        )
        question = result.scalar_one_or_none()

        if not question or question.created_by != user_id:
            return False

        # Check if question is used in any tests
        from app.models.test import TestQuestion
        usage_result = await db.execute(
            select(func.count(TestQuestion.id)).where(TestQuestion.question_id == question_id)
        )
        usage_count = usage_result.scalar()

        if usage_count > 0:
            raise ValueError("Cannot delete question that is used in tests")

        await db.delete(question)
        await db.commit()
        return True

    @staticmethod
    async def create_reading_passage(db: AsyncSession, passage_data: ReadingPassageCreate, creator_id: UUID) -> ReadingPassageResponse:
        """Create a new reading passage"""
        passage = ReadingPassage(
            **passage_data.model_dump(),
            created_by=creator_id
        )
        db.add(passage)
        await db.commit()
        await db.refresh(passage)

        return ReadingPassageResponse(
            id=passage.id,
            title=passage.title,
            content=passage.content,
            word_count=passage.word_count,
            reading_level=passage.reading_level,
            source=passage.source,
            author=passage.author,
            genre=passage.genre,
            subject=passage.subject,
            created_by=passage.created_by,
            created_at=passage.created_at,
            updated_at=passage.updated_at
        )

    @staticmethod
    async def get_reading_passage_by_id(db: AsyncSession, passage_id: UUID) -> Optional[ReadingPassageResponse]:
        """Get reading passage by ID"""
        result = await db.execute(
            select(ReadingPassage)
            .options(
                selectinload(ReadingPassage.questions),
                selectinload(ReadingPassage.creator)
            )
            .where(ReadingPassage.id == passage_id)
        )
        passage = result.scalar_one_or_none()

        if not passage:
            return None

        return ReadingPassageResponse(
            id=passage.id,
            title=passage.title,
            content=passage.content,
            word_count=passage.word_count,
            reading_level=passage.reading_level,
            source=passage.source,
            author=passage.author,
            genre=passage.genre,
            subject=passage.subject,
            created_by=passage.created_by,
            created_at=passage.created_at,
            updated_at=passage.updated_at
        )

    @staticmethod
    async def get_reading_passages(db: AsyncSession, filters: PassageFilters) -> Dict[str, Any]:
        """Get reading passages with filtering and pagination"""
        query = select(ReadingPassage).options(selectinload(ReadingPassage.creator))

        # Apply filters
        if filters.subject:
            query = query.where(ReadingPassage.subject.ilike(f"%{filters.subject}%"))
        if filters.genre:
            query = query.where(ReadingPassage.genre.ilike(f"%{filters.genre}%"))
        if filters.reading_level:
            query = query.where(ReadingPassage.reading_level.ilike(f"%{filters.reading_level}%"))
        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.where(
                or_(
                    ReadingPassage.title.ilike(search_pattern),
                    ReadingPassage.content.ilike(search_pattern),
                    ReadingPassage.author.ilike(search_pattern)
                )
            )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (filters.page - 1) * filters.limit
        query = query.offset(offset).limit(filters.limit).order_by(ReadingPassage.created_at.desc())

        result = await db.execute(query)
        passages = result.scalars().all()

        # Convert SQLAlchemy models to Pydantic schemas manually
        passage_responses = []
        for passage in passages:
            passage_responses.append(ReadingPassageResponse(
                id=passage.id,
                title=passage.title,
                content=passage.content,
                word_count=passage.word_count,
                reading_level=passage.reading_level,
                source=passage.source,
                author=passage.author,
                genre=passage.genre,
                subject=passage.subject,
                created_by=passage.created_by,
                created_at=passage.created_at,
                updated_at=passage.updated_at
            ))

        return {
            "passages": passage_responses,
            "total": total,
            "page": filters.page,
            "limit": filters.limit,
            "total_pages": (total + filters.limit - 1) // filters.limit
        }

    @staticmethod
    async def update_reading_passage(db: AsyncSession, passage_id: UUID, passage_data: ReadingPassageUpdate, user_id: UUID) -> Optional[ReadingPassageResponse]:
        """Update reading passage (only if user is creator)"""
        result = await db.execute(
            select(ReadingPassage).where(ReadingPassage.id == passage_id)
        )
        passage = result.scalar_one_or_none()

        if not passage or passage.created_by != user_id:
            return None

        update_data = passage_data.model_dump(exclude_unset=True)
        if update_data:
            for field, value in update_data.items():
                setattr(passage, field, value)

            await db.commit()
            await db.refresh(passage)

        return ReadingPassageResponse(
            id=passage.id,
            title=passage.title,
            content=passage.content,
            word_count=passage.word_count,
            reading_level=passage.reading_level,
            source=passage.source,
            author=passage.author,
            genre=passage.genre,
            subject=passage.subject,
            created_by=passage.created_by,
            created_at=passage.created_at,
            updated_at=passage.updated_at
        )

    @staticmethod
    async def delete_reading_passage(db: AsyncSession, passage_id: UUID, user_id: UUID) -> bool:
        """Delete reading passage (only if user is creator and not used)"""
        result = await db.execute(
            select(ReadingPassage)
            .options(selectinload(ReadingPassage.questions))
            .where(ReadingPassage.id == passage_id)
        )
        passage = result.scalar_one_or_none()

        if not passage or passage.created_by != user_id:
            return False

        # Check if passage has questions
        if passage.questions:
            raise ValueError("Cannot delete passage that has questions")

        await db.delete(passage)
        await db.commit()
        return True

    @staticmethod
    async def add_answer_option(db: AsyncSession, question_id: UUID, option_data: AnswerOptionCreate, user_id: UUID) -> Optional[AnswerOptionResponse]:
        """Add answer option to a question"""
        # Check if question exists and user has permission
        result = await db.execute(
            select(Question).where(Question.id == question_id)
        )
        question = result.scalar_one_or_none()

        if not question or question.created_by != user_id:
            return None

        option = AnswerOption(
            question_id=question_id,
            **option_data.model_dump()
        )
        db.add(option)
        await db.commit()
        await db.refresh(option)

        return AnswerOptionResponse(
            id=option.id,
            question_id=option.question_id,
            option_text=option.option_text,
            option_type=option.option_type,
            option_group=option.option_group,
            is_correct=option.is_correct,
            order_number=option.order_number,
            image_url=option.image_url,
            s3_key=option.s3_key,
            pattern_data=option.pattern_data,
            created_at=option.created_at
        )

    @staticmethod
    async def remove_answer_option(db: AsyncSession, option_id: UUID, user_id: UUID) -> bool:
        """Remove answer option"""
        result = await db.execute(
            select(AnswerOption)
            .join(Question)
            .where(and_(AnswerOption.id == option_id, Question.created_by == user_id))
        )
        option = result.scalar_one_or_none()

        if not option:
            return False

        await db.delete(option)
        await db.commit()
        return True

    @staticmethod
    async def get_questions_by_passage(db: AsyncSession, passage_id: UUID) -> List[QuestionResponse]:
        """Get all questions for a specific passage"""
        result = await db.execute(
            select(Question)
            .options(selectinload(Question.answer_options))
            .where(Question.passage_id == passage_id)
            .order_by(Question.created_at)
        )
        questions = result.scalars().all()

        question_responses = []
        for question in questions:
            # Convert answer options
            answer_option_responses = []
            for option in question.answer_options:
                answer_option_responses.append(AnswerOptionResponse(
                    id=option.id,
                    question_id=option.question_id,
                    option_text=option.option_text,
                    option_type=option.option_type,
                    option_group=option.option_group,
                    is_correct=option.is_correct,
                    order_number=option.order_number,
                    image_url=option.image_url,
                    s3_key=option.s3_key,
                    pattern_data=option.pattern_data,
                    created_at=option.created_at
                ))

            question_responses.append(QuestionResponse(
                id=question.id,
                question_text=question.question_text,
                question_type=question.question_type,
                question_format=question.question_format,
                passage_id=question.passage_id,
                passage_reference_lines=question.passage_reference_lines,
                subject=question.subject,
                topic=question.topic,
                difficulty=question.difficulty,
                points=question.points,
                image_url=question.image_url,
                s3_key=question.s3_key,
                explanation=question.explanation,
                instruction_text=question.instruction_text,
                pattern_sequence=question.pattern_sequence,
                tags=question.tags,
                created_by=question.created_by,
                created_at=question.created_at,
                updated_at=question.updated_at,
                answer_options=answer_option_responses
            ))

        return question_responses

    @staticmethod
    async def get_question_bank_stats(db: AsyncSession, user_id: Optional[UUID] = None) -> QuestionBankStats:
        """Get question bank statistics"""
        base_query = select(Question)
        if user_id:
            base_query = base_query.where(Question.created_by == user_id)

        # Total questions
        total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
        total_questions = total_result.scalar()

        # Questions by type
        type_query = select(Question.question_type, func.count()).group_by(Question.question_type)
        if user_id:
            type_query = type_query.where(Question.created_by == user_id)
        type_result = await db.execute(type_query)
        questions_by_type = {str(qtype.value): count for qtype, count in type_result.fetchall()}

        # Questions by subject
        subject_query = select(Question.subject, func.count()).group_by(Question.subject).where(Question.subject.isnot(None))
        if user_id:
            subject_query = subject_query.where(Question.created_by == user_id)
        subject_result = await db.execute(subject_query)
        questions_by_subject = dict(subject_result.fetchall())

        # Questions by difficulty
        difficulty_query = select(Question.difficulty, func.count()).group_by(Question.difficulty)
        if user_id:
            difficulty_query = difficulty_query.where(Question.created_by == user_id)
        difficulty_result = await db.execute(difficulty_query)
        questions_by_difficulty = {str(diff.value): count for diff, count in difficulty_result.fetchall()}

        # Passage stats
        passage_query = select(func.count()).select_from(ReadingPassage)
        if user_id:
            passage_query = passage_query.where(ReadingPassage.created_by == user_id)
        total_passages_result = await db.execute(passage_query)
        total_passages = total_passages_result.scalar()

        # Passages by subject
        passage_subject_query = select(ReadingPassage.subject, func.count()).group_by(ReadingPassage.subject).where(ReadingPassage.subject.isnot(None))
        if user_id:
            passage_subject_query = passage_subject_query.where(ReadingPassage.created_by == user_id)
        passage_subject_result = await db.execute(passage_subject_query)
        passages_by_subject = dict(passage_subject_result.fetchall())

        return QuestionBankStats(
            total_questions=total_questions,
            questions_by_type=questions_by_type,
            questions_by_subject=questions_by_subject,
            questions_by_difficulty=questions_by_difficulty,
            total_passages=total_passages,
            passages_by_subject=passages_by_subject
        )