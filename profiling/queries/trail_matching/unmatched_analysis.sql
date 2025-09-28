-- Analysis of unmatched GMaps points
-- Shows which points couldn't be matched and potential reasons

SELECT 
    park_code,
    location_name,
    latitude,
    longitude,
    'No matching trail found within 100m' as potential_reason
FROM gmaps_hiking_locations_matched 
WHERE matched = FALSE
ORDER BY park_code, location_name;
