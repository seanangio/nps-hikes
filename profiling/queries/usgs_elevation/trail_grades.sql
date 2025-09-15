-- Trail grade analysis
-- Calculates steepness (grade) between consecutive elevation points
-- Grade is calculated as (elevation_change / horizontal_distance) * 100

WITH elevation_segments AS (
    SELECT 
        trail_id,
        trail_name,
        park_code,
        source,
        (elevation_point->>'point_index')::int as point_index,
        (elevation_point->>'distance_m')::numeric as distance_m,
        (elevation_point->>'elevation_m')::numeric as elevation_m,
        -- Calculate distance and elevation change from previous point
        (elevation_point->>'distance_m')::numeric - 
        LAG((elevation_point->>'distance_m')::numeric) OVER (PARTITION BY trail_id ORDER BY (elevation_point->>'point_index')::int) as segment_distance_m,
        (elevation_point->>'elevation_m')::numeric - 
        LAG((elevation_point->>'elevation_m')::numeric) OVER (PARTITION BY trail_id ORDER BY (elevation_point->>'point_index')::int) as segment_elevation_change_m
    FROM usgs_trail_elevations,
         jsonb_array_elements(elevation_points) as elevation_point
    WHERE collection_status IN ('COMPLETE', 'PARTIAL')
),
grade_calculations AS (
    SELECT 
        trail_id,
        trail_name,
        park_code,
        source,
        point_index,
        distance_m,
        elevation_m,
        segment_distance_m,
        segment_elevation_change_m,
        -- Calculate grade as percentage (elevation_change / horizontal_distance * 100)
        CASE 
            WHEN segment_distance_m > 0 
            THEN (segment_elevation_change_m / segment_distance_m) * 100
            ELSE 0
        END as grade_percent,
        -- Calculate absolute grade (steepness regardless of direction)
        CASE 
            WHEN segment_distance_m > 0 
            THEN ABS(segment_elevation_change_m / segment_distance_m) * 100
            ELSE 0
        END as absolute_grade_percent
    FROM elevation_segments
    WHERE segment_distance_m IS NOT NULL
)
SELECT 
    trail_id,
    trail_name,
    park_code,
    source,
    -- Grade statistics
    MIN(grade_percent) as min_grade_percent,
    MAX(grade_percent) as max_grade_percent,
    AVG(grade_percent) as avg_grade_percent,
    MIN(absolute_grade_percent) as min_steepness_percent,
    MAX(absolute_grade_percent) as max_steepness_percent,
    AVG(absolute_grade_percent) as avg_steepness_percent,
    -- Find steepest segments
    MAX(absolute_grade_percent) as steepest_grade_percent,
    -- Count segments by steepness categories
    COUNT(CASE WHEN absolute_grade_percent < 5 THEN 1 END) as gentle_segments,
    COUNT(CASE WHEN absolute_grade_percent >= 5 AND absolute_grade_percent < 10 THEN 1 END) as moderate_segments,
    COUNT(CASE WHEN absolute_grade_percent >= 10 AND absolute_grade_percent < 20 THEN 1 END) as steep_segments,
    COUNT(CASE WHEN absolute_grade_percent >= 20 THEN 1 END) as very_steep_segments,
    -- Total segments
    COUNT(*) as total_segments,
    -- Trail length
    MAX(distance_m) as trail_length_m
FROM grade_calculations
GROUP BY trail_id, trail_name, park_code, source
ORDER BY park_code, trail_name;
