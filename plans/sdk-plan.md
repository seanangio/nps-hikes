# NPS Hikes Python SDK Plan

## Context

The NPS Hikes project is a FastAPI REST API backed by a PostGIS database, deployed on Render, with a Streamlit web app as an existing client. The API has 14 endpoints serving trail and park data for U.S. National Parks. This document captures the decision-making process for building a Python SDK for the API and serves as a handoff for implementation.

## What is an SDK and why build one?

An SDK (Software Development Kit) is a convenience layer over a network call. It wraps an HTTP API so that developers interact with Python objects and methods instead of constructing URLs, parsing JSON, and handling status codes.

The server speaks HTTP and JSON. Python developers think in objects and methods. The SDK sits in between and translates one to the other. The data is identical -- the experience of working with it is different.

### Benefits of the SDK

- **Type safety.** The API returns JSON dicts. The SDK returns Pydantic model instances with typed fields. Typos like `trail.trai_name` get caught by the IDE before runtime, instead of producing a `KeyError` when the code runs.
- **Discoverability.** With raw JSON, you need to read docs or `print(data.keys())` to know what fields exist. With SDK objects, IDE autocomplete shows every available field as you type.
- **Cleaner interface.** The SDK can present more Pythonic parameter names (e.g., `min_length_mi` instead of the API's `min_length` query param), hiding the raw API's naming conventions.
- **Error handling.** The SDK raises meaningful exceptions like `ParkNotFoundError` instead of requiring developers to check `response.status_code` themselves.
- **No URL/HTTP knowledge required.** Developers call `client.get_trails(park_code="yose")` instead of knowing the base URL, endpoint path, and query parameter names.

### Learning objectives

- Understand the full developer experience chain: database -> API -> client library -> end user.
- Practice the industry-standard pattern of maintaining a separate SDK repo, which is what companies with multi-language SDKs do (Python, Go, TypeScript, etc.).
- Learn how to manage model duplication across repos using OpenAPI spec code generation.
- Gain firsthand experience with the maintenance tradeoffs (cross-repo coordination, model drift, versioning) that SDK teams deal with daily.
- Build a portfolio artifact that demonstrates understanding of SDK design, not just API design.

## How the developer experience compares: API vs SDK

### Raw API usage

```python
import requests

response = requests.get(
    "https://seanangio-nps-hikes.onrender.com/trails",
    params={"park_code": "yose", "min_length": 5},
)
response.raise_for_status()
data = response.json()

for trail in data["trails"]:
    print(f"{trail['trail_name']}: {trail['length_miles']} mi")
```

The developer must: know the URL, know parameter names from the docs, call `.json()`, navigate dicts with string keys (no autocomplete, no type checking), and handle HTTP errors manually.

### SDK usage

```python
from nps_hikes import Client

client = Client()
result = client.get_trails(park_code="yose", min_length_mi=5)

for trail in result.trails:
    print(f"{trail.trail_name}: {trail.length_miles} mi")
```

The developer gets: method names instead of URLs, IDE autocomplete for parameters and response fields, typed objects instead of dicts, and meaningful exceptions instead of HTTP status codes.

### Summary table

| Concern | Raw API | SDK |
|---|---|---|
| Know the URL | Yes | No |
| Know param names | From docs | IDE autocomplete |
| Parse response | `.json()` + dict navigation | Already done |
| Discover fields | Read docs or `print(keys())` | IDE autocomplete |
| Catch typos | Runtime `KeyError` | IDE warning |
| Handle errors | Check `status_code` | Typed exceptions |

## Architecture

```
Developer's machine                     Render deployment
+---------------------+                 +---------------------+
|                     |   HTTP request  |                     |
|  their_script.py    |--------------->|  FastAPI server     |
|    |                |                 |    |                |
|  nps_hikes (SDK)    |<---------------|  PostGIS database   |
|    |                |   HTTP response |  (347 trails)       |
|  Python objects     |   (JSON body)   |                     |
+---------------------+                 +---------------------+
```

The SDK user never touches the server side. They don't need Docker, the database, or the source code. They install the SDK, create a `Client()`, and call methods. The SDK sends HTTP requests to the Render deployment and converts JSON responses into Python objects.

The Streamlit app is already a client of the same API. The SDK is a second client. Both hit the same server, get the same data, go through the same endpoints.

## Endpoints to wrap

Not all 14 endpoints belong in the SDK. Visualization endpoints return PNGs/HTML (no structured data to model), and the NLQ endpoint requires a local Ollama instance. The SDK wraps the 6 data endpoints:

| SDK method | Endpoint | Returns |
|---|---|---|
| `get_parks()` | `GET /parks` | `ParksResponse` |
| `get_park_summary(park_code)` | `GET /parks/{park_code}/summary` | `ParkSummaryResponse` |
| `get_trails()` | `GET /trails` | `TrailsResponse` |
| `get_hiked_points()` | `GET /trails/hiked-points` | `HikedPointsResponse` |
| `get_stats()` | `GET /stats` | `StatsResponse` |
| `get_park_stats()` | `GET /stats/parks` | `ParkStatsResponse` |

Visualization endpoints don't benefit from an SDK because the response is already a consumable artifact (an image or HTML page). There's no JSON to parse, no fields to discover, no type safety to add. The SDK adds value specifically when it transforms unstructured data (JSON) into structured objects.

## Distribution decision: separate Git repo

### Options considered

1. **PyPI (public)** -- installable via `pip install name`. Maximum reach but unnecessary overhead for a learning project.
2. **Private registry** (CodeArtifact, Artifactory, etc.) -- access-controlled PyPI mirror. Requires infrastructure. Overkill.
3. **Separate Git repo** -- installable via `pip install git+https://github.com/...`. Clean separation, industry-standard pattern. **Chosen.**
4. **Monorepo subdirectory** -- SDK lives inside the server repo. Convenient but blurs boundaries. Unusual install syntax (`#subdirectory=`).
5. **Copy a file** -- no packaging at all. Doesn't demonstrate SDK design.

### Why separate repo

- Mirrors the industry convention used by companies with multi-language SDKs (`{company}-python-sdk`).
- Clean dependency boundary -- physically impossible to import server code.
- Independent git history, CI, and release cycle.
- Installable via standard git URL: `pip install git+https://github.com/seanangio/nps-hikes-python-sdk.git`.
- Can be published to PyPI later without restructuring.

### Known tradeoffs (and why they're acceptable)

- **Two repos to maintain.** This is unavoidable at any company with separate SDKs. Learning to manage it is part of the point.
- **Model duplication.** Addressed by code generation (see below).
- **Cross-repo coordination.** When the API changes, the SDK must be updated separately. Real SDK teams deal with this daily through versioning and changelogs.
- **GitHub overhead.** Separate README, CI, issues. Minor for a one-person project.

## Managing model duplication: OpenAPI code generation

The server's Pydantic models in `api/models.py` must be replicated in the SDK. Rather than hand-copying and manually syncing them, the SDK generates its models from the API's OpenAPI spec.

FastAPI auto-generates the spec at `/openapi.json`. The tool `datamodel-code-generator` reads this spec and outputs Pydantic models.

### Generation command

```bash
pip install datamodel-code-generator

datamodel-codegen \
    --url https://seanangio-nps-hikes.onrender.com/openapi.json \
    --output src/nps_hikes/models.py \
    --output-model-type pydantic_v2
```

### Workflow for keeping models in sync

1. Change a model in the server repo (`api/models.py`).
2. Deploy the server (Render rebuilds from the updated code).
3. In the SDK repo, re-run `datamodel-codegen` to regenerate models from the updated spec.
4. Review the diff, update SDK tests if needed, commit, and tag a new version.

### Why code generation over manual duplication

- Models are always derivable from the spec -- eliminates drift.
- Scales to multiple SDKs (the same spec could generate Go, TypeScript, Flutter models).
- Demonstrates understanding of the real-world SDK maintenance pipeline.
- For 6-8 simple models, hand-writing is also viable, but code generation is the more instructive choice.

## Repo structure

```
nps-hikes-python-sdk/
├── src/
│   └── nps_hikes/
│       ├── __init__.py        # exports Client, models, exceptions
│       ├── client.py          # NPSHikesClient class (6 methods)
│       ├── models.py          # generated from OpenAPI spec
│       └── exceptions.py      # ParkNotFoundError, etc.
├── tests/
│   ├── test_client.py         # mock HTTP responses, verify parsing
│   └── test_models.py         # verify model validation
├── examples/
│   └── basic_usage.py         # runnable demo script
├── pyproject.toml             # package metadata, dependencies: requests, pydantic
└── README.md                  # quickstart, method reference, install instructions
```

### pyproject.toml

```toml
[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"

[project]
name = "nps-hikes-sdk"
version = "0.1.0"
description = "Python client for the NPS Hikes trail API"
readme = "README.md"
requires-python = ">=3.12"
license = {text = "CC-BY-NC-SA-4.0"}
authors = [{name = "Sean Angiolillo"}]
dependencies = [
    "requests>=2.31",
    "pydantic>=2.0",
]

[project.urls]
Homepage = "https://github.com/seanangio/nps-hikes-python-sdk"
Documentation = "https://seanangio.github.io/nps-hikes/"
API = "https://seanangio-nps-hikes.onrender.com/docs"
```

### Install methods

```bash
# From GitHub
pip install git+https://github.com/seanangio/nps-hikes-python-sdk.git

# Local development (editable)
git clone https://github.com/seanangio/nps-hikes-python-sdk.git
cd nps-hikes-python-sdk
pip install -e .
```

## Implementation steps

1. ~~Create the `nps-hikes-python-sdk` GitHub repo.~~ **Done.**
2. ~~Set up the directory structure above.~~ **Done.**
3. ~~Generate models from the OpenAPI spec using `datamodel-codegen`.~~ **Done.** Generated from a local snapshot saved to `specs/openapi-2026-05-01.json`. Removed NlqRequest, NlqResponse, ValidationError, and HTTPValidationError (not needed in the SDK).
4. ~~Implement `client.py` with the 6 SDK methods wrapping the data endpoints.~~ **Done.** Added Pythonic param names (e.g., `min_length_mi` maps to API's `min_length`). Default timeout set to 120s to accommodate Render cold starts.
5. ~~Implement `exceptions.py` with custom error classes.~~ **Done.** `NPSHikesError` (base), `APIError`, `ParkNotFoundError`, `ValidationError`.
6. ~~Write tests using `unittest.mock.patch` to mock HTTP responses.~~ **Done.** 29 tests across `test_client.py` (15) and `test_models.py` (14). All mocked, no network needed.
7. ~~Write `examples/basic_usage.py` as a runnable demo.~~ **Done.**
8. ~~Write the SDK README with install instructions, quickstart, and method reference.~~ **Done.** Also includes cold start note, error handling, configuration, model regeneration, and full dev setup (pyenv, venv, pytest).
9. ~~Set up CI (GitHub Actions) to run SDK tests independently.~~ **Done.** `.github/workflows/test.yml`.
10. ~~Add a CLAUDE.md to the SDK repo referencing the server repo, OpenAPI spec URL, and the sdk-plan.md file path for cross-repo context.~~ **Done.** Also documents the `specs/` directory and model regeneration workflow.
11. ~~Add a section to the nps-hikes server repo docs mentioning the SDK with install instructions and a link to the SDK repo.~~ **Done.** Added "Python SDK" section to `docs/api-tutorial.md`.
12. Tag `v0.1.0`. **Ready to go** -- commit, tag, and push.
