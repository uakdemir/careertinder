import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path("logs")
ERROR_LOG_PATH = Path("tmp/error_logs.txt")
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging(verbose: bool = False) -> None:
    """Configure Python logging for the entire application.

    - Root logger: WARNING level
    - jobhunter.* loggers: INFO (or DEBUG if verbose)
    - File handler: rotating, daily, 30-day retention, logs/ directory
    - Error file handler: ERROR+ only, written to tmp/error_logs.txt
    - Console handler: human-readable format
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

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

    # Error-only file handler (tmp/error_logs.txt) for AI-assisted debugging
    error_handler = logging.FileHandler(
        filename=ERROR_LOG_PATH,
        mode="a",
        encoding="utf-8",
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    app_logger.addHandler(error_handler)
