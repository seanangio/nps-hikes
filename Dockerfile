# Dockerfile for NPS Trails API
#
# Builds a container image for the FastAPI application that serves
# National Park trail data from a PostGIS database.
#
# Usage:
#   docker build -t nps-trails-api .
#   docker run -p 8000:8000 --env-file .env nps-trails-api

FROM python:3.12-slim

# Install system dependencies required by geospatial Python packages
# - gdal-bin + libgdal-dev: GDAL library for spatial data formats
# - libgeos-dev: Geometry engine (shapely)
# - libproj-dev: Cartographic projections (pyproj)
# - gcc: C compiler needed to build some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory inside the container
WORKDIR /app

# Copy requirements first (Docker layer caching: this layer only
# rebuilds when requirements.txt changes, not on every code change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the directories needed at runtime
COPY api/ api/
COPY config/ config/
COPY profiling/ profiling/
COPY scripts/ scripts/
COPY utils/ utils/
COPY sql/ sql/

# Create the profiling_results directory structure
# (will be overlaid by volume mount, but ensures the path exists)
RUN mkdir -p profiling_results/visualizations/static_maps \
             profiling_results/visualizations/elevation_changes \
             profiling_results/visualizations/3d_trails

# Expose the API port
EXPOSE 8000

# Health check: verify the API is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the API server
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
