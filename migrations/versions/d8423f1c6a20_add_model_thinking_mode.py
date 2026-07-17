"""add model thinking mode

Revision ID: d8423f1c6a20
Revises: b719f2d0a641
Create Date: 2026-07-17 19:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8423f1c6a20"
down_revision: str | None = "b719f2d0a641"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_model_configs",
        sa.Column(
            "thinking_mode",
            sa.Enum(
                "provider_default",
                "disabled",
                "enabled",
                name="thinking_mode",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="provider_default",
            nullable=False,
        ),
    )
    op.alter_column("ai_model_configs", "thinking_mode", server_default=None)


def downgrade() -> None:
    op.drop_column("ai_model_configs", "thinking_mode")
