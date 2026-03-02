import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path("logs")
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging(verbose: bool = False) -> None:
    """Configure Python logging for the entire application.

    - Root logger: WARNING level
    - jobhunter.* loggers: INFO (or DEBUG if verbose)
    - File handler: rotating, daily, 30-day retention, logs/ directory
    - Console handler: human-readable format
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)

    app_logger = logging.getLogger("jobhunter")
    app_logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    formatter = logging.Formatter(LOG_FORMAT)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    app_logger.addHandler(console_handler)

    # Rotating file handler (daily, 30-day retention)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOG_DIR / "jobhunter.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    app_logger.addHandler(file_handler)
