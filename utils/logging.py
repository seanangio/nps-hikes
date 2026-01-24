"""
Centralized logging configuration for the NPS Hikes project.

This module provides a consistent logging setup that can be used across all
collection scripts and modules in the project. It handles both file and
console output with proper formatting and rotation.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from config.settings import Config


# Minimal fallback values only if config unavailable
class _FallbackConfig:
    LOG_LEVEL = "INFO"
    LOG_MAX_BYTES = 5 * 1024 * 1024
    LOG_BACKUP_COUNT = 3
    NPS_LOG_FILE = "logs/nps_collector.log"
    OSM_LOG_FILE = "logs/osm_collector.log"
    TNM_LOG_FILE = "logs/tnm_collector.log"


# Type annotation tells mypy this can be either Config or _FallbackConfig
config: Config | _FallbackConfig = _FallbackConfig()

# Try to import the real config, fall back to _FallbackConfig if import fails
try:
    from config.settings import config as imported_config

    config = imported_config
except Exception:
    pass  # Keep using fallback


def setup_logging(
    log_level: str | None = None,
    log_file: str | None = None,
    logger_name: str | None = None,
    max_bytes: int | None = None,
    backup_count: int | None = None,
) -> logging.Logger:
    """
    Configure logging for the application with both file and console output.

    This function sets up a logger with:
    - File output with rotation to prevent large log files
    - Console output for real-time monitoring
    - Consistent formatting across all modules
    - Proper handler cleanup to prevent duplicates

    Args:
        log_level (str, optional): Logging level (e.g., 'INFO', 'DEBUG', 'WARNING').
                                 If None, uses config.LOG_LEVEL
        log_file (str, optional): Path to log file. If None, uses a default based on logger_name
        logger_name (str, optional): Name for the logger. If None, uses root logger
        max_bytes (int, optional): Maximum bytes before log rotation. If None, uses config.LOG_MAX_BYTES
        backup_count (int, optional): Number of backup files to keep. If None, uses config.LOG_BACKUP_COUNT

    Returns:
        logging.Logger: Configured logger instance

    Example:
        >>> from utils.logging import setup_logging
        >>> logger = setup_logging('INFO', 'logs/my_script.log', 'my_script')
        >>> logger.info("This is a test message")
    """
    # Set defaults from config
    if log_level is None:
        log_level = config.LOG_LEVEL
    if max_bytes is None:
        max_bytes = config.LOG_MAX_BYTES
    if backup_count is None:
        backup_count = config.LOG_BACKUP_COUNT

    # Determine log file path
    if log_file is None:
        if logger_name == "nps_collector":
            log_file = config.NPS_LOG_FILE
        elif logger_name == "osm_collector":
            log_file = config.OSM_LOG_FILE
        elif logger_name == "tnm_collector":
            log_file = config.TNM_LOG_FILE
        else:
            log_file = f"logs/{logger_name or 'default'}.log"

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Get logger (root logger if no name specified)
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()

    # Set level
    logger.setLevel(getattr(logging, log_level.upper()))

    # Clear existing handlers to prevent duplicates
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler with rotation
    try:
        # Ensure log directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.info(f"Logging configured - Level: {log_level}, File: {log_file}")
    except Exception as e:
        logger.warning(f"Failed to setup file logging to {log_file}: {e}")
        logger.info("Continuing with console logging only")

    return logger


def setup_nps_collector_logging(log_level: str | None = None) -> logging.Logger:
    """
    Convenience function to set up logging specifically for nps_collector.py

    Args:
        log_level (str, optional): Logging level. If None, uses config default

    Returns:
        logging.Logger: Configured logger for NPS collector
    """
    return setup_logging(
        log_level=log_level, log_file=config.NPS_LOG_FILE, logger_name="nps_collector"
    )


def setup_osm_collector_logging(log_level: str | None = None) -> logging.Logger:
    """
    Convenience function to set up logging specifically for osm_hikes_collector.py

    Args:
        log_level (str, optional): Logging level. If None, uses config default

    Returns:
        logging.Logger: Configured logger for OSM collector
    """
    return setup_logging(
        log_level=log_level, log_file=config.OSM_LOG_FILE, logger_name="osm_collector"
    )


def setup_tnm_collector_logging(log_level: str | None = None) -> logging.Logger:
    """
    Convenience function to set up logging specifically for tnm_hikes_collector.py

    Args:
        log_level (str, optional): Logging level. If None, uses config default

    Returns:
        logging.Logger: Configured logger for TNM collector
    """
    return setup_logging(
        log_level=log_level, log_file=config.TNM_LOG_FILE, logger_name="tnm_collector"
    )
