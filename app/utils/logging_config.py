from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.utils.paths import AppPaths


def configure_logging(paths: AppPaths, file_name: str = "application.log") -> None:
    """Configure application logging once in the selected writable data tree."""
    root_logger = logging.getLogger()
    if any(getattr(handler, "_yt_downloader_handler", False) for handler in root_logger.handlers):
        return

    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        paths.logs_dir / file_name,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler._yt_downloader_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
