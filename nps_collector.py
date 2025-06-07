"""
National Park Service API Data Collector

This reads a list of parks from a CSV file, queries the NPS API for each park
to collect basic park information and spatial boundary data, then creates
structured datasets with comprehensive park information.
"""

import requests
import pandas as pd
import os
import time
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

# Set up rotating log files
file_handler = RotatingFileHandler(
    'nps_collector.log',
    maxBytes=5*1024*1024,  # 5MB per file
    backupCount=3  # Keep 3 old files
)

# Configure logging for debugging and monitoring
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        file_handler,
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class NPSDataCollector:
    """
    A class for collecting comprehensive National Park Service data.
    
    This class encapsulates functionality to query multiple NPS API endpoints
    and build structured datasets including basic park information and 
    spatial boundary data.
    """
    
    def __init__(self, api_key: str):
        """
        Initialize the collector with API credentials.
        
        Args:
            api_key (str): Your NPS API key from the environment
        """
        self.api_key = api_key
        self.base_url = "https://developer.nps.gov/api/v1"
        self.session = requests.Session()  # Reuse connections for efficiency
        
        # Set up session headers that will be used for all requests
        self.session.headers.update({
            'X-Api-Key': self.api_key,
            'User-Agent': 'Python-NPS-Collector/1.0 (sean.angiolillo@gmail.com)'
        })
        
        logger.info("NPS Data Collector initialized successfully")
    
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
            required_columns = ['park_name', 'month', 'year']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                raise ValueError(f"CSV missing required columns: {missing_columns}")
            
            # Remove any rows with missing park names
            original_count = len(df)
            df = df.dropna(subset=['park_name'])
            
            if len(df) < original_count:
                logger.warning(f"Removed {original_count - len(df)} rows with missing park names")
            
            return df
            
        except FileNotFoundError:
            logger.error(f"Could not find CSV file: {csv_path}")
            raise
        except Exception as e:
            logger.error(f"Error loading CSV file: {str(e)}")
            raise
    
    def query_park_api(self, park_name: str) -> Optional[Dict]:
        """
        Query the NPS API for a specific park using fuzzy matching.
        
        Args:
            park_name (str): Name of the park to search for
            
        Returns:
            Optional[Dict]: Park data if found, None if not found or error occurred
        """
        try:
            # Build the API endpoint URL
            endpoint = f"{self.base_url}/parks"
            
            # Set up query parameters for fuzzy matching
            search_query = f"{park_name} National Park"
            params = {
                'q': search_query,
                'limit': 10,  # Get multiple results to find the best match
                'sort': '-relevanceScore',
                'fields': 'addresses,contacts,description,directionsInfo,latitude,longitude,name,parkCode,states,url,fullName'
            }
            
            logger.debug(f"Querying API for park: '{park_name}' (searching for: '{search_query}')")
            
            # Make the API request with timeout for reliability
            response = self.session.get(endpoint, params=params, timeout=30)
            
            # Check if the request was successful
            response.raise_for_status()

            # Log rate limit information
            rate_limit_remaining = response.headers.get('X-RateLimit-Remaining')
            rate_limit_limit = response.headers.get('X-RateLimit-Limit')
            
            if rate_limit_remaining:
                logger.info(f"Rate limit status: {rate_limit_remaining}/{rate_limit_limit} requests remaining")
                
                # Warn if getting close to the limit
                if int(rate_limit_remaining) < 50:
                    logger.warning(f"Approaching rate limit! Only {rate_limit_remaining} requests remaining")
                        
            # Parse the JSON response
            data = response.json()

            # Validate that it returned data
            if 'data' not in data or not data['data']:
                logger.warning(f"No results found for park: {park_name}")
                return None
            
            # Find the best match using relevance score logic
            best_match = self._find_best_park_match(data['data'], search_query, park_name)

            if best_match:
                return best_match
            else:
                logger.warning(f"No suitable match found for park: {park_name}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error(f"API request timed out for park: {park_name}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for park '{park_name}': {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error querying park '{park_name}': {str(e)}")
            return None
    
    def _find_best_park_match(self, park_results: List[Dict], search_query: str, original_park_name: str) -> Optional[Dict]:
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
            Optional[Dict]: Best matching park or None if no results
        """
        if not park_results:
            logger.warning(f"No results returned for '{original_park_name}'")
            return None
        
        # Strategy 1: Look for exact fullName match
        for park in park_results:
            park_full_name = park.get('fullName', '')
            if park_full_name == search_query:
                logger.info(f"Found exact match for '{original_park_name}': '{park_full_name}'")
                return park
        
        # Strategy 2: No exact match, so take the first result (highest relevance)
        best_park = park_results[0]
        best_score = best_park.get('relevanceScore', 'N/A')
        best_name = best_park.get('fullName', 'Unknown')
        
        logger.info(f"No exact match for '{original_park_name}'. Using highest relevance: '{best_name}' (score: {best_score})")
        
        # Log other top candidates for debugging
        if len(park_results) > 1:
            logger.debug(f"Other candidates for '{original_park_name}':")
            for i, park in enumerate(park_results[1:4], 2):  # Show next 3 candidates
                candidate_name = park.get('fullName', 'Unknown')
                candidate_score = park.get('relevanceScore', 'N/A')
                logger.debug(f"  {i}. {candidate_name} (score: {candidate_score})")
        
        return best_park
    
    def _extract_valid_park_codes(self, park_data: pd.DataFrame) -> List[str]:
        """
        Extract valid, unique park codes from park data for boundary collection.
        
        This method safely extracts park codes, removes duplicates to avoid
        redundant API calls, and provides logging about the extraction process.
        
        Args:
            park_data (pd.DataFrame): DataFrame containing park data with park_code column
            
        Returns:
            List[str]: List of unique, valid park codes ready for boundary collection
        """
        if park_data.empty:
            logger.warning("Park data is empty - no park codes available")
            return []
        
        if 'park_code' not in park_data.columns:
            logger.warning("Park data missing 'park_code' column - no park codes available")
            return []
        
        # Get valid park codes (non-empty, non-null)
        valid_mask = park_data['park_code'].notna() & (park_data['park_code'] != '')
        total_parks_with_codes = valid_mask.sum()
        
        if total_parks_with_codes == 0:
            logger.warning("No valid park codes found in park data")
            return []
        
        # Remove duplicates to avoid redundant API calls
        unique_park_codes = park_data[valid_mask]['park_code'].drop_duplicates().tolist()
        
        # Log extraction results
        logger.info(f"Found {len(unique_park_codes)} unique park codes for boundary collection")
        
        if total_parks_with_codes > len(unique_park_codes):
            duplicates_removed = total_parks_with_codes - len(unique_park_codes)
            logger.info(f"Removed {duplicates_removed} duplicate park codes to avoid redundant API calls")
        
        return unique_park_codes
    
    def _print_collection_summary(self, park_data: pd.DataFrame, boundary_data: pd.DataFrame, 
                                 park_output_csv: str, boundary_output_csv: str) -> None:
        """
        Print comprehensive summary of the data collection results.
        
        Args:
            park_data (pd.DataFrame): Collected park data
            boundary_data (pd.DataFrame): Collected boundary data  
            park_output_csv (str): Path where park data was saved
            boundary_output_csv (str): Path where boundary data was saved
        """
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
            print(f"  Output saved to: {boundary_output_csv}")
        else:
            print(f"Boundary data: No boundaries collected")
        
        # Show sample of park data
        print(f"\nFirst few rows of park data:")
        print(park_data.head().to_string())
        
        # Show sample of boundary data if available
        if not boundary_data.empty:
            print(f"\nFirst few rows of boundary data (geometry truncated):")
            boundary_display = boundary_data.copy()
            if 'geometry' in boundary_display.columns:
                boundary_display['geometry'] = boundary_display['geometry'].apply(
                    lambda x: f"{str(x)[:50]}..." if x is not None else None
                )
            print(boundary_display.head().to_string())

    def _validate_coordinates(self, lat_value: str, lon_value: str, park_name: str) -> Tuple[Optional[float], Optional[float]]:
            """
            Validate and convert coordinate values to proper floats.
            
            This method handles the common issues with geographic coordinate data:
            conversion errors, invalid ranges, and missing values.
            
            Args:
                lat_value (str): Raw latitude value from API
                lon_value (str): Raw longitude value from API  
                park_name (str): Park name for error logging context
                
            Returns:
                Tuple[Optional[float], Optional[float]]: Validated lat/lon or (None, None) if invalid
            """
            try:
                # Convert to float
                lat_float = float(lat_value)
                lon_float = float(lon_value)
                
                # Validate geographic ranges
                if not (-90 <= lat_float <= 90):
                    logger.warning(f"Invalid latitude {lat_float} for {park_name} (must be between -90 and 90)")
                    return None, None
                    
                if not (-180 <= lon_float <= 180):
                    logger.warning(f"Invalid longitude {lon_float} for {park_name} (must be between -180 and 180)")
                    return None, None
                
                logger.debug(f"Valid coordinates for {park_name}: ({lat_float}, {lon_float})")
                return lat_float, lon_float
                
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse coordinates for {park_name}: lat='{lat_value}', lon='{lon_value}' - {str(e)}")
                return None, None

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
            'park_name': original_data['park_name'],
            'visit_month': original_data['month'],
            'visit_year': original_data['year'],
            'park_code': park_api_data.get('parkCode', ''),
            'full_name': park_api_data.get('fullName', ''),
            'states': park_api_data.get('states', ''),
            'url': park_api_data.get('url', ''),
            'latitude': None,
            'longitude': None,
            'description': park_api_data.get('description', '')
        }

        # Handle geographic coordinates with proper validation
        lat_raw = park_api_data.get('latitude')
        lon_raw = park_api_data.get('longitude')
        
        if lat_raw and lon_raw:
            # Use validation method to safely convert and validate coordinates
            validated_lat, validated_lon = self._validate_coordinates(
                lat_raw, 
                lon_raw, 
                extracted_data['full_name']
            )
            extracted_data['latitude'] = validated_lat
            extracted_data['longitude'] = validated_lon
        else:
            # Log when coordinate data is missing
            if not lat_raw and not lon_raw:
                logger.info(f"No coordinate data available for {extracted_data['full_name']}")
            else:
                logger.warning(f"Incomplete coordinate data for {extracted_data['full_name']}: lat={lat_raw}, lon={lon_raw}")
        
        return extracted_data
    
    def query_park_boundaries_api(self, park_code: str) -> Optional[Dict]:
        """
        Query the NPS API for park boundary spatial data.
        
        This method queries the mapdata/parkboundaries endpoint to retrieve
        geometric boundary information for a specific park.
        
        Args:
            park_code (str): NPS park code (e.g., 'zion', 'yell')
            
        Returns:
            Optional[Dict]: Boundary data if found, None if not found or error occurred
        """
        try:
            # Build the API endpoint URL for park boundaries
            endpoint = f"{self.base_url}/mapdata/parkboundaries/{park_code}"
            
            logger.debug(f"Querying boundary API for park code: '{park_code}'")
            
            # Make the API request with timeout for reliability
            response = self.session.get(endpoint, timeout=30)
            
            # Check if the request was successful
            response.raise_for_status()

            # Log rate limit information
            rate_limit_remaining = response.headers.get('X-RateLimit-Remaining')
            rate_limit_limit = response.headers.get('X-RateLimit-Limit')
            
            if rate_limit_remaining:
                logger.debug(f"Rate limit status: {rate_limit_remaining}/{rate_limit_limit} requests remaining")
                
                # Warn if getting close to the limit
                if int(rate_limit_remaining) < 50:
                    logger.warning(f"Approaching rate limit! Only {rate_limit_remaining} requests remaining")
                        
            # Parse the JSON response
            data = response.json()
            
            # Validate boundary data - boundaries endpoint returns GeoJSON directly
            if isinstance(data, dict):
                # Check for GeoJSON FeatureCollection format
                if data.get('type') == 'FeatureCollection' and 'features' in data:
                    if data['features']:  # Has features
                        logger.info(f"Successfully retrieved boundary data for park code: {park_code}")
                        return data
                    else:
                        logger.warning(f"No boundary features found for park code: {park_code}")
                        return None
                # Check for single Feature format
                elif data.get('type') == 'Feature':
                    logger.info(f"Successfully retrieved boundary data for park code: {park_code}")
                    return data
                # Check for direct geometry
                elif 'geometry' in data:
                    logger.info(f"Successfully retrieved boundary data for park code: {park_code}")
                    return data
                else:
                    logger.warning(f"Unexpected boundary data format for park code: {park_code}")
                    return None
            else:
                logger.warning(f"Invalid boundary data response for park code: {park_code}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error(f"Boundary API request timed out for park code: {park_code}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Boundary API request failed for park '{park_code}': {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error querying boundaries for park '{park_code}': {str(e)}")
            return None
    
    def extract_boundary_data(self, boundary_api_data: Dict, park_code: str) -> Dict:
        """
        Extract the specific boundary fields needed from the API response.
        
        This method safely extracts geometric and metadata information from
        the park boundaries API response.
        
        Args:
            boundary_api_data (Dict): Raw boundary data from the NPS API
            park_code (str): Park code for reference and logging
            
        Returns:
            Dict: Clean, structured boundary data for our dataset
        """
        # Initialize with park code for reference
        extracted_data = {
            'park_code': park_code,
            'geometry': None,
            'geometry_type': None,
            'boundary_source': 'NPS API'
        }
        
        # The boundary data is now properly structured GeoJSON
        try:
            # Handle GeoJSON FeatureCollection
            if boundary_api_data.get('type') == 'FeatureCollection':
                features = boundary_api_data.get('features', [])
                if features:
                    # Take the first feature (most parks have one main boundary)
                    first_feature = features[0]
                    geometry = first_feature.get('geometry')
                    if geometry:
                        extracted_data['geometry'] = geometry
                        extracted_data['geometry_type'] = geometry.get('type', 'Unknown')
                        logger.debug(f"Extracted {geometry.get('type', 'Unknown')} geometry from FeatureCollection for {park_code}")
                    else:
                        logger.warning(f"No geometry found in first feature for {park_code}")
                else:
                    logger.warning(f"No features found in FeatureCollection for {park_code}")
            
            # Handle single GeoJSON Feature
            elif boundary_api_data.get('type') == 'Feature':
                geometry = boundary_api_data.get('geometry')
                if geometry:
                    extracted_data['geometry'] = geometry
                    extracted_data['geometry_type'] = geometry.get('type', 'Unknown')
                    logger.debug(f"Extracted {geometry.get('type', 'Unknown')} geometry from Feature for {park_code}")
                else:
                    logger.warning(f"No geometry found in Feature for {park_code}")
            
            # Handle direct geometry object
            elif 'geometry' in boundary_api_data:
                geometry = boundary_api_data['geometry']
                extracted_data['geometry'] = geometry
                extracted_data['geometry_type'] = geometry.get('type', 'Unknown')
                logger.debug(f"Extracted {geometry.get('type', 'Unknown')} geometry from direct object for {park_code}")
            
            else:
                logger.warning(f"Unrecognized boundary data structure for {park_code}")
            
        except Exception as e:
            logger.error(f"Error extracting boundary data for {park_code}: {str(e)}")
        
        return extracted_data
    
    def collect_park_boundaries(self, park_codes: List[str], delay_seconds: float = 1.0, limit_for_testing: Optional[int] = None) -> pd.DataFrame:
        """
        Collect boundary data for a list of park codes.
        
        This method queries the boundaries endpoint for each park code and
        builds a structured dataset of spatial boundary information.
        
        Args:
            park_codes (List[str]): List of NPS park codes to collect boundaries for
            delay_seconds (float): Delay between API calls to be respectful
            
        Returns:
            pd.DataFrame: Dataset with boundary information for each park
        """
        logger.info("Starting park boundary data collection process")
        
        # FOR TESTING: Limit to specified number of park codes
        if limit_for_testing is not None:
            park_codes = park_codes[:limit_for_testing]
            logger.info(f"TESTING MODE: Limited to first {limit_for_testing} park codes")
        
        total_parks = len(park_codes)
        successful_boundaries = []
        failed_boundaries = []
        
        # Process each park code with progress tracking
        for index, park_code in enumerate(park_codes):
            progress = f"({index + 1}/{total_parks})"
            
            logger.info(f"Processing boundary {progress}: {park_code}")
            
            # Query the boundaries API for this park
            boundary_data = self.query_park_boundaries_api(park_code)
            
            if boundary_data:
                # Extract the boundary data we need
                extracted = self.extract_boundary_data(boundary_data, park_code)
                successful_boundaries.append(extracted)
                logger.info(f"✓ Successfully processed boundary for {park_code}")
            else:
                # Track failures for reporting
                failed_boundaries.append(park_code)
                logger.error(f"✗ Failed to process boundary for {park_code}")
            
            # Be respectful to the API with rate limiting
            if index < total_parks - 1:  # Don't delay after the last request
                time.sleep(delay_seconds)
        
        # Create final boundary dataset
        results_df = pd.DataFrame(successful_boundaries)
        
        # Report final statistics
        logger.info(f"Boundary collection complete: {len(successful_boundaries)} successful, {len(failed_boundaries)} failed")
        
        if failed_boundaries:
            logger.warning(f"Failed boundary collection for: {', '.join(map(str, failed_boundaries))}")
        
        return results_df
    
    def save_boundary_results(self, df: pd.DataFrame, output_path: str) -> None:
        """
        Save the collected boundary data to a CSV file with proper error handling.
        
        Note: This saves geometry data as JSON strings. For production use,
        consider specialized formats like GeoJSON or database storage.
        
        Args:
            df (pd.DataFrame): The boundary dataset to save
            output_path (str): Where to save the CSV file
        """
        try:
            # Convert geometry objects to JSON strings for CSV storage
            df_to_save = df.copy()
            if 'geometry' in df_to_save.columns:
                df_to_save['geometry'] = df_to_save['geometry'].apply(
                    lambda x: str(x) if x is not None else None
                )
            
            df_to_save.to_csv(output_path, index=False)
            logger.info(f"Boundary results saved to: {output_path}")
            logger.info(f"Boundary dataset contains {len(df)} parks with {len(df.columns)} columns")
        except Exception as e:
            logger.error(f"Failed to save boundary results: {str(e)}")
            raise
    
    def collect_park_data(self, csv_path: str, delay_seconds: float = 1.0, limit_for_testing: Optional[int] = None) -> pd.DataFrame:
        """
        Main orchestration method that processes all parks and builds the final dataset.
        
        Args:
            csv_path (str): Path to the CSV file with park names
            delay_seconds (float): Delay between API calls to be respectful
            
        Returns:
            pd.DataFrame: Complete dataset with all park information
        """
        logger.info("Starting park data collection process")
        
        # Load park list
        parks_df = self.load_parks_from_csv(csv_path)
        
        # FOR TESTING: Limit to specified number of parks
        if limit_for_testing is not None:
            parks_df = parks_df.head(limit_for_testing)
            logger.info(f"TESTING MODE: Limited to first {limit_for_testing} parks")
        
        total_parks = len(parks_df)
        
        # Track our results
        successful_parks = []
        failed_parks = []
        
        # Process each park with progress tracking
        for index, park_row in parks_df.iterrows():
            park_name = park_row['park_name']
            progress = f"({index + 1}/{total_parks})"
            
            logger.info(f"Processing {progress}: {park_name}")
            
            # Query the API for this park
            park_data = self.query_park_api(park_name)
            
            if park_data:
                # Extract the data needed
                extracted = self.extract_park_data(park_data, park_row)
                successful_parks.append(extracted)
                logger.info(f"✓ Successfully processed {park_name}")
            else:
                # Track failures for reporting
                failed_parks.append(park_name)
                logger.error(f"✗ Failed to process {park_name}")
            
            # Be respectful to the API with rate limiting
            if index < total_parks - 1:  # Don't delay after the last request
                time.sleep(delay_seconds)
        
        # Create final dataset
        results_df = pd.DataFrame(successful_parks)
        
        # Report final statistics
        logger.info(f"Collection complete: {len(successful_parks)} successful, {len(failed_parks)} failed")
        
        if failed_parks:
            logger.warning(f"Failed parks: {', '.join(failed_parks)}")
        
        return results_df
    
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
            logger.info(f"Dataset contains {len(df)} parks with {len(df.columns)} columns")
        except Exception as e:
            logger.error(f"Failed to save results: {str(e)}")
            raise


def main():
    """
    Main function demonstrating the complete NPS data collection pipeline.
    
    This function orchestrates a two-stage data collection process:
    1. Collect basic park information from the parks endpoint
    2. Collect spatial boundary data using the park codes from stage 1
    """
    try:
        # Load environment variables from .env file
        load_dotenv()
        
        # Get API key with validation
        api_key = os.getenv('NPS_API_KEY')
        if not api_key:
            raise ValueError("NPS_API_KEY not found in environment variables. Please check your .env file.")
        
        # Initialize our data collector
        collector = NPSDataCollector(api_key)
        
        # Define file paths
        input_csv = 'parks.csv'
        park_output_csv = 'park_data_collected.csv'
        boundary_output_csv = 'park_boundaries_collected.csv'
        
        # Check that input file exists before starting
        if not os.path.exists(input_csv):
            raise FileNotFoundError(f"Input file '{input_csv}' not found. Please create this file with your park data.")
        
        # STAGE 1: Collect basic park data
        logger.info("=" * 60)
        logger.info("STAGE 1: COLLECTING BASIC PARK DATA")
        logger.info("=" * 60)
        
        park_data = collector.collect_park_data(input_csv, delay_seconds=1.0)
        
        # Save park data results
        collector.save_park_results(park_data, park_output_csv)
        
        # STAGE 2: Collect boundary data using park codes from stage 1
        logger.info("=" * 60)
        logger.info("STAGE 2: COLLECTING PARK BOUNDARY DATA")
        logger.info("=" * 60)
        
        # Initialize boundary_data to handle cases where it might not get created
        boundary_data = pd.DataFrame()
        
        # Extract valid park codes from successful park data collection
        valid_park_codes = collector._extract_valid_park_codes(park_data)
        
        if valid_park_codes:
            # Collect boundary data
            boundary_data = collector.collect_park_boundaries(valid_park_codes, delay_seconds=1.0)
            
            # Save boundary results
            if not boundary_data.empty:
                collector.save_boundary_results(boundary_data, boundary_output_csv)
            else:
                logger.warning("No boundary data was successfully collected")
        else:
            logger.warning("Skipping boundary collection - no valid park codes available")
        
        # Print comprehensive summary information
        collector._print_collection_summary(park_data, boundary_data, park_output_csv, boundary_output_csv)
        
        logger.info("NPS data collection pipeline completed successfully")
        
    except Exception as e:
        logger.error(f"Pipeline execution failed: {str(e)}")
        print(f"\nERROR: {str(e)}")
        print("Check the log file 'nps_collector.log' for detailed error information.")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())