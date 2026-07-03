# NLQ Feature Walkthrough — How It All Works

Notes from a step-by-step walkthrough of the natural language query feature, intended as source material for a blog post.

## The big picture

The `/query` endpoint lets users ask questions in plain English (e.g., "short hikes in Yosemite") and get back structured API results. Under the hood, a local LLM translates natural language into function parameters for the existing `/trails`, `/parks`, `/stats`, and `/parks/{park_code}/summary` endpoints. The LLM doesn't answer questions — it just extracts parameters. All the actual data work is done by existing Python code.

Five files in `api/nlq/` handle this, each with a focused responsibility:

| File | Role |
|------|------|
| `ollama_client.py` | HTTP client — talks to Ollama |
| `park_lookup.py` | Park name resolution — "Yosemite" → "yose" |
| `prompt.py` | Tool definitions + system prompt |
| `parser.py` | Parse LLM response + validate/normalize params |
| `main.py` (endpoint) | Ties everything together |

## What is Ollama?

Ollama is a program that runs on your Mac and serves an LLM locally. No data leaves your computer. It works like a mini web server: when you start it (`ollama serve`), it listens at `http://localhost:11434` and exposes a REST API. Your Python code talks to it by sending HTTP requests and getting JSON responses back — the same way FastAPI talks to a browser.

Three config values in `config/settings.py` control the connection:

- `OLLAMA_BASE_URL` = `http://localhost:11434` — where Ollama is listening
- `OLLAMA_MODEL` = `llama3.1:8b` — which model to use
- `OLLAMA_TIMEOUT` = `60` seconds — how long to wait for a response

### What is Llama 3.1?

