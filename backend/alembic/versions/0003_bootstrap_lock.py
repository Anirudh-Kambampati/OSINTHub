"""bootstrap lock singleton

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-10 09:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'bootstrap_lock',
        sa.Column('key', sa.String(length=32), nullable=False),
        sa.Column('allow_registration', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade() -> None:
    op.drop_table('bootstrap_lock')
