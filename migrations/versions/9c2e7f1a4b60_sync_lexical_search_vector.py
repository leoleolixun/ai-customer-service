"""keep lexical search vectors synchronized

Revision ID: 9c2e7f1a4b60
Revises: 5a1e8c9d7b32
Create Date: 2026-07-17 05:20:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "9c2e7f1a4b60"
down_revision: str | None = "5a1e8c9d7b32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sync_knowledge_chunk_lexical_vector()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.lexical_vector := to_tsvector('simple'::regconfig, NEW.lexical_text);
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_sync_knowledge_chunk_lexical_vector
        BEFORE INSERT OR UPDATE OF lexical_text
        ON knowledge_chunks
        FOR EACH ROW
        EXECUTE FUNCTION sync_knowledge_chunk_lexical_vector()
        """
    )
    op.execute(
        """
        UPDATE knowledge_chunks
        SET lexical_vector = to_tsvector('simple'::regconfig, lexical_text)
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS trg_sync_knowledge_chunk_lexical_vector ON knowledge_chunks")
    op.execute("DROP FUNCTION IF EXISTS sync_knowledge_chunk_lexical_vector()")
