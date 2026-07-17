"""harden knowledge retrieval

Revision ID: b719f2d0a641
Revises: 9c2e7f1a4b60
Create Date: 2026-07-17 10:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b719f2d0a641"
down_revision: str | None = "9c2e7f1a4b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "keyword_score_threshold",
            sa.Float(),
            server_default=sa.text("0.15"),
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column(
            "vector_similarity_threshold",
            sa.Float(),
            server_default=sa.text("0.72"),
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("source_locator", sa.String(length=1000), server_default="", nullable=False),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_dimension", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "disabled",
                name="knowledge_chunk_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="active",
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE knowledge_chunks AS chunk
        SET source_locator = COALESCE(document.source_url, document.source_filename),
            embedding_dimension = base.embedding_dimension
        FROM knowledge_documents AS document, knowledge_bases AS base
        WHERE document.id = chunk.document_id
          AND base.id = chunk.knowledge_base_id
        """
    )
    op.alter_column("knowledge_bases", "keyword_score_threshold", server_default=None)
    op.alter_column("knowledge_bases", "vector_similarity_threshold", server_default=None)
    op.alter_column("knowledge_chunks", "source_locator", server_default=None)
    op.alter_column("knowledge_chunks", "embedding_dimension", server_default=None)
    op.alter_column("knowledge_chunks", "status", server_default=None)


def downgrade() -> None:
    op.drop_column("knowledge_chunks", "status")
    op.drop_column("knowledge_chunks", "embedding_dimension")
    op.drop_column("knowledge_chunks", "source_locator")
    op.drop_column("knowledge_bases", "vector_similarity_threshold")
    op.drop_column("knowledge_bases", "keyword_score_threshold")
