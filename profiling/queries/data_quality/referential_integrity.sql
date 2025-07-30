-- Referential integrity checks between tables
-- Validates relationships between parks, park_boundaries, and park_hikes

SELECT 'Parks without Boundaries' as check_type,
       COUNT(*)::varchar as count,
       CASE 
           WHEN COUNT(*) > 0 THEN STRING_AGG(park_code, ', ')
           ELSE 'None'
       END as details
FROM parks p
WHERE NOT EXISTS (
    SELECT 1 FROM park_boundaries pb 
    WHERE pb.park_code = p.park_code
)

UNION ALL

SELECT 'Parks without Trails' as check_type,
       COUNT(*)::varchar as count,
       CASE 
           WHEN COUNT(*) > 0 THEN STRING_AGG(park_code, ', ')
           ELSE 'None'
       END as details
FROM parks p
WHERE NOT EXISTS (
    SELECT 1 FROM park_hikes ph 
    WHERE ph.park_code = p.park_code
)

UNION ALL

SELECT 'Orphaned Boundaries' as check_type,
       COUNT(*)::varchar as count,
       CASE 
           WHEN COUNT(*) > 0 THEN STRING_AGG(DISTINCT park_code, ', ')
           ELSE 'None'
       END as details
FROM park_boundaries pb
WHERE NOT EXISTS (
    SELECT 1 FROM parks p 
    WHERE p.park_code = pb.park_code
)

UNION ALL

SELECT 'Orphaned Trails' as check_type,
       COUNT(*)::varchar as count,
       CASE 
           WHEN COUNT(*) > 0 THEN STRING_AGG(DISTINCT park_code, ', ')
           ELSE 'None'
       END as details
FROM park_hikes ph
WHERE NOT EXISTS (
    SELECT 1 FROM parks p 
    WHERE p.park_code = ph.park_code
)

ORDER BY check_type;