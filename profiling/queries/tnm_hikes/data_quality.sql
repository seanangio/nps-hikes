-- TNM Data Quality Assessment Query
-- This query assesses data quality and completeness for TNM trail data

SELECT 
    park_code,
    COUNT(*) as total_trails,
    COUNT(CASE WHEN name IS NOT NULL AND name != '' THEN 1 END) as named_trails,
    COUNT(CASE WHEN lengthmiles IS NOT NULL THEN 1 END) as trails_with_length,
    COUNT(CASE WHEN trailtype IS NOT NULL THEN 1 END) as trails_with_type,
    COUNT(CASE WHEN hikerpedestrian IS NOT NULL THEN 1 END) as trails_with_hiker_status,
    COUNT(CASE WHEN primarytrailmaintainer IS NOT NULL THEN 1 END) as trails_with_maintainer,
    COUNT(CASE WHEN nationaltraildesignation IS NOT NULL THEN 1 END) as trails_with_designation,
    COUNT(CASE WHEN geometry IS NOT NULL THEN 1 END) as trails_with_geometry,
    ROUND(
        (COUNT(CASE WHEN name IS NOT NULL AND name != '' THEN 1 END)::numeric / COUNT(*) * 100), 2
    ) as name_completeness_percent,
    ROUND(
        (COUNT(CASE WHEN lengthmiles IS NOT NULL THEN 1 END)::numeric / COUNT(*) * 100), 2
    ) as length_completeness_percent,
    ROUND(
        (COUNT(CASE WHEN trailtype IS NOT NULL THEN 1 END)::numeric / COUNT(*) * 100), 2
    ) as type_completeness_percent,
    ROUND(
        (COUNT(CASE WHEN hikerpedestrian IS NOT NULL THEN 1 END)::numeric / COUNT(*) * 100), 2
    ) as hiker_status_completeness_percent,
    ROUND(
        (COUNT(CASE WHEN primarytrailmaintainer IS NOT NULL THEN 1 END)::numeric / COUNT(*) * 100), 2
    ) as maintainer_completeness_percent,
    ROUND(
        (COUNT(CASE WHEN nationaltraildesignation IS NOT NULL THEN 1 END)::numeric / COUNT(*) * 100), 2
    ) as designation_completeness_percent,
    ROUND(
        (COUNT(CASE WHEN geometry IS NOT NULL THEN 1 END)::numeric / COUNT(*) * 100), 2
    ) as geometry_completeness_percent
FROM tnm_hikes
GROUP BY park_code
ORDER BY total_trails DESC; 