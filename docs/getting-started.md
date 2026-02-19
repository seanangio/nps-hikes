# Getting Started

This guide walks you through setting up NPS Hikes from scratch: collecting national park and trail data, personalizing it with your own visit history, and exploring it through the REST API. By the end, you'll have a PostGIS database with all 63 U.S. national parks and thousands of hiking trails, queryable through an interactive API.

## What you'll need

Before you begin, make sure you have the following installed and ready:

- **Docker Desktop** &mdash; [Install Docker Desktop](https://www.docker.com/products/docker-desktop/) for your platform. Docker runs the database and API in containers so you don't need to install PostgreSQL or PostGIS locally.
- **Python 3.12+** &mdash; The data collection scripts run on your local machine. Check your version with `python3 --version`. If you need to install or upgrade, see [python.org](https://www.python.org/downloads/) or use a version manager like [pyenv](https://github.com/pyenv/pyenv).
- **Git** &mdash; To clone the repository.
- **An NPS API key** &mdash; Free and instant. Sign up at the [NPS Developer Portal](https://www.nps.gov/subjects/developer/get-started.htm). You'll receive your key by email within minutes.

## Step 1: Clone the repository

```bash
git clone https://github.com/seanangio/nps-hikes.git
cd nps-hikes
```

## Step 2: Set up a Python environment

Create a virtual environment and install the project dependencies. These are needed for the data collection pipeline, which runs outside of Docker.

```bash
python3.12 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> **Tip:** If you use [pyenv](https://github.com/pyenv/pyenv), the `.python-version` file in the repo will automatically select the right Python version.

## Step 3: Configure environment variables

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Open `.env` in your editor. You need to set three values:

```dotenv
# Required: your NPS API key from Step 0
NPS_API_KEY=your_actual_api_key

# Required: choose any password for the Docker database
POSTGRES_PASSWORD=choose_a_password

# Required: choose a database username (or keep the default)
POSTGRES_USER=postgres
```

The remaining defaults work as-is for the Docker setup:

```dotenv
# These defaults are fine — no changes needed
NPS_USER_EMAIL=your_email@example.com
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=nps_hikes_db
```

> **How the `.env` file is used:** Docker Compose reads it automatically to configure the database container. The Python scripts also read it (via `python-dotenv`) for API credentials and database connections.

## Step 4: Create your park visit log

The project tracks which national parks you've visited. The pipeline reads a simple CSV file at `raw_data/park_visit_log.csv` with three columns:

```
park_name,month,year
```

**To add your own visits**, edit this file with the parks you've been to:

```csv
park_name,month,year
Yosemite,July,2023
Grand Canyon,March,2024
Acadia,Oct,2024
```

The `park_name` column uses fuzzy matching &mdash; you don't need exact official names. "Yosemite" matches "Yosemite National Park", "Grand Canyon" matches "Grand Canyon National Park", and so on.

**If you haven't visited any parks yet** (or want to start fresh), just keep the header row:

```csv
park_name,month,year
```

Either way, all 63 national parks will be collected. Parks without a matching row in this file are simply marked as unvisited.

## Step 5: Start the Docker services

Launch the database and API containers:

```bash
docker compose up --build -d
```

This starts two services:

| Service | Port | Description |
|---------|------|-------------|
| `db` | 5433 | PostGIS database (mapped to 5433 to avoid conflicts with any local PostgreSQL) |
| `api` | 8000 | FastAPI REST API |

On first startup, the database container automatically creates the required PostGIS and pg_trgm extensions and runs all schema migrations. You can verify the services are running:

```bash
docker compose ps
```

You should see both `db` and `api` with a status of "Up" (the database should show "healthy").

> **Note:** The database uses port **5433** on your machine, not the standard 5432. This is intentional to avoid conflicts if you have PostgreSQL installed locally.

## Step 6: Run the data collection pipeline

Now you'll populate the database with park and trail data. The pipeline runs on your local machine and writes to the Docker database.

Since the Docker database is on port 5433, override the port when running the pipeline:

```bash
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/orchestrator.py --write-db --test-limit 3
```

The `--test-limit 3` flag processes only 3 parks, so you can verify everything works before committing to the full run. This should complete in a few minutes.

The pipeline runs six steps in order:

| Step | What it does | Data source |
|------|-------------|-------------|
| 1. NPS Data Collection | Park metadata, coordinates, and boundary polygons | [NPS API](https://www.nps.gov/subjects/developer/) |
| 2. OSM Trails Collection | Hiking trails within park boundaries | [OpenStreetMap](https://www.openstreetmap.org/) |
| 3. TNM Trails Collection | Additional trail data with detailed attributes | [The National Map](https://www.usgs.gov/programs/national-geospatial-program/national-map) |
| 4. GMaps Import | Personal hiking locations from Google Maps (optional) | Your KML files |
| 5. Trail Matching | Matches GMaps locations to trail geometries | Internal |
| 6. Elevation Collection | Elevation profiles for matched trails | [USGS](https://www.usgs.gov/) |

> **About steps 4&ndash;6:** These steps use Google Maps hiking data, which is covered in the [advanced personalization](#advanced-add-your-google-maps-hiking-data) section below. If you haven't added any KML files, these steps will run but simply find no data to process. This is normal &mdash; the pipeline completes successfully either way.

### Verify the test run

Check that data was collected by querying the API:

```bash
curl http://localhost:8000/parks | python3 -m json.tool
```

You should see a JSON response with `park_count` showing the number of parks collected and a `parks` array with details for each one. If you set up your visit log, parks you've visited will have `visit_month` and `visit_year` populated.

### Run the full pipeline

Once you've confirmed the test run works, collect data for all 63 national parks:

```bash
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/orchestrator.py --write-db
```

This takes longer &mdash; mainly due to the OSM and TNM trail collection steps, which query external APIs for each park. Expect roughly 30&ndash;60 minutes for the full run depending on your internet connection and API response times.

> **Tip:** The pipeline is fail-fast. If a step fails, check `logs/orchestrator.log` for details. You can also run individual collectors directly for debugging (see the [README](../README.md) for individual component commands).

## Step 7: Explore your data

With the pipeline complete, you now have a database full of national park and trail data. The API is already running at `http://localhost:8000`.

### Interactive API documentation

Open **http://localhost:8000/docs** in your browser to access the Swagger UI. This interactive interface lets you try every endpoint, see request/response schemas, and experiment with query parameters &mdash; no code required.

### Quick examples

**Browse all parks:**

```
http://localhost:8000/parks
```

**Filter to parks you've visited:**

```
http://localhost:8000/parks?visited=true
```

**See all trails for a specific park** (use the 4-letter park code, e.g., `yose` for Yosemite):

```
http://localhost:8000/parks/yose/trails
```

**Find long trails across all parks:**

```
http://localhost:8000/trails?min_length=10
```

**Filter by state:**

```
http://localhost:8000/trails?state=CA
```

For a deeper dive into the API's capabilities, see the [API Tutorial](api-tutorial.md).

## Stopping and restarting

**Stop the services** (data is preserved):

```bash
docker compose down
```

**Restart later** (no rebuild needed unless code changed):

```bash
docker compose up -d
```

**Start fresh** (removes all database data):

```bash
docker compose down -v
```

## Troubleshooting

### "Set POSTGRES_PASSWORD in .env"

Docker Compose requires `POSTGRES_PASSWORD` to be set. Make sure your `.env` file exists in the project root and contains a `POSTGRES_PASSWORD` value.

### Pipeline can't connect to the database

When running the pipeline from your local machine against the Docker database, make sure you're using port 5433:

```bash
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/orchestrator.py --write-db
```

### "Visit log file not found"

The NPS collector expects a file at `raw_data/park_visit_log.csv`. If you don't have one, create it with just the header row:

```bash
echo "park_name,month,year" > raw_data/park_visit_log.csv
```

### Docker containers won't start

Make sure Docker Desktop is running, then try rebuilding:

```bash
docker compose down
docker compose up --build
```

Check the logs for specific errors:

```bash
docker compose logs db
docker compose logs api
```

### API returns empty results after pipeline

Verify data was written to the database:

```bash
curl http://localhost:8000/health
```

The response should show `"database": "connected"`. If connected but no data, re-run the pipeline and check `logs/orchestrator.log` for errors.

---

## Advanced: Add your Google Maps hiking data

If you track your hikes using [Google My Maps](https://www.google.com/maps/d/), you can import that data to enable additional features: trail matching, hiked/unhiked filtering, and 3D trail visualizations with elevation profiles.

### How it works

The project reads KML files exported from Google My Maps. Each KML file contains hiking locations (points) organized into folders named by park code. For example, a map for Zion would have a folder named `zion` containing placemarks like "Angels Landing" and "The Narrows".

### Step 1: Create your hiking maps

In [Google My Maps](https://www.google.com/maps/d/), create a map for each park where you've hiked. For each map:

1. Name it using the pattern `nps_points_<park_code>` (e.g., `nps_points_zion`)
2. Create a layer (folder) named with the 4-letter park code (e.g., `zion`)
3. Add placemarks for each trail or location you've hiked

> **Finding park codes:** Park codes are the 4-letter abbreviations used by the NPS (e.g., `yose` for Yosemite, `grca` for Grand Canyon). You can find them in the API response at `http://localhost:8000/parks` or on the [NPS website](https://www.nps.gov/) in each park's URL.

### Step 2: Export and add KML files

Export each map as KML and save the files to `raw_data/gmaps/`:

```
raw_data/gmaps/
├── nps_points_zion.kml
├── nps_points_yose.kml
└── nps_points_grca.kml
```

### Step 3: Re-run the pipeline

Run the full pipeline again to process the new data:

```bash
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/orchestrator.py --write-db
```

Steps 4&ndash;6 will now find your KML data and:
- Import your hiking locations
- Match them to trail geometries from OSM and TNM
- Collect elevation data for matched trails

After this, you can use the API to filter trails by hiking status and view 3D trail visualizations:

```
http://localhost:8000/trails?hiked=true
http://localhost:8000/parks/zion/trails/angels_landing/viz/3d
```

## Next steps

- **[API Tutorial](api-tutorial.md)** &mdash; A guided tour of the API's query capabilities and visualizations
- **[README](../README.md)** &mdash; Full project documentation including architecture, testing, and data profiling
