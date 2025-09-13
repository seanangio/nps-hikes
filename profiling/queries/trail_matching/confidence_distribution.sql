-- Confidence score distribution for trail matching
-- Shows quality metrics and score ranges

SELECT 
    'Average Confidence Score' as metric,
    ROUND(AVG(confidence_score)::numeric, 3)::text as value
FROM gmaps_hiking_locations_matched 
WHERE match_status = 'MATCHED'

UNION ALL

SELECT 
    'Average Distance (meters)' as metric,
    ROUND(AVG(min_point_to_trail_distance_m)::numeric, 1)::text as value
FROM gmaps_hiking_locations_matched 
WHERE match_status = 'MATCHED'

UNION ALL

SELECT 
    'Average Name Similarity' as metric,
    ROUND(AVG(name_similarity_score)::numeric, 3)::text as value
FROM gmaps_hiking_locations_matched 
WHERE match_status = 'MATCHED'

UNION ALL

SELECT 
    'High Confidence Matches (>0.9)' as metric,
    COUNT(*)::text as value
FROM gmaps_hiking_locations_matched 
WHERE match_status = 'MATCHED' AND confidence_score > 0.9

UNION ALL

SELECT 
    'Medium Confidence Matches (0.7-0.9)' as metric,
    COUNT(*)::text as value
FROM gmaps_hiking_locations_matched 
WHERE match_status = 'MATCHED' AND confidence_score BETWEEN 0.7 AND 0.9

UNION ALL

SELECT 
    'Low Confidence Matches (<0.7)' as metric,
    COUNT(*)::text as value
FROM gmaps_hiking_locations_matched 
WHERE match_status = 'MATCHED' AND confidence_score < 0.7;
