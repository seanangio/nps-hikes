-- Trail summary statistics by park
-- Shows total trails, average/min/max length per park_code
-- Uses parks table as base to show ALL parks, including those with 0 trails

SELECT
    p.park_code,
    p.full_name,
    COALESCE(COUNT(o.osm_id), 0) as total_trails,
    COALESCE(ROUND(AVG(o.length_miles)::numeric, 3), 0) as avg_length_miles,
    COALESCE(ROUND(MIN(o.length_miles)::numeric, 3), 0) as min_length_miles,
    COALESCE(ROUND(MAX(o.length_miles)::numeric, 3), 0) as max_length_miles,
    COALESCE(ROUND(SUM(o.length_miles)::numeric, 2), 0) as total_length_miles
FROM parks p
LEFT JOIN osm_hikes o ON p.park_code = o.park_code
GROUP BY p.park_code, p.full_name
ORDER BY total_trails DESC, p.park_code;
