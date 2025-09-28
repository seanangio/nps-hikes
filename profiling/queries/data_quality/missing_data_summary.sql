-- Comprehensive missing data summary across all tables
-- Shows data completeness percentages for key fields

SELECT 
    'parks' as table_name,
    COUNT(*) as total_records,
    ROUND((COUNT(park_code) * 100.0 / COUNT(*))::numeric, 1) || '%' as park_code_complete,
    ROUND((COUNT(park_name) * 100.0 / COUNT(*))::numeric, 1) || '%' as name_complete,
    ROUND((COUNT(latitude) * 100.0 / COUNT(*))::numeric, 1) || '%' as latitude_complete,
    ROUND((COUNT(longitude) * 100.0 / COUNT(*))::numeric, 1) || '%' as longitude_complete
FROM parks

UNION ALL

SELECT 
    'park_boundaries' as table_name,
    COUNT(*) as total_records,
    ROUND((COUNT(park_code) * 100.0 / COUNT(*))::numeric, 1) || '%' as park_code_complete,
    'N/A' as name_complete,
    'N/A' as latitude_complete,
    ROUND((COUNT(geometry) * 100.0 / COUNT(*))::numeric, 1) || '%' as geometry_complete
FROM park_boundaries

UNION ALL

SELECT 
    'osm_hikes' as table_name,
    COUNT(*) as total_records,
    ROUND((COUNT(park_code) * 100.0 / COUNT(*))::numeric, 1) || '%' as park_code_complete,
    ROUND((COUNT(name) * 100.0 / COUNT(*))::numeric, 1) || '%' as name_complete,
    ROUND((COUNT(length_miles) * 100.0 / COUNT(*))::numeric, 1) || '%' as length_complete,
    ROUND((COUNT(highway) * 100.0 / COUNT(*))::numeric, 1) || '%' as highway_complete

ORDER BY table_name;