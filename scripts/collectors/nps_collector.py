"""
National Park Service API Data Collector

This module collects data for all official U.S. National Parks from the NPS API.
It fetches all NPS sites in bulk, filters for national parks by designation,
merges visit dates from a visit log CSV, and collects spatial boundary data.

The module handles the foundational data collection that
enables subsequent trail data collection from OSM and TNM sources.

Key Features:
- Bulk fetch of all national parks from NPS API with designation filtering
- Visit date tracking via CSV visit log (raw_data/park_visit_log.csv)
- Comprehensive park metadata collection (descriptions, coordinates, URLs, etc.)
- Spatial boundary data collection with proper geometry handling
- Data quality validation and coordinate verification
- Rate limiting to respect NPS API policies
- Comprehensive logging and progress tracking
- Dual output: CSV/GPKG files and PostgreSQL database

Data Processing Pipeline:
Stage 1 - Basic Park Data Collection:
1. Fetch all NPS sites from API using paginated bulk fetch
2. Filter for national parks by designation (National Park, National Park & Preserve, etc.)
3. Merge visit dates from visit log CSV using name matching
4. Save park data to CSV file and optionally to database
5. Extract valid park codes for boundary collection

Stage 2 - Spatial Boundary Data Collection:
6. Query NPS API for spatial boundary data for all national parks
7. Transform boundary geometries to standardized format (MultiPolygon)
8. Validate coordinate data and geometry quality
9. Save boundary data to GeoPackage file and optionally to database
10. Generate comprehensive collection summaries and validation reports
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from typing import cast

import geopandas as gpd
import pandas as pd
import requests
from dotenv import load_dotenv
from pydantic import ValidationError
from shapely.geometry import shape

# Load .env before local imports that need env vars
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from config.settings import config
from scripts.collectors.nps_schemas import (
    NPSBoundaryResponse,
    NPSParkResponse,
)
from scripts.database.db_writer import DatabaseWriter, get_postgres_engine
from utils.logging import setup_nps_collector_logging

logger = setup_nps_collector_logging()


class NPSDataCollector:
    """
    A class for collecting comprehensive National Park Service data.

    This class encapsulates functionality to query multiple NPS API endpoints
    and build structured datasets including basic park information and
    spatial boundary data.
    """

    def __init__(self, api_key: str | None = None):
        """
        Initialize the collector with API credentials.

        Args:
            api_key (str): NPS API key from the environment (optional, will use config if not provided)
        """
        self.api_key = api_key or config.API_KEY
        if not self.api_key:
            raise ValueError(
                "API key is required. Set NPS_API_KEY environment variable or pass api_key parameter."
            )

        self.base_url = config.API_BASE_URL
        self.rate_limit_warning_threshold = config.RATE_LIMIT_WARNING_THRESHOLD
        self.session = requests.Session()

        # Set up session headers that will be used for all requests
        self.session.headers.update(
            {
                "X-Api-Key": self.api_key,
                "User-Agent": f"{config.APP_NAME}/{config.APP_VERSION} ({config.USER_EMAIL})",
            }
        )

        logger.info("NPS Data Collector initialized successfully")

    # ====================================
    # STAGE 1: BASIC PARK DATA COLLECTION
    # ====================================

    def load_parks_from_csv(self, csv_path: str) -> pd.DataFrame:
        """
        Load the list of parks to process from a CSV file.

        Args:
            csv_path (str): Path to the CSV file containing park data

        Returns:
            pd.DataFrame: DataFrame containing park names and visit dates

        Raises:
            FileNotFoundError: If the CSV file doesn't exist
            ValueError: If the CSV doesn't have required columns
        """
        try:
            # Load the CSV with explicit error handling
            df = pd.read_csv(csv_path)
            logger.info(f"Successfully loaded CSV with {len(df)} parks")

            # Validate that we have the expected columns
            required_columns = ["park_name", "month", "year"]
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                raise ValueError(f"CSV missing required columns: {missing_columns}")

            # Remove any rows with missing park names
            original_count = len(df)
            df = df.dropna(subset=["park_name"])
            df = df[df["park_name"].str.strip() != ""]

            if len(df) < original_count:
                logger.warning(
                    f"Removed {original_count - len(df)} rows with missing park names"
                )

            return df

        except FileNotFoundError:
            logger.error(f"Could not find CSV file: {csv_path}")
            raise
        except Exception as e:
            logger.error(f"Error loading CSV file: {e!s}")
            raise

    def query_park_api(
        self,
        park_name: str,
        max_retries: int | None = None,
        retry_delay: float | None = None,
    ) -> dict | None:
        """
        Query the NPS API for a specific park using relevance-based search with retry logic.

        This method includes automatic retry logic for temporary server errors,
        using conservative retry settings since park data is critical for the pipeline.

        Args:
            park_name (str): Name of the park to search for
            max_retries (int): Maximum number of retry attempts for server errors
            retry_delay (float): Delay in seconds between retry attempts

        Returns:
            dict | None: Park data if found, None if not found or error occurred
        """
        # Use config defaults if not provided
        max_retries = max_retries or config.PARK_SEARCH_MAX_RETRIES
        retry_delay = retry_delay or config.PARK_SEARCH_RETRY_DELAY

        # Build the API endpoint URL and parameters once
        endpoint = f"{self.base_url}/parks"
        search_query = f"{park_name} National Park"
        params: dict[str, str | int] = {
            "q": search_query,
            "limit": config.API_RESULT_LIMIT,  # Get multiple results to find the best match
            "sort": "-relevanceScore",
            "fields": "addresses,contacts,description,directionsInfo,latitude,longitude,name,parkCode,states,url,fullName",
        }

        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                if attempt > 0:
                    logger.info(
                        f"Retry attempt {attempt}/{max_retries} for park '{park_name}' after {retry_delay}s delay"
                    )
                    time.sleep(retry_delay)

                logger.debug(
                    f"Querying API for park: '{park_name}' (searching for: '{search_query}') - attempt {attempt + 1}"
                )

                # Make the API request with timeout for reliability
                response = self.session.get(
                    endpoint, params=params, timeout=config.REQUEST_TIMEOUT
                )

                # Check if the request was successful
                response.raise_for_status()

                # Log rate limit information
                rate_limit_remaining = response.headers.get("X-RateLimit-Remaining")
                rate_limit_limit = response.headers.get("X-RateLimit-Limit")

                if rate_limit_remaining:
                    logger.info(
                        f"Rate limit status: {rate_limit_remaining}/{rate_limit_limit} requests remaining"
                    )

                    # Warn if getting close to the limit
                    if int(rate_limit_remaining) < self.rate_limit_warning_threshold:
                        logger.warning(
                            f"Approaching rate limit! Only {rate_limit_remaining} requests remaining"
                        )

                # Parse the JSON response
                data = response.json()

                # Validate that it returned data
                if "data" not in data or not data["data"]:
                    logger.warning(f"No results found for park: {park_name}")
                    return None

                # Find the best match using relevance score logic
                best_match = self._find_best_park_match(
                    data["data"], search_query, park_name
                )

                if best_match:
                    # Validate the API response with Pydantic before returning
                    try:
                        validated_park = NPSParkResponse(**best_match)
                        return validated_park.model_dump()
                    except ValidationError as e:
                        logger.error(
                            f"Invalid park data from API for '{park_name}': {e}"
                        )
                        return None
                else:
                    logger.warning(f"No suitable match found for park: {park_name}")
                    return None

            except requests.exceptions.Timeout:
                logger.error(
                    f"Park API request timed out for park: {park_name} (attempt {attempt + 1})"
                )
                if attempt == max_retries:
                    return None

            except requests.exceptions.HTTPError as e:
                if e.response.status_code >= 500:  # Server errors - retry
                    logger.warning(
                        f"Server error {e.response.status_code} for park '{park_name}' (attempt {attempt + 1}): {e!s}"
                    )
                    if attempt == max_retries:
                        logger.error(
                            f"Max retries exceeded for park '{park_name}' due to server errors"
                        )
                        return None
                else:  # Client errors (4xx) - don't retry
                    logger.error(
                        f"Client error {e.response.status_code} for park '{park_name}': {e!s}"
                    )
                    return None

            except requests.exceptions.RequestException as e:
                logger.error(
                    f"Network error for park '{park_name}' (attempt {attempt + 1}): {e!s}"
                )
                if attempt == max_retries:
                    return None

            except Exception as e:
                logger.error(f"Unexpected error querying park '{park_name}': {e!s}")
                return None

        return None

    def extract_park_data(
        self, park_api_data: dict, visit_data: pd.Series | dict | None = None
    ) -> dict:
        """
        Extract the specific fields needed from the API response.

        Args:
            park_api_data (Dict): Raw park data from the NPS API
            visit_data (pd.Series | Dict | None): Optional visit info with 'park_name', 'month', 'year'.
                If None, visit_month and visit_year will be NULL (unvisited park).

        Returns:
            Dict: Clean, structured park data for our dataset
        """
        # Extract basic park information with safe defaults
        extracted_data = {
            "park_name": park_api_data.get("fullName", ""),
            "visit_month": visit_data["month"] if visit_data is not None else None,
            "visit_year": visit_data["year"] if visit_data is not None else None,
            "park_code": park_api_data.get("parkCode", ""),
            "full_name": park_api_data.get("fullName", ""),
            "designation": park_api_data.get("designation", ""),
            "states": park_api_data.get("states", ""),
            "url": park_api_data.get("url", ""),
            "latitude": None,
            "longitude": None,
            "description": park_api_data.get("description", ""),
            "error_message": None,
            "collection_status": "success",
        }

        # Handle geographic coordinates with proper validation
        lat_raw = park_api_data.get("latitude")
        lon_raw = park_api_data.get("longitude")

        if lat_raw and lon_raw:
            # Use validation method to safely convert and validate coordinates
            validated_lat, validated_lon = self._validate_coordinates(
                lat_raw, lon_raw, extracted_data["full_name"]
            )
            extracted_data["latitude"] = validated_lat
            extracted_data["longitude"] = validated_lon
        else:
            # Log when coordinate data is missing
            if not lat_raw and not lon_raw:
                logger.info(
                    f"No coordinate data available for {extracted_data['full_name']}"
                )
            else:
                logger.warning(
                    f"Incomplete coordinate data for {extracted_data['full_name']}: lat={lat_raw}, lon={lon_raw}"
                )

        return extracted_data

    def fetch_all_national_parks(
        self,
        delay_seconds: float | None = None,
    ) -> list[dict]:
        """
        Fetch all National Parks from the NPS API using paginated bulk fetch.

        Queries all ~474 NPS sites and filters client-side for parks with
        designations matching the configured NPS_DESIGNATION_FILTERS list.

        Args:
            delay_seconds (float): Delay between paginated API calls

        Returns:
            List[Dict]: List of validated park data dictionaries for national parks
        """
        delay_seconds = delay_seconds or config.DEFAULT_DELAY_SECONDS
        limit = config.NPS_BULK_FETCH_LIMIT
        designation_filters = config.NPS_DESIGNATION_FILTERS
        additional_park_codes = config.NPS_ADDITIONAL_PARK_CODES

        logger.info("Fetching all NPS sites from API for national park filtering...")
        logger.info(f"Designation filters: {designation_filters}")
        logger.info(f"Additional park codes: {additional_park_codes}")

        all_parks = []
        start = 0
        total = None
        fields = "addresses,contacts,description,directionsInfo,latitude,longitude,name,parkCode,states,url,fullName,designation"

        while True:
            try:
                endpoint = f"{self.base_url}/parks"
                params: dict[str, str | int] = {
                    "limit": limit,
                    "start": start,
                    "fields": fields,
                }

                response = self.session.get(
                    endpoint, params=params, timeout=config.REQUEST_TIMEOUT
                )
                response.raise_for_status()
                data = response.json()

                if total is None:
                    total = int(data.get("total", 0))
                    logger.info(f"Total NPS sites in API: {total}")

                page_parks = data.get("data", [])
                if not page_parks:
                    break

                all_parks.extend(page_parks)
                logger.debug(
                    f"Fetched page {start // limit + 1}: {len(page_parks)} sites (total fetched: {len(all_parks)})"
                )

                start += limit
                if start >= total:
                    break

                # Rate limiting between pages
                time.sleep(delay_seconds)

            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching NPS sites (start={start}): {e!s}")
                break

        logger.info(f"Fetched {len(all_parks)} total NPS sites")

        # Filter for national parks by designation or explicit park code
        national_parks = []
        for park in all_parks:
            designation = park.get("designation", "")
            park_code = park.get("parkCode", "")
            if designation in designation_filters or park_code in additional_park_codes:
                # Validate through Pydantic schema
                try:
                    validated = NPSParkResponse(**park)
                    national_parks.append(validated.model_dump())
                except ValidationError as e:
                    logger.warning(
                        f"Invalid park data for '{park.get('fullName', 'unknown')}': {e}"
                    )

        # Log the complete filtered list for verification
        logger.info(f"Filtered to {len(national_parks)} national parks:")
        for park in sorted(national_parks, key=lambda p: p.get("fullName", "")):
            logger.info(
                f"  {park['parkCode']:5s}  {park['fullName']:<55s}  [{park.get('designation', '')}]"
            )

        return national_parks

    def merge_visit_dates(
        self,
        api_parks: list[dict],
        csv_path: str,
    ) -> list[dict]:
        """
        Merge visit dates from the visit log CSV into API-fetched park data.

        Uses name matching to associate CSV visit records with API parks.
        Parks without matching CSV entries get NULL visit_month/visit_year.

        Args:
            api_parks (List[Dict]): Park data from fetch_all_national_parks()
            csv_path (str): Path to the visit log CSV

        Returns:
            List[Dict]: Park data dicts with visit dates merged in
        """
        # Load visit log
        visit_df = self.load_parks_from_csv(csv_path)
        logger.info(f"Loaded {len(visit_df)} visit records from {csv_path}")

        # Build a lookup of API parks by fullName (lowered) for matching
        parks_by_name: dict[str, int] = {}
        for idx, park in enumerate(api_parks):
            full_name_lower = park.get("fullName", "").lower()
            parks_by_name[full_name_lower] = idx

        # Process each park through extract_park_data
        results = []
        matched_indices: set = set()

        for _, visit_row in visit_df.iterrows():
            csv_name = visit_row["park_name"]
            # Try matching by appending "National Park" and comparing to fullName
            search_name = f"{csv_name} National Park".lower()

            matched_idx = parks_by_name.get(search_name)

            # Try broader matching if exact match fails
            if matched_idx is None:
                # Search for parks whose fullName contains the CSV name
                for full_name_lower, idx in parks_by_name.items():
                    if csv_name.lower() in full_name_lower:
                        matched_idx = idx
                        break

            if matched_idx is not None:
                matched_indices.add(matched_idx)
                park_data = self.extract_park_data(api_parks[matched_idx], visit_row)
                results.append(park_data)
                logger.info(
                    f"Matched visit '{csv_name}' -> {api_parks[matched_idx]['fullName']}"
                )
            else:
                logger.warning(
                    f"Could not match visit record '{csv_name}' to any national park"
                )

        # Add unvisited parks (those not matched to any CSV entry)
        for idx, park in enumerate(api_parks):
            if idx not in matched_indices:
                park_data = self.extract_park_data(park)
                results.append(park_data)

        visited_count = len(matched_indices)
        unvisited_count = len(api_parks) - visited_count
        logger.info(
            f"Visit merge complete: {visited_count} visited, {unvisited_count} unvisited"
        )

        return results

    def process_park_data(
        self,
        csv_path: str,
        delay_seconds: float | None = None,
        limit_for_testing: int | None = None,
        force_refresh: bool = False,
        output_path: str | None = None,
    ) -> pd.DataFrame:
        """
        Main orchestration method that processes all parks and builds the final dataset.

        Fetches all national parks from the NPS API, merges visit dates from the
        visit log CSV, and returns a complete dataset of all national parks.

        Args:
            csv_path (str): Path to the visit log CSV file with park visit dates
            delay_seconds (float): Delay between API calls to be respectful
            limit_for_testing (int | None): For development/testing - limit to first N parks.
                                              None processes all parks (production default).
            force_refresh (bool): If True, reprocess all parks. If False, skip existing data.
            output_path (str): Path to output CSV file (used for incremental processing)

        Returns:
            pd.DataFrame: Complete dataset with all national park information
        """
        # Use config defaults if not provided
        delay_seconds = delay_seconds or config.DEFAULT_DELAY_SECONDS
        output_path = output_path or config.DEFAULT_OUTPUT_CSV

        logger.info("Starting park data collection process")

        # Handle incremental processing - load existing data to identify already-collected parks
        existing_data = pd.DataFrame()
        existing_park_codes = set()

        if not force_refresh and os.path.exists(output_path):
            try:
                existing_data = pd.read_csv(output_path)
                if not existing_data.empty and "park_code" in existing_data.columns:
                    existing_park_codes = set(existing_data["park_code"].tolist())
                logger.info(f"Found existing data with {len(existing_data)} records")
            except Exception as e:
                logger.warning(f"Could not load existing data from {output_path}: {e}")
                logger.info("Proceeding with full processing")
        elif force_refresh:
            logger.info("Force refresh mode: reprocessing all parks")

        # Step 1: Fetch all national parks from the NPS API
        api_parks = self.fetch_all_national_parks(delay_seconds=delay_seconds)

        if not api_parks:
            logger.error("No national parks retrieved from API")
            return existing_data if not existing_data.empty else pd.DataFrame()

        # FOR TESTING: Limit to specified number of parks
        if limit_for_testing is not None:
            api_parks = api_parks[:limit_for_testing]
            logger.info(f"TESTING MODE: Limited to first {limit_for_testing} parks")

        # Skip parks already in existing data
        if existing_park_codes:
            new_parks = [
                p for p in api_parks if p.get("parkCode", "") not in existing_park_codes
            ]
            skipped = len(api_parks) - len(new_parks)
            if skipped > 0:
                logger.info(f"Skipping {skipped} already collected parks")
            api_parks = new_parks

        if not api_parks:
            logger.info("No new parks to process")
            return existing_data

        # Step 2: Merge visit dates from CSV
        park_results = self.merge_visit_dates(api_parks, csv_path)

        # Step 3: Convert to DataFrame and deduplicate (handles seki case)
        combined_df = pd.DataFrame(park_results)
        # Replace NaN with None so PostgreSQL gets NULL instead of NaN
        # (pandas converts None to NaN for numeric columns like visit_year)
        combined_df = combined_df.where(combined_df.notna(), None)

        # Combine with existing data if any
        if not existing_data.empty:
            combined_df = pd.concat([existing_data, combined_df], ignore_index=True)
            logger.info(
                f"Combined {len(existing_data)} existing parks with "
                f"{len(park_results)} new parks"
            )

        combined_df = self._deduplicate_and_aggregate_parks(combined_df)

        logger.info(f"Final dataset: {len(combined_df)} parks")
        return combined_df

    def save_park_results(self, df: pd.DataFrame, output_path: str) -> None:
        """
        Save the collected data to a CSV file with proper error handling.

        Args:
            df (pd.DataFrame): The dataset to save
            output_path (str): Where to save the CSV file
        """
        try:
            df.to_csv(output_path, index=False)
            logger.info(f"Results saved to: {output_path}")
            logger.info(
                f"Dataset contains {len(df)} parks with {len(df.columns)} columns"
            )
        except Exception as e:
            logger.error(f"Failed to save results: {e!s}")
            raise

    # ==================================
    # STAGE 2: BOUNDARY DATA COLLECTION
    # ==================================

    def query_park_boundaries_api(
        self,
        park_code: str,
        max_retries: int | None = None,
        retry_delay: float | None = None,
    ) -> dict | None:
        """
        Query the NPS API for park boundary spatial data with retry logic.

        This method queries the mapdata/parkboundaries endpoint to retrieve
        geometric boundary information for a specific park. Includes automatic
        retry logic for temporary server errors.

        Args:
            park_code (str): NPS park code (e.g., 'zion', 'yell')
            max_retries (int): Maximum number of retry attempts for server errors
            retry_delay (float): Delay in seconds between retry attempts

        Returns:
            dict | None: Boundary data if found, None if not found or error occurred
        """
        # Use config defaults if not provided
        max_retries = max_retries or config.BOUNDARY_MAX_RETRIES
        retry_delay = retry_delay or config.BOUNDARY_RETRY_DELAY

        endpoint = f"{self.base_url}/mapdata/parkboundaries/{park_code}"

        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                if attempt > 0:
                    logger.info(
                        f"Retry attempt {attempt}/{max_retries} for park code '{park_code}' after {retry_delay}s delay"
                    )
                    time.sleep(retry_delay)

                logger.debug(
                    f"Querying boundary API for park code: '{park_code}' (attempt {attempt + 1})"
                )

                # Make the API request with timeout for reliability
                response = self.session.get(endpoint, timeout=config.REQUEST_TIMEOUT)

                # Check if the request was successful
                response.raise_for_status()

                # Log rate limit information
                rate_limit_remaining = response.headers.get("X-RateLimit-Remaining")
                rate_limit_limit = response.headers.get("X-RateLimit-Limit")

                if rate_limit_remaining:
                    logger.debug(
                        f"Rate limit status: {rate_limit_remaining}/{rate_limit_limit} requests remaining"
                    )

                    # Warn if getting close to the limit
                    if int(rate_limit_remaining) < config.RATE_LIMIT_WARNING_THRESHOLD:
                        logger.warning(
                            f"Approaching rate limit! Only {rate_limit_remaining} requests remaining"
                        )

                # Parse the JSON response
                data = response.json()

                # Validate boundary data with Pydantic schema
                if isinstance(data, dict):
                    try:
                        # Validate the GeoJSON structure
                        validated_boundary = NPSBoundaryResponse(**data)

                        # Check if FeatureCollection has any features
                        if (
                            validated_boundary.type == "FeatureCollection"
                            and not validated_boundary.features
                        ):
                            logger.warning(
                                f"No boundary features found for park code: {park_code}"
                            )
                            return None

                        logger.info(
                            f"Successfully retrieved boundary data for {park_code}"
                        )
                        return validated_boundary.model_dump()

                    except ValidationError as e:
                        logger.error(
                            f"Invalid boundary data from API for park code '{park_code}': {e}"
                        )
                        return None
                else:
                    logger.warning(
                        f"Invalid boundary data response for park code: {park_code}"
                    )
                    return None

            except requests.exceptions.Timeout:
                logger.error(
                    f"Boundary API request timed out for park code: {park_code} (attempt {attempt + 1})"
                )
                if attempt == max_retries:
                    return None

            except requests.exceptions.HTTPError as e:
                if e.response.status_code >= 500:  # Server errors - retry
                    logger.warning(
                        f"Server error {e.response.status_code} for park '{park_code}' (attempt {attempt + 1}): {e!s}"
                    )
                    if attempt == max_retries:
                        logger.error(
                            f"Max retries exceeded for park '{park_code}' due to server errors"
                        )
                        return None
                else:  # Client errors (4xx) - don't retry
                    logger.error(
                        f"Client error {e.response.status_code} for park '{park_code}': {e!s}"
                    )
                    return None

            except requests.exceptions.RequestException as e:
                logger.error(
                    f"Network error for park '{park_code}' (attempt {attempt + 1}): {e!s}"
                )
                if attempt == max_retries:
                    return None

            except Exception as e:
                logger.error(
                    f"Unexpected error querying boundaries for park '{park_code}': {e!s}"
                )
                return None

        return None

    def transform_boundary_data(self, boundary_api_data: dict, park_code: str) -> dict:
        """
        Transform the specific boundary fields needed from the API response.

        This method safely transforms geometric and metadata information from
        the park boundaries API response.

        Args:
            boundary_api_data (Dict): Raw boundary data from the NPS API
            park_code (str): Park code for reference and logging

        Returns:
            Dict: Clean, structured boundary data for our dataset
        """
        # Initialize with park code for reference
        extracted_data = {
            "park_code": park_code,
            "geometry": None,
            "geometry_type": None,
            "boundary_source": "NPS API",
            "error_message": None,
            "collection_status": "success",
            "bbox": None,  # Will be calculated if geometry is available
        }

        # The boundary data is now properly structured GeoJSON
        try:
            # Handle GeoJSON FeatureCollection
            if boundary_api_data.get("type") == "FeatureCollection":
                features = boundary_api_data.get("features", [])
                if features:
                    # Take the first feature (most parks have one main boundary)
                    first_feature = features[0]
                    geometry = first_feature.get("geometry")
                    if geometry:
                        extracted_data["geometry"] = geometry
                        extracted_data["geometry_type"] = geometry.get(
                            "type", "Unknown"
                        )
                        # Calculate bounding box
                        extracted_data["bbox"] = self.calculate_bounding_box(geometry)
                        logger.debug(
                            f"Extracted {geometry.get('type', 'Unknown')} geometry from FeatureCollection for {park_code}"
                        )
                    else:
                        logger.warning(
                            f"No geometry found in first feature for {park_code}"
                        )
                else:
                    logger.warning(
                        f"No features found in FeatureCollection for {park_code}"
                    )

            # Handle single GeoJSON Feature
            elif boundary_api_data.get("type") == "Feature":
                geometry = boundary_api_data.get("geometry")
                if geometry:
                    extracted_data["geometry"] = geometry
                    extracted_data["geometry_type"] = geometry.get("type", "Unknown")
                    # Calculate bounding box
                    extracted_data["bbox"] = self.calculate_bounding_box(geometry)
                    logger.debug(
                        f"Extracted {geometry.get('type', 'Unknown')} geometry from Feature for {park_code}"
                    )
                else:
                    logger.warning(f"No geometry found in Feature for {park_code}")

            # Handle direct geometry object
            elif "geometry" in boundary_api_data:
                geometry = boundary_api_data["geometry"]
                extracted_data["geometry"] = geometry
                extracted_data["geometry_type"] = geometry.get("type", "Unknown")
                # Calculate bounding box
                extracted_data["bbox"] = self.calculate_bounding_box(geometry)
                logger.debug(
                    f"Extracted {geometry.get('type', 'Unknown')} geometry from direct object for {park_code}"
                )

            else:
                logger.warning(f"Unrecognized boundary data structure for {park_code}")

        except Exception as e:
            logger.error(f"Error extracting boundary data for {park_code}: {e!s}")

        return extracted_data

    def calculate_bounding_box(self, geometry: dict) -> str | None:
        """
        Calculate bounding box from park geometry and return as string.

        Validates geometry using Shapely and attempts to fix invalid geometries
        (e.g., self-intersecting polygons) before calculating bounds.

        Args:
            geometry (Dict): GeoJSON geometry object

        Returns:
            str | None: Bounding box as "xmin,ymin,xmax,ymax" string, or None if calculation fails
        """
        try:
            from shapely.geometry import shape
            from shapely.validation import explain_validity

            # Convert GeoJSON to Shapely geometry
            shapely_geom = shape(geometry)

            # Validate geometry and attempt to fix if invalid
            if not shapely_geom.is_valid:
                validity_reason = explain_validity(shapely_geom)
                logger.warning(
                    f"Invalid geometry detected: {validity_reason}. Attempting to fix with buffer(0)"
                )

                # buffer(0) is a common fix for invalid geometries
                # It removes self-intersections and fixes topology issues
                shapely_geom = shapely_geom.buffer(0)

                if not shapely_geom.is_valid:
                    logger.error(
                        f"Failed to fix invalid geometry: {explain_validity(shapely_geom)}"
                    )
                    return None

                logger.info("Successfully repaired invalid geometry")

            # Get bounds (xmin, ymin, xmax, ymax)
            bounds = shapely_geom.bounds

            # Format as string
            bbox_string = f"{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}"

            logger.debug(f"Calculated bbox: {bbox_string}")
            return bbox_string

        except Exception as e:
            logger.warning(f"Failed to calculate bounding box: {e}")
            return None

    def process_park_boundaries(
        self,
        park_codes: list[str],
        delay_seconds: float | None = None,
        limit_for_testing: int | None = None,
        force_refresh: bool = False,
        output_path: str | None = None,
    ) -> gpd.GeoDataFrame:
        """
        Process boundary data for a list of park codes.

        This method queries the boundaries endpoint for each park code and
        builds a structured GeoDataFrame of spatial boundary information. Includes
        incremental processing to avoid re-processing existing boundary data.

        Args:
            park_codes (List[str]): List of NPS park codes to process boundaries for
            delay_seconds (float): Delay between API calls to be respectful
            limit_for_testing (int | None): Limit processing to first N codes for testing
            force_refresh (bool): If True, reprocess all boundaries. If False, skip existing data.
            output_path (str): Path to output GPKG file (used for incremental processing)

        Returns:
            gpd.GeoDataFrame: GeoDataFrame with boundary information for each park, including error records
        """
        # Use config defaults if not provided
        delay_seconds = delay_seconds or config.DEFAULT_DELAY_SECONDS
        output_path = output_path or config.DEFAULT_OUTPUT_GPKG

        logger.info("Starting park boundary data collection process")

        # FOR TESTING: Limit to specified number of park codes
        if limit_for_testing is not None:
            park_codes = park_codes[:limit_for_testing]
            logger.info(
                f"TESTING MODE: Limited to first {limit_for_testing} park codes"
            )

        # Handle incremental processing
        existing_data = gpd.GeoDataFrame()
        codes_to_process = park_codes.copy()

        if not force_refresh and os.path.exists(output_path):
            try:
                existing_data = gpd.read_file(output_path)
                logger.info(
                    f"Found existing boundary data with {len(existing_data)} records"
                )

                # Identify park codes that still need processing
                if not existing_data.empty and "park_code" in existing_data.columns:
                    existing_park_codes = set(existing_data["park_code"].tolist())
                    codes_to_process = [
                        code for code in park_codes if code not in existing_park_codes
                    ]

                    skipped_count = len(park_codes) - len(codes_to_process)
                    if skipped_count > 0:
                        logger.info(
                            f"Incremental processing: Skipping {skipped_count} boundaries already collected"
                        )
                        logger.info(
                            f"Processing {len(codes_to_process)} new/missing boundaries"
                        )
                    else:
                        logger.info(
                            "All boundaries already collected, no new processing needed"
                        )

            except Exception as e:
                logger.warning(
                    f"Could not load existing boundary data from {output_path}: {e}"
                )
                logger.info("Proceeding with full boundary processing")
                existing_data = gpd.GeoDataFrame()
                codes_to_process = park_codes.copy()
        elif force_refresh:
            logger.info("Force refresh mode: Processing all boundaries")
        else:
            logger.info("No existing boundary data found: Processing all boundaries")

        total_parks = len(codes_to_process)

        if total_parks == 0:
            logger.info("No boundaries to process")
            return existing_data if not existing_data.empty else gpd.GeoDataFrame()

        # Track all results including failures
        new_results = []

        # Process each park code with progress tracking
        for index, park_code in enumerate(codes_to_process):
            progress = f"({index + 1}/{total_parks})"

            logger.info(f"Processing boundary {progress}: {park_code}")

            # Query the boundaries API for this park
            boundary_data = self.query_park_boundaries_api(park_code)

            if boundary_data:
                # Transform the boundary data we need
                extracted = self.transform_boundary_data(boundary_data, park_code)
                new_results.append(extracted)
                logger.info(f"Successfully processed boundary for {park_code}")
            else:
                # Create error record to maintain complete dataset
                error_record = {
                    "park_code": park_code,
                    "geometry": None,
                    "geometry_type": None,
                    "boundary_source": "NPS API",
                    "error_message": "Failed to retrieve boundary data - see logs for details",
                    "collection_status": "failed",
                }
                new_results.append(error_record)
                logger.error(f"✗ Failed to process boundary for {park_code}")

            # Be respectful to the API with rate limiting
            if index < total_parks - 1:  # Don't delay after the last request
                time.sleep(delay_seconds)

        # Convert results to GeoDataFrame
        if new_results:
            # Convert GeoJSON geometries to Shapely objects
            geometries = []
            for result in new_results:
                if result["geometry"]:
                    try:
                        geom = shape(result["geometry"])  # Convert GeoJSON to Shapely
                        geometries.append(geom)
                    except Exception as e:
                        logger.warning(
                            f"Invalid geometry for {result['park_code']}: {e}"
                        )
                        geometries.append(None)
                else:
                    # Use empty geometry for failed records
                    geometries.append(None)

            # Create GeoDataFrame from results
            new_results_gdf = gpd.GeoDataFrame(
                data=[
                    {k: v for k, v in result.items() if k != "geometry"}
                    for result in new_results
                ],
                geometry=geometries,
                crs=config.DEFAULT_CRS,
            )

            # Report statistics for new processing
            successful_count = len(
                new_results_gdf[new_results_gdf["collection_status"] == "success"]
            )
            failed_count = len(
                new_results_gdf[new_results_gdf["collection_status"] == "failed"]
            )

            logger.info(
                f"New boundary collection complete: {successful_count} successful, {failed_count} failed"
            )

            if failed_count > 0:
                failed_codes = new_results_gdf[
                    new_results_gdf["collection_status"] == "failed"
                ]["park_code"].tolist()
                logger.warning(
                    f"Failed boundary collection for: {', '.join(failed_codes)}"
                )
        else:
            new_results_gdf = gpd.GeoDataFrame()

        # Combine existing data with new results
        if not existing_data.empty and not new_results_gdf.empty:
            # Combine existing and new data - ensure result is GeoDataFrame
            combined_gdf = gpd.GeoDataFrame(
                pd.concat([existing_data, new_results_gdf], ignore_index=True)
            )
            logger.info(
                f"Combined {len(existing_data)} existing boundary records with {len(new_results_gdf)} new records"
            )
        elif not new_results_gdf.empty:
            # Only new data
            combined_gdf = new_results_gdf
        else:
            # Only existing data (no new processing)
            combined_gdf = existing_data

        return combined_gdf

    def save_boundary_results(self, gdf: gpd.GeoDataFrame, output_path: str) -> None:
        """
        Save the collected boundary data to a GPKG file with proper error handling.

        This saves the GeoDataFrame directly to GeoPackage format, preserving
        the spatial geometry data and coordinate reference system.

        Args:
            gdf (gpd.GeoDataFrame): The boundary dataset to save
            output_path (str): Where to save the GPKG file
        """
        try:
            gdf.to_file(output_path, driver="GPKG")
            logger.info(f"Boundary results saved to: {output_path}")
            logger.info(f"GeoDataFrame contains {len(gdf)} parks with CRS: {gdf.crs}")
        except Exception as e:
            logger.error(f"Failed to save boundary results: {e!s}")
            raise

    # ===============
    # UTILITY METHODS
    # ===============

    def _find_best_park_match(
        self, park_results: list[dict], search_query: str, original_park_name: str
    ) -> dict | None:
        """
        Find the best matching park from API results using a tiered approach.

        Strategy:
        1. Look for exact fullName match with search query
        2. If no exact match, take the first result (highest relevance due to sorting)
        3. Log the matching decision for debugging

        Args:
            park_results (List[Dict]): List of park results from the API (pre-sorted by relevance)
            search_query (str): The actual query string sent to API
            original_park_name (str): Original park name from CSV for logging

        Returns:
            dict | None: Best matching park or None if no results
        """
        if not park_results:
            logger.warning(f"No results returned for '{original_park_name}'")
            return None

        # Strategy 1: Look for exact fullName match
        for park in park_results:
            park_full_name = park.get("fullName", "")
            if park_full_name == search_query:
                logger.info(
                    f"Found exact match for '{original_park_name}': '{park_full_name}'"
                )
                return park

        # Strategy 2: No exact match, so take the first result (highest relevance)
        best_park = park_results[0]
        best_score = best_park.get("relevanceScore", "N/A")
        best_name = best_park.get("fullName", "Unknown")

        logger.info(
            f"No exact match for '{original_park_name}'. Using highest relevance: '{best_name}' (score: {best_score})"
        )

        # Log other top candidates for debugging
        if len(park_results) > 1:
            logger.debug(f"Other candidates for '{original_park_name}':")
            for i, park in enumerate(park_results[1:4], 2):  # Show next 3 candidates
                candidate_name = park.get("fullName", "Unknown")
                candidate_score = park.get("relevanceScore", "N/A")
                logger.debug(f"  {i}. {candidate_name} (score: {candidate_score})")

        return best_park

    def _extract_valid_park_codes(self, park_data: pd.DataFrame) -> list[str]:
        """
        Extract valid, unique park codes from park data for boundary collection.

        This method safely extracts park codes, defensively removes duplicates to avoid potential for
        redundant API calls, and provides logging about the extraction process.
        """
        if park_data.empty:
            logger.warning("Park data is empty - no park codes available")
            return []

        if "park_code" not in park_data.columns:
            logger.warning(
                "Park data missing 'park_code' column - no park codes available"
            )
            return []

        # Get valid park codes (non-empty, non-null)
        valid_mask = park_data["park_code"].notna() & (park_data["park_code"] != "")
        total_parks_with_codes = valid_mask.sum()

        if total_parks_with_codes == 0:
            logger.warning("No valid park codes found in park data")
            return []

        # Remove duplicates to avoid redundant API calls
        unique_park_codes = cast(
            list[str],
            pd.Series(park_data[valid_mask]["park_code"]).drop_duplicates().tolist(),
        )

        # Log extraction results
        logger.info(
            f"Found {len(unique_park_codes)} unique park codes for boundary collection"
        )

        if total_parks_with_codes > len(unique_park_codes):
            duplicates_removed = total_parks_with_codes - len(unique_park_codes)
            logger.info(
                f"Removed {duplicates_removed} duplicate park codes to avoid redundant API calls"
            )

        return unique_park_codes

    def _validate_coordinates(
        self, lat_value: str, lon_value: str, park_name: str
    ) -> tuple[float | None, float | None]:
        """
        Convert validated coordinate strings to floats.

        Note: Coordinate validation (type checking and range validation) is
        performed by the Pydantic schema at the API boundary. This method
        simply converts the already-validated strings to float types for use
        in the data pipeline.

        Args:
            lat_value (str): Latitude value from API (already validated by Pydantic)
            lon_value (str): Longitude value from API (already validated by Pydantic)
            park_name (str): Park name for error logging context

        Returns:
            tuple[float | None, float | None]: Converted lat/lon or (None, None) if conversion fails
        """
        try:
            # Pydantic already validated these can be converted to float and are in valid ranges
            lat_float = float(lat_value)
            lon_float = float(lon_value)

            logger.debug(
                f"Converted coordinates for {park_name}: ({lat_float}, {lon_float})"
            )
            return lat_float, lon_float

        except (ValueError, TypeError) as e:
            # This should rarely happen since Pydantic validated the data first
            logger.warning(
                f"Unexpected coordinate conversion error for {park_name}: lat='{lat_value}', lon='{lon_value}' - {e!s}"
            )
            return None, None

    def _deduplicate_and_aggregate_parks(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Deduplicate and aggregate park records by park_code.

        Guidelines for writing this utility function:
        - Group by 'park_code'.
        - For 'park_name' and 'full_name', join unique non-null values with ' / '.
        - For all other columns (except 'error_message' and 'collection_status'), take the first non-null value.
        - For 'error_message' and 'collection_status', also take the first (these are status fields).
        - Return a DataFrame with one row per park_code.
        - If 'park_code' is missing or empty, drop those rows.

        This function is used both immediately after loading the CSV (to avoid redundant
        API calls and processing) and at the end of the pipeline (as a safety net to
        guarantee output integrity).
        """
        if df.empty or "park_code" not in df.columns:
            if isinstance(df, pd.DataFrame):
                return df
            else:
                return pd.DataFrame([df])
        # Drop rows with missing or empty park_code
        df = df[df["park_code"].notna() & (df["park_code"] != "")]

        def join_unique(series: pd.Series[str]) -> str:
            # Split any already-combined values and flatten the list
            all_values = []
            for x in series:
                if pd.notnull(x) and str(x).strip() != "":
                    # Split by " / " to handle already-combined values
                    values = str(x).split(" / ")
                    all_values.extend([v.strip() for v in values if v.strip()])

            # Remove duplicates and sort
            unique_values = sorted(set(all_values))
            return " / ".join(unique_values)

        # Type annotation: pandas agg accepts both callable functions and strings
        agg_dict: dict[str, Callable | str] = {}
        for col in df.columns:
            if col in ["park_code"]:
                continue
            elif col in ["park_name", "full_name"]:
                agg_dict[col] = join_unique
            else:
                agg_dict[col] = "first"
        result = df.groupby("park_code", as_index=False).agg(agg_dict)
        if isinstance(result, pd.DataFrame):
            return result
        else:
            return pd.DataFrame(result)

    def _print_collection_summary(
        self,
        park_data: pd.DataFrame,
        boundary_data: gpd.GeoDataFrame,
        park_output_csv: str,
        boundary_output_gpkg: str,
    ) -> None:
        """
        Print comprehensive summary of the data collection results.

        Args:
            park_data (pd.DataFrame): Collected park data
            boundary_data (gpd.GeoDataFrame): Collected boundary data
            park_output_csv (str): Path where park data was saved
            boundary_output_gpkg (str): Path where boundary data was saved
        """
        # User-friendly console output
        print("\n" + "=" * 60)
        print("COLLECTION SUMMARY")
        print("=" * 60)

        # Park data summary
        print("Basic park data:")
        print(f"  Parks processed: {len(park_data)}")
        print(f"  Output saved to: {park_output_csv}")

        # Boundary data summary
        if not boundary_data.empty:
            print("Boundary data:")
            print(f"  Boundaries processed: {len(boundary_data)}")
            print(f"  Output saved to: {boundary_output_gpkg}")
            print(f"  CRS: {boundary_data.crs}")
        else:
            print("Boundary data: No boundaries collected")

        # Also log the summary for audit trail
        logger.info("=" * 60)
        logger.info("COLLECTION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Parks processed: {len(park_data)}")
        logger.info(f"Park output saved to: {park_output_csv}")
        if not boundary_data.empty:
            logger.info(f"Boundaries processed: {len(boundary_data)}")
            logger.info(f"Boundary output saved to: {boundary_output_gpkg}")
            logger.info(f"CRS: {boundary_data.crs}")
        else:
            logger.info("No boundaries collected")
        logger.info("=" * 60)


