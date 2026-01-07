# Five-Week Review Agent / Student Intervention System

**Date:** 2026-01-06
**Author:** Implementation by Claude Code
**Version:** 1.0

---

## Overview

The Five-Week Review Agent is an automated intervention system that monitors student performance across four subjects over academic weeks. When a student's performance falls below configured thresholds, the system generates alerts that require teacher approval before notifying parents.

### Key Features

- Analyzes performance over configurable review periods (default: 5 weeks)
- Tracks 4 subjects: Verbal Reasoning, Non-Verbal Reasoning, English, Mathematics
- Uses academic weeks (1-40, Friday-Wednesday cycle, starting September 5, 2025)
- Teacher approval workflow before parent notification
- Configurable thresholds by admin
- Audit logging for all actions

---

## System Architecture

### Data Flow

```
WeeklyPerformance Data
         │
         ▼
┌─────────────────────┐
│  Intervention Check │  (Scheduled or Manual)
│  - Reviews thresholds│
│  - Analyzes scores  │
└─────────────────────┘
         │
         ▼ (If threshold met)
┌─────────────────────┐
│  InterventionAlert  │  Status: PENDING
│  - Student info     │
│  - Subject          │
│  - Weekly scores    │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│  Teacher Dashboard  │
│  - Review alerts    │
│  - Approve/Dismiss  │
└─────────────────────┘
         │
         ▼ (If approved)
┌─────────────────────┐
│  Parent Notification│
│  - Email sent       │
│  - Alert: IN_PROGRESS│
└─────────────────────┘
```

---

## Database Models

### InterventionThreshold

Configurable thresholds that define when alerts are triggered.

| Field | Type | Description |
|-------|------|-------------|
| `name` | String | Threshold name |
| `subject` | String (nullable) | Specific subject or NULL for all |
| `min_score_percent` | Float | Score below this triggers alert (default: 50%) |
| `max_score_percent` | Float | Upper bound of concern range (default: 60%) |
| `weeks_to_review` | Integer | Number of weeks to analyze (default: 5) |
| `failures_required` | Integer | Weeks below threshold to trigger (default: 3) |
| `alert_priority` | Enum | LOW, MEDIUM, HIGH, CRITICAL |
| `notify_parent` | Boolean | Whether to notify parent |
| `notify_teacher` | Boolean | Whether to notify teacher |
| `is_active` | Boolean | Enable/disable threshold |

### WeeklyPerformance

Aggregated weekly performance data per student.

| Field | Type | Description |
|-------|------|-------------|
| `student_id` | UUID | Reference to student |
| `week_start` | Date | Start of the week |
| `week_end` | Date | End of the week |
| `week_number` | Integer | Academic week number (1-40) |
| `year` | Integer | Academic year |
| `average_score` | Float | Overall average score |
| `subject_scores` | JSONB | Per-subject breakdown |

**subject_scores format:**
```json
{
  "Verbal Reasoning": {"average": 45.0, "count": 2, "tests": ["Test A", "Test B"]},
  "Non-Verbal Reasoning": {"average": 38.0, "count": 2, "tests": ["Test A", "Test B"]},
  "English": {"average": 52.0, "count": 2, "tests": ["Test A", "Test B"]},
  "Mathematics": {"average": 41.0, "count": 2, "tests": ["Test A", "Test B"]}
}
```

### InterventionAlert

Generated alerts requiring teacher review.

| Field | Type | Description |
|-------|------|-------------|
| `student_id` | UUID | Reference to student |
| `threshold_id` | UUID | Reference to threshold that triggered |
| `subject` | String | Subject that triggered alert |
| `priority` | Enum | Alert priority level |
| `status` | Enum | PENDING, IN_PROGRESS, RESOLVED, DISMISSED |
| `current_average` | Float | Student's current average in subject |
| `weeks_failing` | Integer | Number of weeks below threshold |
| `weekly_scores` | JSONB | Weekly score breakdown |
| `approved_at` | DateTime | When teacher approved |
| `approved_by` | UUID | Teacher who approved |

---

## Academic Calendar

The system uses a custom academic calendar:

- **Academic Year Start:** September 5, 2025 (Friday)
- **Week Cycle:** Friday to Wednesday (6 days)
- **Total Weeks:** 40 weeks per year
- **Week 0:** Outside academic year

### AcademicCalendarService

```python
from app.services.academic_calendar_service import calendar_service

# Get current academic week
current_week = calendar_service.get_current_week()  # Returns 1-40 or 0

# Get week info
week_info = calendar_service.get_week_info(18)
# Returns: WeekInfo(week_number=18, start_date=date, end_date=date, ...)
```

---

## Intervention Check Logic

The intervention check runs through these steps:

