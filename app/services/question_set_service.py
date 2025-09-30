from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.orm import selectinload

from app.models import QuestionSet, QuestionSetItem, Question, TestQuestionSet, Test
from app.models.test import TestStatus
from app.schemas.question_set import (
    QuestionSetCreate, QuestionSetUpdate, QuestionSetResponse,
    QuestionSetWithItems, QuestionSetFilters, QuestionSetListResponse,
    TestQuestionSetCreate, AddQuestionsToSetRequest, RemoveQuestionsFromSetRequest,
    ReorderQuestionsInSetRequest
)


class QuestionSetService:

    @staticmethod
    async def create_question_set(
        db: AsyncSession,
        question_set_data: QuestionSetCreate,
        user_id: UUID
    ) -> QuestionSetWithItems:
        """Create a new question set with questions"""

        # Create the question set
        question_set = QuestionSet(
            name=question_set_data.name,
            description=question_set_data.description,
            subject=question_set_data.subject,
            topic=question_set_data.topic,
            grade_level=question_set_data.grade_level,
            metadata_json=question_set_data.metadata_json,
            created_by=user_id
        )

        db.add(question_set)
        await db.flush()

        # Add questions to the set if provided
        total_points = 0
        if question_set_data.question_items:
            for item_data in question_set_data.question_items:
                # Verify question exists
                question = await db.get(Question, item_data.question_id)
                if not question:
                    raise ValueError(f"Question with ID {item_data.question_id} not found")

                # Create question set item
                item = QuestionSetItem(
                    question_set_id=question_set.id,
                    question_id=item_data.question_id,
                    order_number=item_data.order_number,
                    points_override=item_data.points_override
                )
                db.add(item)

                # Calculate total points
                points = item_data.points_override if item_data.points_override else question.points
                total_points += points or 1

        # Update question set totals
        question_set.total_points = total_points
        question_set.question_count = len(question_set_data.question_items)

        await db.commit()
        await db.refresh(question_set)

        # Load relationships for response
        result = await db.execute(
            select(QuestionSet)
            .options(selectinload(QuestionSet.question_set_items).selectinload(QuestionSetItem.question))
            .where(QuestionSet.id == question_set.id)
        )
        question_set = result.scalar_one()

        # Convert to dict and handle Question objects manually
        question_set_dict = {
            "id": question_set.id,
            "name": question_set.name,
            "description": question_set.description,
            "subject": question_set.subject,
            "topic": question_set.topic,
            "grade_level": question_set.grade_level,
            "metadata_json": question_set.metadata_json,
            "total_points": question_set.total_points,
            "question_count": question_set.question_count,
            "is_active": question_set.is_active,
            "created_by": question_set.created_by,
            "created_at": question_set.created_at,
            "updated_at": question_set.updated_at,
            "creator_name": None,
            "question_set_items": []
        }

        # Process question set items
        for item in question_set.question_set_items:
            item_dict = {
                "id": item.id,
                "question_set_id": item.question_set_id,
                "question_id": item.question_id,
                "order_number": item.order_number,
                "points_override": item.points_override,
                "created_at": item.created_at,
                "question": None
            }

            # Convert Question object to dict if present
            if item.question:
                item_dict["question"] = {
                    "id": item.question.id,
                    "question_text": item.question.question_text,
                    "question_type": item.question.question_type.value if item.question.question_type else None,
                    "question_format": item.question.question_format.value if item.question.question_format else None,
                    "subject": item.question.subject,
                    "topic": item.question.topic,
                    "difficulty": item.question.difficulty.value if item.question.difficulty else None,
                    "points": item.question.points,
                    "image_url": item.question.image_url,
                    "s3_key": item.question.s3_key,
                    "explanation": item.question.explanation,
                    "instruction_text": item.question.instruction_text,
                    "pattern_sequence": item.question.pattern_sequence,
                    "tags": item.question.tags,
                    "created_by": item.question.created_by,
                    "created_at": item.question.created_at,
                    "updated_at": item.question.updated_at
                }

            question_set_dict["question_set_items"].append(item_dict)

        return QuestionSetWithItems(**question_set_dict)

    @staticmethod
    async def get_question_sets(
        db: AsyncSession,
        filters: QuestionSetFilters
    ) -> QuestionSetListResponse:
        """Get question sets with filtering and pagination"""

        query = select(QuestionSet)

        # Apply filters
        conditions = []

        if filters.subject:
            conditions.append(QuestionSet.subject == filters.subject)

        if filters.topic:
            conditions.append(QuestionSet.topic == filters.topic)

        if filters.grade_level:
            conditions.append(QuestionSet.grade_level == filters.grade_level)

        if filters.is_active is not None:
            conditions.append(QuestionSet.is_active == filters.is_active)

        if filters.search:
            search_term = f"%{filters.search}%"
            conditions.append(
                or_(
                    QuestionSet.name.ilike(search_term),
                    QuestionSet.description.ilike(search_term),
                    QuestionSet.subject.ilike(search_term),
                    QuestionSet.topic.ilike(search_term)
                )
            )

        if conditions:
            query = query.where(and_(*conditions))

        # Get total count
        count_query = select(func.count()).select_from(QuestionSet)
        if conditions:
            count_query = count_query.where(and_(*conditions))

        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (filters.page - 1) * filters.limit
        query = query.offset(offset).limit(filters.limit).order_by(QuestionSet.created_at.desc())

        # Execute query
        result = await db.execute(query)
        question_sets = result.scalars().all()

        # Calculate pages
        pages = (total + filters.limit - 1) // filters.limit

        return QuestionSetListResponse(
            question_sets=[QuestionSetResponse.from_orm(qs) for qs in question_sets],
            total=total,
            page=filters.page,
            pages=pages,
            limit=filters.limit
        )

    @staticmethod
    async def get_question_set(
        db: AsyncSession,
        question_set_id: UUID
    ) -> QuestionSetWithItems:
        """Get a single question set with all its questions"""

        result = await db.execute(
            select(QuestionSet)
            .options(selectinload(QuestionSet.question_set_items).selectinload(QuestionSetItem.question))
            .where(QuestionSet.id == question_set_id)
        )

        question_set = result.scalar_one_or_none()
        if not question_set:
            raise ValueError(f"Question set with ID {question_set_id} not found")

        # Convert to dict and handle Question objects manually
        question_set_dict = {
            "id": question_set.id,
            "name": question_set.name,
            "description": question_set.description,
            "subject": question_set.subject,
            "topic": question_set.topic,
            "grade_level": question_set.grade_level,
            "metadata_json": question_set.metadata_json,
            "total_points": question_set.total_points,
            "question_count": question_set.question_count,
            "is_active": question_set.is_active,
            "created_by": question_set.created_by,
            "created_at": question_set.created_at,
            "updated_at": question_set.updated_at,
            "creator_name": None,
            "question_set_items": []
        }

        # Process question set items
        for item in question_set.question_set_items:
            item_dict = {
                "id": item.id,
                "question_set_id": item.question_set_id,
                "question_id": item.question_id,
                "order_number": item.order_number,
                "points_override": item.points_override,
                "created_at": item.created_at,
                "question": None
            }

            # Convert Question object to dict if present
            if item.question:
                item_dict["question"] = {
                    "id": item.question.id,
                    "question_text": item.question.question_text,
                    "question_type": item.question.question_type.value if item.question.question_type else None,
                    "question_format": item.question.question_format.value if item.question.question_format else None,
                    "subject": item.question.subject,
                    "topic": item.question.topic,
                    "difficulty": item.question.difficulty.value if item.question.difficulty else None,
                    "points": item.question.points,
                    "image_url": item.question.image_url,
                    "s3_key": item.question.s3_key,
                    "explanation": item.question.explanation,
                    "instruction_text": item.question.instruction_text,
                    "pattern_sequence": item.question.pattern_sequence,
                    "tags": item.question.tags,
                    "created_by": item.question.created_by,
                    "created_at": item.question.created_at,
                    "updated_at": item.question.updated_at
                }

            question_set_dict["question_set_items"].append(item_dict)

        return QuestionSetWithItems(**question_set_dict)

    @staticmethod
    async def update_question_set(
        db: AsyncSession,
        question_set_id: UUID,
        update_data: QuestionSetUpdate
    ) -> QuestionSetResponse:
        """Update a question set"""

        question_set = await db.get(QuestionSet, question_set_id)
        if not question_set:
            raise ValueError(f"Question set with ID {question_set_id} not found")

        # Update fields
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(question_set, field, value)

        await db.commit()
        await db.refresh(question_set)

        return QuestionSetResponse.from_orm(question_set)

    @staticmethod
    async def delete_question_set(
        db: AsyncSession,
        question_set_id: UUID
    ) -> bool:
        """Delete a question set"""

        question_set = await db.get(QuestionSet, question_set_id)
        if not question_set:
            raise ValueError(f"Question set with ID {question_set_id} not found")

        # Check if question set is used in any test
        result = await db.execute(
            select(TestQuestionSet).where(TestQuestionSet.question_set_id == question_set_id)
        )
        if result.scalar():
            raise ValueError("Cannot delete question set that is assigned to tests")

        await db.delete(question_set)
        await db.commit()

        return True

    @staticmethod
    async def add_questions_to_set(
        db: AsyncSession,
        question_set_id: UUID,
        request: AddQuestionsToSetRequest
    ) -> QuestionSetWithItems:
        """Add questions to an existing question set"""

        question_set = await db.get(QuestionSet, question_set_id)
        if not question_set:
            raise ValueError(f"Question set with ID {question_set_id} not found")

        # Get current max order number
        result = await db.execute(
            select(func.max(QuestionSetItem.order_number))
            .where(QuestionSetItem.question_set_id == question_set_id)
        )
        max_order = result.scalar() or 0

        # Add new questions
        total_points_added = 0
        questions_added = 0

        for question_id in request.question_ids:
            # Check if question already exists in set
            existing = await db.execute(
                select(QuestionSetItem)
                .where(and_(
                    QuestionSetItem.question_set_id == question_set_id,
                    QuestionSetItem.question_id == question_id
                ))
            )
            if existing.scalar():
                continue

            # Verify question exists
            question = await db.get(Question, question_id)
            if not question:
                continue

            # Add question to set
            max_order += 1
            item = QuestionSetItem(
                question_set_id=question_set_id,
                question_id=question_id,
                order_number=max_order
            )
            db.add(item)

            total_points_added += question.points or 1
            questions_added += 1

        # Update question set totals
        question_set.total_points += total_points_added
        question_set.question_count += questions_added

        await db.commit()

        return await QuestionSetService.get_question_set(db, question_set_id)

    @staticmethod
    async def remove_questions_from_set(
        db: AsyncSession,
        question_set_id: UUID,
        request: RemoveQuestionsFromSetRequest
    ) -> QuestionSetWithItems:
        """Remove questions from a question set"""

        question_set = await db.get(QuestionSet, question_set_id)
        if not question_set:
            raise ValueError(f"Question set with ID {question_set_id} not found")

        # Remove questions
        total_points_removed = 0
        questions_removed = 0

        for question_id in request.question_ids:
            # Get the item to remove
            result = await db.execute(
                select(QuestionSetItem)
                .options(selectinload(QuestionSetItem.question))
                .where(and_(
                    QuestionSetItem.question_set_id == question_set_id,
                    QuestionSetItem.question_id == question_id
                ))
            )
            item = result.scalar_one_or_none()

            if item:
                points = item.points_override if item.points_override else item.question.points
                total_points_removed += points or 1
                questions_removed += 1
                await db.delete(item)

        # Update question set totals
        question_set.total_points = max(0, question_set.total_points - total_points_removed)
        question_set.question_count = max(0, question_set.question_count - questions_removed)

        # Reorder remaining questions
        await QuestionSetService._reorder_questions_after_removal(db, question_set_id)

        await db.commit()

        return await QuestionSetService.get_question_set(db, question_set_id)

    @staticmethod
    async def reorder_questions_in_set(
        db: AsyncSession,
        question_set_id: UUID,
        request: ReorderQuestionsInSetRequest
    ) -> QuestionSetWithItems:
        """Reorder questions within a question set"""

        question_set = await db.get(QuestionSet, question_set_id)
        if not question_set:
            raise ValueError(f"Question set with ID {question_set_id} not found")

        # Update order for each question
        for order_data in request.question_orders:
            question_id = order_data.get('question_id')
            order_number = order_data.get('order_number')

            if question_id and order_number is not None:
                result = await db.execute(
                    select(QuestionSetItem)
                    .where(and_(
                        QuestionSetItem.question_set_id == question_set_id,
                        QuestionSetItem.question_id == question_id
                    ))
                )
                item = result.scalar_one_or_none()

                if item:
                    item.order_number = order_number

        await db.commit()

        return await QuestionSetService.get_question_set(db, question_set_id)

    @staticmethod
    async def assign_question_sets_to_test(
        db: AsyncSession,
        test_id: UUID,
        question_set_ids: List[UUID]
    ) -> List[TestQuestionSetCreate]:
        """Assign question sets to a test with duplicate validation"""

        # Verify test exists and is not published
        test = await db.get(Test, test_id)
        if not test:
            raise ValueError(f"Test with ID {test_id} not found")

        if test.status == TestStatus.PUBLISHED:
            raise ValueError("Cannot modify questions for a published test. Unpublish the test first.")

        # Check for already assigned question sets
        existing_result = await db.execute(
            select(TestQuestionSet.question_set_id)
            .where(TestQuestionSet.test_id == test_id)
        )
        existing_set_ids = {row[0] for row in existing_result.fetchall()}

        # Find duplicates
        duplicate_set_ids = [set_id for set_id in question_set_ids if set_id in existing_set_ids]

        if duplicate_set_ids:
            # Get names of duplicate question sets for better error message
            duplicate_names_result = await db.execute(
                select(QuestionSet.name)
                .where(QuestionSet.id.in_(duplicate_set_ids))
            )
            duplicate_names = [row[0] for row in duplicate_names_result.fetchall()]

            error_msg = f"The following question sets are already assigned to this test: {', '.join(duplicate_names)}. Please remove duplicate selections."
            raise ValueError(error_msg)

        # Get current max order number
        max_order_result = await db.execute(
            select(func.max(TestQuestionSet.order_number))
            .where(TestQuestionSet.test_id == test_id)
        )
        max_order = max_order_result.scalar() or 0

        # Add new question sets
        test_question_sets = []
        invalid_sets = []

        for set_id in question_set_ids:
            # Verify question set exists and is active
            question_set = await db.get(QuestionSet, set_id)
            if not question_set:
                invalid_sets.append(f"Question set with ID {set_id} not found")
                continue
            elif not question_set.is_active:
                invalid_sets.append(f"Question set '{question_set.name}' is inactive and cannot be assigned")
                continue

            # Create assignment
            max_order += 1
            test_question_set = TestQuestionSet(
                test_id=test_id,
                question_set_id=set_id,
                order_number=max_order
            )
            db.add(test_question_set)
            test_question_sets.append(test_question_set)

        if invalid_sets:
            raise ValueError(f"Invalid question sets: {'; '.join(invalid_sets)}")

        await db.commit()

        return test_question_sets

    @staticmethod
    async def _reorder_questions_after_removal(
        db: AsyncSession,
        question_set_id: UUID
    ) -> None:
        """Reorder questions after some have been removed"""

        result = await db.execute(
            select(QuestionSetItem)
            .where(QuestionSetItem.question_set_id == question_set_id)
            .order_by(QuestionSetItem.order_number)
        )
        items = result.scalars().all()

        for index, item in enumerate(items, start=1):
            item.order_number = index