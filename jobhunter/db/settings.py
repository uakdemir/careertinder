"""DS12 — DB-backed operational settings.

Each row represents one settings category (scraping, filtering, etc.).
Single JSON blob per category, validated by Pydantic on read/write.
"""

import json
import logging
from datetime import datetime

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from jobhunter.config.schema import (
    AICostConfig,
    FilteringConfig,
    NotificationsConfig,
    SchedulingConfig,
    ScrapingConfig,
)
from jobhunter.db.models import Base

logger = logging.getLogger(__name__)

# Category names used as keys in the settings table
CATEGORY_SCRAPING = "scraping"
CATEGORY_FILTERING = "filtering"
CATEGORY_SCHEDULING = "scheduling"
CATEGORY_NOTIFICATIONS = "notifications"
CATEGORY_AI_COST = "ai_cost"

# Map of category names to their Pydantic model classes
_CATEGORY_MODELS: dict[
    str, type[ScrapingConfig | FilteringConfig | SchedulingConfig | NotificationsConfig | AICostConfig]
] = {
    CATEGORY_SCRAPING: ScrapingConfig,
    CATEGORY_FILTERING: FilteringConfig,
    CATEGORY_SCHEDULING: SchedulingConfig,
    CATEGORY_NOTIFICATIONS: NotificationsConfig,
    CATEGORY_AI_COST: AICostConfig,
}


class SettingsEntry(Base):
    """DS12 — DB-backed operational settings.

    Each row represents one settings category (scraping, filtering, etc.).
    Single JSON blob per category, validated by Pydantic on read/write.
    """

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(50), unique=True)
    settings_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())


def get_settings(session: Session, category: str) -> dict:
    """Load and parse JSON for a settings category.

    Returns Pydantic defaults if the category is not found in the DB.
    """
    row = session.query(SettingsEntry).filter_by(category=category).first()
    if row is None:
        model_cls = _CATEGORY_MODELS.get(category)
        if model_cls is not None:
            logger.debug("Settings category '%s' not in DB, returning defaults", category)
            return model_cls().model_dump()
        return {}
    result: dict = json.loads(row.settings_json)
    return result


def update_settings(session: Session, category: str, data: dict) -> None:
    """Validate via Pydantic, serialize to JSON, and upsert a settings category."""
    model_cls = _CATEGORY_MODELS.get(category)
    if model_cls is not None:
        # Validate by constructing the Pydantic model (raises ValidationError on bad data)
        model_cls(**data)

    json_str = json.dumps(data)
    row = session.query(SettingsEntry).filter_by(category=category).first()
    if row is None:
        row = SettingsEntry(category=category, settings_json=json_str)
        session.add(row)
    else:
        row.settings_json = json_str
    session.flush()


def get_scraping_config(session: Session) -> ScrapingConfig:
    """Convenience wrapper that returns the typed ScrapingConfig."""
    data = get_settings(session, CATEGORY_SCRAPING)
    return ScrapingConfig(**data)


def get_filtering_config(session: Session) -> FilteringConfig:
    """Convenience wrapper that returns the typed FilteringConfig."""
    data = get_settings(session, CATEGORY_FILTERING)
    return FilteringConfig(**data)


def get_ai_cost_config(session: Session) -> AICostConfig:
    """Convenience wrapper that returns the typed AICostConfig."""
    data = get_settings(session, CATEGORY_AI_COST)
    return AICostConfig(**data)


def seed_defaults(session: Session) -> None:
    """Seed all settings categories with Pydantic defaults if not already present."""
    for category, model_cls in _CATEGORY_MODELS.items():
        existing = session.query(SettingsEntry).filter_by(category=category).first()
        if existing is None:
            defaults = model_cls().model_dump()
            row = SettingsEntry(
                category=category,
                settings_json=json.dumps(defaults),
            )
            session.add(row)
            logger.info("Seeded default settings for category '%s'", category)
    session.flush()