1. **Get Active Thresholds**
   ```python
   thresholds = await self.get_all_thresholds(active_only=True)
   ```

2. **For Each Threshold, Check All Active Students**
   ```python
   for student in active_students:
       alert = await self._check_student_threshold(student, threshold)
   ```

3. **Check Student Against Threshold**
   - Get current academic week
   - Calculate review window (e.g., weeks 14-18 for 5-week review)
   - Fetch `WeeklyPerformance` records for the window
   - For each subject (or specific subject if threshold is subject-specific):
     - Count weeks where `subject_scores[subject]['average'] < min_score_percent`
     - If `weeks_failing >= failures_required`, create alert

4. **Prevent Duplicate Alerts**
   - Check if student already has PENDING or IN_PROGRESS alert for same subject
   - Only create new alert if no active alert exists

---

## API Endpoints

### Admin Threshold Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/interventions/thresholds` | Create threshold |
| GET | `/api/v1/interventions/thresholds` | List all thresholds |
| GET | `/api/v1/interventions/thresholds/{id}` | Get threshold |
| PUT | `/api/v1/interventions/thresholds/{id}` | Update threshold |
| DELETE | `/api/v1/interventions/thresholds/{id}` | Delete threshold |

### Teacher Intervention Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/admin/teachers/me/intervention/alerts` | List alerts for teacher's classes |
| GET | `/api/v1/admin/teachers/me/intervention/alerts/{id}` | Get alert detail |
| POST | `/api/v1/admin/teachers/me/intervention/alerts/{id}/approve` | Approve & notify parent |
| POST | `/api/v1/admin/teachers/me/intervention/alerts/{id}/dismiss` | Dismiss alert |
| GET | `/api/v1/admin/teachers/me/intervention/stats` | Get alert statistics |

---

## Teacher Approval Workflow

### 1. Teacher Views Pending Alerts

Teachers only see alerts for students in their assigned classes.

### 2. Teacher Reviews Alert

Alert shows:
- Student name, code, class
- Subject and current average
- Weeks failing
- Recommended actions

### 3. Teacher Approves or Dismisses

**Approve:**
- Alert status changes to `IN_PROGRESS`
- `approved_at` and `approved_by` are set
- Parent notification email is sent
- Audit log created

**Dismiss:**
- Alert status changes to `RESOLVED`
- Reason is logged
- No parent notification
- Audit log created

---

## Test Scripts

### setup_intervention_test_data.py

**Location:** `/scripts/setup_intervention_test_data.py`

**Purpose:** Creates test data to trigger intervention alerts without requiring actual test-taking.

**What it does:**

1. **Creates/Finds Intervention Threshold**
   ```python
   threshold = InterventionThreshold(
       name="Test Performance Alert",
       min_score_percent=50.0,
       weeks_to_review=5,
       failures_required=3,
       alert_priority=AlertPriority.HIGH,
       ...
   )
   ```

2. **Creates WeeklyPerformance Records**
   - For each student (tmbaka.gcp@gmail.com, mamafairapp@gmail.com)
   - Creates 5 weeks of data (current week minus 0-4)
   - First 4 weeks have LOW scores (35-50%) to trigger alerts
   - Last week has passing score (65%)
   - Subject scores are varied slightly per subject

3. **Runs Intervention Check**
   ```python
   service = InterventionService(db)
   alerts = await service.run_intervention_check()
   ```

**Usage:**
```bash
docker-compose -f docker-compose-dev.yml exec api python scripts/setup_intervention_test_data.py
```

**Sample Output:**
```
============================================================
Setting up Intervention Alert Test Data
============================================================

Using admin: support@ae-tuition.com

Found 2 students:
  - tmbaka.gcp@gmail.com (Code: 22222, Class: 7A)
  - mamafairapp@gmail.com (Code: 33333, Class: 6A)

--- Creating Intervention Threshold ---
Threshold already exists: Test Performance Alert (ID: ad603c4f-...)

--- Creating Weekly Performance Data ---
Student: tmbaka.gcp@gmail.com
  Current academic week: 18
  Created academic week 18 (2026-01-02 to 2026-01-07, avg: 35.0%)
  Created academic week 17 (2025-12-26 to 2025-12-31, avg: 40.0%)
  ...

--- Running Intervention Check ---
Created 6 new intervention alerts

============================================================
SUMMARY
============================================================
Total active alerts: 6
  - Performance Alert: Jane Doe - Verbal Reasoning
    Student: Jane Doe
    Subject: Verbal Reasoning
    Priority: high, Status: pending
  ...
```

### Important Notes About Test Data

