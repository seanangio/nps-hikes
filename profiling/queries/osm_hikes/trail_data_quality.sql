-- Data quality checks for OSM hiking trails
-- Identifies missing data, potential issues, and geometry validation

SELECT 'Total Records' as check_type,
       COUNT(*)::varchar as count,
       '' as details
FROM osm_hikes

UNION ALL

SELECT 'Missing Length Data' as check_type,
       COUNT(*)::varchar as count,
       ROUND((COUNT(*) * 100.0 / (SELECT COUNT(*) FROM osm_hikes))::numeric, 1)::varchar || '%' as details
FROM osm_hikes
WHERE length_miles IS NULL

UNION ALL

SELECT 'Missing Park Code' as check_type,
       COUNT(*)::varchar as count,
       ROUND((COUNT(*) * 100.0 / (SELECT COUNT(*) FROM osm_hikes))::numeric, 1)::varchar || '%' as details
FROM osm_hikes
WHERE park_code IS NULL OR park_code = ''

UNION ALL

SELECT 'Missing Highway Type' as check_type,
       COUNT(*)::varchar as count,
       ROUND((COUNT(*) * 100.0 / (SELECT COUNT(*) FROM osm_hikes))::numeric, 1)::varchar || '%' as details
FROM osm_hikes
WHERE highway IS NULL OR highway = ''

UNION ALL

SELECT 'Zero Length Trails' as check_type,
       COUNT(*)::varchar as count,
       ROUND((COUNT(*) * 100.0 / (SELECT COUNT(*) FROM osm_hikes))::numeric, 1)::varchar || '%' as details
FROM osm_hikes
WHERE length_miles = 0

UNION ALL

SELECT 'Very Short Trails' as check_type,
       COUNT(*)::varchar as count,
       'Under 0.01 miles' as details
FROM osm_hikes
WHERE length_miles > 0 AND length_miles < 0.01

UNION ALL

SELECT 'Very Long Trails' as check_type,
       COUNT(*)::varchar as count,
       'Over 20 miles' as details
FROM osm_hikes
WHERE length_miles > 20

ORDER BY check_type;
