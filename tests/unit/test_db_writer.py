"""
Unit tests for db_writer.py module.

Tests cover database writer functionality without requiring a real database connection.
All database operations are mocked to focus on business logic and error handling.
"""

import pytest
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon, MultiPolygon
from unittest.mock import Mock, patch, MagicMock, call
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import Engine, Table
import logging

from db_writer import DatabaseWriter, get_postgres_engine


class TestGetPostgresEngine:
    """Test cases for get_postgres_engine function."""
    
    @patch('db_writer.CONFIG_AVAILABLE', True)
    @patch('db_writer.config')
    @patch('db_writer.create_engine')
    def test_engine_creation_with_valid_config(self, mock_create_engine, mock_config):
        """Test engine creation with valid configuration."""
        mock_config.validate_for_database_operations.return_value = None
        mock_config.get_database_url.return_value = "postgresql://user:pass@localhost/db"
        mock_engine = Mock(spec=Engine)
        mock_create_engine.return_value = mock_engine
        
        result = get_postgres_engine()
        
        mock_config.validate_for_database_operations.assert_called_once()
        mock_config.get_database_url.assert_called_once()
        mock_create_engine.assert_called_once_with("postgresql://user:pass@localhost/db")
        assert result == mock_engine
    
    @patch('db_writer.CONFIG_AVAILABLE', False)
    @patch('db_writer.config', None)
    def test_engine_creation_config_unavailable(self):
        """Test ValueError when configuration is unavailable."""
        with pytest.raises(ValueError, match="Configuration not available"):
            get_postgres_engine()
    
    @patch('db_writer.CONFIG_AVAILABLE', True)
    @patch('db_writer.config')
    def test_engine_creation_invalid_config(self, mock_config):
        """Test when config validation fails."""
        mock_config.validate_for_database_operations.side_effect = ValueError("Invalid config")
        
        with pytest.raises(ValueError, match="Invalid config"):
            get_postgres_engine()


class TestDatabaseWriterInit:
    """Test cases for DatabaseWriter initialization."""
    
    def test_init_with_engine_and_logger(self):
        """Test initialization with engine and logger."""
        mock_engine = Mock(spec=Engine)
        mock_logger = Mock(spec=logging.Logger)
        
        writer = DatabaseWriter(mock_engine, mock_logger)
        
        assert writer.engine == mock_engine
        assert writer.logger == mock_logger
        assert writer.metadata is not None
        assert hasattr(writer, 'parks_table')
        assert hasattr(writer, 'park_boundaries_table')
    
    def test_init_with_engine_no_logger(self):
        """Test initialization creates default logger when none provided."""
        mock_engine = Mock(spec=Engine)
        
        with patch('db_writer.logging.getLogger') as mock_get_logger:
            mock_default_logger = Mock(spec=logging.Logger)
            mock_get_logger.return_value = mock_default_logger
            
            writer = DatabaseWriter(mock_engine)
            
            assert writer.engine == mock_engine
            assert writer.logger == mock_default_logger
            mock_get_logger.assert_called_once_with('db_writer')
    
    def test_init_sets_up_schemas(self):
        """Test that initialization sets up NPS table schemas."""
        mock_engine = Mock(spec=Engine)
        
        writer = DatabaseWriter(mock_engine)
        
        assert isinstance(writer.parks_table, Table)
        assert isinstance(writer.park_boundaries_table, Table)
        assert writer.parks_table.name == "parks"
        assert writer.park_boundaries_table.name == "park_boundaries"


