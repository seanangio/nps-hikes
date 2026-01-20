-- Trail matching summary statistics
-- Shows overall matching performance and source distribution

SELECT
    COUNT(*) as total_gmaps_points,
    COUNT(CASE WHEN matched = TRUE THEN 1 END) as successfully_matched,
    COUNT(CASE WHEN matched = FALSE THEN 1 END) as no_match,
    COUNT(CASE WHEN source = 'TNM' THEN 1 END) as tnm_matches,
    COUNT(CASE WHEN source = 'OSM' THEN 1 END) as osm_matches,
    ROUND(
        (COUNT(CASE WHEN matched = TRUE THEN 1 END)::float / COUNT(*) * 100)::numeric,
        1
    ) as match_rate_percent,
    ROUND(
        (COUNT(CASE WHEN source = 'TNM' THEN 1 END)::float / COUNT(CASE WHEN matched = TRUE THEN 1 END) * 100)::numeric,
        1
    ) as tnm_preference_percent
FROM gmaps_hiking_locations_matched;
