-- Basic summary statistics for Google Maps hiking locations
-- Shows total locations, coordinate completeness, and park coverage

SELECT
    COUNT(*) as total_locations,
    COUNT(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1 END) as locations_with_coordinates,
    COUNT(CASE WHEN latitude IS NULL OR longitude IS NULL THEN 1 END) as locations_without_coordinates,
    ROUND(
        (COUNT(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1 END)::float / COUNT(*) * 100)::numeric,
        1
    ) as coordinate_completeness_percent
FROM gmaps_hiking_locations;