Llama 3.1 8B is an open-source LLM built by Meta (Facebook's parent company). "8B" means 8 billion parameters — the learned weights that encode language patterns. The model file is about 4.7GB.

Meta spent tens of millions training it (thousands of GPUs, enormous amounts of text data, weeks/months of training time), then released the weights publicly. Anyone can download and run them. Ollama downloads the weights from a public registry, loads them into your Mac's memory, and runs the math locally.

Why give it away? Industry influence (if everyone builds on Meta's model, Meta shapes the ecosystem), recruiting, and competitive strategy (commoditizing the layer that rivals like OpenAI charge for).

### The contrast with cloud APIs (ChatGPT, Claude, etc.)

With a cloud API, your question goes over the internet to someone else's servers, they run it on their GPUs, and send back the answer. You pay per request. With Ollama, the model lives on your Mac, your CPU/GPU does the math, and nothing leaves your machine. The tradeoff: it's slower and the model is smaller, but it's free and private.

### Swapping models

The model is just one env var. Change `OLLAMA_MODEL=llama3.1:8b` to `OLLAMA_MODEL=mistral:7b`, pull the new model (`ollama pull mistral:7b`), restart the API, and everything works. Your code doesn't care which model is behind Ollama — the HTTP interface is the same.

### Why Ollama over alternatives?

Without Ollama, you'd either:
1. **Call a cloud API** (OpenAI, Anthropic) — pay per request, data leaves your machine, dependent on their uptime
2. **Load the model directly in Python** (via `llama-cpp-python` or Hugging Face `transformers`) — need to write model loading, tokenization, and generation code yourself; model lives inside your process; switching models means changing code
3. **Use a different local server** (LM Studio, vLLM, LocalAI) — similar concept to Ollama with different tradeoffs

Ollama's value is standardization: it handles downloading/storing/loading models, manages GPU/CPU memory, and exposes one consistent HTTP API regardless of which model is behind it. Your code talks to one interface — swapping models is an env var, not a code change.

## The Ollama client (`api/nlq/ollama_client.py`)

This is the simplest file in the NLQ module — 79 lines, two functions. Its only job is sending HTTP requests to Ollama and handling connection failures.

### httpx — async HTTP client

The code uses `httpx` to send HTTP requests to Ollama. It's very similar to the `requests` library — same style of API (`client.post(url, json=payload)`). The key difference: `httpx` supports `async/await`, which FastAPI requires.

With synchronous `requests`, the entire API server would freeze while waiting for the LLM to respond (5-30 seconds). With async `httpx`, the server can handle other requests (serving `/trails`, `/parks`, health checks) while the LLM is thinking. The `await` keyword is what enables this:

```python
response = await client.post(url, json=payload)
```

A new `AsyncClient` is created per request (the `async with` context manager). This is fine for the low-volume NLQ use case — you're not making hundreds of concurrent LLM calls.

### Error handling

Three `httpx` exceptions are caught and re-raised as the project's own `LlmConnectionError`:

| Exception | When | User-facing message |
|-----------|------|---------------------|
| `ConnectError` | Ollama isn't running | "Is Ollama running? Start it with: ollama serve" |
| `TimeoutException` | LLM took too long (default 60s) | "The model may still be loading" |
| `HTTPStatusError` | Ollama returned 4xx/5xx | Shows the status code and body |

These become **503** responses at the endpoint level. The `context=` kwarg on each error passes debugging info (URL, timeout value, status code) that gets logged but isn't shown to the API user.

### Health check

`check_ollama_health()` is a simple function that hits `GET /api/tags` (Ollama's "list models" endpoint) with a 5-second timeout and returns `True`/`False`. It's not wired up to the API's `/health` endpoint — deliberately. The `/health` endpoint checks database connectivity, which the entire API depends on. Ollama is optional (only the `/query` endpoint needs it), so reporting Ollama as "unhealthy" would be misleading. Instead, when someone hits `POST /query` and Ollama is down, they get a clear 503 with a helpful message — feedback at the point of use, not in a general health check.

## Step-by-step flow

### Step 1: Build the payload

When someone hits `POST /query`, the code in `api/main.py` builds a JSON payload to send to Ollama:

```python
payload = {
    "model": "llama3.1:8b",
    "messages": messages,
    "tools": tools,
    "stream": False,
}
```

Four things: which model, the chat messages, the tool definitions, and `stream: False` (give me the complete response at once, don't send it word by word).

### Step 2: The messages (chat format)

Built in `api/nlq/prompt.py`, the messages follow the chat format that OpenAI introduced with ChatGPT and everyone else adopted:

```json
[
    {"role": "system", "content": "You are a trail finder assistant..."},
    {"role": "user", "content": "short hikes in Yosemite"}
]
```

Every message has a `role` and `content`. Three roles exist:

- **`system`** — Instructions that frame the LLM's behavior. The user doesn't "see" this in a chat UI, but the model reads it. It's where you set personality, rules, constraints, and inject context like the park lookup table. Think of it as stage directions for an actor — the audience doesn't hear them, but they shape the performance.
- **`user`** — The human's input. In this case, the natural language question.
- **`assistant`** — The LLM's own previous responses. Only relevant in multi-turn conversations. For example, in a chatbot you'd include prior assistant responses so the model remembers what it already said. Our NLQ feature is single-turn — one question, one answer — so no `assistant` message is included. We send system + user, and the response *is* the assistant turn.

**Why this format exists:** Before ChatGPT, you'd send a single text prompt to an LLM — no roles, just one big string. The chat format was introduced to separate concerns: instructions (system) vs. input (user) vs. conversation history (assistant). It also lets API providers apply different processing to each role.

#### The system message

The system message is where the real work happens. It's built from a template in `api/nlq/prompt.py` with a park lookup table dynamically injected:

```
You are a trail finder assistant for US National Parks.
Your ONLY job is to call the appropriate function with the correct parameters
based on the user's question. Always respond with a function call, never with plain text.

Park name to park_code lookup:
- yosemite national park → yose
- zion national park → zion
- grand canyon national park → grca
... (~63 entries)

Rules:
- Always use the park_code (4 lowercase letters), never the full park name, as the parameter value.
- State codes must be 2 uppercase letters (e.g., CA, UT, CO).
- When the user mentions a US state (e.g., "in Colorado", "California trails"), use the state parameter. Do NOT pick a specific park within that state instead.
- Trail lengths are in miles.
- For "short" trails, use max_length=3. For "long" trails, use min_length=5.
- "Under X miles", "less than X miles", "shorter than X miles" → use max_length=X.
- "Over X miles", "more than X miles", "at least X miles", "longer than X miles" → use min_length=X.
- If the user asks about trails or hikes, use search_trails.
- If the user asks about parks (not trails), use search_parks.
- Words like "haven't", "not", "never", "unvisited" indicate negation. "Parks I haven't visited" → visited=false. "Trails I haven't hiked" → hiked=false.
- If the user mentions a specific year for park visits, include visit_year in search_parks.
- If the user mentions a specific month or season for park visits, include visit_month with the month name or season name (spring, summer, fall, winter).
- If the user asks about overall statistics (total miles, trail counts, park counts, averages, longest/shortest), use search_stats.
- If the user asks for a per-park breakdown of stats, use search_stats with per_park=true.
- If the user asks about a specific park's details, summary, or overview, use search_park_summary.
- Only include parameters that the user's question implies. Do not add extra filters.
```

Several things to notice. The rules evolved through iterative eval runs (see the evaluation section below). The state rule, min/max rules, and negation rules were all added to address specific LLM failures — the small model would narrow "Colorado" to a single park, confuse min/max for "under X miles", and ignore negation words like "haven't" and "never". Prompt engineering fixed the first two; negation required a normalization-level fix as well.

The rules are very prescriptive — the model is told to be a structured data extractor, not a chatbot.

#### Dynamic vs. hardcoded park lookup

The park lookup table is **dynamically injected** — `api/nlq/park_lookup.py` queries the database for all parks, builds a dict mapping names/codes to 4-letter codes, and `build_park_lookup_text()` formats it into the text shown above. Then `build_system_message()` does a simple Python `.format()` substitution to inject it into the template.

Could the table be hardcoded directly in the template instead? Absolutely — there are ~63 parks and they don't change often. The tradeoff: hardcoded is simpler (no DB dependency at prompt-build time), but if you add a park to the database, you have to remember to update the prompt too. Dynamic means the prompt always matches the database automatically. For a rarely-changing dataset of this size, either approach works. The dynamic approach was chosen for correctness over simplicity.

There's no standardized framework for prompt templating. Some projects use Jinja2, some use Python's `.format()`, some load from YAML files. Libraries exist (LangChain's `PromptTemplate`, Guidance, LMQL) but none have won broad adoption. For a project with one template and one substitution variable, `.format()` is the right call.

### Step 3: The tool definitions

This is the key concept. You want the LLM to produce **structured data**, not English. "Tools" are the mechanism. You tell the LLM: "here are functions you can call, here are the parameters each one accepts." The LLM doesn't actually *call* anything — it outputs a structured response saying "I'd like to call this function with these arguments." Your code does the actual calling.

The four tools defined in `api/nlq/prompt.py` are essentially these function signatures expressed as JSON Schema:

```python
# Tool 1: Trail search — mirrors GET /trails
def search_trails(
    park_code: str = None,    # "4-character lowercase park code"
    state: str = None,        # "2-letter uppercase US state code"
    source: str = None,       # "TNM" or "OSM"
    hiked: bool = None,       # true = hiked, false = not hiked
    min_length: float = None, # minimum trail length in miles
    max_length: float = None, # maximum trail length in miles
    limit: int = None,        # max number of results
): ...

# Tool 2: Park search — mirrors GET /parks
def search_parks(
    visited: bool = None,     # true = visited, false = unvisited
    visit_year: int = None,   # filter by visit year (e.g., 2024)
    visit_month: str = None,  # month name or season ("October", "summer")
): ...

# Tool 3: Aggregate statistics — mirrors GET /stats and GET /stats/parks
def search_stats(
    hiked: bool = None,       # filter stats by hiked/unhiked status
    per_park: bool = None,    # true = per-park breakdown, false = aggregate totals
): ...

# Tool 4: Park summary — mirrors GET /parks/{park_code}/summary
def search_park_summary(
    park_code: str,           # REQUIRED — 4-character lowercase park code
): ...
```

Most parameters are optional (`"required": []`) because users might ask broad questions ("what trails have I hiked?") that only need one filter. The exception is `search_park_summary`, which requires a `park_code` — you can't summarize a park without knowing which one.

These mirror the existing API parameters. There is some inevitable duplication — the same concept of "park_code is a 4-letter lowercase string" lives in the database schema, the FastAPI endpoint validation, and the tool definition. But the tool descriptions include LLM-specific guidance (like "for short trails, use max_length=3") that wouldn't belong in an API schema.

As the API grows, adding a new NLQ tool means three things: define the tool schema in `prompt.py`, add routing rules to the system message, and add a dispatch branch in `main.py`. The LLM handles the new routing automatically — no retraining needed, just updated descriptions.

#### The OpenAI tool format — a de facto standard

The tool definitions use the format that OpenAI introduced and everyone else adopted — Ollama, Anthropic, Google, Mistral's API. It's a de facto standard, not an official spec. The pragmatic reason: developers don't want to rewrite their tool definitions for every provider, so competitors adopted OpenAI's format because that's what the ecosystem already uses.

It's really three layers of "following OpenAI's lead": Meta trains Llama 3.1 on tool-calling examples in this format, Ollama accepts it in its API, and our code produces it. Each tool is `"type": "function"` — in practice this is the only type anyone uses. OpenAI's spec technically allows other values, but for user-defined tools it's always `"function"`. Treat it as boilerplate.

#### Why tools instead of asking for raw JSON?

1. **The model is trained for it** — Llama 3.1 was fine-tuned on tool-calling examples. It's more reliable than hoping it follows a custom JSON format.
2. **Structured output** — Ollama returns tool calls in a predictable `tool_calls` field, separate from free text. Easier to parse.
3. That said, the parser handles both approaches as a fallback (see below).

#### How does the LLM know not to generate text?

Two things: the system prompt says "Always respond with a function call, never with plain text", and the model was trained to produce `tool_calls` responses with empty `content` when given tool definitions. Neither is a guarantee — LLMs don't follow instructions 100% of the time — which is why the parser has a fallback strategy.

#### The `search_stats` routing parameter

Note the `per_park` parameter on `search_stats`. The API has two separate statistics endpoints: `GET /stats` (aggregate totals — one row) and `GET /stats/parks` (per-park breakdown — one row per park). But from a natural language perspective, "How many miles have I hiked?" and "Which park has the most trails?" feel like the same kind of question — they're both about statistics. So instead of making the LLM choose between two tools, there's one tool with a boolean toggle.

When the LLM returns `search_stats` with `per_park: true`, the dispatch code uses `.pop()` to consume the flag and route to the right function:

```python
per_park = params.pop("per_park", False)
results = fetch_park_stats(**params) if per_park else fetch_stats(**params)
```

The `.pop()` removes `per_park` from `params` before `**params` unpacking, because neither `fetch_stats()` nor `fetch_park_stats()` accepts a `per_park` argument. It's consumed by routing logic and never reaches the database.

### Step 4: What Ollama returns

For "long trails I've hiked in Zion", the LLM (hopefully) returns a structured tool call:

```json
{
  "model": "llama3.1:8b",
  "message": {
    "role": "assistant",
    "content": "",
    "tool_calls": [
      {
        "function": {
          "name": "search_trails",
          "arguments": {
            "park_code": "zion",
            "min_length": 5,
            "hiked": true
          }
        }
      }
    ]
  },
  "done": true
}
```

Notice: `content` is empty (no English), "Zion" was resolved to `"zion"` using the lookup table, "long" became `min_length: 5` following the rules, "I've hiked" became `hiked: true`, and no extra parameters were added.

But sometimes the LLM ignores the tool format and writes text instead:

```json
{
  "model": "llama3.1:8b",
  "message": {
    "role": "assistant",
    "content": "I'll search for long trails in Zion.\n\n```json\n{\"function\": \"search_trails\", \"arguments\": {\"park_code\": \"zion\", \"min_length\": 5, \"hiked\": true}}\n```"
  },
  "done": true
}
```

No `tool_calls` field at all — just JSON embedded in conversational text. The parser handles both formats.

### Step 5: Parsing the response

The parser in `api/nlq/parser.py` has one job: extract a function name + arguments dict from whatever Ollama sent back. Two strategies:

**Strategy 1 (clean path):** Look for `tool_calls` in the response. Reach in and grab the function name and arguments. Straightforward dict access. This is what happens ~95% of the time with Llama 3.1.

**Strategy 2 (fallback):** If `tool_calls` is missing, the LLM may have written English with JSON mixed in. The parser searches the `content` string for JSON — first looking for markdown code blocks (`` ```json {...} ``` ``), then finding balanced braces and trying to parse them. It's saying "I don't care what else the LLM wrote, just find me something that looks like `{...}`."

The fallback also tries multiple key names — `function` or `name` for the function, `arguments` or `args` or `parameters` for the params — because different models format their fallback JSON differently.

If both strategies fail, it raises `LlmResponseError` (422 to the user: "Could not interpret query").

### Step 6: Park name resolution (`api/nlq/park_lookup.py`)

Before normalization, it's worth understanding how park names get resolved. The LLM might output "Yosemite", "Yosemite National Park", or "yose" — the database only understands the 4-letter code `yose`.

`get_park_lookup()` queries the database once (via `fetch_all_parks()`), then builds a dictionary mapping every way you might refer to a park down to its code:

```python
{
    "yose": "yose",                          # code itself
    "yosemite": "yose",                      # short park_name from DB
    "yosemite national park": "yose",        # full_name from DB
    ...
}
```

The suffix stripping handles designations like "National Park", "National Park & Preserve", etc. — "Denali National Park & Preserve" gets indexed as both its full name and just "denali".

The result is cached in a module-level global after the first DB query.

`resolve_park_code()` then uses this lookup with three resolution strategies, tried in order:

1. **Exact match** — handles "yose", "yosemite", "yosemite national park" directly
2. **4-letter code passthrough** — if it matches `^[a-z]{4}$`, trust it (defensive)
3. **Fuzzy match** — `difflib.get_close_matches()` with 0.6 cutoff catches misspellings like "Yosemmite" or partial names

The choice to use `difflib` over something heavier (vector search, Levenshtein library) makes sense — only ~63 parks, so brute-force comparison is instant.

The lookup is used in two places: injected into the system prompt so the LLM can map names to codes on its own, and called during normalization as a safety net for when the LLM outputs a name instead of a code anyway. Belt-and-suspenders: teach the LLM the right answer, then fix it if it still gets it wrong.

### Step 7: Validation and normalization

After extraction, `validate_and_normalize()` cleans up common LLM mistakes. It accepts an optional `query` parameter (the original user text) so it can catch errors that require looking at the original phrasing, not just the extracted params.

Each tool has its own normalizer. They all follow the same pattern: build a new `cleaned` dict, only including params that pass validation.

**Trail normalization** (`_normalize_trail_params`):

- `park_code`: passed through `resolve_park_code()` (fuzzy matching)
- `state`: full name → 2-letter code via a state name dict. "California" → "CA". If already 2 letters, just uppercases it
- `source`: uppercased, validated against "TNM"/"OSM"
- `hiked`: coerced to bool
- `min_length`/`max_length`: cast to float, clamped to 0.0-100.0
- `limit`: cast to int, clamped to 1-1000

**Park normalization** (`_normalize_park_params`):

- `visited`: coerced to bool
- `visit_year`: cast to int, range-checked 2000-2100
- `visit_month`: the most complex normalizer (see below)

**Month and season normalization:**

The `visit_month` parameter is flexible — the LLM might send `"October"`, `"Oct"`, `"10"`, or `"summer"`. Four lookup dicts handle all of them:

- Full name: `"october"` → `["Oct", "October"]`
- 3-letter abbreviation: `"oct"` → `"october"` → `["Oct", "October"]`
- Numeric string: `"10"` → `"october"` → `["Oct", "October"]`
- Season: `"summer"` → `["june", "july", "august"]` → `["Jun", "June", "Jul", "July", "Aug", "August"]`

The output is always a list of DB-compatible strings. Both 3-letter and full formats are included because the DB stores a mix.

**Visited inference:**

If `visit_year` or `visit_month` is present but `visited` is not, the normalizer auto-sets `visited=True`. The reasoning: asking "where did I go in October?" implies you visited those parks. Without this inference, the LLM sometimes omits `visited=true`, returning unvisited parks alongside visited ones.

**Park summary normalization** (`_normalize_park_summary_params`):

Resolves `park_code` via fuzzy matching, raises `LlmResponseError` if it can't resolve or if `park_code` is missing entirely — `search_park_summary` is the only tool with a required parameter.

**Negation correction:**

Small LLMs consistently struggle with negation. "Parks I *haven't* visited" → the LLM sees "visited" and sets `visited: true`, ignoring "haven't." Prompt engineering alone didn't fix this for Llama 3.1 8B (0/5 negation cases passed even with explicit rules).

The fix is a regex-based post-normalization step. A compiled pattern checks the original query for negation words (`haven't`, `hasn't`, `don't`, `not`, `never`, `unvisited`, `unhiked`). If found, and the LLM set a boolean param to `True`, the normalizer flips it to `False`:

```python
_NEGATION_PATTERN = re.compile(
    r"\b(haven'?t|hasn'?t|don'?t|didn'?t|not|never|unvisited|unhiked)\b",
    re.IGNORECASE,
)
```

This is applied *after* tool-specific normalization, so it acts as a safety net: if the LLM gets it right, the regex doesn't trigger (no negation words means no flip). If the LLM gets it wrong, deterministic code catches it.

The key insight: you don't trust the LLM to be perfect. You trust it to be *roughly right* and clean up programmatically. The LLM does the hard part (understanding natural language), and deterministic Python code does the easy part (enforcing exact formats). Each normalization layer was added in response to a specific eval failure — not speculatively.

### Step 8: The endpoint and dispatch (`api/main.py`)

The `POST /query` endpoint ties everything together in ~40 lines of logic.

#### Request/response models

FastAPI validates input and output through Pydantic models:

- `NlqRequest` — one field: `query`, a string between 3 and 500 characters. If validation fails, FastAPI returns 422 automatically before the endpoint function ever runs.
- `NlqResponse` — `original_query`, `interpreted_as`, `function_called`, and `results`.

#### The function signature

```python
async def natural_language_query(request: NlqRequest) -> dict[str, Any]:
```

- `async` — makes this a coroutine, required because it uses `await call_ollama(...)` inside. FastAPI runs it on its event loop, so other requests get served while waiting for the LLM.
- `request: NlqRequest` — FastAPI sees the Pydantic type and parses the JSON request body into it automatically.
- `-> dict[str, Any]` — return type hint. FastAPI validates the return value against the `response_model=NlqResponse` from the decorator.

#### The flow

Five steps in the function body:

1. **Build the prompt** — `get_park_lookup()` (cached after first call), build lookup text, build system message, build chat messages
2. **Call the LLM** — `await call_ollama(messages, TOOLS)` — the slow part (1-20+ seconds)
3. **Parse and normalize** — `parse_tool_call()` then `validate_and_normalize()` with `query=request.query` for negation detection
4. **Dispatch** — route to the existing query function based on function name
5. **Return** — wrap results with `original_query`, `interpreted_as`, and `function_called` for transparency

#### Dispatch

```python
if function_name == "search_trails":
    results = fetch_trails(**params)
elif function_name == "search_parks":
    results = fetch_all_parks(**params)
elif function_name == "search_stats":
    per_park = params.pop("per_park", False)
    results = fetch_park_stats(**params) if per_park else fetch_stats(**params)
elif function_name == "search_park_summary":
    summary = fetch_park_summary(**params)
    if summary is None:
        raise HTTPException(status_code=404, ...)
    results = summary
```

The `**params` unpacks the dict into keyword arguments. These are the **existing functions** behind `GET /trails`, `GET /parks`, `GET /stats`, `GET /stats/parks`, and `GET /parks/{park_code}/summary`. No new database logic was written for NLQ.

#### HTTP status codes

The endpoint uses standard HTTP status codes:

- **200** — success (the normal case)
- **404** — `search_park_summary` resolved a code that doesn't exist in the DB
- **422** — the LLM returned something unparseable, or the request body failed Pydantic validation
- **503** — Ollama isn't running or timed out

These aren't invented — they're part of the HTTP protocol (RFC 9110). Clients have built-in handling for them: a frontend might show a retry button for 503 but a "not found" message for 404.

#### The `interpreted_as` transparency field

The response includes `interpreted_as` so users can see exactly what parameters the LLM extracted. If you ask "short hikes in Yosemite" and get unexpected results, you can see `{"park_code": "yose", "max_length": 3.0}` and know *why*.

One subtlety: the `search_stats` branch uses `.pop("per_park")`, which mutates `params` before it goes into `interpreted_as`. So the user sees params *after* `per_park` was consumed — a minor transparency gap.

## End-to-end summary

```
User: POST /query  {"query": "long trails I've hiked in Zion"}

1. Build payload
   → System prompt with park lookup table injected from database
   → Tool definitions (search_trails, search_parks, search_stats, search_park_summary)
   → User's question

2. Send to Ollama
   → httpx POSTs JSON to localhost:11434
   → Llama 3.1 generates a tool call response

3. Parse response
   → Extract function name + arguments from tool_calls (or fallback to JSON in text)

4. Normalize values
   → Lowercase park codes, map state names to codes, clamp ranges
   → Resolve park names via fuzzy matching
   → Normalize month/season to DB-compatible values
   → Infer visited=True from visit timing
   → Flip booleans when negation words detected

5. Dispatch
   → fetch_trails(park_code="zion", min_length=5, hiked=True)
   → Same SQL query as GET /trails?park_code=zion&min_length=5&hiked=true

6. Return results with interpreted_as for transparency
```

The LLM's only role is translating English into function parameters. Everything before and after is deterministic Python code.

## Evaluating accuracy

With four tools and many possible phrasings, how do you know if the LLM is routing correctly? Manual testing catches obvious failures, but you need something systematic — especially when you want to compare models or measure the impact of a prompt change.

### The problem

LLMs are non-deterministic. The same question might route correctly most of the time but fail on edge cases. Negation is a classic example: "parks I've visited" correctly sets `visited: true`, but "parks I've *never* visited" might also set `visited: true` — the LLM sees "visited" and ignores "never." You won't catch this by trying a few queries by hand.

### The approach: golden dataset + eval script

The standard practice for evaluating LLM tool-calling is a **golden dataset** ��� a set of (query, expected function, expected params) tuples — paired with a script that runs each query through the real pipeline and reports accuracy.

### The golden dataset (`tests/eval/golden_queries.json`)

Currently 47 queries across 4 tools:

| Tool | Count |
|------|-------|
| `search_trails` | 16 |
| `search_parks` | 13 |
| `search_stats` | 9 |
| `search_park_summary` | 9 |

Each case specifies what the LLM *should* extract:

```json
{
  "query": "Parks I've never been to",
  "expected_function": "search_parks",
  "expected_params": {"visited": false},
  "category": "search_parks"
}
```

The `expected_params` is a **subset check** — if the LLM adds extra parameters beyond what's specified, that's fine. Only the listed parameters are verified. For example, "Show me trails in Yosemite" with `expected_params: {"park_code": "yose"}` passes even if the LLM also returns `source: "TNM"` or `limit: 50`. Extra params aren't great, but they're not failures — the required params being correct matters more.

The cases are designed to cover specific challenges:

- **Park resolution**: "Yosemite", "Zion National Park", "Saguaro NP" — different name formats
- **State vs. park**: "Trails in Utah", "California hiking trails", "Hikes under 2 miles in Colorado"
- **Length semantics**: "Short trails" → `max_length=3`, "Long hikes" → `min_length=5`, "between 3 and 8 miles"
- **Negation**: "Parks I haven't visited", "Which parks have I never been to?", "Unvisited national parks", "Acadia trails I haven't done", "Stats for trails I haven't hiked"
- **Visit timing**: year, month name, seasons, combined ("January 2025")
- **Broad queries**: "Show me all parks", "All the trails" — no params expected

For `visit_month`, the expected params use the post-normalization format — a list of DB-compatible values:

```json
{
  "query": "Parks visited in summer",
  "expected_function": "search_parks",
  "expected_params": {
    "visited": true,
    "visit_month": ["Jun", "June", "Jul", "July", "Aug", "August"]
  },
  "category": "search_parks"
}
```

### The eval script (`tests/eval/run_eval.py`)

Runs each query through the full NLQ pipeline — `build_chat_messages → call_ollama → parse_tool_call → validate_and_normalize` — the same code path as the `/query` endpoint. This is testing the real pipeline, not a mock. It requires Ollama running and the database up.

Three possible outcomes:

- **PASS**: correct function and all expected params match
- **PARTIAL**: correct function, but one or more params are wrong (e.g., `visited: true` instead of `false`)
- **FAIL**: wrong function entirely, or pipeline error

The param comparison handles float/int coercion — `3` in the golden file matches `3.0` from the normalizer.

### What the output looks like

```
  [ 1/47] Show me trails in Yosemite                          [+] (21.9s)
  [ 2/47] Hikes in Zion National Park                         [+] (1.8s)
  ...
  [34/47] What do you know about Lassen?                      [X] (1.3s)

============================================================
Model: llama3.1:8b | Runs: 1 | Queries per run: 47
============================================================

Overall: 46/47 pass (97.9%)
  PASS: 46  PARTIAL: 0  FAIL: 1

Per tool:
  search_park_summary    8/ 9 (88.9%)
  search_parks          13/13 (100.0%)
  search_stats           9/ 9 (100.0%)
  search_trails         16/16 (100.0%)

FAILURES (1):
  "What do you know about Lassen?"
    expected: search_park_summary {'park_code': 'lavo'}
    got:      search_parks {'visited': true}
    status:   FAIL
```

The first query takes ~22 seconds (model loading into memory), subsequent queries average ~1.5-2 seconds. The one failure — "What do you know about Lassen?" — is a routing ambiguity: the question doesn't contain trigger words like "summary", "details", or "overview" that would push toward the summary tool.

Results are saved to `eval_results/` as JSON files (timestamped with the model name) for later comparison.

### Using it

```bash
python tests/eval/run_eval.py                      # default model
python tests/eval/run_eval.py --model qwen2.5:7b   # try a different model
python tests/eval/run_eval.py --runs 3              # check consistency
python tests/eval/run_eval.py --threshold 0.8       # fail if below 80%
```

The `--threshold` flag is designed for CI — exit code 0 if pass rate meets the threshold, 1 if not. You could gate deployments on eval accuracy.

The workflow: run the eval, see what fails, tweak the prompt or tool descriptions, re-run, and compare. The JSON output files make it easy to track whether a change helped or hurt across the full dataset.

### The improvement cycle in practice

The eval started at roughly 84% and the following categories of failures were identified:

1. **Ambiguous queries** (removed from the golden set): "What's in Yellowstone?" could reasonably route to `search_trails` or `search_park_summary`. "How many parks have I hiked in?" could be `search_stats` or `search_parks`. These aren't LLM failures — there's no single correct answer. The fix was to delete them from the golden dataset rather than try to force one interpretation.

2. **State vs. park narrowing** (fixed by prompt engineering): "Hikes under 2 miles in Colorado" — the LLM picked a specific park in Colorado instead of using `state=CO`. Adding a system message rule ("When the user mentions a US state, use the state parameter. Do NOT pick a specific park within that state instead.") fixed this.

3. **Min/max confusion** (fixed by prompt engineering): "Hikes under 2 miles" — the LLM used `min_length=2` instead of `max_length=2`. Explicit rules for "under X miles → max_length" and "over X miles → min_length" fixed this.

4. **Visited inference** (fixed by normalization): "Where did I go in January 2025?" — the LLM correctly extracted `visit_year=2025` and `visit_month=January` but omitted `visited=true`. This is LLM non-determinism; sometimes it includes `visited`, sometimes it doesn't. The normalization layer now auto-infers `visited=True` when visit timing params are present.

5. **Negation blindness** (fixed by normalization): All five negation queries ("Parks I haven't visited", "Trails I haven't hiked", etc.) failed. Even after adding a negation rule to the system message, Llama 3.1 8B consistently set boolean params to `True` when it should have set `False`. The regex-based `_apply_negation_correction()` catches this at the normalization layer.

The pattern: prompt engineering first (cheap, no code), normalization fixes second (when the LLM consistently fails despite good prompts). Each fix was backed by unit tests to prevent regressions.
