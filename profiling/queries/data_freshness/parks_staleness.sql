-- Parks Data Freshness Query
-- Shows collection dates and staleness status for all parks

SELECT
    park_code,
    full_name,
    collected_at,
    NOW() - collected_at as age,
    CASE
        WHEN collected_at >= NOW() - INTERVAL '7 days' THEN 'Fresh'
        WHEN collected_at >= NOW() - INTERVAL '30 days' THEN 'Warning'
        ELSE 'Stale'
    END as staleness_status,
    collection_status
FROM parks
ORDER BY collected_at ASC;
