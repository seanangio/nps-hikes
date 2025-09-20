-- TNM vs OSM Comparison Query
-- This query compares TNM data with OSM data for the same parks

SELECT 
    t.park_code,
    COUNT(DISTINCT t.permanent_identifier) as tnm_trail_count,
    COUNT(DISTINCT o.osm_id) as osm_trail_count,
    COALESCE(SUM(t.length_miles), 0) as tnm_total_length,
    COALESCE(SUM(o.length_mi), 0) as osm_total_length,
    COALESCE(AVG(t.length_miles), 0) as tnm_avg_length,
    COALESCE(AVG(o.length_mi), 0) as osm_avg_length,
    CASE 
        WHEN COUNT(DISTINCT o.osm_id) > 0 
        THEN ROUND(COUNT(DISTINCT t.permanent_identifier)::numeric / COUNT(DISTINCT o.osm_id), 3)
        ELSE NULL 
    END as trail_count_ratio,
    CASE 
        WHEN COALESCE(SUM(o.length_mi), 0) > 0 
        THEN ROUND((COALESCE(SUM(t.length_miles), 0)::numeric / COALESCE(SUM(o.length_mi), 0)::numeric), 3)
        ELSE NULL 
    END as length_ratio,
    CASE 
        WHEN COALESCE(AVG(o.length_mi), 0) > 0 
        THEN ROUND((COALESCE(AVG(t.length_miles), 0)::numeric / COALESCE(AVG(o.length_mi), 0)::numeric), 3)
        ELSE NULL 
    END as avg_length_ratio
FROM tnm_hikes t
FULL OUTER JOIN osm_hikes o ON t.park_code = o.park_code
GROUP BY t.park_code
ORDER BY tnm_trail_count DESC; 