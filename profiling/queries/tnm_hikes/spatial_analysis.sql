-- TNM Spatial Analysis Query
-- This query performs spatial analysis on TNM trail data

SELECT
    park_code,
    COUNT(*) as trail_count,
    ST_Length(ST_Union(geometry)) as total_geometry_length,
    ST_Area(ST_ConvexHull(ST_Union(geometry))) as convex_hull_area,
    ST_AsText(ST_Centroid(ST_Union(geometry))) as centroid,
    ST_AsText(ST_Envelope(ST_Union(geometry))) as bounding_box
FROM tnm_hikes
GROUP BY park_code
ORDER BY trail_count DESC;
