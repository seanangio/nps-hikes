-- Park counts by individual state with coordinate coverage
SELECT 
    TRIM(unnest(string_to_array(states, ','))) as individual_state,
    COUNT(*) as park_count,
    COUNT(CASE WHEN latitude IS NOT NULL THEN 1 END) as parks_with_coords,
    COUNT(CASE WHEN collection_status = 'success' THEN 1 END) as successful_collections,
    ROUND(COUNT(CASE WHEN latitude IS NOT NULL THEN 1 END) * 100.0 / COUNT(*), 1) as coord_coverage_pct,
    ROUND(COUNT(CASE WHEN collection_status = 'success' THEN 1 END) * 100.0 / COUNT(*), 1) as success_rate_pct
FROM parks 
WHERE states IS NOT NULL 
    AND states != '' 
    AND states != 'null'
GROUP BY TRIM(unnest(string_to_array(states, ',')))
ORDER BY park_count DESC; 