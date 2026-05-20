"""
app/platform/logger.py
----------------------
Structured Loguru-based logger for the Platform Intelligence layer.

Usage:
    from app.platform.logger import get_logger
    log = get_logger(__name__)
    log.info("Profiling table {table}", table="employees")
"""
from __future__ import annotations

import sys

from loguru import logger as _loguru_logger

# Remove Loguru's default stderr sink so we control the format ourselves.
_loguru_logger.remove()

# Add a clean, structured sink to stderr.
_loguru_logger.add(
    sys.stderr,
    level="INFO",
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level:<8}</level> | "
        "<cyan>{extra[module]:<40}</cyan> | "
        "<level>{message}</level>"
    ),
    colorize=True,
    backtrace=True,
    diagnose=True,
)


def get_logger(module_name: str):
    """
    Return a loguru logger bound to the given module name.

    Args:
        module_name: Typically ``__name__`` from the calling module.

    Returns:
        A loguru ``BoundLogger`` that includes ``module`` in every record.
    """
    return _loguru_logger.bind(module=module_name)