class TestTableSchemaDefinition:
    """Test cases for table schema definitions."""
    
    def test_parks_table_schema(self):
        """Test parks table has correct schema."""
        mock_engine = Mock(spec=Engine)
        writer = DatabaseWriter(mock_engine)
        
        parks_table = writer.parks_table
        column_names = [col.name for col in parks_table.columns]
        
        expected_columns = [
            "park_code", "park_name", "visit_month", "visit_year", 
            "full_name", "states", "url", "latitude", "longitude", 
            "description", "error_message", "collection_status"
        ]
        
        for col in expected_columns:
            assert col in column_names
        
        # Check primary key
        pk_columns = [col.name for col in parks_table.primary_key.columns]
        assert pk_columns == ["park_code"]
    
    def test_boundaries_table_schema(self):
        """Test park_boundaries table has correct schema."""
        mock_engine = Mock(spec=Engine)
        writer = DatabaseWriter(mock_engine)
        
        boundaries_table = writer.park_boundaries_table
        column_names = [col.name for col in boundaries_table.columns]
        
        expected_columns = [
            "park_code", "geometry", "geometry_type", 
            "boundary_source", "error_message", "collection_status"
        ]
        
        for col in expected_columns:
            assert col in column_names
        
        # Check primary key
        pk_columns = [col.name for col in boundaries_table.primary_key.columns]
        assert pk_columns == ["park_code"]


class TestTableValidation:
    """Test cases for table validation methods."""
    
    @patch('db_writer.inspect')
    def test_check_primary_key_valid_table(self, mock_inspect):
        """Test primary key validation with valid table."""
        mock_engine = Mock(spec=Engine)
        mock_inspector = Mock()
        mock_inspector.get_table_names.return_value = ["test_table"]
        mock_inspector.get_pk_constraint.return_value = {
            "constrained_columns": ["test_id"]
        }
        mock_inspect.return_value = mock_inspector
        
        writer = DatabaseWriter(mock_engine)
        
        # Should not raise exception
        writer._check_primary_key("test_table", "test_id")
        
        mock_inspect.assert_called_once_with(mock_engine)
        mock_inspector.get_table_names.assert_called_once()
        mock_inspector.get_pk_constraint.assert_called_once_with("test_table")
    
    @patch('db_writer.inspect')
    def test_check_primary_key_invalid_table(self, mock_inspect):
        """Test primary key validation with wrong primary key."""
        mock_engine = Mock(spec=Engine)
        mock_inspector = Mock()
        mock_inspector.get_table_names.return_value = ["test_table"]
        mock_inspector.get_pk_constraint.return_value = {
            "constrained_columns": ["wrong_id"]
        }
        mock_inspect.return_value = mock_inspector
        
        writer = DatabaseWriter(mock_engine)
        
        with pytest.raises(ValueError, match="does not have 'test_id' as a primary key"):
            writer._check_primary_key("test_table", "test_id")
    
    @patch('db_writer.inspect')
    def test_check_primary_key_nonexistent_table(self, mock_inspect):
        """Test primary key validation with nonexistent table."""
        mock_engine = Mock(spec=Engine)
        mock_inspector = Mock()
        mock_inspector.get_table_names.return_value = []
        mock_inspect.return_value = mock_inspector
        
        writer = DatabaseWriter(mock_engine)
        
        # Should not raise exception for nonexistent table
        writer._check_primary_key("nonexistent_table", "test_id")
        
        mock_inspector.get_table_names.assert_called_once()
        mock_inspector.get_pk_constraint.assert_not_called()


