-- Trail analysis by highway type (footway, path, etc.)
-- Shows count and length statistics by trail type

SELECT 
    highway as trail_type,
    COUNT(*) as trail_count,
    ROUND(AVG(length_mi)::numeric, 3) as avg_length_mi,
    ROUND(MIN(length_mi)::numeric, 3) as min_length_mi,  
    ROUND(MAX(length_mi)::numeric, 3) as max_length_mi,
    ROUND(SUM(length_mi)::numeric, 2) as total_length_mi,
    ROUND((COUNT(*) * 100.0 / SUM(COUNT(*)) OVER())::numeric, 1) as percentage_of_trails
FROM park_hikes
WHERE length_mi IS NOT NULL
GROUP BY highway
ORDER BY trail_count DESC;