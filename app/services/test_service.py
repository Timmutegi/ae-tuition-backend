from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, update, delete
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from app.models import (
    Test, TestQuestion, TestAssignment, Question, ReadingPassage, AnswerOption,
    TestType, TestStatus, AssignmentStatus, Class, User
)
from app.schemas.test import (
    TestCreate, TestUpdate, TestResponse, TestWithDetails, TestFilters,
    TestQuestionCreate, TestAssignmentCreate, TestAssignmentUpdate,
    BulkAssignmentRequest, TestCloneRequest, TestStatsResponse
)


class TestService:
    @staticmethod
    async def create_test(db: AsyncSession, test_data: TestCreate, creator_id: UUID) -> Test:
        """Create a new test"""
        test = Test(
            **test_data.model_dump(),
            created_by=creator_id
        )
        db.add(test)
        await db.commit()
        await db.refresh(test)
        return test

    @staticmethod
    async def get_test_by_id(db: AsyncSession, test_id: UUID) -> Optional[Test]:
        """Get test by ID with full details"""
        result = await db.execute(
            select(Test)
            .options(
                selectinload(Test.test_questions).selectinload(TestQuestion.question),
                selectinload(Test.test_assignments).selectinload(TestAssignment.class_info),
                selectinload(Test.creator)
            )
            .where(Test.id == test_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_tests(db: AsyncSession, filters: TestFilters) -> Dict[str, Any]:
        """Get tests with filtering and pagination"""
        query = select(Test).options(selectinload(Test.creator))

        # Apply filters
        if filters.type:
            query = query.where(Test.type == filters.type)
        if filters.status:
            query = query.where(Test.status == filters.status)
        if filters.created_by:
            query = query.where(Test.created_by == filters.created_by)
        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.where(
                or_(
                    Test.title.ilike(search_pattern),
                    Test.description.ilike(search_pattern)
                )
            )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (filters.page - 1) * filters.limit
        query = query.offset(offset).limit(filters.limit).order_by(Test.created_at.desc())

        result = await db.execute(query)
        tests = result.scalars().all()

        from app.schemas.test import TestResponse

        # Convert SQLAlchemy objects to Pydantic models
        test_responses = [TestResponse.model_validate(test) for test in tests]

        return {
            "tests": test_responses,
            "total": total,
            "page": filters.page,
            "limit": filters.limit,
            "total_pages": (total + filters.limit - 1) // filters.limit
        }

    @staticmethod
    async def update_test(db: AsyncSession, test_id: UUID, test_data: TestUpdate, user_id: UUID) -> Optional[Test]:
        """Update test (only if user is creator and test is draft)"""
        test = await TestService.get_test_by_id(db, test_id)
        if not test or test.created_by != user_id:
            return None

        # Only allow updates if test is in draft status
        if test.status != TestStatus.DRAFT:
            raise ValueError("Cannot update published or archived tests")

        update_data = test_data.model_dump(exclude_unset=True)
        if update_data:
            for field, value in update_data.items():
                setattr(test, field, value)

            await db.commit()
            await db.refresh(test)

        return test

    @staticmethod
    async def delete_test(db: AsyncSession, test_id: UUID, user_id: UUID) -> bool:
        """Delete test (only if user is creator and no attempts exist)"""
        test = await TestService.get_test_by_id(db, test_id)
        if not test or test.created_by != user_id:
            return False

        # Check if test has any attempts
        from app.models.test import TestAttempt
        attempt_result = await db.execute(
            select(func.count(TestAttempt.id)).where(TestAttempt.test_id == test_id)
        )
        attempt_count = attempt_result.scalar()

        if attempt_count > 0:
            raise ValueError("Cannot delete test with existing attempts")

        await db.delete(test)
        await db.commit()
        return True

    @staticmethod
    async def clone_test(db: AsyncSession, test_id: UUID, clone_data: TestCloneRequest, user_id: UUID) -> Optional[Test]:
        """Clone an existing test"""
        original_test = await TestService.get_test_by_id(db, test_id)
        if not original_test:
            return None

        # Create new test
        new_test = Test(
            title=clone_data.new_title,
            description=original_test.description,
            type=original_test.type,
            test_format=original_test.test_format,
            duration_minutes=original_test.duration_minutes,
            warning_intervals=original_test.warning_intervals,
            pass_mark=original_test.pass_mark,
            instructions=original_test.instructions,
            question_order=original_test.question_order,
            status=TestStatus.DRAFT,
            created_by=user_id
        )
        db.add(new_test)
        await db.flush()

        # Clone questions if requested
        if clone_data.copy_questions:
            for test_question in original_test.test_questions:
                new_test_question = TestQuestion(
                    test_id=new_test.id,
                    question_id=test_question.question_id,
                    passage_id=test_question.passage_id,
                    order_number=test_question.order_number,
                    question_group=test_question.question_group,
                    points=test_question.points
                )
                db.add(new_test_question)

        # Clone assignments if requested
        if clone_data.copy_assignments:
            for assignment in original_test.test_assignments:
                new_assignment = TestAssignment(
                    test_id=new_test.id,
                    class_id=assignment.class_id,
                    scheduled_start=assignment.scheduled_start,
                    scheduled_end=assignment.scheduled_end,
                    buffer_time_minutes=assignment.buffer_time_minutes,
                    allow_late_submission=assignment.allow_late_submission,
                    late_submission_grace_minutes=assignment.late_submission_grace_minutes,
                    auto_submit=assignment.auto_submit,
                    extended_time_students=assignment.extended_time_students,
                    custom_instructions=assignment.custom_instructions,
                    status=AssignmentStatus.SCHEDULED,
                    created_by=user_id
                )
                db.add(new_assignment)

        await db.commit()
        await db.refresh(new_test)
        return new_test

    @staticmethod
    async def assign_questions_to_test(db: AsyncSession, test_id: UUID, questions: List[TestQuestionCreate], user_id: UUID) -> bool:
        """Assign questions to a test"""
        test = await TestService.get_test_by_id(db, test_id)
        if not test or test.created_by != user_id or test.status != TestStatus.DRAFT:
            return False

        # Remove existing questions
        await db.execute(delete(TestQuestion).where(TestQuestion.test_id == test_id))

        # Add new questions
        total_marks = 0
        for question_data in questions:
            test_question = TestQuestion(
                test_id=test_id,
                **question_data.model_dump()
            )
            db.add(test_question)
            total_marks += question_data.points

        # Update test total marks
        test.total_marks = total_marks
        await db.commit()
        return True

    @staticmethod
    async def assign_test_to_classes(db: AsyncSession, test_id: UUID, assignment_data: BulkAssignmentRequest, user_id: UUID) -> List[TestAssignment]:
        """Assign test to multiple classes"""
        test = await TestService.get_test_by_id(db, test_id)
        if not test or test.status != TestStatus.PUBLISHED:
            raise ValueError("Can only assign published tests")

        assignments = []
        for class_id in assignment_data.class_ids:
            # Check if assignment already exists
            existing = await db.execute(
                select(TestAssignment).where(
                    and_(TestAssignment.test_id == test_id, TestAssignment.class_id == class_id)
                )
            )
            if existing.scalar_one_or_none():
                continue  # Skip if already assigned

            assignment = TestAssignment(
                test_id=test_id,
                **assignment_data.assignment_data.model_dump(),
                created_by=user_id
            )
            db.add(assignment)
            assignments.append(assignment)

        await db.commit()
        return assignments

    @staticmethod
    async def get_test_assignments(db: AsyncSession, test_id: UUID) -> List[TestAssignment]:
        """Get all assignments for a test"""
        result = await db.execute(
            select(TestAssignment)
            .options(selectinload(TestAssignment.class_info))
            .where(TestAssignment.test_id == test_id)
            .order_by(TestAssignment.scheduled_start)
        )
        return result.scalars().all()

    @staticmethod
    async def update_test_assignment(db: AsyncSession, assignment_id: UUID, assignment_data: TestAssignmentUpdate, user_id: UUID) -> Optional[TestAssignment]:
        """Update a test assignment"""
        assignment = await db.execute(
            select(TestAssignment).where(TestAssignment.id == assignment_id)
        )
        assignment = assignment.scalar_one_or_none()

        if not assignment or assignment.created_by != user_id:
            return None

        update_data = assignment_data.model_dump(exclude_unset=True)
        if update_data:
            for field, value in update_data.items():
                setattr(assignment, field, value)

            await db.commit()
            await db.refresh(assignment)

        return assignment

    @staticmethod
    async def remove_test_assignment(db: AsyncSession, test_id: UUID, class_id: UUID, user_id: UUID) -> bool:
        """Remove test assignment for a specific class"""
        assignment = await db.execute(
            select(TestAssignment).where(
                and_(
                    TestAssignment.test_id == test_id,
                    TestAssignment.class_id == class_id,
                    TestAssignment.created_by == user_id
                )
            )
        )
        assignment = assignment.scalar_one_or_none()

        if not assignment:
            return False

        # Check if there are any attempts
        from app.models.test import TestAttempt
        attempt_result = await db.execute(
            select(func.count(TestAttempt.id)).where(TestAttempt.assignment_id == assignment.id)
        )
        attempt_count = attempt_result.scalar()

        if attempt_count > 0:
            raise ValueError("Cannot remove assignment with existing attempts")

        await db.delete(assignment)
        await db.commit()
        return True

    @staticmethod
    async def publish_test(db: AsyncSession, test_id: UUID, user_id: UUID) -> Optional[Test]:
        """Publish a draft test"""
        test = await TestService.get_test_by_id(db, test_id)
        if not test or test.created_by != user_id or test.status != TestStatus.DRAFT:
            return None

        # Validate test has questions
        if not test.test_questions:
            raise ValueError("Cannot publish test without questions")

        test.status = TestStatus.PUBLISHED
        await db.commit()
        await db.refresh(test)
        return test

    @staticmethod
    async def archive_test(db: AsyncSession, test_id: UUID, user_id: UUID) -> Optional[Test]:
        """Archive a test"""
        test = await TestService.get_test_by_id(db, test_id)
        if not test or test.created_by != user_id:
            return None

        test.status = TestStatus.ARCHIVED
        await db.commit()
        await db.refresh(test)
        return test

    @staticmethod
    async def get_test_stats(db: AsyncSession, user_id: Optional[UUID] = None) -> TestStatsResponse:
        """Get test statistics"""
        base_query = select(Test)
        if user_id:
            base_query = base_query.where(Test.created_by == user_id)

        # Total tests
        total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
        total_tests = total_result.scalar()

        # Tests by status
        status_query = select(Test.status, func.count()).group_by(Test.status)
        if user_id:
            status_query = status_query.where(Test.created_by == user_id)

        status_result = await db.execute(status_query)
        status_counts = dict(status_result.fetchall())

        # Assignment stats
        assignment_query = select(func.count()).select_from(TestAssignment)
        if user_id:
            assignment_query = assignment_query.join(Test).where(Test.created_by == user_id)

        total_assignments_result = await db.execute(assignment_query)
        total_assignments = total_assignments_result.scalar()

        # Active assignments
        active_assignment_query = select(func.count()).select_from(TestAssignment).where(
            TestAssignment.status == AssignmentStatus.ACTIVE
        )
        if user_id:
            active_assignment_query = active_assignment_query.join(Test).where(Test.created_by == user_id)

        active_assignments_result = await db.execute(active_assignment_query)
        active_assignments = active_assignments_result.scalar()

        return TestStatsResponse(
            total_tests=total_tests,
            draft_tests=status_counts.get(TestStatus.DRAFT, 0),
            published_tests=status_counts.get(TestStatus.PUBLISHED, 0),
            archived_tests=status_counts.get(TestStatus.ARCHIVED, 0),
            total_assignments=total_assignments,
            active_assignments=active_assignments
        )