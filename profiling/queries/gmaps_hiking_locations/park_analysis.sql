-- Park-level analysis for Google Maps hiking locations
-- Shows detailed statistics per park including coordinate completeness and averages

SELECT
    park_code,
    COUNT(*) as total_locations,
    COUNT(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1 END) as with_coordinates,
    COUNT(CASE WHEN latitude IS NULL OR longitude IS NULL THEN 1 END) as without_coordinates,
    ROUND(
        (COUNT(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1 END)::float / COUNT(*) * 100)::numeric,
        1
    ) as coordinate_completeness_percent,
    ROUND(AVG(latitude)::numeric, 6) as avg_latitude,
    ROUND(AVG(longitude)::numeric, 6) as avg_longitude
FROM gmaps_hiking_locations
GROUP BY park_code
ORDER BY total_locations DESC, park_code;
