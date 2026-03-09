# Dockerfile for NPS Trails API
#
# Multi-stage build: compiles Python packages in a builder stage,
# then copies them into a slim runtime image with a non-root user.
#
# Usage:
#   docker build -t nps-trails-api .
#   docker run -p 8000:8000 --env-file .env nps-trails-api

# ---------- Stage 1: Builder ----------
FROM python:3.12-slim AS builder

# Install build dependencies for geospatial Python packages
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
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Build Python packages into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- Stage 2: Runtime ----------
FROM python:3.12-slim

# Install only runtime libraries (no compilers or -dev headers).
# gdal-bin pulls in the GDAL, GEOS, and PROJ shared libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

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

# Create non-root user, assign ownership, and switch to it
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

# Expose the API port
EXPOSE 8000

# Health check: verify the API is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the API server
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
