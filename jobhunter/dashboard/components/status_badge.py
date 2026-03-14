"""Colored status badges for scraper run statuses."""

# Mapping of status to (emoji, color label) for display
_STATUS_MAP: dict[str, tuple[str, str]] = {
    "success": ("✓", "green"),
    "partial_success": ("~", "orange"),
    "failed": ("✗", "red"),
    "timeout": ("⏱", "orange"),
    "blocked": ("🚫", "red"),
    "cancelled": ("⊘", "gray"),
    "running": ("●", "blue"),
}

# Source abbreviation mapping
SOURCE_ABBREV: dict[str, str] = {
    "linkedin": "LI",
    "wellfound": "WF",
    "remote_io": "RIO",
    "remote_rocketship": "RRS",
    "manual": "MAN",
}

# Full display names for sources
SOURCE_LABEL: dict[str, str] = {
    "linkedin": "LinkedIn",
    "wellfound": "Wellfound",
    "remote_io": "Remote.io",
    "remote_rocketship": "RemoteRocketship",
    "manual": "Manual",
}


def status_badge(status: str) -> str:
    """Return a styled status string with emoji prefix."""
    emoji, _color = _STATUS_MAP.get(status, ("?", "gray"))
    return f"{emoji} {status}"


def source_badge(source: str) -> str:
    """Return a short abbreviation for a scraper source name."""
    return SOURCE_ABBREV.get(source, source.upper())


def source_label(source: str) -> str:
    """Return the full display name for a scraper source."""
    return SOURCE_LABEL.get(source, source)
