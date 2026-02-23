# Artifacts Directory

This directory contains generated files from the NPS hiking data collection process.

## Contents

- `*.gpkg` - GeoPackage files with collected trail and boundary data
- `*.csv` - Generated CSV reports from collection scripts
- `test_results.xml` - pytest coverage reports

## Usage

- **Collection scripts**: Write output files here.
- **Profiling modules**: Read from these files for analysis.
- **Safe to delete**: You can regenerate all files by re-running collection scripts.
- **Not version controlled**: These are temporary artifacts.

## Regeneration

To regenerate all artifacts:
```bash
# Clear the directory
rm artifacts/*

# Re-run collection scripts
python scripts/collectors/nps_collector.py --write-db
python scripts/collectors/osm_hikes_collector.py --write-db
python scripts/collectors/tnm_hikes_collector.py --write-db
```

## Notes

- Data collection runs generate these files.
- Keep this directory structure for consistent file paths.
- The `.gitkeep` file ensures that Git tracks this directory.
