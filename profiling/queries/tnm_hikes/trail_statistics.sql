-- TNM Trail Statistics Query
-- This query provides comprehensive statistics for TNM hiking trails by park

SELECT 
    park_code,
    COUNT(*) as trail_count,
    COUNT(CASE WHEN name IS NOT NULL AND name != '' THEN 1 END) as named_trail_count,
    COUNT(CASE WHEN name IS NULL OR name = '' THEN 1 END) as unnamed_trail_count,
    AVG(lengthmiles) as avg_length_miles,
    MIN(lengthmiles) as min_length_miles,
    MAX(lengthmiles) as max_length_miles,
    SUM(lengthmiles) as total_length_miles,
    COUNT(CASE WHEN hikerpedestrian = 'Y' THEN 1 END) as hiker_pedestrian_count,
    COUNT(CASE WHEN hikerpedestrian = 'N' THEN 1 END) as non_hiker_pedestrian_count,
    COUNT(CASE WHEN hikerpedestrian IS NULL THEN 1 END) as unknown_hiker_pedestrian_count,
    COUNT(CASE WHEN trailtype IS NOT NULL THEN 1 END) as typed_trail_count,
    COUNT(CASE WHEN nationaltraildesignation IS NOT NULL THEN 1 END) as designated_trail_count
FROM tnm_hikes
GROUP BY park_code
ORDER BY trail_count DESC; 