from celery import Celery

import app.models  # noqa: F401
from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "ai_customer_service",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.knowledge"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
