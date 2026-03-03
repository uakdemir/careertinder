"""add settings table

Revision ID: a1b2c3d4e5f6
Revises: 78e4764af7b0
Create Date: 2026-03-03 12:00:00.000000

"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from jobhunter.config.schema import (
    FilteringConfig,
    NotificationsConfig,
    SchedulingConfig,
    ScrapingConfig,
)

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "78e4764af7b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Default settings seeded from Pydantic models
_DEFAULTS = {
    "scraping": ScrapingConfig().model_dump(),
    "filtering": FilteringConfig().model_dump(),
    "scheduling": SchedulingConfig().model_dump(),
    "notifications": NotificationsConfig().model_dump(),
}


def upgrade() -> None:
    """Create settings table and seed defaults."""
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category"),
    )

    # Note: scraper_runs CHECK constraints are defined in the ORM model but not
    # in the initial Alembic migration. SQLite enforces them at ORM level only.
    # The 'cancelled' status is already in models.py — no ALTER TABLE needed.

    # Seed default settings
    settings_table = sa.table(
        "settings",
        sa.column("category", sa.String),
        sa.column("settings_json", sa.Text),
        sa.column("updated_at", sa.DateTime),
    )
    for category, defaults in _DEFAULTS.items():
        op.execute(
            settings_table.insert().values(
                category=category,
                settings_json=json.dumps(defaults),
                updated_at=sa.func.now(),
            )
        )


def downgrade() -> None:
    """Drop settings table."""
    op.drop_table("settings")
