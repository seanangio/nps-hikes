-- Analyze coordinate data quality
SELECT 
    COUNT(*) as total_parks,
    COUNT(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1 END) as complete_coords,
    COUNT(CASE WHEN latitude IS NULL OR longitude IS NULL THEN 1 END) as missing_coords,
    COUNT(CASE WHEN latitude < -90 OR latitude > 90 THEN 1 END) as invalid_lat,
    COUNT(CASE WHEN longitude < -180 OR longitude > 180 THEN 1 END) as invalid_lon
FROM parks; 