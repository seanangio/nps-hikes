-- Trail length distribution analysis
-- Shows quartiles and length buckets to understand trail length patterns

WITH length_stats AS (
    SELECT 
        COUNT(*) as total_trails,
        ROUND(AVG(length_mi)::numeric, 3) as avg_length,
        ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY length_mi)::numeric, 3) as q1_length,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY length_mi)::numeric, 3) as median_length,
        ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY length_mi)::numeric, 3) as q3_length,
        ROUND(MAX(length_mi)::numeric, 3) as max_length
    FROM osm_hikes 
    WHERE length_mi IS NOT NULL
),
length_buckets AS (
    SELECT 
        CASE 
            WHEN length_mi < 0.5 THEN 'Under 0.5 mi'
            WHEN length_mi < 1.0 THEN '0.5 - 1.0 mi'
            WHEN length_mi < 2.0 THEN '1.0 - 2.0 mi'  
            WHEN length_mi < 5.0 THEN '2.0 - 5.0 mi'
            ELSE 'Over 5.0 mi'
        END as length_bucket,
        COUNT(*) as trail_count
    FROM osm_hikes
    WHERE length_mi IS NOT NULL
    GROUP BY 1
)
SELECT 'Length Statistics' as analysis_type, 
       CAST(total_trails as varchar) as value1,
       CAST(avg_length as varchar) as value2,
       CAST(median_length as varchar) as value3,
       CAST(q3_length as varchar) as value4,
       CAST(max_length as varchar) as value5
FROM length_stats
UNION ALL
SELECT 'Length Buckets' as analysis_type,
       length_bucket as value1,
       CAST(trail_count as varchar) as value2,
       '' as value3, '' as value4, '' as value5
FROM length_buckets
ORDER BY analysis_type, value1;