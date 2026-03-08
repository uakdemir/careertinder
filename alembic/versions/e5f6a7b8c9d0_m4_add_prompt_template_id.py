"""M4: Add prompt_template_id to cover_letters and why_company_answers.

Tracks which prompt template was used for content generation,
enabling prompt versioning and quality analysis.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-08
"""

import sqlalchemy as sa

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cover_letters", sa.Column("prompt_template_id", sa.String(), nullable=True))
    op.add_column("why_company_answers", sa.Column("prompt_template_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("why_company_answers", "prompt_template_id")
    op.drop_column("cover_letters", "prompt_template_id")
