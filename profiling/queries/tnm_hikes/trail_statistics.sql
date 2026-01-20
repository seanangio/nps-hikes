-- TNM Trail Statistics Query
-- This query provides comprehensive statistics for TNM hiking trails by park
-- Uses parks table as base to show ALL parks, including those with 0 trails

SELECT
    p.park_code,
    p.full_name,
    COALESCE(COUNT(t.permanent_identifier), 0) as trail_count,
    COALESCE(COUNT(CASE WHEN t.name IS NOT NULL AND t.name != '' THEN 1 END), 0) as named_trail_count,
    COALESCE(COUNT(CASE WHEN t.name IS NULL OR t.name = '' THEN 1 END), 0) as unnamed_trail_count,
    COALESCE(AVG(t.length_miles), 0) as avg_length_miles,
    COALESCE(MIN(t.length_miles), 0) as min_length_miles,
    COALESCE(MAX(t.length_miles), 0) as max_length_miles,
    COALESCE(SUM(t.length_miles), 0) as total_length_miles,
    COALESCE(COUNT(CASE WHEN t.hiker_pedestrian = 'Y' THEN 1 END), 0) as hiker_pedestrian_count,
    COALESCE(COUNT(CASE WHEN t.hiker_pedestrian = 'N' THEN 1 END), 0) as non_hiker_pedestrian_count,
    COALESCE(COUNT(CASE WHEN t.hiker_pedestrian IS NULL THEN 1 END), 0) as unknown_hiker_pedestrian_count,
    COALESCE(COUNT(CASE WHEN t.trail_type IS NOT NULL THEN 1 END), 0) as typed_trail_count,
    COALESCE(COUNT(CASE WHEN t.national_trail_designation IS NOT NULL THEN 1 END), 0) as designated_trail_count
FROM parks p
LEFT JOIN tnm_hikes t ON p.park_code = t.park_code
GROUP BY p.park_code, p.full_name
ORDER BY trail_count DESC, p.park_code;
