-- Park-level elevation summary statistics
-- Aggregates trail-level stats to park level

WITH trail_stats AS (
    SELECT
        gmaps_location_id,
        trail_name,
        park_code,
        source,
        collection_status,
        total_points_count,
        failed_points_count,
        MIN(elevation_m) as min_elevation_m,
        MAX(elevation_m) as max_elevation_m,
        AVG(elevation_m) as mean_elevation_m,
        SUM(CASE WHEN elevation_change_m > 0 THEN elevation_change_m ELSE 0 END) as elevation_gain_m,
        SUM(CASE WHEN elevation_change_m < 0 THEN ABS(elevation_change_m) ELSE 0 END) as elevation_loss_m,
        MAX(elevation_m) - MIN(elevation_m) as total_elevation_change_m,
        MAX(distance_m) as trail_length_m
    FROM (
        SELECT
            gmaps_location_id,
            trail_name,
            park_code,
            source,
            collection_status,
            total_points_count,
            failed_points_count,
            (elevation_point->>'point_index')::int as point_index,
            (elevation_point->>'distance_m')::numeric as distance_m,
            (elevation_point->>'elevation_m')::numeric as elevation_m,
            (elevation_point->>'elevation_m')::numeric -
            LAG((elevation_point->>'elevation_m')::numeric) OVER (PARTITION BY gmaps_location_id ORDER BY (elevation_point->>'point_index')::int) as elevation_change_m
        FROM usgs_trail_elevations,
             jsonb_array_elements(elevation_points) as elevation_point
        WHERE collection_status IN ('COMPLETE', 'PARTIAL')
    ) elevation_changes
    GROUP BY gmaps_location_id, trail_name, park_code, source, collection_status, total_points_count, failed_points_count
)
SELECT
    park_code,
    COUNT(*) as total_trails,
    COUNT(CASE WHEN collection_status = 'COMPLETE' THEN 1 END) as complete_trails,
    COUNT(CASE WHEN collection_status = 'PARTIAL' THEN 1 END) as partial_trails,
    COUNT(CASE WHEN collection_status = 'FAILED' THEN 1 END) as failed_trails,
    SUM(total_points_count) as total_elevation_points,
    SUM(failed_points_count) as total_failed_points,
    -- Park elevation statistics
    MIN(min_elevation_m) as park_min_elevation_m,
    MAX(max_elevation_m) as park_max_elevation_m,
    AVG(mean_elevation_m) as park_avg_elevation_m,
    -- Park elevation change statistics
    SUM(elevation_gain_m) as total_elevation_gain_m,
    SUM(elevation_loss_m) as total_elevation_loss_m,
    MAX(total_elevation_change_m) as max_trail_elevation_change_m,
    AVG(total_elevation_change_m) as avg_trail_elevation_change_m,
    -- Trail length statistics
    SUM(trail_length_m) as total_trail_length_m,
    AVG(trail_length_m) as avg_trail_length_m,
    MAX(trail_length_m) as max_trail_length_m,
    MIN(trail_length_m) as min_trail_length_m
FROM trail_stats
GROUP BY park_code
ORDER BY park_code;
