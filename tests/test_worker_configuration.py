from app.infrastructure.database.base import Base
from app.workers.celery_app import celery_app
from app.workers.knowledge import ingest_knowledge_document


def test_ingestion_tasks_are_redelivered_and_retried_safely() -> None:
    assert "tenants" in Base.metadata.tables
    assert "ingestion_jobs" in Base.metadata.tables
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert ingest_knowledge_document.max_retries == 3
    assert ingest_knowledge_document.autoretry_for == (Exception,)
