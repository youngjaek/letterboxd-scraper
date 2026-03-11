"""Add current_task_stage to cohorts

Revision ID: 202407111200
Revises:
Create Date: 2024-07-11 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "202407111200"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cohorts", sa.Column("current_task_stage", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("cohorts", "current_task_stage")
