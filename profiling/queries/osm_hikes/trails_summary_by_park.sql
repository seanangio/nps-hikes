-- Trail summary statistics by park
-- Shows total trails, average/min/max length per park_code

SELECT 
    park_code,
    COUNT(*) as total_trails,
    ROUND(AVG(length_mi)::numeric, 3) as avg_length_mi,
    ROUND(MIN(length_mi)::numeric, 3) as min_length_mi,
    ROUND(MAX(length_mi)::numeric, 3) as max_length_mi,
    ROUND(SUM(length_mi)::numeric, 2) as total_length_mi
FROM osm_hikes 
WHERE length_mi IS NOT NULL
GROUP BY park_code
ORDER BY total_trails DESC;