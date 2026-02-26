# NPS Hikes - National Park Hiking Trail Data Collection & Analysis

[![Unit Tests](https://github.com/seanangio/nps-hikes/actions/workflows/unit-tests.yml/badge.svg)](https://github.com/seanangio/nps-hikes/actions/workflows/unit-tests.yml) [![Python](https://img.shields.io/badge/python-3.12%2B-blue)]() [![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

A Python project for collecting, validating, and analyzing hiking trail data from U.S. National Parks. The project combines data from the National Park Service API, OpenStreetMap, and the USGS to build a PostGIS database of park boundaries and hiking trails, queryable through a REST API.

> **Tip**: See [https://seanangio.github.io/nps-hikes/](https://seanangio.github.io/nps-hikes/) for the full documentation, including live demo details.

## Project overview

- Collect park metadata and boundaries from the NPS API.
- Extract hiking trails from OpenStreetMap and The National Map.
- Match personal hiking locations to trail geometries.
- Explore parks and trails through a FastAPI REST API.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Python 3.12+
- A free [NPS API key](https://www.nps.gov/subjects/developer/get-started.htm)

## Quick start

See the [Getting Started](https://seanangio.github.io/nps-hikes/getting-started/) guide for the complete setup instructions. The short version:

```bash
git clone https://github.com/seanangio/nps-hikes.git
cd nps-hikes
cp .env.example .env              # add your NPS API key and a database password
docker compose up --build -d      # start the database and API
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/orchestrator.py --write-db --test-limit 1
```

Then open http://localhost:8000/docs to explore the API.

## Development

For development work, you'll need:

```bash
pip install -r requirements-dev.txt
pre-commit install
pytest tests/
```

## License

I've licensed this project under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