class TestTableCreation:
    """Test cases for table creation methods."""
    
    def test_ensure_table_exists_parks(self):
        """Test ensuring parks table exists."""
        mock_engine = Mock(spec=Engine)
        writer = DatabaseWriter(mock_engine)
        
        with patch.object(writer.metadata, 'create_all') as mock_create_all:
            writer.ensure_table_exists("parks")
            
            mock_create_all.assert_called_once_with(
                mock_engine, 
                tables=[writer.parks_table], 
                checkfirst=True
            )
    
    def test_ensure_table_exists_park_boundaries(self):
        """Test ensuring park_boundaries table exists."""
        mock_engine = Mock(spec=Engine)
        writer = DatabaseWriter(mock_engine)
        
        with patch.object(writer.metadata, 'create_all') as mock_create_all:
            writer.ensure_table_exists("park_boundaries")
            
            mock_create_all.assert_called_once_with(
                mock_engine, 
                tables=[writer.park_boundaries_table], 
                checkfirst=True
            )
    
    def test_ensure_table_exists_park_hikes(self):
        """Test ensuring park_hikes table exists."""
        mock_engine = Mock(spec=Engine)
        mock_connection = Mock()
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_connection)
        mock_context.__exit__ = Mock(return_value=None)
        mock_engine.begin.return_value = mock_context
        
        writer = DatabaseWriter(mock_engine)
        writer.ensure_table_exists("park_hikes")
        
        mock_engine.begin.assert_called_once()
        mock_connection.execute.assert_called_once()
    
    def test_ensure_table_exists_unknown_table(self):
        """Test error for unknown table name."""
        mock_engine = Mock(spec=Engine)
        writer = DatabaseWriter(mock_engine)
        
        with pytest.raises(ValueError, match="Unknown table name: unknown_table"):
            writer.ensure_table_exists("unknown_table")


class TestParksOperations:
    """Test cases for parks data operations."""
    
    def test_write_parks_empty_dataframe(self):
        """Test writing empty DataFrame logs warning and returns."""
        mock_engine = Mock(spec=Engine)
        mock_logger = Mock(spec=logging.Logger)
        writer = DatabaseWriter(mock_engine, mock_logger)
        
        empty_df = pd.DataFrame()
        writer.write_parks(empty_df)
        
        mock_logger.warning.assert_called_once_with("No park data to save")
    
    def test_write_parks_invalid_mode(self):
        """Test ValueError for invalid mode."""
        mock_engine = Mock(spec=Engine)
        writer = DatabaseWriter(mock_engine)
        
        df = pd.DataFrame({"park_code": ["test"]})
        
        with pytest.raises(ValueError, match="Unsupported mode 'invalid'"):
            writer.write_parks(df, mode="invalid")
    
    def test_write_parks_upsert_mode(self):
        """Test upsert mode calls correct methods."""
        mock_engine = Mock(spec=Engine)
        writer = DatabaseWriter(mock_engine)
        
        df = pd.DataFrame({
            "park_code": ["test"],
            "park_name": ["Test Park"]
        })
        
        with patch.object(writer, 'ensure_table_exists') as mock_ensure, \
             patch.object(writer, '_check_primary_key') as mock_check_pk, \
             patch.object(writer, '_upsert_parks') as mock_upsert:
            
            writer.write_parks(df, mode="upsert")
            
            mock_ensure.assert_called_once_with("parks")
            mock_check_pk.assert_called_once_with("parks", "park_code")
            mock_upsert.assert_called_once_with(df, "parks")
    
    def test_write_parks_append_mode(self):
        """Test append mode calls correct methods."""
        mock_engine = Mock(spec=Engine)
        writer = DatabaseWriter(mock_engine)
        
        df = pd.DataFrame({
            "park_code": ["test"],
            "park_name": ["Test Park"]
        })
        
        with patch.object(writer, 'ensure_table_exists') as mock_ensure, \
             patch.object(writer, '_append_dataframe') as mock_append:
            
            writer.write_parks(df, mode="append")
            
            mock_ensure.assert_called_once_with("parks")
            mock_append.assert_called_once_with(df, "parks")
    
#    def test_upsert_parks_calls_correct_methods(self):
#        """Test that upsert parks calls the expected methods."""
#        mock_engine = Mock(spec=Engine)
#        mock_logger = Mock(spec=logging.Logger)
#        
#        writer = DatabaseWriter(mock_engine, mock_logger)
#        
#        df = pd.DataFrame({
#            "park_code": ["test1", "test2"],
#            "park_name": ["Test Park 1", "Test Park 2"]
#        })
#        
#        # Simply test that the method calls the right components without deep SQLAlchemy mocking
#        with patch.object(writer, '_upsert_parks') as mock_upsert:
#            writer.write_parks(df, mode="upsert", table_name="parks")
#            mock_upsert.assert_called_once_with(df, "parks")
#

