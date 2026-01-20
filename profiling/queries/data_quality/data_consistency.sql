-- Data consistency checks across tables
-- Validates park codes, formats, and data consistency

SELECT 'Invalid Park Code Format' as check_type,
       COUNT(*)::varchar as count,
       CASE
           WHEN COUNT(*) > 0 THEN STRING_AGG(park_code, ', ')
           ELSE 'All valid'
       END as details
FROM (
    SELECT park_code FROM parks WHERE park_code !~ '^[a-z]{4}$'
    UNION
    SELECT park_code FROM park_boundaries WHERE park_code !~ '^[a-z]{4}$'
    UNION
    SELECT park_code FROM osm_hikes WHERE park_code !~ '^[a-z]{4}$'
) invalid_codes

UNION ALL

SELECT 'Duplicate Park Codes in Parks Table' as check_type,
       COUNT(*)::varchar as count,
       CASE
           WHEN COUNT(*) > 0 THEN STRING_AGG(park_code, ', ')
           ELSE 'None'
       END as details
FROM (
    SELECT park_code
    FROM parks
    GROUP BY park_code
    HAVING COUNT(*) > 1
) duplicates

UNION ALL

SELECT 'Parks with Multiple Names' as check_type,
       COUNT(*)::varchar as count,
       CASE
           WHEN COUNT(*) > 0 THEN STRING_AGG(park_code || '(' || name_count || ')', ', ')
           ELSE 'None'
       END as details
FROM (
    SELECT park_code, COUNT(DISTINCT park_name) as name_count
    FROM parks
    WHERE park_name IS NOT NULL
    GROUP BY park_code
    HAVING COUNT(DISTINCT park_name) > 1
) multi_names

UNION ALL

SELECT 'Missing Critical Park Data' as check_type,
       COUNT(*)::varchar as count,
       CASE
           WHEN COUNT(*) > 0 THEN STRING_AGG(park_code, ', ')
           ELSE 'All complete'
       END as details
FROM parks
WHERE park_name IS NULL OR park_code IS NULL

ORDER BY check_type;
