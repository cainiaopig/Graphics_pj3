"""Logging utilities for the pipeline."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logger(
    name: str = "blender_scene_agent",
    level: int = logging.INFO,
    log_file: str | Path | None = None,
) -> logging.Logger:
    """Create and configure a logger with console and optional file output.

    Args:
        name: Logger name.
        level: Logging level.
        log_file: Optional path to a log file.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Console handler with rich-compatible formatting
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console_fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console.setFormatter(console_fmt)
    logger.addHandler(console)

    # File handler (optional)
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(console_fmt)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "blender_scene_agent") -> logging.Logger:
    """Get or create the default logger.

    Args:
        name: Logger name.

    Returns:
        Logger instance.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger
