-- USGS elevation data quality analysis
-- Assesses the quality and completeness of elevation data collection

SELECT 
    park_code,
    COUNT(*) as total_trails,
    -- Collection status breakdown
    COUNT(CASE WHEN collection_status = 'COMPLETE' THEN 1 END) as complete_trails,
    COUNT(CASE WHEN collection_status = 'PARTIAL' THEN 1 END) as partial_trails,
    COUNT(CASE WHEN collection_status = 'FAILED' THEN 1 END) as failed_trails,
    -- Data completeness metrics
    SUM(total_points_count) as total_elevation_points,
    SUM(failed_points_count) as total_failed_points,
    ROUND(
        (SUM(total_points_count) - SUM(failed_points_count))::numeric / 
        NULLIF(SUM(total_points_count), 0) * 100, 2
    ) as data_completeness_percent,
    -- Average points per trail
    ROUND(AVG(total_points_count), 1) as avg_points_per_trail,
    -- Trail length statistics
    ROUND(AVG(
        (SELECT MAX((ep->>'distance_m')::numeric) 
         FROM jsonb_array_elements(elevation_points) ep)
    ), 1) as avg_trail_length_m,
    -- Elevation range statistics
    ROUND(AVG(
        (SELECT MAX((ep->>'elevation_m')::numeric) - MIN((ep->>'elevation_m')::numeric)
         FROM jsonb_array_elements(elevation_points) ep)
    ), 1) as avg_elevation_range_m,
    -- Source breakdown
    COUNT(CASE WHEN source = 'TNM' THEN 1 END) as tnm_trails,
    COUNT(CASE WHEN source = 'OSM' THEN 1 END) as osm_trails
FROM usgs_trail_elevations
GROUP BY park_code
ORDER BY park_code;
