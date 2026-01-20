-- Park coverage analysis for Google Maps hiking locations
-- Shows which valid parks from the parks table are missing from the KML data

SELECT
    p.park_code,
    p.full_name,
    CASE
        WHEN g.park_code IS NOT NULL THEN 'Covered'
        ELSE 'Missing'
    END as coverage_status,
    COALESCE(g.location_count, 0) as gmaps_locations
FROM parks p
LEFT JOIN (
    SELECT park_code, COUNT(*) as location_count
    FROM gmaps_hiking_locations
    GROUP BY park_code
) g ON p.park_code = g.park_code
ORDER BY
    CASE WHEN g.park_code IS NOT NULL THEN 0 ELSE 1 END,
    g.location_count DESC NULLS LAST,
    p.park_code;
