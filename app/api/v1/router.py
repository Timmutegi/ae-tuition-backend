from fastapi import APIRouter

from .auth import router as auth_router
from .admin import router as admin_router
from .tests import router as tests_router
from .questions import router as questions_router
from .question_sets import router as question_sets_router
from .student import router as student_router
from .teacher import router as teacher_router
from .supervisor import router as supervisor_router
from .monitoring import router as monitoring_router
from .marking import router as marking_router
from .support import router as support_router
from .intervention import router as intervention_router
from .notification import router as notification_router
from .books import router as books_router
from .weekly_attendance import router as weekly_attendance_router

# Create main API router
api_router = APIRouter()

# Include all routers
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(admin_router, tags=["Admin"])
api_router.include_router(tests_router, prefix="/admin", tags=["Tests"])
api_router.include_router(questions_router, prefix="/admin", tags=["Questions"])
api_router.include_router(question_sets_router, prefix="/admin", tags=["Question Sets"])
api_router.include_router(student_router, tags=["Student"])
api_router.include_router(teacher_router, prefix="/admin", tags=["Teachers"])
api_router.include_router(supervisor_router, prefix="/admin", tags=["Supervisors"])
api_router.include_router(monitoring_router, prefix="/monitoring", tags=["Monitoring"])
api_router.include_router(marking_router, prefix="/marking", tags=["Marking"])
api_router.include_router(support_router, tags=["Support"])
api_router.include_router(intervention_router, tags=["Interventions"])
api_router.include_router(notification_router, tags=["Notifications"])
api_router.include_router(books_router, tags=["Books"])
api_router.include_router(weekly_attendance_router, tags=["Weekly Attendance"])