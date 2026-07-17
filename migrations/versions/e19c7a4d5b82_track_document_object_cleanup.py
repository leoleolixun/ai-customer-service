"""track document object cleanup

Revision ID: e19c7a4d5b82
Revises: d8423f1c6a20
Create Date: 2026-07-17 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e19c7a4d5b82"
down_revision: str | None = "d8423f1c6a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("object_cleanup_pending", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("object_cleanup_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("object_cleanup_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_knowledge_documents_object_cleanup",
        "knowledge_documents",
        ["object_cleanup_pending", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    pending_cleanup = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM knowledge_documents WHERE object_cleanup_pending = true")
    )
    if pending_cleanup:
        raise RuntimeError("cannot downgrade while knowledge document object cleanup is pending")
    op.drop_index("ix_knowledge_documents_object_cleanup", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "object_cleanup_error")
    op.drop_column("knowledge_documents", "object_cleanup_attempts")
    op.drop_column("knowledge_documents", "object_cleanup_pending")
