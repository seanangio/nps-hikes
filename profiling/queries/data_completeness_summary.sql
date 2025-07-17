SELECT 
    COUNT(*) as total_parks,
    COUNT(CASE WHEN park_code IS NOT NULL AND park_code != '' THEN 1 END) as parks_with_codes,
    COUNT(CASE WHEN full_name IS NOT NULL AND full_name != '' THEN 1 END) as parks_with_names,
    COUNT(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1 END) as parks_with_coords,
    COUNT(CASE WHEN description IS NOT NULL AND description != '' THEN 1 END) as parks_with_descriptions,
    COUNT(CASE WHEN url IS NOT NULL AND url != '' THEN 1 END) as parks_with_urls,
    ROUND(COUNT(CASE WHEN park_code IS NOT NULL AND park_code != '' THEN 1 END) * 100.0 / COUNT(*), 1) as code_completeness_pct,
    ROUND(COUNT(CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 1 END) * 100.0 / COUNT(*), 1) as coord_completeness_pct,
    ROUND(COUNT(CASE WHEN description IS NOT NULL AND description != '' THEN 1 END) * 100.0 / COUNT(*), 1) as desc_completeness_pct
FROM parks