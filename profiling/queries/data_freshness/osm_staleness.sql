-- OSM Hikes Data Freshness Query (Park-Level Summary)
-- Shows the most recent trail collection date per park and staleness status

SELECT 
    park_code,
    MAX(collected_at) as latest_trail_collected,
    MIN(collected_at) as oldest_trail_collected,
    COUNT(*) as total_trails,
    NOW() - MAX(collected_at) as age_of_freshest_data,
    CASE 
        WHEN MAX(collected_at) >= NOW() - INTERVAL '7 days' THEN 'Fresh'
        WHEN MAX(collected_at) >= NOW() - INTERVAL '30 days' THEN 'Warning'
        ELSE 'Stale'
    END as staleness_status
FROM osm_hikes 
GROUP BY park_code
ORDER BY latest_trail_collected ASC; 