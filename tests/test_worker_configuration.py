from uuid import UUID

from app.infrastructure.database.base import Base
from app.workers.celery_app import celery_app
from app.workers.knowledge import _document_lock_id, ingest_knowledge_document


def test_ingestion_tasks_are_redelivered_and_retried_safely() -> None:
    assert "tenants" in Base.metadata.tables
    assert "ingestion_jobs" in Base.metadata.tables
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert ingest_knowledge_document.max_retries == 3
    assert ingest_knowledge_document.autoretry_for == (Exception,)


def test_document_lock_id_is_stable_and_tenant_scoped() -> None:
    tenant_a = UUID("00000000-0000-0000-0000-000000000001")
    tenant_b = UUID("00000000-0000-0000-0000-000000000002")
    document_id = UUID("00000000-0000-0000-0000-000000000003")

    first = _document_lock_id(tenant_a, document_id)

    assert first == _document_lock_id(tenant_a, document_id)
    assert first != _document_lock_id(tenant_b, document_id)
    assert -(2**63) <= first < 2**63
