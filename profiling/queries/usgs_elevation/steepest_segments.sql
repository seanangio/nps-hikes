-- Steepest trail segments analysis
-- Identifies the steepest segments on each trail and where they occur

WITH elevation_segments AS (
    SELECT 
        trail_id,
        trail_name,
        park_code,
        source,
        (elevation_point->>'point_index')::int as point_index,
        (elevation_point->>'distance_m')::numeric as distance_m,
        (elevation_point->>'elevation_m')::numeric as elevation_m,
        (elevation_point->>'latitude')::numeric as latitude,
        (elevation_point->>'longitude')::numeric as longitude,
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
        latitude,
        longitude,
        segment_distance_m,
        segment_elevation_change_m,
        -- Calculate grade as percentage
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
    WHERE segment_distance_m IS NOT NULL AND segment_distance_m > 0
),
steepest_per_trail AS (
    SELECT 
        trail_id,
        trail_name,
        park_code,
        source,
        point_index,
        distance_m,
        elevation_m,
        latitude,
        longitude,
        segment_distance_m,
        segment_elevation_change_m,
        grade_percent,
        absolute_grade_percent,
        ROW_NUMBER() OVER (PARTITION BY trail_id ORDER BY absolute_grade_percent DESC) as steepness_rank
    FROM grade_calculations
)
SELECT 
    trail_id,
    trail_name,
    park_code,
    source,
    point_index,
    distance_m,
    elevation_m,
    latitude,
    longitude,
    segment_distance_m,
    segment_elevation_change_m,
    grade_percent,
    absolute_grade_percent,
    -- Calculate position along trail as percentage
    ROUND((distance_m / MAX(distance_m) OVER (PARTITION BY trail_id)) * 100, 1) as position_percent_of_trail,
    -- Trail statistics for context
    MAX(distance_m) OVER (PARTITION BY trail_id) as total_trail_length_m,
    MAX(elevation_m) OVER (PARTITION BY trail_id) as trail_max_elevation_m,
    MIN(elevation_m) OVER (PARTITION BY trail_id) as trail_min_elevation_m
FROM steepest_per_trail
WHERE steepness_rank <= 5  -- Top 5 steepest segments per trail
ORDER BY park_code, trail_name, absolute_grade_percent DESC;