def main() -> int | None:
    """
    Main function demonstrating the complete NPS data collection pipeline.

    This function orchestrates a two-stage data collection process:
    1. Collect basic park information from the parks endpoint
    2. Collect spatial boundary data using the park codes from stage 1

    Supports incremental processing to avoid re-collecting existing data.
    """
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(
        description="Collect National Park Service data from API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Process all parks, skip existing data
  %(prog)s --test-limit 3               # Test with first 3 parks only
  %(prog)s --force-refresh              # Reprocess all parks, overwrite existing
  %(prog)s --delay 2.0                  # Use 2 second delays between API calls
  %(prog)s --test-limit 5 --force-refresh  # Test mode with forced refresh
  %(prog)s --write-db                   # Write results directly to PostgreSQL/PostGIS database
  %(prog)s --truncate-parks             # Truncate parks table before writing to DB
  %(prog)s --truncate-boundaries        # Truncate park_boundaries table before writing to DB
  %(prog)s --truncate-hikes             # Truncate osm_hikes table before writing to DB
  %(prog)s --truncate-all               # Truncate all tables before writing to DB
  %(prog)s --db-name my_database       # Override the database name for PostgreSQL/PostGIS connection (default: use POSTGRES_DB env var or .env)
  %(prog)s --write-db --profile-data    # Write to DB and run all profiling modules
  %(prog)s --write-db --truncate-all    # Clear all tables and write fresh data
        """,
    )

    parser.add_argument(
        "--test-limit",
        type=int,
        metavar="N",
        help="Limit processing to first N parks (for development/testing)",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Reprocess all parks, overwriting existing data",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=config.DEFAULT_DELAY_SECONDS,
        metavar="SECONDS",
        help=f"Delay between API calls in seconds (default: {config.DEFAULT_DELAY_SECONDS})",
    )
    parser.add_argument(
        "--input-csv",
        default=config.DEFAULT_INPUT_CSV,
        metavar="FILE",
        help=f"Visit log CSV file with park visit dates (default: {config.DEFAULT_INPUT_CSV})",
    )
    parser.add_argument(
        "--park-output",
        default=config.DEFAULT_OUTPUT_CSV,
        metavar="FILE",
        help=f"Output CSV file for park data (default: {config.DEFAULT_OUTPUT_CSV})",
    )
    parser.add_argument(
        "--boundary-output",
        default=config.DEFAULT_OUTPUT_GPKG,
        metavar="FILE",
        help=f"Output GPKG file for boundary data (default: {config.DEFAULT_OUTPUT_GPKG})",
    )
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Write results directly to PostgreSQL/PostGIS database (optional)",
    )
    parser.add_argument(
        "--truncate-parks",
        action="store_true",
        help="Truncate parks table before writing to database",
    )
    parser.add_argument(
        "--truncate-boundaries",
        action="store_true",
        help="Truncate park_boundaries table before writing to database",
    )
    parser.add_argument(
        "--truncate-hikes",
        action="store_true",
        help="Truncate osm_hikes table before writing to database",
    )
    parser.add_argument(
        "--truncate-all",
        action="store_true",
        help="Truncate all tables (parks, park_boundaries, osm_hikes) before writing to database",
    )
    parser.add_argument(
        "--db-name",
        default=None,
        help="Override the database name for PostgreSQL/PostGIS connection (default: use POSTGRES_DB env var or .env)",
    )
    parser.add_argument(
        "--profile-data",
        action="store_true",
        help="Run data profiling queries after collection (requires database connection)",
    )

    args = parser.parse_args()

    # Optionally override the database name via CLI
    if args.db_name:
        os.environ["POSTGRES_DB"] = args.db_name
        logger.info(f"Overriding POSTGRES_DB to '{args.db_name}' via --db-name flag.")

    try:
        # Load environment variables from .env file
        load_dotenv()

        # Validate configuration based on operation type
        if args.write_db:
            # Need both API and database credentials when writing to DB
            config.validate_for_api_and_database_operations()
        else:
            # Only need API credentials for CSV output
            config.validate_for_api_operations()

        # Initialize NPS data collector (API key loaded from config)
        collector = NPSDataCollector()

        # Check that visit log CSV exists before starting
        if not os.path.exists(args.input_csv):
            logger.warning(
                f"Visit log file '{args.input_csv}' not found. "
                "All parks will be marked as unvisited."
            )

        # STAGE 1: Collect basic park data from NPS API
        logger.info("=" * 60)
        logger.info("STAGE 1: FETCHING ALL NATIONAL PARKS FROM NPS API")
        logger.info("=" * 60)

        park_data = collector.process_park_data(
            csv_path=args.input_csv,
            delay_seconds=args.delay,
            limit_for_testing=args.test_limit,
            force_refresh=args.force_refresh,
            output_path=args.park_output,
        )

        # Save park data results
        collector.save_park_results(park_data, args.park_output)

        # STAGE 2: Collect boundary data using park codes from stage 1
        logger.info("=" * 60)
        logger.info("STAGE 2: COLLECTING PARK BOUNDARY DATA")
        logger.info("=" * 60)

        # Initialize boundary_data to handle cases where it might not get created
        boundary_data = gpd.GeoDataFrame()

        # Extract valid park codes from successful park data collection
        valid_park_codes = collector._extract_valid_park_codes(park_data)

        if valid_park_codes:
            if args.force_refresh:
                logger.info("Force refresh mode: Will reprocess all boundaries")
            elif os.path.exists(args.boundary_output):
                logger.info(
                    f"Incremental mode: Will skip boundaries already in {args.boundary_output}"
                )
            else:
                logger.info(
                    "No existing boundary data found: Will process all boundaries"
                )

            # Process boundary data
            boundary_data = collector.process_park_boundaries(
                park_codes=valid_park_codes,
                delay_seconds=args.delay,
                limit_for_testing=args.test_limit,
                force_refresh=args.force_refresh,
                output_path=args.boundary_output,
            )

            # Save boundary results
            if not boundary_data.empty:
                collector.save_boundary_results(boundary_data, args.boundary_output)
            else:
                logger.warning("No boundary data was successfully collected")
        else:
            logger.warning(
                "Skipping boundary collection - no valid park codes available"
            )

        # Print comprehensive summary information
        collector._print_collection_summary(
            park_data, boundary_data, args.park_output, args.boundary_output
        )

        # Optional: Write to database if flag is set
        if args.write_db:
            logger.info(
                "Writing results to PostgreSQL/PostGIS database (via --write-db flag)..."
            )
            engine = get_postgres_engine()
            db_writer = DatabaseWriter(engine, logger)

            # Handle granular table truncation
            tables_to_truncate = []
            if args.truncate_all:
                tables_to_truncate = ["parks", "park_boundaries", "osm_hikes"]
                logger.info(
                    "Truncating all tables before DB write (via --truncate-all flag)..."
                )
            else:
                if args.truncate_parks:
                    tables_to_truncate.append("parks")
                if args.truncate_boundaries:
                    tables_to_truncate.append("park_boundaries")
                if args.truncate_hikes:
                    tables_to_truncate.append("osm_hikes")

                if tables_to_truncate:
                    logger.info(f"Truncating tables: {', '.join(tables_to_truncate)}")

            if tables_to_truncate:
                db_writer.truncate_tables(tables_to_truncate)

            db_writer.write_parks(park_data, mode="upsert")
            if not boundary_data.empty:
                db_writer.write_park_boundaries(boundary_data, mode="upsert")
            logger.info("Database write complete.")

        # Optional: Run data profiling if flag is set
        if args.profile_data:
            logger.info("Running data profiling queries (via --profile-data flag)...")
            try:
                from profiling.orchestrator import run_all_profiling

                run_all_profiling()
                logger.info("Data profiling complete.")
            except Exception as e:
                logger.error(f"Data profiling failed: {e!s}")
                print(f"WARNING: Data profiling failed - {e!s}")
                print(
                    "Profiling requires database connection and data to be written to DB."
                )

        logger.info("NPS data collection pipeline completed successfully")

    except Exception as e:
        logger.error(f"Pipeline execution failed: {e!s}")
        print(f"\nERROR: {e!s}")
        print(
            "Check the log file 'logs/nps_collector.log' for detailed error information."
        )
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
