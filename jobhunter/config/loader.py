import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from jobhunter.config.schema import AppConfig, ConfigurationError, SecretsConfig

logger = logging.getLogger(__name__)


def load_config(config_path: Path = Path("config.yaml")) -> AppConfig:
    """Load and validate application configuration from YAML file.

    1. Read config.yaml
    2. Parse YAML into dict
    3. Validate with Pydantic (raises ConfigurationError on failure)
    4. Return frozen AppConfig instance
    """
    if not config_path.exists():
        raise ConfigurationError(
            f"config.yaml not found at {config_path}. Copy config.example.yaml and customize."
        )

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Failed to parse {config_path}: {e}") from e

    if raw is None:
        raw = {}

    try:
        config = AppConfig(**raw)
    except ValidationError as e:
        raise ConfigurationError(f"Configuration validation failed:\n{e}") from e

    logger.info("Configuration loaded from %s", config_path)
    return config


def load_secrets() -> SecretsConfig:
    """Load secrets from environment variables and .env file."""
    return SecretsConfig()
