#!/usr/bin/env python3
"""
Test script to verify configuration management is working correctly.
"""

import os
import sys

from dotenv import load_dotenv

# Explicitly load .env from the project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from config.settings import config


def test_config():
    """Test that configuration is loaded correctly."""
    print("=== Configuration Test ===")

    # Test API configuration
    print(f"API Base URL: {config.API_BASE_URL}")
    print(f"API Key: {'Set' if config.API_KEY else 'Not set'}")
    print(f"User Email: {config.USER_EMAIL}")

    # Test request settings
    print(f"Request Timeout: {config.REQUEST_TIMEOUT}")
    print(f"Default Delay: {config.DEFAULT_DELAY_SECONDS}")

    # Test retry configuration
    print(f"Park Search Max Retries: {config.PARK_SEARCH_MAX_RETRIES}")
    print(f"Park Search Retry Delay: {config.PARK_SEARCH_RETRY_DELAY}")
    print(f"Boundary Max Retries: {config.BOUNDARY_MAX_RETRIES}")
    print(f"Boundary Retry Delay: {config.BOUNDARY_RETRY_DELAY}")

    # Test database configuration
    print(f"DB Host: {config.DB_HOST}")
    print(f"DB Port: {config.DB_PORT}")
    print(f"DB Name: {config.DB_NAME}")
    print(f"DB User: {config.DB_USER}")
    print(f"DB Password: {'Set' if config.DB_PASSWORD else 'Not set'}")

    # Test file paths
    print(f"Default Input CSV: {config.DEFAULT_INPUT_CSV}")
    print(f"Default Output CSV: {config.DEFAULT_OUTPUT_CSV}")
    print(f"Default Output GPKG: {config.DEFAULT_OUTPUT_GPKG}")
    print(f"Log File: {config.NPS_LOG_FILE}")

    # Test logging configuration
    print(f"Log Level: {config.LOG_LEVEL}")
    print(f"Log Max Bytes: {config.LOG_MAX_BYTES}")
    print(f"Log Backup Count: {config.LOG_BACKUP_COUNT}")
    print(f"Rate Limit Warning Threshold: {config.RATE_LIMIT_WARNING_THRESHOLD}")
    print(f"API Result Limit: {config.API_RESULT_LIMIT}")
    print(f"Default CRS: {config.DEFAULT_CRS}")

    # Test database URL generation
    try:
        db_url = config.get_database_url()
        print(f"Database URL: {db_url}")
    except Exception as e:
        print(f"Database URL Error: {e}")

    print("=== Configuration Test Complete ===")


if __name__ == "__main__":
    test_config()