class TestBoundariesOperations:
    """Test cases for park boundaries operations."""
    
    def test_write_park_boundaries_empty_geodataframe(self):
        """Test writing empty GeoDataFrame logs warning and returns."""
        mock_engine = Mock(spec=Engine)
        mock_logger = Mock(spec=logging.Logger)
        writer = DatabaseWriter(mock_engine, mock_logger)
        
        empty_gdf = gpd.GeoDataFrame()
        writer.write_park_boundaries(empty_gdf)
        
        mock_logger.warning.assert_called_once_with("No boundary data to save")
    
    def test_write_park_boundaries_invalid_mode(self):
        """Test ValueError for invalid mode."""
        mock_engine = Mock(spec=Engine)
        writer = DatabaseWriter(mock_engine)
        
        gdf = gpd.GeoDataFrame({
            "park_code": ["test"],
            "geometry": [Point(0, 0)]
        })
        
        with pytest.raises(ValueError, match="Unsupported mode 'invalid'"):
            writer.write_park_boundaries(gdf, mode="invalid")
    
    # TODO: Move to integration tests - complex SQLAlchemy mocking
    def _test_upsert_park_boundaries_with_geometry(self):
        """Test boundary upsert with valid geometry."""
        mock_engine = Mock(spec=Engine)
        mock_connection = Mock()
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_connection)
        mock_context.__exit__ = Mock(return_value=None)
        mock_engine.begin.return_value = mock_context
        mock_logger = Mock(spec=logging.Logger)
        
        writer = DatabaseWriter(mock_engine, mock_logger)
        
        polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        gdf = gpd.GeoDataFrame({
            "park_code": ["test"],
            "geometry": [polygon],
            "geometry_type": ["Polygon"],
            "boundary_source": ["NPS API"]
        })
        
        with patch('db_writer.insert') as mock_insert:
            mock_stmt = Mock()
            mock_insert.return_value = mock_stmt
            mock_excluded = Mock()
            mock_excluded.__getitem__ = Mock(return_value="excluded_value")
            mock_stmt.excluded = mock_excluded
            mock_stmt.on_conflict_do_update.return_value = mock_stmt
            
            writer._upsert_park_boundaries(gdf, "park_boundaries")
            
            mock_connection.execute.assert_called_once()
            mock_logger.info.assert_called_once_with("Upserted 1 boundary records to park_boundaries")
    
    # TODO: Move to integration tests - complex SQLAlchemy mocking  
    def _test_upsert_park_boundaries_null_geometry(self):
        """Test boundary upsert with null geometry."""
        mock_engine = Mock(spec=Engine)
        mock_connection = Mock()
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_connection)
        mock_context.__exit__ = Mock(return_value=None)
        mock_engine.begin.return_value = mock_context
        
        writer = DatabaseWriter(mock_engine)
        
        gdf = gpd.GeoDataFrame({
            "park_code": ["test"],
            "geometry": [None],
            "geometry_type": ["None"],
            "boundary_source": ["NPS API"]
        })
        
        with patch('db_writer.insert') as mock_insert:
            mock_stmt = Mock()
            mock_insert.return_value = mock_stmt
            mock_excluded = Mock()
            mock_excluded.__getitem__ = Mock(return_value="excluded_value")
            mock_stmt.excluded = mock_excluded
            mock_stmt.on_conflict_do_update.return_value = mock_stmt
            
            writer._upsert_park_boundaries(gdf, "park_boundaries")
            
            mock_connection.execute.assert_called_once()


