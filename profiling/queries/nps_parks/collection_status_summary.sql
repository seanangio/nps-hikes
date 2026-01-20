-- Collection status summary
SELECT
    collection_status,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) as percentage
FROM parks
GROUP BY collection_status
ORDER BY count DESC;
