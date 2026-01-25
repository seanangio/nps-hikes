"""
National Park Service API Data Collector

This module provides a solution for collecting National Park Service (NPS)
data from the NPS API. It reads a list of parks from a CSV file, queries
multiple NPS API endpoints for each park to collect basic park information and
spatial boundary data, then creates structured datasets with comprehensive park metadata.

The module handles the foundational data collection that
enables subsequent trail data collection from OSM and TNM sources.

Key Features:
- Automated park discovery and data collection from NPS API
- Intelligent park name matching and fuzzy search capabilities
- Comprehensive park metadata collection (descriptions, coordinates, URLs, etc.)
- Spatial boundary data collection with proper geometry handling
- Data quality validation and coordinate verification
- Resumable collection runs for large datasets
- Rate limiting to respect NPS API policies
- Comprehensive logging and progress tracking
- Dual output: CSV/GPKG files and PostgreSQL database
- Error handling and retry logic for robust data collection

Data Processing Pipeline:
Stage 1 - Basic Park Data Collection:
1. Load park list from CSV file with visit dates and names
2. Query NPS API for basic park information using fuzzy name matching
3. Extract and validate comprehensive park metadata (descriptions, coordinates, URLs, etc.)
4. Save basic park data to CSV file and optionally to database
5. Extract valid park codes for boundary collection

Stage 2 - Spatial Boundary Data Collection:
6. Query NPS API for spatial boundary data using validated park codes from Stage 1
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
from typing import Callable, Dict, List, Tuple, cast

import geopandas as gpd
import pandas as pd
import requests
from dotenv import load_dotenv
from shapely.geometry import Point, shape

# Load .env before local imports that need env vars
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from config.settings import config
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
            logger.error(f"Error loading CSV file: {str(e)}")
            raise

    def query_park_api(
        self,
        park_name: str,
        max_retries: int | None = None,
        retry_delay: float | None = None,
    ) -> dict | None:
        """
        Query the NPS API for a specific park using fuzzy matching with retry logic.

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
        params: Dict[str, str | int] = {
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
                    return best_match
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
                        f"Server error {e.response.status_code} for park '{park_name}' (attempt {attempt + 1}): {str(e)}"
                    )
                    if attempt == max_retries:
                        logger.error(
                            f"Max retries exceeded for park '{park_name}' due to server errors"
                        )
                        return None
                else:  # Client errors (4xx) - don't retry
                    logger.error(
                        f"Client error {e.response.status_code} for park '{park_name}': {str(e)}"
                    )
                    return None

            except requests.exceptions.RequestException as e:
                logger.error(
                    f"Network error for park '{park_name}' (attempt {attempt + 1}): {str(e)}"
                )
                if attempt == max_retries:
                    return None

            except Exception as e:
                logger.error(f"Unexpected error querying park '{park_name}': {str(e)}")
                return None

        return None

    def extract_park_data(self, park_api_data: Dict, original_data: pd.Series) -> Dict:
        """
        Extract the specific fields needed from the API response.

        Args:
            park_api_data (Dict): Raw park data from the NPS API
            original_data (pd.Series): Original row from CSV with visit info

        Returns:
            Dict: Clean, structured park data for our dataset
        """
        # Extract basic park information with safe defaults
        extracted_data = {
            "park_name": original_data["park_name"],
            "visit_month": original_data["month"],
            "visit_year": original_data["year"],
            "park_code": park_api_data.get("parkCode", ""),
            "full_name": park_api_data.get("fullName", ""),
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

        This method includes complete error tracking and incremental processing
        to avoid unnecessary API calls for existing data.

        Args:
            csv_path (str): Path to the CSV file with park names
            delay_seconds (float): Delay between API calls to be respectful
            limit_for_testing (int | None): For development/testing - limit to first N parks.
                                              None processes all parks (production default).
            force_refresh (bool): If True, reprocess all parks. If False, skip existing data.
            output_path (str): Path to output CSV file (used for incremental processing)

        Returns:
            pd.DataFrame: Complete dataset with all park information, including error records
        """
        # Use config defaults if not provided
        delay_seconds = delay_seconds or config.DEFAULT_DELAY_SECONDS
        output_path = output_path or config.DEFAULT_OUTPUT_CSV

        logger.info("Starting park data collection process")

        # Load park list
        parks_df = self.load_parks_from_csv(csv_path)

        # EARLY DEDUPLICATION: Remove duplicate parks by park_code immediately after loading CSV.
        # Aggregate park_name/full_name and take the first for other fields.
        parks_df = self._deduplicate_and_aggregate_parks(parks_df)

        # FOR TESTING: Limit to specified number of parks
        if limit_for_testing is not None:
            parks_df = parks_df.head(limit_for_testing)
            logger.info(f"TESTING MODE: Limited to first {limit_for_testing} parks")

        # Handle incremental processing
        existing_data = pd.DataFrame()
        parks_to_process = parks_df.copy()

        if not force_refresh and os.path.exists(output_path):
            try:
                existing_data = pd.read_csv(output_path)
                logger.info(f"Found existing data with {len(existing_data)} records")

                # Identify parks that still need processing
                if not existing_data.empty and "park_name" in existing_data.columns:
                    # Check if existing data has been deduplicated (has combined park names)
                    has_combined_names = (
                        existing_data["park_name"].str.contains(" / ").any()
                    )

                    if has_combined_names:
                        logger.info(
                            "Found existing data with deduplicated park names. Processing all parks to ensure consistency."
                        )
                        parks_to_process = parks_df.copy()
                    else:
                        # Original logic for non-deduplicated data
                        existing_park_names = list(existing_data["park_name"].tolist())
                        parks_to_process = parks_df[
                            ~parks_df["park_name"].isin(existing_park_names)
                        ]

                        skipped_count = len(parks_df) - len(parks_to_process)
                        if skipped_count > 0:
                            logger.info(
                                f"Incremental processing: Skipping {skipped_count} parks already collected"
                            )
                            logger.info(
                                f"Processing {len(parks_to_process)} new/missing parks"
                            )
                        else:
                            logger.info(
                                "All parks already collected, no new processing needed"
                            )

            except Exception as e:
                logger.warning(f"Could not load existing data from {output_path}: {e}")
                logger.info("Proceeding with full processing")
                existing_data = pd.DataFrame()
                parks_to_process = parks_df.copy()
        elif force_refresh:
            logger.info("Force refresh mode: Processing all parks")
        else:
            logger.info("No existing data found: Processing all parks")

        total_parks = len(parks_to_process)

        if total_parks == 0:
            logger.info("No parks to process")
            return existing_data if not existing_data.empty else pd.DataFrame()

        # Track all results including failures
        new_results = []

        # Process each park with progress tracking
        for index, (_, park_row) in enumerate(parks_to_process.iterrows()):
            park_name = park_row["park_name"]
            progress = f"({index + 1}/{total_parks})"

            logger.info(f"Processing {progress}: {park_name}")

            # Query the API for this park
            park_data = self.query_park_api(park_name)

            if park_data:
                # Extract the data needed
                extracted = self.extract_park_data(park_data, park_row)
                new_results.append(extracted)
                logger.info(f"✓ Successfully processed {park_name}")
            else:
                # Create error record to maintain complete dataset
                error_record = {
                    "park_name": park_row["park_name"],
                    "visit_month": park_row["month"],
                    "visit_year": park_row["year"],
                    "park_code": "",
                    "full_name": "",
                    "states": "",
                    "url": "",
                    "latitude": None,
                    "longitude": None,
                    "description": "",
                    "error_message": "Failed to retrieve park data - see logs for details",
                    "collection_status": "failed",
                }
                new_results.append(error_record)
                logger.error(f"✗ Failed to process {park_name}")

            # Be respectful to the API with rate limiting
            if index < total_parks - 1:  # Don't delay after the last request
                time.sleep(delay_seconds)

        # Combine existing data with new results
        if not existing_data.empty and new_results:
            # Combine existing and new data
            new_results_df = pd.DataFrame(new_results)
            combined_df = pd.concat([existing_data, new_results_df], ignore_index=True)
            logger.info(
                f"Combined {len(existing_data)} existing records with {len(new_results)} new records"
            )
        elif new_results:
            # Only new data
            combined_df = pd.DataFrame(new_results)
        else:
            # Only existing data (no new processing)
            combined_df = existing_data

        # FINAL DEDUPLICATION: As a safety net, deduplicate and aggregate again at the end for output integrity.
        combined_df = self._deduplicate_and_aggregate_parks(combined_df)
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
            logger.error(f"Failed to save results: {str(e)}")
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

                # Validate boundary data - boundaries endpoint returns GeoJSON directly
                if isinstance(data, dict):
                    # Check for GeoJSON FeatureCollection format
                    if data.get("type") == "FeatureCollection" and "features" in data:
                        if data["features"]:  # Has features
                            logger.info(
                                f"Successfully retrieved boundary data for {park_code}"
                            )
                            return data
                        else:
                            logger.warning(
                                f"No boundary features found for park code: {park_code}"
                            )
                            return None
                    # Check for single Feature format
                    elif data.get("type") == "Feature":
                        logger.info(
                            f"Successfully retrieved boundary data for park code: {park_code}"
                        )
                        return data
                    # Check for direct geometry
                    elif "geometry" in data:
                        logger.info(
                            f"Successfully retrieved boundary data for park code: {park_code}"
                        )
                        return data
                    else:
                        logger.warning(
                            f"Unexpected boundary data format for park code: {park_code}"
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
                        f"Server error {e.response.status_code} for park '{park_code}' (attempt {attempt + 1}): {str(e)}"
                    )
                    if attempt == max_retries:
                        logger.error(
                            f"Max retries exceeded for park '{park_code}' due to server errors"
                        )
                        return None
                else:  # Client errors (4xx) - don't retry
                    logger.error(
                        f"Client error {e.response.status_code} for park '{park_code}': {str(e)}"
                    )
                    return None

            except requests.exceptions.RequestException as e:
                logger.error(
                    f"Network error for park '{park_code}' (attempt {attempt + 1}): {str(e)}"
                )
                if attempt == max_retries:
                    return None

            except Exception as e:
                logger.error(
                    f"Unexpected error querying boundaries for park '{park_code}': {str(e)}"
                )
                return None

        return None

    def transform_boundary_data(self, boundary_api_data: Dict, park_code: str) -> Dict:
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
            logger.error(f"Error extracting boundary data for {park_code}: {str(e)}")

        return extracted_data

    def calculate_bounding_box(self, geometry: Dict) -> str | None:
        """
        Calculate bounding box from park geometry and return as string.

        Args:
            geometry (Dict): GeoJSON geometry object

        Returns:
            str | None: Bounding box as "xmin,ymin,xmax,ymax" string, or None if calculation fails
        """
        try:
            from shapely.geometry import shape

            # Convert GeoJSON to Shapely geometry
            shapely_geom = shape(geometry)

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
        park_codes: List[str],
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
            logger.error(f"Failed to save boundary results: {str(e)}")
            raise

    # ===============
    # UTILITY METHODS
    # ===============

    def _find_best_park_match(
        self, park_results: List[Dict], search_query: str, original_park_name: str
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

    def _extract_valid_park_codes(self, park_data: pd.DataFrame) -> List[str]:
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
        Validate and convert coordinate values to proper floats.

        This method handles the common issues with geographic coordinate data:
        conversion errors, invalid ranges, and missing values.

        Args:
            lat_value (str): Raw latitude value from API
            lon_value (str): Raw longitude value from API
            park_name (str): Park name for error logging context

        Returns:
            tuple[float | None, float | None]: Validated lat/lon or (None, None) if invalid
        """
        try:
            # Convert to float
            lat_float = float(lat_value)
            lon_float = float(lon_value)

            # Validate geographic ranges
            if not (-90 <= lat_float <= 90):
                logger.warning(
                    f"Invalid latitude {lat_float} for {park_name} (must be between -90 and 90)"
                )
                return None, None

            if not (-180 <= lon_float <= 180):
                logger.warning(
                    f"Invalid longitude {lon_float} for {park_name} (must be between -180 and 180)"
                )
                return None, None

            logger.debug(
                f"Valid coordinates for {park_name}: ({lat_float}, {lon_float})"
            )
            return lat_float, lon_float

        except (ValueError, TypeError) as e:
            logger.warning(
                f"Could not parse coordinates for {park_name}: lat='{lat_value}', lon='{lon_value}' - {str(e)}"
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

        def join_unique(series):
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
        agg_dict: Dict[str, Callable | str] = {}
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
        print(f"Basic park data:")
        print(f"  Parks processed: {len(park_data)}")
        print(f"  Output saved to: {park_output_csv}")

        # Boundary data summary
        if not boundary_data.empty:
            print(f"Boundary data:")
            print(f"  Boundaries processed: {len(boundary_data)}")
            print(f"  Output saved to: {boundary_output_gpkg}")
            print(f"  CRS: {boundary_data.crs}")
        else:
            print(f"Boundary data: No boundaries collected")

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


def main():
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
        help=f"Input CSV file with park data (default: {config.DEFAULT_INPUT_CSV})",
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

        # Check that input file exists before starting
        if not os.path.exists(args.input_csv):
            raise FileNotFoundError(
                f"Input file '{args.input_csv}' not found. Please create this file with your park data."
            )

        # STAGE 1: Collect basic park data
        logger.info("=" * 60)
        logger.info("STAGE 1: COLLECTING BASIC PARK DATA")
        logger.info("=" * 60)

        if args.force_refresh:
            logger.info("Force refresh mode: Will reprocess all parks")
        elif os.path.exists(args.park_output):
            logger.info(
                f"Incremental mode: Will skip parks already in {args.park_output}"
            )
        else:
            logger.info("No existing data found: Will process all parks")

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
                logger.error(f"Data profiling failed: {str(e)}")
                print(f"WARNING: Data profiling failed - {str(e)}")
                print(
                    "Profiling requires database connection and data to be written to DB."
                )

        logger.info("NPS data collection pipeline completed successfully")

    except Exception as e:
        logger.error(f"Pipeline execution failed: {str(e)}")
        print(f"\nERROR: {str(e)}")
        print(
            "Check the log file 'logs/nps_collector.log' for detailed error information."
        )
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
