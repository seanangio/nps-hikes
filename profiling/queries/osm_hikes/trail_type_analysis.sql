-- Trail analysis by highway type (footway, path, etc.)
-- Shows count and length statistics by trail type

SELECT 
    highway as trail_type,
    COUNT(*) as trail_count,
    ROUND(AVG(length_miles)::numeric, 3) as avg_length_miles,
    ROUND(MIN(length_miles)::numeric, 3) as min_length_miles,  
    ROUND(MAX(length_miles)::numeric, 3) as max_length_miles,
    ROUND(SUM(length_miles)::numeric, 2) as total_length_miles,
    ROUND((COUNT(*) * 100.0 / SUM(COUNT(*)) OVER())::numeric, 1) as percentage_of_trails
FROM osm_hikes
WHERE length_miles IS NOT NULL
GROUP BY highway
ORDER BY trail_count DESC;