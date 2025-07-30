-- Analyze parks by geographic region
SELECT 
    CASE 
        WHEN longitude < -100 THEN 'Western'
        WHEN longitude < -80 THEN 'Central' 
        ELSE 'Eastern'
    END as region,
    COUNT(*) as park_count,
    COUNT(CASE WHEN latitude IS NOT NULL THEN 1 END) as parks_with_coords
FROM parks 
WHERE latitude IS NOT NULL
GROUP BY region
ORDER BY park_count DESC; 