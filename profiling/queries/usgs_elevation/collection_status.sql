-- USGS elevation collection status summary
-- Provides overview of elevation data collection across all parks

WITH stats AS (
    SELECT 
        COUNT(DISTINCT park_code) as total_parks,
        COUNT(*) as total_trails,
        COUNT(CASE WHEN collection_status = 'COMPLETE' THEN 1 END) as complete_trails,
        COUNT(CASE WHEN collection_status = 'PARTIAL' THEN 1 END) as partial_trails,
        COUNT(CASE WHEN collection_status = 'FAILED' THEN 1 END) as failed_trails,
        SUM(total_points_count) as total_elevation_points,
        SUM(failed_points_count) as total_failed_points
    FROM usgs_trail_elevations
)
SELECT 
    'Total Parks' as metric,
    total_parks::text as value
FROM stats

UNION ALL

SELECT 
    'Total Trails' as metric,
    total_trails::text as value
FROM stats

UNION ALL

SELECT 
    'Complete Collections' as metric,
    complete_trails::text as value
FROM stats

UNION ALL

SELECT 
    'Partial Collections' as metric,
    partial_trails::text as value
FROM stats

UNION ALL

SELECT 
    'Failed Collections' as metric,
    failed_trails::text as value
FROM stats

UNION ALL

SELECT 
    'Total Elevation Points' as metric,
    total_elevation_points::text as value
FROM stats

UNION ALL

SELECT 
    'Failed Elevation Points' as metric,
    total_failed_points::text as value
FROM stats

UNION ALL

SELECT 
    'Success Rate (%)' as metric,
    ROUND(complete_trails::numeric / total_trails * 100, 2)::text as value
FROM stats

UNION ALL

SELECT 
    'Data Completeness (%)' as metric,
    ROUND((total_elevation_points - total_failed_points)::numeric / NULLIF(total_elevation_points, 0) * 100, 2)::text as value
FROM stats

ORDER BY metric;