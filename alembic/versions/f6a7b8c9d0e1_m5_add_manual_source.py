"""M5: Add 'manual' to RawJobPosting source CheckConstraint.

Enables manual job entry via the dashboard. The source column now accepts
'manual' in addition to the four scraper sources.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-09
"""

from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_raw_job_postings_source", "raw_job_postings", type_="check")
    op.create_check_constraint(
        "ck_raw_job_postings_source",
        "raw_job_postings",
        "source IN ('remote_io', 'remote_rocketship', 'wellfound', 'linkedin', 'manual')",
    )


def downgrade() -> None:
    # WARNING: Downgrade is unsupported once manual entries have been processed
    # through the pipeline. Downstream FK references will cause failures.
    # This downgrade only works on a clean database (no processed manual data).
    op.execute("DELETE FROM raw_job_postings WHERE source = 'manual'")
    op.drop_constraint("ck_raw_job_postings_source", "raw_job_postings", type_="check")
    op.create_check_constraint(
        "ck_raw_job_postings_source",
        "raw_job_postings",
        "source IN ('remote_io', 'remote_rocketship', 'wellfound', 'linkedin')",
    )