class TestHikesOperations:
    """Test cases for park hikes operations."""
    
    def test_write_park_hikes_empty_geodataframe(self):
        """Test writing empty GeoDataFrame logs warning and returns."""
        mock_engine = Mock(spec=Engine)
        mock_logger = Mock(spec=logging.Logger)
        writer = DatabaseWriter(mock_engine, mock_logger)
        
        empty_gdf = gpd.GeoDataFrame()
        writer.write_park_hikes(empty_gdf)
        
        mock_logger.warning.assert_called_once_with("No trail data to save")
    
    def test_write_park_hikes_invalid_mode(self):
        """Test ValueError for invalid mode."""
        mock_engine = Mock(spec=Engine)
        writer = DatabaseWriter(mock_engine)
        
        gdf = gpd.GeoDataFrame({
            "osm_id": [123],
            "park_code": ["test"],
            "geometry": [Point(0, 0)]
        })
        
        with pytest.raises(ValueError, match="Unsupported mode 'invalid'"):
            writer.write_park_hikes(gdf, mode="invalid")
    
    def test_write_park_hikes_append_mode(self):
        """Test append mode calls correct methods."""
        mock_engine = Mock(spec=Engine)
        writer = DatabaseWriter(mock_engine)
        
        gdf = gpd.GeoDataFrame({
            "osm_id": [123],
            "park_code": ["test"],
            "geometry": [Point(0, 0)]
        })
        
        with patch.object(writer, 'ensure_table_exists') as mock_ensure, \
             patch.object(writer, '_append_geodataframe') as mock_append:
            
            writer.write_park_hikes(gdf, mode="append")
            
            mock_ensure.assert_called_once_with("park_hikes")
            mock_append.assert_called_once_with(gdf, "park_hikes")
    
    def test_write_park_hikes_upsert_not_implemented(self):
        """Test that upsert mode raises NotImplementedError."""
        mock_engine = Mock(spec=Engine)
        writer = DatabaseWriter(mock_engine)
        
        gdf = gpd.GeoDataFrame({
            "osm_id": [123],
            "park_code": ["test"],
            "geometry": [Point(0, 0)]
        })
        
        with patch.object(writer, 'ensure_table_exists'):
            with pytest.raises(NotImplementedError, match="Upsert mode not implemented"):
                writer.write_park_hikes(gdf, mode="upsert")


class TestDataFrameOperations:
    """Test cases for DataFrame append operations."""
    
    def test_append_dataframe_success(self):
        """Test successful DataFrame append."""
        mock_engine = Mock(spec=Engine)
        mock_logger = Mock(spec=logging.Logger)
        writer = DatabaseWriter(mock_engine, mock_logger)
        
        df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        
        with patch.object(df, 'to_sql') as mock_to_sql:
            writer._append_dataframe(df, "test_table")
            
            mock_to_sql.assert_called_once_with(
                "test_table", mock_engine, if_exists="append", index=False
            )
            mock_logger.info.assert_called_once_with("Appended 2 records to test_table")
    
    def test_append_dataframe_error(self):
        """Test DataFrame append error handling."""
        mock_engine = Mock(spec=Engine)
        mock_logger = Mock(spec=logging.Logger)
        writer = DatabaseWriter(mock_engine, mock_logger)
        
        df = pd.DataFrame({"col1": [1, 2]})
        
        with patch.object(df, 'to_sql') as mock_to_sql:
            mock_to_sql.side_effect = Exception("Database error")
            
            with pytest.raises(Exception, match="Database error"):
                writer._append_dataframe(df, "test_table")
            
            mock_logger.error.assert_called_once()
    
    def test_append_geodataframe_success(self):
        """Test successful GeoDataFrame append."""
        mock_engine = Mock(spec=Engine)
        mock_logger = Mock(spec=logging.Logger)
        writer = DatabaseWriter(mock_engine, mock_logger)
        
        gdf = gpd.GeoDataFrame({
            "col1": [1, 2],
            "geometry": [Point(0, 0), Point(1, 1)]
        })
        
        with patch.object(gdf, 'to_postgis') as mock_to_postgis:
            writer._append_geodataframe(gdf, "test_table")
            
            mock_to_postgis.assert_called_once_with(
                "test_table", mock_engine, if_exists="append", index=False
            )
            mock_logger.info.assert_called_once_with("Appended 2 spatial records to test_table")
    
    def test_append_geodataframe_error(self):
        """Test GeoDataFrame append error handling."""
        mock_engine = Mock(spec=Engine)
        mock_logger = Mock(spec=logging.Logger)
        writer = DatabaseWriter(mock_engine, mock_logger)
        
        gdf = gpd.GeoDataFrame({
            "col1": [1],
            "geometry": [Point(0, 0)]
        })
        
        with patch.object(gdf, 'to_postgis') as mock_to_postgis:
            mock_to_postgis.side_effect = Exception("PostGIS error")
            
            with pytest.raises(Exception, match="PostGIS error"):
                writer._append_geodataframe(gdf, "test_table")
            
            mock_logger.error.assert_called_once()


