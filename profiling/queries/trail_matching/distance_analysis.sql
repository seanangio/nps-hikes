-- Distance analysis for trail matching
-- Shows geographic accuracy of matches

WITH distance_ranges AS (
    SELECT 
        CASE 
            WHEN min_point_to_trail_distance_m = 0 THEN '0m (exact)'
            WHEN min_point_to_trail_distance_m <= 10 THEN '1-10m'
            WHEN min_point_to_trail_distance_m <= 25 THEN '11-25m'
            WHEN min_point_to_trail_distance_m <= 50 THEN '26-50m'
            WHEN min_point_to_trail_distance_m <= 100 THEN '51-100m'
            ELSE '>100m'
        END as distance_range,
        CASE 
            WHEN min_point_to_trail_distance_m = 0 THEN 0
            WHEN min_point_to_trail_distance_m <= 10 THEN 1
            WHEN min_point_to_trail_distance_m <= 25 THEN 2
            WHEN min_point_to_trail_distance_m <= 50 THEN 3
            WHEN min_point_to_trail_distance_m <= 100 THEN 4
            ELSE 5
        END as sort_order,
        confidence_score
    FROM gmaps_hiking_locations_matched 
    WHERE matched = TRUE
)
SELECT 
    distance_range,
    COUNT(*) as match_count,
    ROUND((COUNT(*)::float / SUM(COUNT(*)) OVER() * 100)::numeric, 1) as percentage,
    ROUND(AVG(confidence_score)::numeric, 3) as avg_confidence_score
FROM distance_ranges
GROUP BY distance_range, sort_order
ORDER BY sort_order;
