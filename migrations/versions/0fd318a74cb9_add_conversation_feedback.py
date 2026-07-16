"""add conversation feedback

Revision ID: 0fd318a74cb9
Revises: 826b5b312653
Create Date: 2026-07-17 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0fd318a74cb9"
down_revision: str | None = "826b5b312653"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_feedback",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("end_user_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column(
            "rating",
            sa.Enum(
                "helpful",
                "unhelpful",
                name="feedback_rating",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["end_user_id"], ["end_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "message_id"),
    )
    op.create_index(
        "ix_conversation_feedback_application_id",
        "conversation_feedback",
        ["application_id"],
    )
    op.create_index(
        "ix_conversation_feedback_conversation_id",
        "conversation_feedback",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_feedback_end_user_id",
        "conversation_feedback",
        ["end_user_id"],
    )
    op.create_index(
        "ix_conversation_feedback_message_id",
        "conversation_feedback",
        ["message_id"],
    )
    op.create_index(
        "ix_conversation_feedback_tenant_id",
        "conversation_feedback",
        ["tenant_id"],
    )
    op.create_index(
        "ix_feedback_tenant_created",
        "conversation_feedback",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_tenant_created", table_name="conversation_feedback")
    op.drop_index("ix_conversation_feedback_tenant_id", table_name="conversation_feedback")
    op.drop_index("ix_conversation_feedback_message_id", table_name="conversation_feedback")
    op.drop_index("ix_conversation_feedback_end_user_id", table_name="conversation_feedback")
    op.drop_index("ix_conversation_feedback_conversation_id", table_name="conversation_feedback")
    op.drop_index("ix_conversation_feedback_application_id", table_name="conversation_feedback")
    op.drop_table("conversation_feedback")