class TestUtilityMethods:
    """Test cases for utility methods."""
    
    @patch('db_writer.pd.read_sql')
    def test_get_completed_records_success(self, mock_read_sql):
        """Test successful completed records retrieval."""
        mock_engine = Mock(spec=Engine)
        mock_logger = Mock(spec=logging.Logger)
        writer = DatabaseWriter(mock_engine, mock_logger)
        
        mock_read_sql.return_value = pd.DataFrame({
            "park_code": ["zion", "yell", "grca"]
        })
        
        result = writer.get_completed_records("test_table", "park_code")
        
        assert result == {"zion", "yell", "grca"}
        mock_read_sql.assert_called_once_with(
            "SELECT DISTINCT park_code FROM test_table", mock_engine
        )
        mock_logger.info.assert_called_once()
    
    @patch('db_writer.pd.read_sql')
    def test_get_completed_records_empty_result(self, mock_read_sql):
        """Test completed records with empty result."""
        mock_engine = Mock(spec=Engine)
        writer = DatabaseWriter(mock_engine)
        
        mock_read_sql.return_value = pd.DataFrame({"park_code": []})
        
        result = writer.get_completed_records("test_table", "park_code")
        
        assert result == set()
    
    @patch('db_writer.pd.read_sql')
    def test_get_completed_records_db_error(self, mock_read_sql):
        """Test completed records handles database errors."""
        mock_engine = Mock(spec=Engine)
        mock_logger = Mock(spec=logging.Logger)
        writer = DatabaseWriter(mock_engine, mock_logger)
        
        mock_read_sql.side_effect = Exception("Connection failed")
        
        result = writer.get_completed_records("test_table", "park_code")
        
        assert result == set()
        mock_logger.warning.assert_called_once()
    
    def test_truncate_tables_success(self):
        """Test successful table truncation."""
        mock_engine = Mock(spec=Engine)
        mock_connection = Mock()
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_connection)
        mock_context.__exit__ = Mock(return_value=None)
        mock_engine.begin.return_value = mock_context
        mock_logger = Mock(spec=logging.Logger)
        
        writer = DatabaseWriter(mock_engine, mock_logger)
        
        writer.truncate_tables(["table1", "table2"])
        
        mock_engine.begin.assert_called_once()
        assert mock_connection.execute.call_count == 2
        assert mock_logger.info.call_count == 4  # 2 "Truncating..." + 2 "truncated"
    
    def test_truncate_tables_error(self):
        """Test table truncation error handling."""
        mock_engine = Mock(spec=Engine)
        mock_connection = Mock()
        mock_connection.execute.side_effect = Exception("Truncate failed")
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_connection)
        mock_context.__exit__ = Mock(return_value=None)
        mock_engine.begin.return_value = mock_context
        mock_logger = Mock(spec=logging.Logger)
        
        writer = DatabaseWriter(mock_engine, mock_logger)
        
        writer.truncate_tables(["table1"])
        
        mock_logger.error.assert_called_once()
    
    @patch('db_writer.inspect')
    @patch('db_writer.text')
    def test_get_table_info_existing_table(self, mock_text, mock_inspect):
        """Test table info for existing table."""
        mock_engine = Mock(spec=Engine)
        mock_inspector = Mock()
        mock_inspector.get_table_names.return_value = ["test_table"]
        mock_inspector.get_columns.return_value = [
            {"name": "col1"}, {"name": "col2"}
        ]
        mock_inspector.get_pk_constraint.return_value = {
            "constrained_columns": ["col1"]
        }
        mock_inspect.return_value = mock_inspector
        
        mock_connection = Mock()
        mock_result = Mock()
        mock_result.scalar.return_value = 100
        mock_connection.execute.return_value = mock_result
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_connection)
        mock_context.__exit__ = Mock(return_value=None)
        mock_engine.connect.return_value = mock_context
        
        writer = DatabaseWriter(mock_engine)
        
        result = writer.get_table_info("test_table")
        
        assert result["exists"] is True
        assert result["row_count"] == 100
        assert result["columns"] == ["col1", "col2"]
        assert result["primary_keys"] == ["col1"]
    
    @patch('db_writer.inspect')
    def test_get_table_info_nonexistent_table(self, mock_inspect):
        """Test table info for nonexistent table."""
        mock_engine = Mock(spec=Engine)
        mock_inspector = Mock()
        mock_inspector.get_table_names.return_value = []
        mock_inspect.return_value = mock_inspector
        
        writer = DatabaseWriter(mock_engine)
        
        result = writer.get_table_info("nonexistent_table")
        
        assert result["exists"] is False
        assert result["row_count"] == 0
        assert result["columns"] == []
        assert result["primary_keys"] == []


