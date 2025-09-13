-- Trail matching analysis by park
-- Shows matching performance and source preferences by park

SELECT 
    park_code,
    COUNT(*) as total_points,
    COUNT(CASE WHEN match_status = 'MATCHED' THEN 1 END) as matched_points,
    COUNT(CASE WHEN match_status = 'NO_MATCH' THEN 1 END) as unmatched_points,
    COUNT(CASE WHEN source = 'TNM' THEN 1 END) as tnm_matches,
    COUNT(CASE WHEN source = 'OSM' THEN 1 END) as osm_matches,
    ROUND(
        (COUNT(CASE WHEN match_status = 'MATCHED' THEN 1 END)::float / COUNT(*) * 100)::numeric, 
        1
    ) as match_rate_percent,
    ROUND(AVG(confidence_score)::numeric, 3) as avg_confidence_score,
    ROUND(AVG(min_point_to_trail_distance_m)::numeric, 1) as avg_distance_m
FROM gmaps_hiking_locations_matched
GROUP BY park_code
ORDER BY match_rate_percent DESC, total_points DESC;
