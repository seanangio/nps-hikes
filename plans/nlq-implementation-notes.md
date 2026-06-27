# NLQ (Natural Language Query) Feature — Implementation Notes

## What was built

A `POST /query` endpoint that accepts natural language questions about trails and parks (e.g., "short hikes in Yosemite I haven't done") and uses a local LLM via Ollama to translate them into structured API calls against the existing `fetch_trails()`, `fetch_all_parks()`, `fetch_stats()`, `fetch_park_stats()`, and `fetch_park_summary()` functions. Four tools cover trail search, park search, aggregate statistics, and per-park summaries. The LLM's only job is parameter extraction — no new database logic was added.

### Architecture

```
User query (natural language)
    → POST /query endpoint (api/main.py)
    → build_system_message() injects tool definitions + park lookup table
    → call_ollama() sends prompt to local LLM via httpx
    → parse_tool_call() extracts function name + args from LLM response
    → validate_and_normalize(query=...) auto-corrects params
      (case, park names, ranges, month/season, visited inference, negation)
    → dispatch to fetch_trails / fetch_all_parks / fetch_stats /
      fetch_park_stats / fetch_park_summary (existing code, unchanged)
    → NlqResponse returned to user
```

### Files created

- `api/nlq/__init__.py` — Package init
- `api/nlq/park_lookup.py` — Park name → 4-char code resolution. Queries `fetch_all_parks()` once, caches a lookup dict. Uses `difflib.get_close_matches()` for fuzzy matching (stdlib, no dependencies). Handles full names ("Yosemite National Park"), short names ("Yosemite"), and codes ("yose").
- `api/nlq/prompt.py` — Tool definitions in OpenAI-compatible format (four tools: `search_trails`, `search_parks`, `search_stats`, `search_park_summary`). System prompt template that injects the park lookup table (~63 entries) and includes rules for state handling, min/max length, negation, visit timing, and tool routing.
- `api/nlq/ollama_client.py` — Async HTTP client using `httpx.AsyncClient`. Posts to Ollama's `/api/chat` with `stream: false`. Raises `LlmConnectionError` on connect/timeout errors.
- `api/nlq/parser.py` — Extracts tool calls from Ollama responses using two strategies: (1) standard `tool_calls` format, (2) JSON in message content as fallback. Validates and normalizes params per-tool (lowercases park codes, maps state names to 2-letter codes, clamps numeric values, resolves park names via the lookup, normalizes month names/abbreviations/seasons, infers `visited=True` from visit timing). Also applies a post-normalization negation correction using regex detection on the original query.
- `tests/unit/test_nlq_park_lookup.py` — 13 tests for park name resolution
- `tests/unit/test_nlq_parser.py` — 50 tests for response parsing, param validation, month/season normalization, visited inference, and negation correction
- `tests/unit/test_nlq_prompt.py` — 9 tests for tool definitions and prompt building
- `tests/eval/golden_queries.json` — 47 golden queries across 4 tools for eval
- `tests/eval/run_eval.py` — Eval script: runs each query through the full pipeline, reports PASS/PARTIAL/FAIL, saves timestamped JSON results to `eval_results/`

### Files modified

- `api/main.py` — Added `POST /query` endpoint with error handling (503 for Ollama down, 422 for unparseable responses). Dispatch branches for all four tools. Passes `query=request.query` to `validate_and_normalize()` for negation detection. Added `/query` to root endpoint docs.
- `api/models.py` — Added `NlqRequest` (query string, 3-500 chars) and `NlqResponse` (original_query, interpreted_as, function_called, results).
- `api/queries.py` — Added `visit_year` and `visit_month` filters to `fetch_all_parks()`. Month uses `IN` clause with dynamic placeholders for multi-value matching.
- `utils/exceptions.py` — Added `LlmError` → `LlmConnectionError`, `LlmResponseError` to existing hierarchy.
- `config/settings.py` — Added `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT` with env var loading.
- `requirements.in` / `requirements.txt` — Added `httpx`.
- `.env.example` — Added Ollama config vars.
- `tests/test_api.py` — Added endpoint tests for visit_year/visit_month filtering.

