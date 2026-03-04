"""m2 filter schema updates

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-04 10:00:00.000000

M2 changes:
- Add 'decision' column to filter_results (tri-state: pass/fail/ambiguous)
- Add unique constraint on filter_results.raw_id (one row per raw job)
- Add unique constraint on processed_jobs.raw_id
- Add index on processed_jobs.company_id
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply M2 schema changes."""
    # Add 'decision' column to filter_results
    with op.batch_alter_table("filter_results", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("decision", sa.String(20), nullable=True)
        )
        # Create unique index on raw_id for one-row-per-raw upsert strategy
        batch_op.create_index("ix_filter_results_raw_id", ["raw_id"], unique=True)
        # Create index on decision for dashboard filtering
        batch_op.create_index("ix_filter_results_decision", ["decision"], unique=False)

    # Backfill decision column based on passed boolean
    # Use dialect-agnostic boolean check (TRUE works for PostgreSQL, = 1 for SQLite)
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                UPDATE filter_results
                SET decision = CASE WHEN passed = TRUE THEN 'pass' ELSE 'fail' END
                WHERE decision IS NULL
                """
            )
        )
    else:
        # SQLite
        op.execute(
            sa.text(
                """
                UPDATE filter_results
                SET decision = CASE WHEN passed = 1 THEN 'pass' ELSE 'fail' END
                WHERE decision IS NULL
                """
            )
        )

    # Make decision NOT NULL after backfill
    with op.batch_alter_table("filter_results", schema=None) as batch_op:
        batch_op.alter_column(
            "decision",
            existing_type=sa.String(20),
            nullable=False,
        )

    # Add unique constraint on processed_jobs.raw_id
    with op.batch_alter_table("processed_jobs", schema=None) as batch_op:
        batch_op.create_index("ix_processed_jobs_raw_id", ["raw_id"], unique=True)
        batch_op.create_index("ix_processed_jobs_company_id", ["company_id"], unique=False)


def downgrade() -> None:
    """Revert M2 schema changes."""
    with op.batch_alter_table("processed_jobs", schema=None) as batch_op:
        batch_op.drop_index("ix_processed_jobs_company_id")
        batch_op.drop_index("ix_processed_jobs_raw_id")

    with op.batch_alter_table("filter_results", schema=None) as batch_op:
        batch_op.drop_index("ix_filter_results_decision")
        batch_op.drop_index("ix_filter_results_raw_id")
        batch_op.drop_column("decision")
