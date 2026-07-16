"""store lexical search vector

Revision ID: 5a1e8c9d7b32
Revises: 0fd318a74cb9
Create Date: 2026-07-17 04:12:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

revision: str = "5a1e8c9d7b32"
down_revision: str | None = "0fd318a74cb9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.drop_index("ix_knowledge_chunks_lexical_gin", table_name="knowledge_chunks")
    column_type = TSVECTOR() if dialect == "postgresql" else sa.Text()
    op.add_column(
        "knowledge_chunks",
        sa.Column(
            "lexical_vector",
            column_type,
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    if dialect == "postgresql":
        op.execute(
            "UPDATE knowledge_chunks "
            "SET lexical_vector = to_tsvector('simple'::regconfig, lexical_text)"
        )
    else:
        op.execute("UPDATE knowledge_chunks SET lexical_vector = lexical_text")
    if dialect == "postgresql":
        op.alter_column("knowledge_chunks", "lexical_vector", server_default=None)
    else:
        with op.batch_alter_table("knowledge_chunks") as batch_op:
            batch_op.alter_column(
                "lexical_vector",
                existing_type=sa.Text(),
                server_default=None,
            )
    if dialect == "postgresql":
        op.create_index(
            "ix_knowledge_chunks_lexical_gin",
            "knowledge_chunks",
            ["lexical_vector"],
            unique=False,
            postgresql_using="gin",
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.drop_index("ix_knowledge_chunks_lexical_gin", table_name="knowledge_chunks")
    if dialect == "postgresql":
        op.drop_column("knowledge_chunks", "lexical_vector")
    else:
        with op.batch_alter_table("knowledge_chunks") as batch_op:
            batch_op.drop_column("lexical_vector")
    if dialect == "postgresql":
        op.execute(
            "CREATE INDEX ix_knowledge_chunks_lexical_gin ON knowledge_chunks "
            "USING gin (to_tsvector('simple'::regconfig, lexical_text))"
        )
