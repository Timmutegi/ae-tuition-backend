#!/usr/bin/env python3
"""
Script to set up test data for intervention alerts.

This script:
1. Creates an intervention threshold
2. Creates weekly performance records with low scores for existing students
3. Triggers the intervention check to create alerts

Usage:
    docker-compose -f docker-compose-dev.yml exec api python scripts/setup_intervention_test_data.py
"""

import asyncio
import sys
import os
from datetime import date, timedelta
from uuid import UUID

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.models.user import User, UserRole
from app.models.student import Student
from app.models.intervention import (
    InterventionThreshold, InterventionAlert, WeeklyPerformance,
    AlertPriority, AlertStatus
)
from app.services.intervention_service import InterventionService


async def get_students_by_emails(db, emails: list[str]) -> list[Student]:
    """Get students by their user emails."""
    result = await db.execute(
        select(Student)
        .join(User)
        .options(selectinload(Student.user), selectinload(Student.class_info))
        .where(User.email.in_(emails))
    )
    return list(result.scalars().all())


async def get_admin_user(db) -> User:
    """Get the admin user."""
    result = await db.execute(
        select(User).where(User.role == UserRole.ADMIN).limit(1)
    )
    return result.scalar_one_or_none()


async def create_threshold(db, admin_id: UUID) -> InterventionThreshold:
    """Create an intervention threshold for testing."""
    # Check if threshold already exists
    result = await db.execute(
        select(InterventionThreshold).where(InterventionThreshold.name == "Test Performance Alert")
    )
    existing = result.scalar_one_or_none()

    if existing:
        print(f"Threshold already exists: {existing.name} (ID: {existing.id})")
        return existing

    threshold = InterventionThreshold(
        name="Test Performance Alert",
        description="Test threshold for intervention alerts - triggers when score below 50% for 3 out of 5 weeks",
        subject=None,  # All subjects
        min_score_percent=50.0,
        max_score_percent=60.0,
        weeks_to_review=5,
        failures_required=3,
        alert_priority=AlertPriority.HIGH,
        notify_parent=True,
        notify_teacher=True,
        notify_supervisor=False,
        is_active=True,
        created_by=admin_id
    )
    db.add(threshold)
    await db.commit()
    await db.refresh(threshold)
    print(f"Created threshold: {threshold.name} (ID: {threshold.id})")
    return threshold


