-- Comparison of TNM vs OSM matching performance
-- Shows quality differences between data sources

SELECT 
    source,
    COUNT(*) as match_count,
    ROUND(AVG(confidence_score)::numeric, 3) as avg_confidence_score,
    ROUND(AVG(name_similarity_score)::numeric, 3) as avg_name_similarity,
    ROUND(AVG(min_point_to_trail_distance_m)::numeric, 1) as avg_distance_m,
    COUNT(CASE WHEN confidence_score > 0.9 THEN 1 END) as high_confidence_matches,
    ROUND(
        (COUNT(CASE WHEN confidence_score > 0.9 THEN 1 END)::float / COUNT(*) * 100)::numeric, 
        1
    ) as high_confidence_percent
FROM gmaps_hiking_locations_matched 
WHERE matched = TRUE
GROUP BY source
ORDER BY source;
