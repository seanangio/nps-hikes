-- Boundary coverage analysis
SELECT
    p.states,
    COUNT(p.park_code) as total_parks,
    COUNT(b.park_code) as parks_with_boundaries,
    ROUND(COUNT(b.park_code) * 100.0 / COUNT(p.park_code), 1) as boundary_coverage_pct
FROM parks p
LEFT JOIN park_boundaries b ON p.park_code = b.park_code
GROUP BY p.states
ORDER BY boundary_coverage_pct DESC;
