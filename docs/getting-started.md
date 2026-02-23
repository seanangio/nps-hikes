# Getting Started

This guide walks through setting up this NPS hiking project from scratch. By the end, you'll have a PostGIS database with all 63 U.S. national parks and hundreds of hiking trails, queryable through an interactive API.

## Step 0: Prerequisites

Before you begin, make sure you have the following:

- **Docker Desktop**: [Install Docker Desktop](https://www.docker.com/products/docker-desktop/) for your operating system. Docker runs the database and API in containers so you don't need to install PostgreSQL or PostGIS locally.
- **Python 3.12+**: The data collection pipeline runs on your local machine. Check your version with `python3 --version`. If you need to install or upgrade, see [python.org](https://www.python.org/downloads/).
- **Git**: Install [Git](https://git-scm.com/install/) for your operating system to clone the repository.
- An **NPS API key**: Free to sign up at the [NPS Developer Portal](https://www.nps.gov/subjects/developer/get-started.htm). You should receive a key by email within minutes.

## Step 1: Clone the repository

Start by cloning the repository.

```bash
git clone https://github.com/seanangio/nps-hikes.git
cd nps-hikes
```

## Step 2: Set up a Python environment

Create a virtual environment, and install the project dependencies. You need them for the data collection pipeline, which runs outside of Docker.

```bash
python3.12 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Step 3: Configure environment variables

Copy the example environment file, and fill in your credentials:

```bash
cp .env.example .env
```

Open `.env` in your editor. You need to set two values:

```dotenv
# Required: your NPS API key from Step 0
NPS_API_KEY=your_actual_api_key

# Required: choose any password for the Docker database
POSTGRES_PASSWORD=choose_a_password
```

The remaining defaults work as-is for the Docker setup:

```dotenv
# No changes required for these defaults
POSTGRES_USER=postgres
NPS_USER_EMAIL=your_email@example.com
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=nps_hikes_db
```

> **How the project uses the `.env` file:** Docker Compose reads it automatically to configure the database container. The Python scripts also read it (via `python-dotenv`) for API credentials and database connections.

## Step 4: Personalize the raw data

The repository includes two types of sample raw data that you can substitute with your own.

### Park visit log

The file `raw_data/park_visit_log.csv` records which parks you've visited:

```csv
park_name,month,year
Yosemite,July,2023
Grand Canyon,March,2024
Acadia,Oct,2024
```

Edit this file with your own visits. The `park_name` column requires the common short name (for example, "Yosemite" not "Yosemite National Park"). The collector appends "National Park" automatically, so "Yosemite" becomes "Yosemite National Park" and matches directly.

For parks with other designations like "National Park & Preserve," the collector falls back to substring matching. For example, "Denali" doesn't match "Denali National Park & Preserve" exactly, but the pipeline finds a match because the string "Denali" is a substring of the official name.

Make sure your entry is an exact substring of the official name. For example, use "Redwood" (not "Redwoods") for Redwood National and State Parks.

> **Tip:** When you test the pipeline below in Step 6, it processes the first NPS park alphabetically (Acadia). If you include **Acadia** in your visit log, you'll have a visited park with trail data to explore.

### Google My Maps hiking data (KML files)

The `raw_data/gmaps/` directory contains KML files with hiking locations exported from [Google My Maps](https://www.google.com/maps/d/). The pipeline uses these named points to match hiking locations to trail geometries, and then collects elevation data for the matched trails. This enables personalized trail matching, hiked/unhiked filtering, and 3D trail visualizations with elevation profiles.

> **Tip:** The repository includes sample KML files from the author's hikes. You can substitute your own files following the instructions below. Otherwise, leave the samples as-is, and skip ahead to [Step 5](#step-5-start-the-docker-services).

#### How it works

The pipeline processes every `.kml` file in the `raw_data/gmaps/` directory. Inside each KML file, it looks for **folders** (layers) named for 4-letter park codes, and reads the placemarks within them. A single Google My Maps KML file can contain up to ten layers (one per park).

> **Finding park codes:** You can find the 4-letter abbreviation for each park on the [NPS website](https://www.nps.gov/) in each park's URL. Once the API is running, they're also available at `http://localhost:8000/parks`.

#### Create your hiking maps

In [Google My Maps](https://www.google.com/maps/d/), create one or more maps for your hikes:

1. Add a **layer** for each park, named according to the 4-letter park code (for example, `zion`).
2. Add placemarks to each layer for the trails or locations you've hiked.

#### Export and add KML files

Export each map as a KML file, and save the files to `raw_data/gmaps/`:

```
raw_data/gmaps/
├── nps_points_west.kml    # could contain layers: zion, yose, grca, ...
└── nps_points_east.kml    # could contain layers: acad, shen, grsm, ...
```

## Step 5: Start the Docker services

Make sure Docker Desktop is running. Then launch the database and API containers:

```bash
docker compose up --build -d
```

This starts two services:

| Service | Port | Description |
|---------|------|-------------|
| `db` | 5433 | PostGIS database (mapped to 5433 to avoid conflicts with any local PostgreSQL) |
| `api` | 8000 | FastAPI REST API |

> **Tip:** The first run may take a few minutes while Docker downloads the base images. Subsequent runs are much faster.

On first startup, the database container automatically creates the required PostGIS and pg_trgm extensions and runs all schema migrations. You can verify the services are running:

```bash
docker compose ps
```

You should see both `db` and `api` with a status of "Up" (the database should show "healthy").

> **Note:** The database uses port **5433** on your machine, not the standard 5432. This is intentional to avoid conflicts if you have PostgreSQL installed locally.

## Step 6: Run the data collection pipeline

Next, populate the database with park and trail data. The pipeline runs on your local machine and writes to the Docker database.

Since the Docker database is on port 5433, override the port when running the pipeline:

```bash
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/orchestrator.py --write-db --test-limit 1
```

The `--test-limit 1` flag processes only one park, so you can verify it works before committing to the full run. Due to the elevation data collection step, this test run may take approximately 10 minutes.

The pipeline runs six steps in order:

| Step | What it does | Data source |
|------|-------------|-------------|
| 1. NPS Data Collection | Park metadata, coordinates, and boundary polygons | [NPS API](https://www.nps.gov/subjects/developer/) |
| 2. OSM Trails Collection | Hiking trails within park boundaries | [OpenStreetMap](https://www.openstreetmap.org/) |
| 3. TNM Trails Collection | Official trail data within park boundaries | [The National Map](https://www.usgs.gov/programs/national-geospatial-program/national-map) |
| 4. GMaps Import | Hiking locations from Google My Maps KML files | KML files in `raw_data/gmaps/` |
| 5. Trail Matching | Matches GMaps locations to TNM or OSM trail geometries | Internal |
| 6. Elevation Collection | Elevation profiles for matched trails | [USGS EPQS](https://apps.nationalmap.gov/epqs/) |

### Verify the test run

First, confirm that the pipeline created and populated the tables by querying the database directly:

```bash
docker compose exec db bash -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT park_code, park_name FROM parks;"'
```

> **Tip:** You should see the park code and name of parks collected (one if you used `--test-limit 1`). This runs `psql` inside the already-running database container, so you don't need PostgreSQL installed locally.

You can also verify through the API:

```bash
curl http://localhost:8000/parks | python3 -m json.tool
```

You should see a JSON response with `park_count` showing the number of parks collected and a `parks` array with details for each one.

### Run the full pipeline

Once you've confirmed the test run works, collect data for all 63[^1] national parks:

```bash
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/orchestrator.py --write-db
```

This takes longer. If using the author's files, expect more than 2 hours for the full run. The main bottleneck is the elevation collection step, which queries the USGS EPQS API for sampled points along each matched trail (one request per point, with a rate limit delay between calls). The more trails matched from your KML files, the longer this step takes.

The pipeline is resumable: with `--write-db`, each collector skips parks or trails that already have data in the database, and the elevation collector also maintains a persistent cache of individual elevation lookups. If a run is interrupted, re-running the same command picks up roughly where it left off. To force a full re-collection, pass `--force-refresh`.

> **Tip:** The pipeline is fail-fast. If a step fails, check `logs/orchestrator.log` for details. You can also run individual collectors directly for debugging (see the [README](https://github.com/seanangio/nps-hikes) for individual component commands).

## Step 7: Explore your data

With the pipeline complete, you now have a database full of national park and trail data. The API should be running at `http://localhost:8000`.

### Interactive API documentation

Open [http://localhost:8000/docs](http://localhost:8000/docs) in your browser to access the Swagger UI. This interactive interface lets you try every endpoint, see request/response schemas, and experiment with query parameters.

### Quick examples

| Description | URL |
|---|---|
| Browse all parks | `http://localhost:8000/parks` |
| Filter to parks you've visited | `http://localhost:8000/parks?visited=true` |
| See all trails for a specific park | `http://localhost:8000/parks/yose/trails` |
| Find long trails across all parks | `http://localhost:8000/trails?min_length=10` |
| Filter by state | `http://localhost:8000/trails?state=CA` |

> **Tip**: For a deeper dive into the API's capabilities, see the [API Tutorial](api-tutorial.md).

## Stopping and restarting

Here are a few handy commands for stopping and restarting the Docker services.

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

## Next steps

- **[API Tutorial](api-tutorial.md)** &mdash; A guided tour of the API's query capabilities and visualizations
- **[README](https://github.com/seanangio/nps-hikes)** &mdash; Full project documentation including architecture, testing, and data profiling

[^1]: The NPS manages Sequoia and Kings Canyon as one park (`seki`), and so it appears as one entry.
