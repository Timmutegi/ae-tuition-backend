from fastapi import APIRouter

from .auth import router as auth_router
from .admin import router as admin_router
from .tests import router as tests_router
from .questions import router as questions_router
from .question_sets import router as question_sets_router
from .student import router as student_router

# Create main API router
api_router = APIRouter()

# Include all routers
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(admin_router, tags=["Admin"])
api_router.include_router(tests_router, prefix="/admin", tags=["Tests"])
api_router.include_router(questions_router, prefix="/admin", tags=["Questions"])
api_router.include_router(question_sets_router, prefix="/admin", tags=["Question Sets"])
api_router.include_router(student_router, tags=["Student"])