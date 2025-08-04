-- TNM Trail Type Breakdown Query
-- This query provides breakdown of trails by type and designation

-- Trail type breakdown
SELECT 
    trailtype,
    COUNT(*) as count,
    AVG(lengthmiles) as avg_length_miles,
    SUM(lengthmiles) as total_length_miles
FROM tnm_hikes
GROUP BY trailtype
ORDER BY count DESC;

-- National designation breakdown
SELECT 
    nationaltraildesignation,
    COUNT(*) as count,
    AVG(lengthmiles) as avg_length_miles,
    SUM(lengthmiles) as total_length_miles
FROM tnm_hikes
GROUP BY nationaltraildesignation
ORDER BY count DESC; 