## Key decisions made

### Tool-use/function-calling over text-to-SQL
The LLM extracts structured parameters for existing API endpoints rather than generating SQL directly. Rationale: safer (LLM is sandboxed to known parameters, validated by Pydantic), simpler, and the existing API covers the common queries. Text-to-SQL was discussed as a potential future enhancement for analytical queries the API can't handle (aggregations, spatial queries).

### Llama 3.1 8B (Meta) as default model
Chosen over Qwen 2.5 7B (Alibaba) and Mistral 7B. All three work well for structured output. Llama was preferred for being Western-developed (user preference), well-documented, and having strong tool-calling support. ~4.7GB download, ~5-6GB RAM — fits on 16GB MacBook Pro alongside macOS + Docker. Configurable via `OLLAMA_MODEL` env var.

### httpx over ollama Python package
Direct HTTP calls via `httpx` to Ollama's REST API rather than using the `ollama` pip package. More educational (see exactly what goes to/from the LLM), fewer dependencies, and `httpx` pairs naturally with FastAPI's async.

### No LangChain
Direct HTTP calls are ~100 lines of code and fully transparent. LangChain would add abstraction layers that obscure the mechanics — counterproductive for a learning project.

### Park name resolution via prompt injection + fuzzy matching
The full park name → code lookup table (~63 entries, ~2-3KB) is injected into the system prompt so the LLM can resolve names directly. Post-LLM `difflib.get_close_matches()` handles cases where the LLM outputs a name instead of a code. No vector store or embedding model needed for 63 parks.

### Ollama runs on host, not in Docker
Running Ollama natively on macOS allows Metal GPU acceleration. Docker would force CPU-only inference, which is significantly slower.

## Current state

- 72 NLQ unit tests pass (parser: 50, park lookup: 13, prompt: 9).
- 415 project-wide unit tests pass (27 integration test errors are pre-existing — database not running).
- 47 golden queries in the eval dataset across 4 tools.
- Pre-commit hooks pass (mypy, ruff, black, bandit).
- Branch: `main`

## Possible next steps

### Immediate
- Experiment with different models (swap `OLLAMA_MODEL` env var) to compare quality/speed — the eval framework makes this easy (`--model qwen2.5:7b`)
- Re-run eval to confirm negation correction fixes (the 5 negation failures should now pass)
- If eval results are ~90%+, move to summarization step

### Feature additions
- **Natural language summary in response** — Have the LLM generate a human-readable summary of the results after the query executes (second LLM call with results in context). Wait until routing accuracy is stable at ~90%+ before adding this complexity.
- **Multi-step queries** — Let the LLM chain calls for questions like "Compare Utah and California trails" (would need two `search_trails` calls and aggregation).

### Completed features (formerly next steps)
- ~~`/stats` endpoint~~ — Done. `GET /stats` (aggregate) and `GET /stats/parks` (per-park breakdown). NLQ tool `search_stats` routes to these.
- ~~`/parks/{park_code}/summary` endpoint~~ — Done. NLQ tool `search_park_summary` routes to this.
- ~~Eval framework~~ — Done. Golden dataset + eval script with PASS/PARTIAL/FAIL scoring.
- ~~Visit timing filters~~ — Done. `visit_year` and `visit_month` params on `GET /parks` and in `search_parks` tool.

### Text-to-SQL (phase 2)
A hybrid approach was discussed: tool-use for common queries (80% of use cases), text-to-SQL fallback for analytical questions. The schema is clean with proper foreign keys and indexes, making it a good target. Would need a read-only database role and SQL validation. PostGIS spatial functions would enable powerful queries ("trails above 10,000 feet", "parks within 200 miles of Denver").

### Infrastructure
- Docker hardening (non-root user, multi-stage build) — discussed but independent of NLQ
- Optionally add Ollama to `docker-compose.yml` (but Metal GPU won't work in Docker on macOS)
