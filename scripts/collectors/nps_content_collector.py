#!/usr/bin/env python3
"""
NPS Content Collector

Collects rich text content from the NPS API /thingstodo and /places endpoints
for all parks in the database. This content is used for semantic search via
the RAG pipeline.

Usage:
    # Test with one park
    python scripts/collectors/nps_content_collector.py --test-limit 1 --write-db

    # Full collection
    python scripts/collectors/nps_content_collector.py --write-db

    # Force refresh (re-collect all parks)
    python scripts/collectors/nps_content_collector.py --write-db --force-refresh
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import time

import pandas as pd
import requests
from pydantic import ValidationError
from sqlalchemy import Engine, text

# Add project root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from config.settings import config
from scripts.collectors.nps_content_schemas import (
    NPSPlaceResponse,
    NPSThingsToDoResponse,
)
from scripts.database.db_writer import DatabaseWriter, get_postgres_engine
from utils.exceptions import (
    ApiRequestError,
    NpsHikesError,
)
from utils.logging import setup_nps_content_collector_logging


class NPSContentCollector:
    """Collect things-to-do and places content from the NPS API."""

    def __init__(
        self,
        api_key: str | None = None,
        log_level: str | None = None,
        write_db: bool = False,
        engine: Engine | None = None,
    ) -> None:
        """Initialize the content collector.

        Args:
            api_key: NPS API key. If None, uses config.API_KEY.
            log_level: Logging level override.
            write_db: Whether to write results to the database.
            engine: SQLAlchemy engine. If None and write_db=True, creates one.
        """
        self.api_key: str | None = api_key or config.API_KEY
        self.base_url = config.API_BASE_URL
        self.logger = setup_nps_content_collector_logging(log_level)

        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Api-Key": self.api_key or "",
                "User-Agent": f"{config.APP_NAME}/{config.APP_VERSION} ({config.USER_EMAIL})",
            }
        )

        self.db_writer: DatabaseWriter | None = None
        if write_db:
            db_engine = engine or get_postgres_engine()
            self.db_writer = DatabaseWriter(db_engine, self.logger)

        self._completed_thingstodo: set[str] = set()
        self._completed_places: set[str] = set()
        if self.db_writer:
            self._completed_thingstodo = self.db_writer.get_completed_records(
                "nps_thingstodo", "park_code"
            )
            self._completed_places = self.db_writer.get_completed_records(
                "nps_places", "park_code"
            )

    def get_park_codes_from_db(self) -> list[str]:
        """Get all park codes from the parks table.

        Returns:
            Sorted list of park codes.
        """
        if not self.db_writer:
            raise ApiRequestError(
                "Database writer not initialized. Use --write-db flag.",
                context={"operation": "get_park_codes"},
            )

        try:
            with self.db_writer.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT park_code FROM parks ORDER BY park_code")
                )
                codes = [row[0] for row in result.fetchall()]
                self.logger.info(f"Found {len(codes)} parks in database")
                return codes
        except Exception as e:
            raise ApiRequestError(
                f"Failed to fetch park codes from database: {e}",
                context={"operation": "get_park_codes"},
            ) from e

    def fetch_thingstodo_for_park(self, park_code: str) -> list[dict]:
        """Fetch all things-to-do items for a park.

        Args:
            park_code: 4-character park code.

        Returns:
            List of validated thingstodo dicts.
        """
        endpoint = f"{self.base_url}{config.NPS_CONTENT_THINGSTODO_ENDPOINT}"
        all_items: list[dict] = []
        start = 0
        page_size = config.NPS_CONTENT_PAGE_SIZE

        while True:
            params = {
                "parkCode": park_code,
                "limit": page_size,
                "start": start,
            }

            response = self._make_request(endpoint, params)
            if response is None:
                break

            data = response.get("data", [])
            total = int(response.get("total", "0"))

            for item in data:
                try:
                    validated = NPSThingsToDoResponse.model_validate(item)
                    all_items.append(self._thingstodo_to_dict(validated, park_code))
                except ValidationError as e:
                    self.logger.warning(
                        f"Validation error for thingstodo item in {park_code}: {e}"
                    )

            start += page_size
            if start >= total:
                break

            time.sleep(0.5)

        return all_items

    def fetch_places_for_park(self, park_code: str) -> list[dict]:
        """Fetch all places for a park.

        Args:
            park_code: 4-character park code.

        Returns:
            List of validated places dicts.
        """
        endpoint = f"{self.base_url}{config.NPS_CONTENT_PLACES_ENDPOINT}"
        all_items: list[dict] = []
        start = 0
        page_size = config.NPS_CONTENT_PAGE_SIZE

        while True:
            params = {
                "parkCode": park_code,
                "limit": page_size,
                "start": start,
            }

            response = self._make_request(endpoint, params)
            if response is None:
                break

            data = response.get("data", [])
            total = int(response.get("total", "0"))

            for item in data:
                try:
                    validated = NPSPlaceResponse.model_validate(item)
                    all_items.append(self._place_to_dict(validated, park_code))
                except ValidationError as e:
                    self.logger.warning(
                        f"Validation error for place item in {park_code}: {e}"
                    )

            start += page_size
            if start >= total:
                break

            time.sleep(0.5)

        return all_items

    def _make_request(self, endpoint: str, params: dict) -> dict | None:
        """Make an HTTP request to the NPS API with retry logic.

        Args:
            endpoint: Full URL endpoint.
            params: Query parameters.

        Returns:
            JSON response dict, or None on failure.
        """
        for attempt in range(config.NPS_CONTENT_MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    endpoint,
                    params=params,
                    timeout=config.REQUEST_TIMEOUT,
                )

                # Log rate limit headers
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining is not None:
                    self.logger.debug(f"API rate limit remaining: {remaining}")

                response.raise_for_status()
                result: dict = response.json()
                return result

            except requests.exceptions.Timeout:
                self.logger.error(
                    f"Request timed out (attempt {attempt + 1}/{config.NPS_CONTENT_MAX_RETRIES + 1})"
                )
                if attempt == config.NPS_CONTENT_MAX_RETRIES:
                    return None
                time.sleep(config.NPS_CONTENT_RETRY_DELAY)

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else None
                if status_code is not None and status_code >= 500:
                    self.logger.error(
                        f"Server error {status_code} (attempt {attempt + 1}/"
                        f"{config.NPS_CONTENT_MAX_RETRIES + 1})"
                    )
                    if attempt == config.NPS_CONTENT_MAX_RETRIES:
                        return None
                    time.sleep(config.NPS_CONTENT_RETRY_DELAY)
                else:
                    self.logger.error(f"Client error {status_code}: {e}")
                    return None

            except requests.exceptions.RequestException as e:
                self.logger.error(f"Request failed: {e}")
                if attempt == config.NPS_CONTENT_MAX_RETRIES:
                    return None
                time.sleep(config.NPS_CONTENT_RETRY_DELAY)

        return None

    def _thingstodo_to_dict(self, item: NPSThingsToDoResponse, park_code: str) -> dict:
        """Convert a validated thingstodo response to a flat dict for DB storage."""
        lat = None
        if item.latitude and item.latitude != "":
            with contextlib.suppress(ValueError, TypeError):
                lat = float(item.latitude)

        lon = None
        if item.longitude and item.longitude != "":
            with contextlib.suppress(ValueError, TypeError):
                lon = float(item.longitude)

        return {
            "id": item.id,
            "park_code": park_code,
            "title": item.title,
            "short_description": item.short_description,
            "long_description": item.long_description,
            "activities": [a.get("name", "") for a in item.activities if a.get("name")],
            "topics": [t.get("name", "") for t in item.topics if t.get("name")],
            "tags": item.tags,
            "season": item.season,
            "duration": item.duration,
            "pets_description": item.pets_description,
            "fees_description": item.fee_description,
            "accessibility": item.accessibility_information,
            "location_description": None,
            "url": item.url,
            "latitude": lat,
            "longitude": lon,
        }

    def _place_to_dict(self, item: NPSPlaceResponse, park_code: str) -> dict:
        """Convert a validated place response to a flat dict for DB storage."""
        lat = None
        if item.latitude and item.latitude != "":
            with contextlib.suppress(ValueError, TypeError):
                lat = float(item.latitude)

        lon = None
        if item.longitude and item.longitude != "":
            with contextlib.suppress(ValueError, TypeError):
                lon = float(item.longitude)

        return {
            "id": item.id,
            "park_code": park_code,
            "title": item.title,
            "short_description": item.short_description,
            "body_text": item.body_text,
            "audio_description": item.audio_description,
            "tags": item.tags,
            "url": item.url,
            "latitude": lat,
            "longitude": lon,
        }

    def collect_all_content(
        self,
        test_limit: int | None = None,
        force_refresh: bool = False,
        delay: float = 1.0,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Collect thingstodo and places content for all parks.

        Args:
            test_limit: Limit to first N parks for testing.
            force_refresh: Re-collect all parks even if already done.
            delay: Delay in seconds between parks.

        Returns:
            Tuple of (thingstodo_df, places_df).
        """
        park_codes = self.get_park_codes_from_db()
        if test_limit:
            park_codes = park_codes[:test_limit]

        all_thingstodo: list[dict] = []
        all_places: list[dict] = []

        total = len(park_codes)
        for i, park_code in enumerate(park_codes, 1):
            # Check if already collected (both endpoints)
            thingstodo_done = (
                not force_refresh and park_code in self._completed_thingstodo
            )
            places_done = not force_refresh and park_code in self._completed_places

            if thingstodo_done and places_done:
                self.logger.debug(f"Skipping {park_code} - already collected")
                continue

            # Collect thingstodo
            thingstodo_items: list[dict] = []
            if not thingstodo_done:
                thingstodo_items = self.fetch_thingstodo_for_park(park_code)
                all_thingstodo.extend(thingstodo_items)

            # Collect places
            places_items: list[dict] = []
            if not places_done:
                places_items = self.fetch_places_for_park(park_code)
                all_places.extend(places_items)

            self.logger.info(
                f"Collected {len(thingstodo_items)} thingstodo and "
                f"{len(places_items)} places for {park_code} ({i}/{total})"
            )

            # Write per-park to DB for resumability
            if self.db_writer:
                if thingstodo_items:
                    thingstodo_df = pd.DataFrame(thingstodo_items)
                    self.db_writer.write_thingstodo(thingstodo_df)
                if places_items:
                    places_df = pd.DataFrame(places_items)
                    self.db_writer.write_places(places_df)

            if i < total:
                time.sleep(delay)

        result_thingstodo = (
            pd.DataFrame(all_thingstodo) if all_thingstodo else pd.DataFrame()
        )
        result_places = pd.DataFrame(all_places) if all_places else pd.DataFrame()

        self.logger.info(
            f"Collection complete: {len(all_thingstodo)} thingstodo, "
            f"{len(all_places)} places across {total} parks"
        )

        return result_thingstodo, result_places

    def save_results(
        self, thingstodo_df: pd.DataFrame, places_df: pd.DataFrame
    ) -> None:
        """Save collected content to CSV files.

        Args:
            thingstodo_df: Things-to-do DataFrame.
            places_df: Places DataFrame.
        """
        os.makedirs("artifacts", exist_ok=True)

        if not thingstodo_df.empty:
            path = "artifacts/nps_thingstodo_collected.csv"
            thingstodo_df.to_csv(path, index=False)
            self.logger.info(f"Saved {len(thingstodo_df)} thingstodo records to {path}")

        if not places_df.empty:
            path = "artifacts/nps_places_collected.csv"
            places_df.to_csv(path, index=False)
            self.logger.info(f"Saved {len(places_df)} places records to {path}")


def main() -> int:
    """Main entry point for the NPS content collector.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    parser = argparse.ArgumentParser(
        description="Collect content from NPS API /thingstodo and /places endpoints",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--test-limit",
        type=int,
        metavar="N",
        help="Limit processing to first N parks",
    )
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Write results to PostgreSQL database",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Reprocess all parks (ignore existing data)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between API calls in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )

    args = parser.parse_args()

    try:
        config.validate_for_api_operations()
        if args.write_db:
            config.validate_for_database_operations()

        collector = NPSContentCollector(
            log_level=args.log_level,
            write_db=args.write_db,
        )

        thingstodo_df, places_df = collector.collect_all_content(
            test_limit=args.test_limit,
            force_refresh=args.force_refresh,
            delay=args.delay,
        )

        collector.save_results(thingstodo_df, places_df)
        return 0

    except NpsHikesError as e:
        print(f"Error: {e!s}")
        if e.context:
            print(f"Context: {e.context}")
        return 1
    except KeyboardInterrupt:
        print("\nCollection interrupted by user")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e!s}")
        return 1


if __name__ == "__main__":
    exit(main())
