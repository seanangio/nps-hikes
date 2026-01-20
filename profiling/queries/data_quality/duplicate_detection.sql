-- Duplicate detection across all tables
-- Identifies potential duplicate records that need investigation

SELECT 'Duplicate Parks by Name' as check_type,
       COUNT(*)::varchar as count,
       CASE
           WHEN COUNT(*) > 0 THEN STRING_AGG(normalized_name || '(' || dup_count || ')', ', ')
           ELSE 'None found'
       END as details
FROM (
    SELECT LOWER(TRIM(park_name)) as normalized_name, COUNT(*) as dup_count
    FROM parks
    WHERE park_name IS NOT NULL
    GROUP BY LOWER(TRIM(park_name))
    HAVING COUNT(*) > 1
) name_dups

UNION ALL

SELECT 'Duplicate Parks by Coordinates' as check_type,
       COUNT(*)::varchar as count,
       CASE
           WHEN COUNT(*) > 0 THEN STRING_AGG(coord_key || '(' || dup_count || ')', ', ')
           ELSE 'None found'
       END as details
FROM (
    SELECT
        ROUND(latitude::numeric, 4) || ',' || ROUND(longitude::numeric, 4) as coord_key,
        COUNT(*) as dup_count
    FROM parks
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    GROUP BY ROUND(latitude::numeric, 4), ROUND(longitude::numeric, 4)
    HAVING COUNT(*) > 1
) coord_dups

UNION ALL

SELECT 'Duplicate Trail OSM IDs' as check_type,
       COUNT(*)::varchar as count,
       CASE
           WHEN COUNT(*) > 0 THEN STRING_AGG(osm_id::varchar || '(' || dup_count || ')', ', ')
           ELSE 'None found'
       END as details
FROM (
    SELECT osm_id, COUNT(*) as dup_count
    FROM osm_hikes
    WHERE osm_id IS NOT NULL
    GROUP BY osm_id
    HAVING COUNT(*) > 1
) osm_dups

UNION ALL

SELECT 'Boundary Duplicates per Park' as check_type,
       COUNT(*)::varchar as count,
       CASE
           WHEN COUNT(*) > 0 THEN STRING_AGG(park_code || '(' || boundary_count || ')', ', ')
           ELSE 'All parks have unique boundaries'
       END as details
FROM (
    SELECT park_code, COUNT(*) as boundary_count
    FROM park_boundaries
    GROUP BY park_code
    HAVING COUNT(*) > 5  -- Flag parks with unusually many boundary records
) boundary_dups

ORDER BY check_type;
