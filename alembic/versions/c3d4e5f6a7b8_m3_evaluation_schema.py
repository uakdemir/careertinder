"""M3: Add is_current to match_evaluations, indexes, ai_cost settings seed.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-08
"""

import json

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_current column with server default so existing rows get TRUE
    op.add_column(
        "match_evaluations",
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # Performance indexes
    op.create_index("ix_match_evaluations_tier", "match_evaluations", ["tier_evaluated"])
    op.create_index("ix_match_evaluations_date", "match_evaluations", ["evaluated_at"])
    op.create_index(
        "ix_match_evaluations_current",
        "match_evaluations",
        ["job_id", "tier_evaluated", "is_current"],
    )

    # Partial unique indexes: enforce one current row per evaluation key
    # Tier 2: one current row per job (resume_id is NULL for Tier 2)
    op.execute(
        "CREATE UNIQUE INDEX uq_current_tier2 ON match_evaluations (job_id) "
        "WHERE tier_evaluated = 2 AND is_current = TRUE"
    )
    # Tier 3: one current row per (job, resume) pair
    op.execute(
        "CREATE UNIQUE INDEX uq_current_tier3 ON match_evaluations (job_id, resume_id) "
        "WHERE tier_evaluated = 3 AND is_current = TRUE"
    )

    # Seed ai_cost settings with defaults
    defaults = json.dumps({"daily_cap_usd": 2.0, "warn_at_percent": 0.8})
    op.execute(
        sa.text(
            "INSERT INTO settings (category, settings_json, updated_at) "
            "SELECT :cat, :json, CURRENT_TIMESTAMP "
            "WHERE NOT EXISTS (SELECT 1 FROM settings WHERE category = :cat)"
        ).bindparams(cat="ai_cost", json=defaults)
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_current_tier3")
    op.execute("DROP INDEX IF EXISTS uq_current_tier2")
    op.drop_index("ix_match_evaluations_current", table_name="match_evaluations")
    op.drop_index("ix_match_evaluations_date", table_name="match_evaluations")
    op.drop_index("ix_match_evaluations_tier", table_name="match_evaluations")
    op.drop_column("match_evaluations", "is_current")
    op.execute("DELETE FROM settings WHERE category = 'ai_cost'")