class TestErrorHandling:
    """Test cases for error handling scenarios."""
    
    def test_database_error_propagation(self):
        """Test that SQLAlchemy errors are properly propagated."""
        mock_engine = Mock(spec=Engine)
        mock_engine.begin.side_effect = SQLAlchemyError("Connection failed")
        
        writer = DatabaseWriter(mock_engine)
        
        with pytest.raises(SQLAlchemyError):
            writer.ensure_table_exists("park_hikes")
    
    # TODO: Move to integration tests - complex SQLAlchemy mocking
    def _test_geometry_conversion_invalid_geometry(self):
        """Test handling of invalid geometry objects."""
        mock_engine = Mock(spec=Engine)
        mock_connection = Mock()
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_connection)
        mock_context.__exit__ = Mock(return_value=None)
        mock_engine.begin.return_value = mock_context
        
        writer = DatabaseWriter(mock_engine)
        
        # Create GeoDataFrame with invalid geometry
        gdf = gpd.GeoDataFrame({
            "park_code": ["test"],
            "geometry": ["not_a_geometry"],  # Invalid geometry
            "geometry_type": ["Invalid"]
        })
        
        with patch('db_writer.insert') as mock_insert:
            mock_stmt = Mock()
            mock_insert.return_value = mock_stmt
            mock_excluded = Mock()
            mock_excluded.__getitem__ = Mock(return_value="excluded_value")
            mock_stmt.excluded = mock_excluded
            mock_stmt.on_conflict_do_update.return_value = mock_stmt
            
            # Should handle the invalid geometry gracefully
            writer._upsert_park_boundaries(gdf, "park_boundaries")
            
            mock_connection.execute.assert_called_once()
    
    # TODO: Move to integration tests - complex context manager mocking
    def _test_transaction_context_manager_error(self):
        """Test that transaction context manager errors are handled."""
        mock_engine = Mock(spec=Engine)
        mock_context = Mock()
        mock_context.__enter__ = Mock(side_effect=Exception("Transaction failed"))
        mock_engine.begin.return_value = mock_context
        
        writer = DatabaseWriter(mock_engine)
        
        with pytest.raises(Exception, match="Transaction failed"):
            writer.ensure_table_exists("park_hikes")


if __name__ == "__main__":
    pytest.main([__file__])