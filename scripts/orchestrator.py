#!/usr/bin/env python3
"""
Data Collection Orchestrator

This script orchestrates the complete data collection pipeline for the NPS Hikes project.
It runs all collection and processing scripts in the correct dependency order with proper
error handling and logging.

Pipeline Steps:
1. NPS Data Collection - Collect park metadata and boundaries (foundation)
2. OSM Trails Collection - Collect hiking trails from OpenStreetMap
3. TNM Trails Collection - Collect trails from The National Map
4. GMaps Import - Import Google Maps hiking locations
5. Trail Matching - Match GMaps locations to trail linestrings
6. Elevation Collection - Collect elevation data for matched trails

Usage:
    # Full pipeline
    python scripts/orchestrator.py --write-db

    # Test mode with limited parks
    python scripts/orchestrator.py --test-limit 3 --write-db

    # Dry run to see execution plan
    python scripts/orchestrator.py --dry-run --write-db

    # Help
    python scripts/orchestrator.py --help

Features:
- Sequential execution with dependency management
- Fail-fast error handling
- Pre-flight database connectivity checks
- Comprehensive logging and progress tracking
- Dry run support for testing
- Timeout protection for long-running processes
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from config.settings import config
from scripts.database.db_writer import get_postgres_engine
from utils.logging import setup_logging


class DataCollectionOrchestrator:
    """Orchestrate the complete data collection pipeline."""

    def __init__(self):
        """Initialize the orchestrator with logging and configuration."""
        self.logger = setup_logging(
            log_level=config.LOG_LEVEL,
            log_file=config.ORCHESTRATOR_LOG_FILE,
            logger_name="orchestrator",
        )
        self.start_time = time.time()

    def run_full_pipeline(
        self,
        test_limit: int | None = None,
        write_db: bool = False,
        dry_run: bool = False,
    ) -> bool:
        """
        Run the complete data collection pipeline.

        Args:
            test_limit: Limit processing to first N parks (for testing)
            write_db: Write results to database
            dry_run: Show execution plan without running commands

        Returns:
            bool: True if pipeline completed successfully, False otherwise
        """
        self.logger.info("🚀 Starting NPS Hikes Data Collection Pipeline")
        self.logger.info(
            f"Configuration: test_limit={test_limit}, write_db={write_db}, dry_run={dry_run}"
        )

        # Pre-flight checks
        if not dry_run and not self._pre_flight_checks(write_db):
            return False

        # Define pipeline steps with dependencies and test-limit support
        steps = [
            ("NPS Data Collection", "scripts/collectors/nps_collector.py", True),
            (
                "OSM Trails Collection",
                "scripts/collectors/osm_hikes_collector.py",
                True,
            ),
            (
                "TNM Trails Collection",
                "scripts/collectors/tnm_hikes_collector.py",
                True,
            ),
            ("GMaps Import", "scripts/collectors/gmaps_hiking_importer.py", False),
            (
                "Trail Matching",
                "scripts/processors/trail_matcher.py",
                False,
            ),  # Process all GMaps locations
            (
                "Elevation Collection",
                "scripts/collectors/usgs_elevation_collector.py",
                True,
            ),
        ]

        # Execute steps sequentially
        total_steps = len(steps)
        for i, (step_name, script_path, supports_test_limit) in enumerate(steps, 1):
            self.logger.info(f"📋 Step {i}/{total_steps}: {step_name}")

            # Only pass test_limit to scripts that support it
            effective_test_limit = test_limit if supports_test_limit else None

            if not self._run_step(
                step_name, script_path, effective_test_limit, write_db, dry_run
            ):
                self._log_failure_summary(step_name, i, total_steps)
                return False

            self.logger.info(f"✅ Completed: {step_name}")

            # Brief pause between steps to be respectful to systems
            if not dry_run and i < total_steps:
                time.sleep(2)

        self._log_success_summary(total_steps)
        return True

    def _pre_flight_checks(self, write_db: bool) -> bool:
        """
        Perform pre-flight checks before starting the pipeline.

        Args:
            write_db: Whether database operations will be performed

        Returns:
            bool: True if all checks pass, False otherwise
        """
        self.logger.info("🔍 Performing pre-flight checks...")

        # Check if we're in the correct directory
        if not os.path.exists("scripts/collectors/nps_collector.py"):
            self.logger.error("❌ Not in correct project directory - scripts not found")
            return False

        # Check database connectivity if needed
        if write_db:
            try:
                from sqlalchemy import text

                engine = get_postgres_engine()
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                self.logger.info("✅ Database connectivity verified")
            except Exception as e:
                self.logger.error(f"❌ Database connectivity check failed: {e!s}")
                self.logger.error(
                    "Please verify database configuration and connectivity"
                )
                return False

        # Check that log directory exists
        log_dir = os.path.dirname(config.ORCHESTRATOR_LOG_FILE)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            self.logger.info(f"📁 Created log directory: {log_dir}")

        self.logger.info("✅ All pre-flight checks passed")
        return True

    def _run_step(
        self,
        step_name: str,
        script_path: str,
        test_limit: int | None,
        write_db: bool,
        dry_run: bool,
    ) -> bool:
        """
        Run a single pipeline step.

        Args:
            step_name: Human-readable name of the step
            script_path: Path to the script to execute
            test_limit: Limit processing to first N parks
            write_db: Write results to database
            dry_run: Show command without executing

        Returns:
            bool: True if step completed successfully, False otherwise
        """
        # Build command
        cmd = ["python", script_path]

        # Add common arguments
        if test_limit:
            cmd.extend(["--test-limit", str(test_limit)])
        if write_db:
            cmd.append("--write-db")

        # Log the command
        cmd_str = " ".join(cmd)
        self.logger.info(f"Command: {cmd_str}")

        if dry_run:
            self.logger.info(f"[DRY RUN] Would execute: {cmd_str}")
            return True

        # Execute the command
        try:
            self.logger.info(f"⚙️  Executing: {step_name}")

            # Use longer timeout for elevation collection
            timeout = (
                config.ORCHESTRATOR_ELEVATION_TIMEOUT
                if "Elevation Collection" in step_name
                else config.ORCHESTRATOR_STEP_TIMEOUT
            )

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.path.join(
                    os.path.dirname(__file__), ".."
                ),  # Run from project root
            )

            if result.returncode == 0:
                self.logger.info(f"✅ {step_name} completed successfully")
                # Log any stdout output at debug level
                if result.stdout.strip():
                    self.logger.debug(f"Output from {step_name}:\n{result.stdout}")
                return True
            else:
                self.logger.error(
                    f"❌ {step_name} failed with exit code: {result.returncode}"
                )
                if result.stderr.strip():
                    self.logger.error(f"Error output:\n{result.stderr}")
                if result.stdout.strip():
                    self.logger.error(f"Standard output:\n{result.stdout}")
                return False

        except subprocess.TimeoutExpired:
            timeout_used = (
                config.ORCHESTRATOR_ELEVATION_TIMEOUT
                if "Elevation Collection" in step_name
                else config.ORCHESTRATOR_STEP_TIMEOUT
            )
            self.logger.error(f"❌ {step_name} timed out after {timeout_used} seconds")
            return False
        except Exception as e:
            self.logger.error(f"❌ {step_name} failed with exception: {e!s}")
            return False

    def _log_success_summary(self, total_steps: int) -> None:
        """Log pipeline success summary."""
        elapsed = time.time() - self.start_time
        elapsed_str = f"{elapsed:.1f} seconds"
        if elapsed > 60:
            elapsed_str = f"{elapsed / 60:.1f} minutes"

        self.logger.info("🎉 Pipeline completed successfully!")
        self.logger.info(f"📊 Summary: {total_steps}/{total_steps} steps completed")
        self.logger.info(f"⏱️  Total runtime: {elapsed_str}")
        self.logger.info("📋 All data collection and processing steps finished")

    def _log_failure_summary(
        self, failed_step: str, failed_at: int, total_steps: int
    ) -> None:
        """Log pipeline failure summary."""
        elapsed = time.time() - self.start_time
        elapsed_str = f"{elapsed:.1f} seconds"
        if elapsed > 60:
            elapsed_str = f"{elapsed / 60:.1f} minutes"

        self.logger.error("💥 Pipeline failed!")
        self.logger.error(f"❌ Failed at step {failed_at}/{total_steps}: {failed_step}")
        self.logger.error(f"⏱️  Runtime before failure: {elapsed_str}")
        self.logger.error("🔧 Check the logs above for detailed error information")
        self.logger.error(
            "💡 You can use scripts/database/reset_database.py to start fresh"
        )


def main() -> int:
    """
    Main function for the orchestrator script.

    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    parser = argparse.ArgumentParser(
        description="NPS Hikes Data Collection Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --write-db                    # Run full pipeline with database writes
  %(prog)s --test-limit 3 --write-db     # Test with 3 parks only
  %(prog)s --dry-run --write-db          # Show execution plan without running
  %(prog)s --help                        # Show this help message

Pipeline Steps:
  1. NPS Data Collection    - Collect park metadata and boundaries
  2. OSM Trails Collection  - Collect trails from OpenStreetMap
  3. TNM Trails Collection  - Collect trails from The National Map
  4. GMaps Import           - Import Google Maps hiking locations
  5. Trail Matching         - Match locations to trail linestrings
  6. Elevation Collection   - Collect elevation data for trails

Notes:
  - Pipeline runs sequentially with fail-fast behavior
  - Each step depends on data from previous steps
  - Use --test-limit for development and testing
  - Check logs/orchestrator.log for detailed progress
        """,
    )

    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Write results to PostgreSQL/PostGIS database (required for most use cases)",
    )

    parser.add_argument(
        "--test-limit",
        type=int,
        metavar="N",
        help="Limit processing to first N parks (for development/testing)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show execution plan without actually running commands",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.dry_run and not args.write_db:
        print("WARNING: Running without --write-db will only create file outputs.")
        print("Most pipeline steps require database data from previous steps.")
        print("Consider using --write-db for a complete pipeline run.")
        print()

    # Create and run orchestrator
    try:
        orchestrator = DataCollectionOrchestrator()
        success = orchestrator.run_full_pipeline(
            test_limit=args.test_limit,
            write_db=args.write_db,
            dry_run=args.dry_run,
        )
        return 0 if success else 1

    except KeyboardInterrupt:
        print("\n🛑 Pipeline interrupted by user")
        return 1
    except Exception as e:
        print(f"💥 Orchestrator failed with unexpected error: {e!s}")
        return 1


if __name__ == "__main__":
    exit(main())