async def create_weekly_performance_data(db, student_id: UUID, weeks_back: int = 5):
    """Create weekly performance data with low scores for a student using academic weeks."""
    # Import the calendar service to use academic weeks
    from app.services.academic_calendar_service import AcademicCalendarService
    calendar_service = AcademicCalendarService()

    # Get current academic week
    current_week = calendar_service.get_current_week()
    if current_week == 0:
        print("  ERROR: Outside academic year, cannot create weekly performance data")
        return

    print(f"  Current academic week: {current_week}")

    # Define subjects
    subjects = ["Verbal Reasoning", "Non-Verbal Reasoning", "English", "Mathematics"]

    # Create performance records for the last N academic weeks
    for week_offset in range(weeks_back):
        academic_week = current_week - week_offset
        if academic_week < 1:
            print(f"  Skipping week {academic_week} (before academic year start)")
            continue

        # Get week info to get proper dates
        week_info = calendar_service.get_week_info(academic_week)
        week_start = week_info.start_date
        week_end = week_info.end_date
        week_number = academic_week  # Use academic week number

        # Check if record already exists
        result = await db.execute(
            select(WeeklyPerformance).where(
                WeeklyPerformance.student_id == student_id,
                WeeklyPerformance.week_number == week_number
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"  Academic week {week_number} already exists")
            continue

        # Create low scores for intervention trigger
        # Make 3-4 weeks have scores below 50%
        if week_offset < 4:  # First 4 weeks have low scores
            base_score = 35.0 + (week_offset * 5)  # 35%, 40%, 45%, 50%
        else:
            base_score = 65.0  # Last week has good score

        # Create subject-specific scores
        subject_scores = {}
        for subject in subjects:
            # Vary scores slightly per subject
            score = base_score + (hash(subject) % 10) - 5
            score = max(20, min(100, score))  # Clamp between 20-100
            subject_scores[subject] = {
                "average": score,
                "count": 2,
                "tests": ["Test A", "Test B"]
            }

        performance = WeeklyPerformance(
            student_id=student_id,
            week_start=week_start,
            week_end=week_end,
            week_number=week_number,
            year=week_start.year,
            tests_taken=len(subjects) * 2,
            average_score=base_score,
            highest_score=base_score + 10,
            lowest_score=base_score - 10,
            total_time_minutes=120,
            subject_scores=subject_scores,
            days_present=4,
            days_absent=1,
            days_late=0,
            homework_completed=3,
            homework_missing=1
        )
        db.add(performance)
        print(f"  Created academic week {week_number} ({week_start} to {week_end}, avg: {base_score}%)")

    await db.commit()


async def run_intervention_check(db) -> list[InterventionAlert]:
    """Run the intervention check to create alerts."""
    service = InterventionService(db)
    alerts = await service.run_intervention_check()
    return alerts


async def main():
    print("=" * 60)
    print("Setting up Intervention Alert Test Data")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        # Get admin user
        admin = await get_admin_user(db)
        if not admin:
            print("ERROR: No admin user found!")
            return
        print(f"\nUsing admin: {admin.email}")

        # Get students
        student_emails = ["tmbaka.gcp@gmail.com", "mamafairapp@gmail.com"]
        students = await get_students_by_emails(db, student_emails)

        if not students:
            print(f"ERROR: No students found with emails: {student_emails}")
            return

        # Extract student info upfront to avoid lazy loading issues
        student_info = []
        for s in students:
            student_info.append({
                'id': s.id,
                'email': s.user.email if s.user else "Unknown",
                'code': s.student_code,
                'class_name': s.class_info.name if s.class_info else "No Class"
            })

        print(f"\nFound {len(student_info)} students:")
        for info in student_info:
            print(f"  - {info['email']} (Code: {info['code']}, Class: {info['class_name']})")

        # Create threshold
        print("\n--- Creating Intervention Threshold ---")
        threshold = await create_threshold(db, admin.id)

        # Create weekly performance data for each student
        print("\n--- Creating Weekly Performance Data ---")
        for info in student_info:
            print(f"\nStudent: {info['email']}")
            await create_weekly_performance_data(db, info['id'])

        # Run intervention check
        print("\n--- Running Intervention Check ---")
        alerts = await run_intervention_check(db)
        print(f"\nCreated {len(alerts)} new intervention alerts")

        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        # Query all active alerts with eager loading to avoid lazy loading issues
        result = await db.execute(
            select(InterventionAlert)
            .options(selectinload(InterventionAlert.student).selectinload(Student.user))
            .where(InterventionAlert.status.in_([AlertStatus.PENDING, AlertStatus.IN_PROGRESS]))
        )
        all_alerts = list(result.scalars().all())

        # Extract alert info immediately
        alert_info_list = []
        for a in all_alerts:
            alert_info_list.append({
                'title': a.title,
                'subject': a.subject,
                'priority': a.priority.value,
                'status': a.status.value,
                'student_name': a.student.user.full_name if a.student and a.student.user else "Unknown"
            })

        print(f"Total active alerts: {len(alert_info_list)}")
        for info in alert_info_list:
            print(f"  - {info['title']}")
            print(f"    Student: {info['student_name']}")
            print(f"    Subject: {info['subject']}")
            print(f"    Priority: {info['priority']}, Status: {info['status']}")

        # Re-query threshold to avoid lazy loading
        result = await db.execute(
            select(InterventionThreshold).where(InterventionThreshold.name == "Test Performance Alert")
        )
        threshold_fresh = result.scalar_one_or_none()
        if threshold_fresh:
            print(f"\nThreshold configured: {threshold_fresh.name}")
            print(f"  - Min score: {threshold_fresh.min_score_percent}%")
            print(f"  - Weeks to review: {threshold_fresh.weeks_to_review}")
            print(f"  - Failures required: {threshold_fresh.failures_required}")

        print("\n--- Next Steps ---")
        print("1. Log in as teacher (timothymutegi@outlook.com)")
        print("2. Navigate to 'Intervention Alerts' in the sidebar")
        print("3. You should see pending alerts for your students")
        print("4. Test the Approve and Dismiss functionality")


if __name__ == "__main__":
    asyncio.run(main())
