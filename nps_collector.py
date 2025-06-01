"""
National Park Service API Data Collector

This reads a list of parks from a CSV file, queries the NPS API for each park,
and creates a structured dataset with park information.
"""

import requests
import pandas as pd
import os
import time
import logging
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

# Configure logging for debugging and monitoring
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('nps_collector.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class NPSDataCollector:
    """
    A class for collecting National Park Service data.
    
    This class encapsulates all the functionality needed to query the NPS API
    and build a structured dataset.
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
            'User-Agent': 'Python-NPS-Collector/1.0'
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
            params = {
                'q': park_name,
                'limit': 10,  # Get multiple results to find the best match
                'fields': 'addresses,contacts,description,directionsInfo,latitude,longitude,name,parkCode,states,url,fullName'
            }
            
            logger.debug(f"Querying API for park: {park_name}")
            
            # Make the API request with timeout for reliability
            response = self.session.get(endpoint, params=params, timeout=30)
            
            # Check if the request was successful
            response.raise_for_status()
            
            # Parse the JSON response
            data = response.json()
            
            # Validate that it returend data
            if 'data' not in data or not data['data']:
                logger.warning(f"No results found for park: {park_name}")
                return None
            
            # Find the best match using relevance score logic
            best_match = self._find_best_park_match(data['data'], park_name)
            
            if best_match:
                logger.info(f"Found match for '{park_name}': {best_match.get('fullName', 'Unknown')}")
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
    
    def _find_best_park_match(self, park_results: List[Dict], search_term: str) -> Optional[Dict]:
        """
        Find the best matching park from API results according to the relevanceScore.
        
        Args:
            park_results (List[Dict]): List of park results from the API
            search_term (str): Original search term for logging
            
        Returns:
            Optional[Dict]: Best matching park or None if no good match
        """
        if not park_results:
            return None
        
        # Look for relevance scores in the results
        parks_with_scores = []
        
        for park in park_results:
            # Some API responses include relevanceScore, others don't
            relevance = park.get('relevanceScore', 0)
            parks_with_scores.append((park, relevance))
        
        # Sort by relevance score (highest first)
        parks_with_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Get the highest scoring park
        best_park, best_score = parks_with_scores[0]
        
        # Log matching decision for debugging
        logger.debug(f"Best match for '{search_term}': '{best_park.get('fullName')}' (score: {best_score})")
        
        return best_park
    
    def extract_park_data(self, park_api_data: Dict, original_data: pd.Series) -> Dict:
        """
        Extract the specific fields we need from the API response.
        
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
            'description': park_api_data.get('description', ''),
            'states': park_api_data.get('states', ''),
            'url': park_api_data.get('url', ''),
            'latitude': None,
            'longitude': None
        }
        
        # Handle geographic coordinates safely since they might be missing or malformed
        try:
            lat = park_api_data.get('latitude')
            lon = park_api_data.get('longitude')
            
            if lat and lon:
                extracted_data['latitude'] = float(lat)
                extracted_data['longitude'] = float(lon)
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse coordinates for {extracted_data['full_name']}: {str(e)}")
        
        return extracted_data
    
    def collect_all_park_data(self, csv_path: str, delay_seconds: float = 1.0) -> pd.DataFrame:
        """
        Main orchestration method that processes all parks and builds the final dataset.
        
        Args:
            csv_path (str): Path to the CSV file with park names
            delay_seconds (float): Delay between API calls to be respectful
            
        Returns:
            pd.DataFrame: Complete dataset with all park information
        """
        logger.info("Starting park data collection process")
        
        # Load our park list
        parks_df = self.load_parks_from_csv(csv_path)
        # FOR TESTING: Limit to first 2 parks
        parks_df = parks_df.head(2)
        
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
                # Extract the data we need
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
    
    def save_results(self, df: pd.DataFrame, output_path: str) -> None:
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
    Main function that demonstrates how to use the NPSDataCollector class.
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
        output_csv = 'park_data_collected.csv'
        
        # Check that input file exists before starting
        if not os.path.exists(input_csv):
            raise FileNotFoundError(f"Input file '{input_csv}' not found. Please create this file with your park data.")
        
        # Collect the data
        logger.info("=" * 50)
        logger.info("STARTING NPS PARK DATA COLLECTION")
        logger.info("=" * 50)
        
        park_data = collector.collect_all_park_data(input_csv, delay_seconds=1.0)
        
        # Save results
        collector.save_results(park_data, output_csv)
        
        # Print summary information
        print("\n" + "=" * 50)
        print("COLLECTION SUMMARY")
        print("=" * 50)
        print(f"Parks processed: {len(park_data)}")
        print(f"Output saved to: {output_csv}")
        print("\nFirst few rows of collected data:")
        print(park_data.head().to_string())
        
        logger.info("NPS park data collection completed successfully")
        
    except Exception as e:
        logger.error(f"Script execution failed: {str(e)}")
        print(f"\nERROR: {str(e)}")
        print("Check the log file 'nps_collector.log' for detailed error information.")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
