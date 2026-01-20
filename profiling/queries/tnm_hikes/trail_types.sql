-- TNM Trail Type Breakdown Query
-- This query provides breakdown of trails by type and designation

-- Trail type breakdown
SELECT
    trail_type,
    COUNT(*) as count,
    AVG(length_miles) as avg_length_miles,
    SUM(length_miles) as total_length_miles
FROM tnm_hikes
GROUP BY trail_type
ORDER BY count DESC;

-- National designation breakdown
SELECT
    national_trail_designation,
    COUNT(*) as count,
    AVG(length_miles) as avg_length_miles,
    SUM(length_miles) as total_length_miles
FROM tnm_hikes
GROUP BY national_trail_designation
ORDER BY count DESC;
