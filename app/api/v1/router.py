from fastapi import APIRouter

from app.api.v1.admin_auth import router as admin_auth_router
from app.api.v1.applications import router as applications_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.handoffs import admin_router as admin_handoffs_router
from app.api.v1.handoffs import customer_router as customer_handoffs_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.members import router as members_router
from app.api.v1.model_gateway import router as model_gateway_router
from app.api.v1.platform import router as platform_router
from app.api.v1.usage import router as usage_router

router = APIRouter(prefix="/v1")
router.include_router(platform_router)
router.include_router(admin_auth_router)
router.include_router(applications_router)
router.include_router(conversations_router)
router.include_router(feedback_router)
router.include_router(customer_handoffs_router)
router.include_router(admin_handoffs_router)
router.include_router(knowledge_router)
router.include_router(members_router)
router.include_router(model_gateway_router)
router.include_router(usage_router)
