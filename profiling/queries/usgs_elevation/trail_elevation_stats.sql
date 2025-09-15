-- Trail-level elevation statistics
-- Provides min, max, mean elevation and elevation gain/loss for each trail

WITH elevation_data AS (
    SELECT 
        trail_id,
        trail_name,
        park_code,
        source,
        collection_status,
        total_points_count,
        failed_points_count,
        created_at,
        (elevation_point->>'point_index')::int as point_index,
        (elevation_point->>'distance_m')::numeric as distance_m,
        (elevation_point->>'elevation_m')::numeric as elevation_m
    FROM usgs_trail_elevations,
         jsonb_array_elements(elevation_points) as elevation_point
    WHERE collection_status IN ('COMPLETE', 'PARTIAL')
),
elevation_changes AS (
    SELECT 
        trail_id,
        trail_name,
        park_code,
        source,
        collection_status,
        total_points_count,
        failed_points_count,
        created_at,
        point_index,
        distance_m,
        elevation_m,
        -- Calculate elevation change from previous point
        elevation_m - LAG(elevation_m) OVER (PARTITION BY trail_id ORDER BY point_index) as elevation_change_m
    FROM elevation_data
)
SELECT 
    trail_id,
    trail_name,
    park_code,
    source,
    collection_status,
    total_points_count,
    failed_points_count,
    -- Basic elevation statistics
    MIN(elevation_m) as min_elevation_m,
    MAX(elevation_m) as max_elevation_m,
    AVG(elevation_m) as mean_elevation_m,
    -- Elevation change statistics
    SUM(CASE WHEN elevation_change_m > 0 THEN elevation_change_m ELSE 0 END) as elevation_gain_m,
    SUM(CASE WHEN elevation_change_m < 0 THEN ABS(elevation_change_m) ELSE 0 END) as elevation_loss_m,
    MAX(elevation_m) - MIN(elevation_m) as total_elevation_change_m,
    -- Trail length
    MAX(distance_m) as trail_length_m,
    created_at
FROM elevation_changes
GROUP BY trail_id, trail_name, park_code, source, collection_status, total_points_count, failed_points_count, created_at
ORDER BY park_code, trail_name;