1. **WeeklyPerformance vs TestResults**
   - The script creates `WeeklyPerformance` records directly
   - It does NOT create `TestAttempt` or `TestResult` records
   - This means test results won't appear in the admin test results view
   - This is intentional for quick intervention testing

2. **Academic Weeks**
   - Uses `AcademicCalendarService` for correct week numbers
   - Week numbers are academic weeks (1-40), not calendar weeks

3. **Score Generation**
   ```python
   # Week offset determines base score
   if week_offset < 4:  # First 4 weeks have low scores
       base_score = 35.0 + (week_offset * 5)  # 35%, 40%, 45%, 50%
   else:
       base_score = 65.0  # Last week passes
   ```

---

## Frontend Components

### Admin: Threshold Configuration

**Route:** `/admin/thresholds`
**Component:** `threshold-config.component.ts`

Allows admins to:
- Create new thresholds
- Edit existing thresholds
- Enable/disable thresholds
- Configure notification settings

### Teacher: Intervention Dashboard

**Route:** `/teacher/intervention`
**Component:** `teacher-intervention-dashboard.component.ts`

Features:
- Stats cards (Pending, In Progress, Resolved, Total)
- Filter by status
- Alert table with student info, subject, average, weeks failing
- Action buttons: View, Approve, Dismiss
- Approval modal with optional notes
- Dismiss modal with required reason

---

## Configuration

### Environment Variables

No specific environment variables for intervention system. Uses existing:
- `RESEND_API_KEY` - For sending parent notification emails
- `FROM_EMAIL` - Sender email address
- `FRONTEND_URL` - For links in emails

### Threshold Defaults

| Setting | Default | Description |
|---------|---------|-------------|
| `min_score_percent` | 50.0 | Score triggering concern |
| `max_score_percent` | 60.0 | Upper bound of concern |
| `weeks_to_review` | 5 | Review window |
| `failures_required` | 3 | Weeks failing to trigger |
| `alert_priority` | MEDIUM | Default priority |

---

## Troubleshooting

### Common Issues

1. **"Unknown Student" in dashboard**
   - Ensure `Student.user` relationship is eagerly loaded
   - Check that `get_teacher_alerts()` includes proper joinedloads

2. **Lazy loading errors (MissingGreenlet)**
   - Extract ORM object attributes BEFORE database operations
   - Use data dictionaries instead of passing ORM objects between methods

3. **No alerts created**
   - Check if threshold is active (`is_active=True`)
   - Verify `WeeklyPerformance` records exist for the review period
   - Check `subject_scores` JSONB contains the expected subjects

4. **Teacher can't see alerts**
   - Verify teacher has `TeacherClassAssignment` for student's class
   - Check student's `class_id` is set

### Debug Commands

```bash
# Check weekly performance data
docker-compose -f docker-compose-dev.yml exec api python -c "
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.intervention import WeeklyPerformance
import asyncio

async def check():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(WeeklyPerformance))
        for p in result.scalars().all():
            print(f'Student: {p.student_id}, Week: {p.week_number}, Avg: {p.average_score}')

asyncio.run(check())
"

# Check active alerts
docker-compose -f docker-compose-dev.yml exec api python -c "
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.intervention import InterventionAlert, AlertStatus
import asyncio

async def check():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(InterventionAlert).where(
                InterventionAlert.status.in_([AlertStatus.PENDING, AlertStatus.IN_PROGRESS])
            )
        )
        for a in result.scalars().all():
            print(f'Alert: {a.title}, Status: {a.status.value}')

asyncio.run(check())
"
```

---

## Future Enhancements

1. **Scheduled Daily Check**
   - APScheduler integration (module exists but not installed)
   - Run intervention check at midnight daily

2. **Email Templates**
   - Custom HTML email templates for teacher and parent notifications
   - Currently uses basic email format

3. **Dashboard Analytics**
   - Historical trend charts
   - Class-level intervention statistics

4. **Supervisor Notifications**
   - Optional supervisor alerts for high-priority interventions

---

## Files Reference

### Backend

| File | Description |
|------|-------------|
| `app/models/intervention.py` | Database models |
| `app/schemas/intervention.py` | Pydantic schemas |
| `app/services/intervention_service.py` | Core business logic |
| `app/services/academic_calendar_service.py` | Academic week calculations |
| `app/api/v1/intervention.py` | Admin endpoints |
| `app/api/v1/teacher.py` | Teacher endpoints (includes intervention) |
| `scripts/setup_intervention_test_data.py` | Test data generator |

### Frontend

| File | Description |
|------|-------------|
| `src/app/admin/components/threshold-config/` | Admin threshold UI |
| `src/app/teacher/components/teacher-intervention-dashboard/` | Teacher dashboard |
| `src/app/shared/interfaces/intervention.interface.ts` | TypeScript interfaces |
