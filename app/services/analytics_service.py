import logging
from typing import Dict, List, Optional, Any
from uuid import UUID
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models import (
    User, Student, Class, Test, TestResult, TestAssignment,
    TestAttempt, QuestionResponse, Question
)
from app.models.user import UserRole
from app.models.test import TestType, AssignmentStatus, AttemptStatus, ResultStatus

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for calculating analytics and generating insights"""

    @staticmethod
    async def get_admin_dashboard_overview(db: AsyncSession) -> Dict[str, Any]:
        """Get comprehensive overview for admin dashboard"""
        try:
            # Total counts
            total_students = await db.execute(select(func.count(Student.id)))
            total_tests = await db.execute(select(func.count(Test.id)))
            total_results = await db.execute(select(func.count(TestResult.id)))

            # Active test assignments
            now = datetime.utcnow()
            active_assignments = await db.execute(
                select(func.count(TestAssignment.id))
                .where(and_(
                    TestAssignment.status == AssignmentStatus.ACTIVE,
                    TestAssignment.scheduled_start <= now,
                    TestAssignment.scheduled_end >= now
                ))
            )

            # Recent activity (last 24 hours)
            yesterday = now - timedelta(hours=24)
            recent_submissions = await db.execute(
                select(func.count(TestResult.id))
                .where(TestResult.submitted_at >= yesterday)
            )

            # Average class performance
            avg_performance = await db.execute(
                select(func.avg(TestResult.percentage))
                .where(TestResult.percentage.is_not(None))
            )

            avg_score = avg_performance.scalar() or 0.0

            # Get recent test results with details
            recent_results = await db.execute(
                select(TestResult, Student, User, Test)
                .join(Student, TestResult.student_id == Student.id)
                .join(User, Student.user_id == User.id)
                .join(Test, TestResult.test_id == Test.id)
                .order_by(TestResult.submitted_at.desc())
                .limit(5)
            )

            recent_list = []
            for result, student, user, test in recent_results:
                recent_list.append({
                    "student_name": user.full_name,
                    "test_title": test.title,
                    "score": f"{result.total_score}/{result.max_score}",
                    "percentage": float(result.percentage) if result.percentage else 0.0,
                    "submitted_at": result.submitted_at.isoformat() if result.submitted_at else None
                })

            return {
                "totals": {
                    "students": total_students.scalar(),
                    "tests": total_tests.scalar(),
                    "results": total_results.scalar(),
                    "active_assignments": active_assignments.scalar()
                },
                "activity": {
                    "recent_submissions": recent_submissions.scalar(),
                    "average_performance": round(avg_score, 2)
                },
                "recent_results": recent_list
            }

        except Exception as e:
            logger.error(f"Error getting admin dashboard overview: {str(e)}")
            raise e

    @staticmethod
    async def get_student_analytics(db: AsyncSession, student_id: UUID) -> Dict[str, Any]:
        """Get detailed analytics for a specific student"""
        try:
            # Get student info
            student_result = await db.execute(
                select(Student, User, Class)
                .join(User, Student.user_id == User.id)
                .outerjoin(Class, Student.class_id == Class.id)
                .where(Student.id == student_id)
            )

            student_data = student_result.first()
            if not student_data:
                raise ValueError("Student not found")

            student, user, class_info = student_data

            # Get all test results for this student
            results = await db.execute(
                select(TestResult, Test)
                .join(Test, TestResult.test_id == Test.id)
                .where(TestResult.student_id == student_id)
                .order_by(TestResult.submitted_at.desc())
            )

            all_results = results.fetchall()

            if not all_results:
                return {
                    "student_info": {
                        "name": user.full_name,
                        "email": user.email,
                        "class_name": class_info.name if class_info else None,
                        "year_group": student.year_group
                    },
                    "performance": {
                        "tests_completed": 0,
                        "average_score": 0.0,
                        "best_score": 0.0,
                        "total_time_spent": 0
                    },
                    "subject_breakdown": {},
                    "progress_trend": [],
                    "class_comparison": None
                }

            # Calculate performance metrics
            percentages = [float(result.TestResult.percentage) for result in all_results]
            average_score = sum(percentages) / len(percentages)
            best_score = max(percentages)

            total_time = sum(
                result.TestResult.time_taken for result in all_results
                if result.TestResult.time_taken
            ) or 0

            # Subject breakdown
            subject_breakdown = {}
            for result in all_results:
                subject = result.Test.type.value
                if subject not in subject_breakdown:
                    subject_breakdown[subject] = []
                subject_breakdown[subject].append(float(result.TestResult.percentage))

            # Calculate subject averages
            for subject in subject_breakdown:
                scores = subject_breakdown[subject]
                subject_breakdown[subject] = {
                    "average": sum(scores) / len(scores),
                    "tests_taken": len(scores),
                    "best_score": max(scores)
                }

            # Progress trend (chronological)
            progress_trend = []
            sorted_results = sorted(all_results, key=lambda x: x.TestResult.submitted_at or datetime.min)
            for result in sorted_results:
                progress_trend.append({
                    "date": result.TestResult.submitted_at.isoformat() if result.TestResult.submitted_at else None,
                    "score": float(result.TestResult.percentage),
                    "test_title": result.Test.title,
                    "subject": result.Test.type.value
                })

            # Class comparison (if student has a class)
            class_comparison = None
            if student.class_id:
                # Get class average
                class_avg = await db.execute(
                    select(func.avg(TestResult.percentage))
                    .join(Student, TestResult.student_id == Student.id)
                    .where(Student.class_id == student.class_id)
                )

                class_average = class_avg.scalar() or 0.0

                # Get student rank in class
                class_students = await db.execute(
                    select(Student.id, func.avg(TestResult.percentage).label('avg_score'))
                    .outerjoin(TestResult, TestResult.student_id == Student.id)
                    .where(Student.class_id == student.class_id)
                    .group_by(Student.id)
                    .order_by(func.avg(TestResult.percentage).desc().nulls_last())
                )

                class_results = class_students.fetchall()
                class_size = len(class_results)

                student_rank = None
                for idx, (sid, avg_score) in enumerate(class_results):
                    if sid == student_id:
                        student_rank = idx + 1
                        break

                class_comparison = {
                    "class_average": round(class_average, 2),
                    "student_rank": student_rank,
                    "class_size": class_size,
                    "above_average": average_score > class_average
                }

            return {
                "student_info": {
                    "name": user.full_name,
                    "email": user.email,
                    "class_name": class_info.name if class_info else None,
                    "year_group": student.year_group
                },
                "performance": {
                    "tests_completed": len(all_results),
                    "average_score": round(average_score, 2),
                    "best_score": round(best_score, 2),
                    "total_time_spent": total_time // 60  # Convert to minutes
                },
                "subject_breakdown": subject_breakdown,
                "progress_trend": progress_trend,
                "class_comparison": class_comparison
            }

        except Exception as e:
            logger.error(f"Error getting student analytics: {str(e)}")
            raise e

    @staticmethod
    async def get_class_analytics(db: AsyncSession, class_id: UUID) -> Dict[str, Any]:
        """Get comprehensive analytics for a class"""
        try:
            # Get class info
            class_result = await db.execute(
                select(Class).where(Class.id == class_id)
            )

            class_info = class_result.scalar_one_or_none()
            if not class_info:
                raise ValueError("Class not found")

            # Get all students in class
            students_result = await db.execute(
                select(Student, User)
                .join(User, Student.user_id == User.id)
                .where(Student.class_id == class_id)
            )

            students = students_result.fetchall()

            # Get all test results for class students
            student_ids = [s.Student.id for s in students]

            if not student_ids:
                return {
                    "class_info": {
                        "name": class_info.name,
                        "year_group": class_info.year_group,
                        "student_count": 0
                    },
                    "performance": {
                        "class_average": 0.0,
                        "highest_score": 0.0,
                        "lowest_score": 0.0,
                        "tests_completed": 0
                    },
                    "student_performance": [],
                    "subject_breakdown": {},
                    "test_statistics": []
                }

            results = await db.execute(
                select(TestResult, Student, User, Test)
                .join(Student, TestResult.student_id == Student.id)
                .join(User, Student.user_id == User.id)
                .join(Test, TestResult.test_id == Test.id)
                .where(TestResult.student_id.in_(student_ids))
                .order_by(TestResult.submitted_at.desc())
            )

            all_results = results.fetchall()

            if not all_results:
                return {
                    "class_info": {
                        "name": class_info.name,
                        "year_group": class_info.year_group,
                        "student_count": len(students)
                    },
                    "performance": {
                        "class_average": 0.0,
                        "highest_score": 0.0,
                        "lowest_score": 0.0,
                        "tests_completed": 0
                    },
                    "student_performance": [],
                    "subject_breakdown": {},
                    "test_statistics": []
                }

            # Calculate class performance
            percentages = [float(result.TestResult.percentage) for result in all_results]
            class_average = sum(percentages) / len(percentages)
            highest_score = max(percentages)
            lowest_score = min(percentages)

            # Student performance summary
            student_performance = {}
            for result in all_results:
                student_id = result.Student.id
                if student_id not in student_performance:
                    student_performance[student_id] = {
                        "name": result.User.full_name,
                        "email": result.User.email,
                        "scores": [],
                        "tests_completed": 0
                    }

                student_performance[student_id]["scores"].append(float(result.TestResult.percentage))
                student_performance[student_id]["tests_completed"] += 1

            # Calculate student averages
            for student_id in student_performance:
                scores = student_performance[student_id]["scores"]
                student_performance[student_id]["average"] = sum(scores) / len(scores)
                student_performance[student_id]["best_score"] = max(scores)

            # Convert to list sorted by average
            student_list = []
            for student_id, data in student_performance.items():
                student_list.append({
                    "student_id": str(student_id),
                    "name": data["name"],
                    "email": data["email"],
                    "average": round(data["average"], 2),
                    "best_score": round(data["best_score"], 2),
                    "tests_completed": data["tests_completed"]
                })

            student_list.sort(key=lambda x: x["average"], reverse=True)

            # Subject breakdown for class
            subject_breakdown = {}
            for result in all_results:
                subject = result.Test.type.value
                if subject not in subject_breakdown:
                    subject_breakdown[subject] = []
                subject_breakdown[subject].append(float(result.TestResult.percentage))

            for subject in subject_breakdown:
                scores = subject_breakdown[subject]
                subject_breakdown[subject] = {
                    "average": sum(scores) / len(scores),
                    "tests_taken": len(scores),
                    "highest_score": max(scores),
                    "lowest_score": min(scores)
                }

            # Test statistics (per test averages)
            test_stats = {}
            for result in all_results:
                test_id = result.Test.id
                if test_id not in test_stats:
                    test_stats[test_id] = {
                        "title": result.Test.title,
                        "type": result.Test.type.value,
                        "scores": []
                    }
                test_stats[test_id]["scores"].append(float(result.TestResult.percentage))

            test_statistics = []
            for test_id, data in test_stats.items():
                scores = data["scores"]
                test_statistics.append({
                    "test_id": str(test_id),
                    "title": data["title"],
                    "type": data["type"],
                    "class_average": round(sum(scores) / len(scores), 2),
                    "highest_score": round(max(scores), 2),
                    "lowest_score": round(min(scores), 2),
                    "completion_count": len(scores)
                })

            test_statistics.sort(key=lambda x: x["class_average"], reverse=True)

            return {
                "class_info": {
                    "name": class_info.name,
                    "year_group": class_info.year_group,
                    "student_count": len(students)
                },
                "performance": {
                    "class_average": round(class_average, 2),
                    "highest_score": round(highest_score, 2),
                    "lowest_score": round(lowest_score, 2),
                    "tests_completed": len(all_results)
                },
                "student_performance": student_list,
                "subject_breakdown": subject_breakdown,
                "test_statistics": test_statistics
            }

        except Exception as e:
            logger.error(f"Error getting class analytics: {str(e)}")
            raise e

    @staticmethod
    async def get_test_analytics(db: AsyncSession, test_id: UUID) -> Dict[str, Any]:
        """Get detailed analytics for a specific test"""
        try:
            # Get test info
            test_result = await db.execute(
                select(Test).where(Test.id == test_id)
            )

            test = test_result.scalar_one_or_none()
            if not test:
                raise ValueError("Test not found")

            # Get all results for this test
            results = await db.execute(
                select(TestResult, Student, User, Class)
                .join(Student, TestResult.student_id == Student.id)
                .join(User, Student.user_id == User.id)
                .outerjoin(Class, Student.class_id == Class.id)
                .where(TestResult.test_id == test_id)
                .order_by(TestResult.percentage.desc())
            )

            all_results = results.fetchall()

            if not all_results:
                return {
                    "test_info": {
                        "title": test.title,
                        "type": test.type.value,
                        "duration_minutes": test.duration_minutes,
                        "total_marks": test.total_marks,
                        "pass_mark": test.pass_mark
                    },
                    "statistics": {
                        "completion_count": 0,
                        "average_score": 0.0,
                        "highest_score": 0.0,
                        "lowest_score": 0.0,
                        "pass_rate": 0.0,
                        "average_time": 0
                    },
                    "score_distribution": {},
                    "student_results": []
                }

            # Calculate statistics
            percentages = [float(result.TestResult.percentage) for result in all_results]
            pass_count = sum(1 for p in percentages if p >= test.pass_mark)

            times = [result.TestResult.time_taken for result in all_results if result.TestResult.time_taken]
            average_time = sum(times) / len(times) if times else 0

            # Score distribution (by grade ranges)
            score_distribution = {
                "90-100": 0,
                "80-89": 0,
                "70-79": 0,
                "60-69": 0,
                "50-59": 0,
                "Below 50": 0
            }

            for score in percentages:
                if score >= 90:
                    score_distribution["90-100"] += 1
                elif score >= 80:
                    score_distribution["80-89"] += 1
                elif score >= 70:
                    score_distribution["70-79"] += 1
                elif score >= 60:
                    score_distribution["60-69"] += 1
                elif score >= 50:
                    score_distribution["50-59"] += 1
                else:
                    score_distribution["Below 50"] += 1

            # Student results
            student_results = []
            for result in all_results:
                student_results.append({
                    "student_id": str(result.Student.id),
                    "name": result.User.full_name,
                    "class_name": result.Class.name if result.Class else None,
                    "score": f"{result.TestResult.total_score}/{result.TestResult.max_score}",
                    "percentage": float(result.TestResult.percentage),
                    "grade": result.TestResult.grade,
                    "time_taken": result.TestResult.time_taken,
                    "submitted_at": result.TestResult.submitted_at.isoformat() if result.TestResult.submitted_at else None,
                    "status": "Pass" if result.TestResult.percentage >= test.pass_mark else "Fail"
                })

            return {
                "test_info": {
                    "title": test.title,
                    "type": test.type.value,
                    "duration_minutes": test.duration_minutes,
                    "total_marks": test.total_marks,
                    "pass_mark": test.pass_mark
                },
                "statistics": {
                    "completion_count": len(all_results),
                    "average_score": round(sum(percentages) / len(percentages), 2),
                    "highest_score": round(max(percentages), 2),
                    "lowest_score": round(min(percentages), 2),
                    "pass_rate": round((pass_count / len(all_results)) * 100, 2),
                    "average_time": round(average_time / 60, 2) if average_time else 0  # Convert to minutes
                },
                "score_distribution": score_distribution,
                "student_results": student_results
            }

        except Exception as e:
            logger.error(f"Error getting test analytics: {str(e)}")
            raise e