# Code Sample Linting in Documentation

## Problem

Code samples in documentation rot as the codebase evolves. JSON response examples get stale, bash commands break, and Python snippets drift from project formatting standards. Without automated checks, these errors accumulate silently and erode trust in the docs.

## What we implemented (Tier 1: Static analysis)

Four static checks for code samples embedded in Markdown fenced code blocks, running in both pre-commit hooks and CI. These checks catch syntax, formatting, and lint problems, but they are different from validation against a contract.

### JSON syntax checking

**Script:** `scripts/hooks/check_json_codeblocks.py`

Extracts ` ```json ` blocks from Markdown and checks them with `json.loads()`. Partial examples using ellipsis patterns are sanitized before checking rather than skipped:

- `[...]` is replaced with `[]`
- Standalone `...` lines are removed
- Trailing commas left behind are stripped

This allows structural syntax checking (mismatched braces, missing quotes, missing commas) even in partial response examples.

**Limitations:** Only checks JSON syntax. Does not verify that response examples match the actual API schema.

### Bash syntax checking

**Script:** `scripts/hooks/check_bash_codeblocks.py`

Extracts ` ```bash ` blocks and runs `bash -n` (syntax-only mode) on each one. Catches parse errors like unclosed quotes, mismatched braces, and malformed control structures without executing the commands.

**Limitations:** Only checks shell grammar. Does not verify that commands exist, flags are valid, or commands would succeed. Only checks ` ```bash ` blocks, not ` ```sh ` or ` ```shell `.

### Python formatting

**Tool:** [blacken-docs](https://github.com/adamchainz/blacken-docs)

Runs Black formatting on ` ```python ` blocks inside Markdown. In pre-commit, it auto-fixes formatting. In CI, it runs with `--check` to fail on unformatted code. This also catches syntax errors since Black cannot format unparseable Python.

**Exclusions:** `scratch/` and `reviews/` directories are excluded (working notes, not published docs).

**Limitations:** Only formats and syntax-checks. Does not lint (no unused import detection, no style rule enforcement beyond formatting).

### Python linting

**Script:** `scripts/hooks/check_python_codeblocks.py`

Extracts ` ```python ` blocks from Markdown into temporary `.py` files and runs `ruff check` against those files. Ruff does not lint Markdown fences directly, so this uses the common docs-tooling pattern: extract snippets, run the normal language tool, then map diagnostics back to the original Markdown file and line number.

This complements `blacken-docs`:

- `blacken-docs` formats Python examples and catches syntax errors.
- `check_python_codeblocks.py` catches lint issues such as unused imports, undefined names, import ordering, and other Ruff rules configured in `pyproject.toml`.

**Exclusions:** `scratch/`, `reviews/`, and `tests/` directories are excluded in pre-commit and CI. The `tests/` Markdown files contain internal implementation notes with intentionally partial snippets, which are not good candidates for docs snippet linting.

**Limitations:** Python snippets in docs are often intentionally incomplete. If examples grow and need to show partial code, this hook may need an escape hatch such as `# noqa` comments or a Markdown-level skip annotation.

### Checking vs validation

For this project, **checking** means a tool inspects the sample for local correctness: syntax, formatting, lint rules, or style. **Validation** means the sample is compared against an external contract, such as an API schema, expected command output, or runtime behavior.

That distinction is why the JSON scripts are split:

- `check_json_codeblocks.py` checks whether JSON examples parse.
- `validate_json_schema.py` validates annotated JSON examples against Pydantic response-model schemas.

The Python tooling is still in the checking layer:

- `blacken-docs` formats Python examples and checks that Black can parse them.
- `check_python_codeblocks.py` runs Ruff lint checks on extracted Python examples.

Ruff is more than syntax checking because it catches unused imports, undefined names, import-order issues, and other static-analysis findings. But it is not validation in the same sense as schema validation. A Python docs-validation layer would execute examples, type-check them against a real SDK/API contract, or assert expected output.

### Where they run

**Pre-commit hooks** (`.pre-commit-config.yaml`):

| Hook ID | Runs on | Behavior |
|---|---|---|
| `blacken-docs` | Markdown (excluding `scratch/`, `reviews/`) | Auto-fixes formatting |
| `check-python-codeblocks` | Markdown (excluding `scratch/`, `reviews/`, `tests/`) | Fails on Python lint errors |
| `check-bash-codeblocks` | All Markdown | Fails on syntax errors |
| `check-json-codeblocks` | All Markdown | Fails on invalid JSON |

**CI** (`.github/workflows/docs-lint.yml`):

| Job | Tool | Mode |
|---|---|---|
| `python-codeblocks` | `blacken-docs --check` | Check only (no auto-fix) |
| `python-codeblocks` | `check_python_codeblocks.py` | Check only |
| `bash-codeblocks` | `check_bash_codeblocks.py` | Check only |
| `json-codeblocks` | `check_json_codeblocks.py` | Check only |

These run alongside the existing `markdown-lint`, `vale-lint`, and `docs-build` jobs.

### Files changed

- `scripts/hooks/check_json_codeblocks.py` (new)
- `scripts/hooks/check_bash_codeblocks.py` (new)
- `scripts/hooks/check_python_codeblocks.py` (new)
- `.pre-commit-config.yaml` (4 hooks added)
- `.github/workflows/docs-lint.yml` (3 jobs added, Python job now runs formatting and linting)
- `requirements-dev.in` (added `blacken-docs`)
- `requirements-dev.txt` (recompiled)

## Rethinking the tiers

The original tier numbering (2, 3, 4) implied a linear progression where each tier subsumes the last. That's misleading. These approaches address different failure modes, not increasing levels of sophistication. A project can use any combination depending on which code block types dominate and where drift actually hurts.

### Failure modes by layer

| Layer | Question | Status | What breaks without it |
|---|---|---|---|
| **Syntax** | Does it parse? | Done (Tier 1) | Embarrassing typos in JSON/bash/Python |
| **Schema** | Does it match the API contract? | Done for annotated JSON response examples | JSON examples with renamed fields, missing new fields, wrong types |
| **Execution** | Does the command work? | Not yet | Curl commands with changed flags, wrong endpoints, bad auth |
| **Generation** | Can it even drift? | Not yet | Nothing — drift is impossible by construction |

These are independent. You can validate JSON against the OpenAPI schema (layer 2) without ever executing a curl command (layer 3). You can auto-generate response examples (layer 4) for JSON blocks while staying at syntax-only for bash blocks.

### Code block inventory

The right question is not "which tier next" but "which failure mode matters most for which type of code block."

| Block type | Count | Current coverage | Dominant drift risk |
|---|---|---|---|
| bash | 46 | Syntax only (`bash -n`) | Commands that parse but fail (wrong flags, changed endpoints) |
| JSON | 5 | Syntax check (`json.loads`) + schema validation for annotated response examples | Response examples that don't match the actual API schema |
| Python | 1 | Formatting/syntax (`blacken-docs`) + lint checking (`ruff`) | Low risk — single block, rarely changes |
| text | 8 | None | Directory trees that don't match reality |
| dotenv | 2 | None | Env var names that changed |
| CSV | 1 | None | Low risk — format example, not executable |

The dominant risk is: **curl commands return different responses than the JSON examples show**. That's the bash-to-JSON pipeline, and it's where the 5 JSON blocks and 46 bash blocks interact.

## Approaches by failure mode

### Schema validation (validate structure without running services)

Validate that JSON response examples in the docs conform to the Pydantic response models in the API. No running services needed — load the FastAPI app's OpenAPI schema at test time and check doc examples against it.

**When this is used in industry:** API-first companies (Stripe, Twilio) validate all examples against the OpenAPI spec in CI. This is the standard pattern for API reference docs.

**What it catches that Tier 1 doesn't:** A JSON example with valid syntax but a renamed field, a missing new field, or a changed nesting structure. For example, if `visit_month` gets renamed to `visited_month` in the Pydantic model, the doc example would fail validation even though it's perfectly valid JSON.

**Limitations:** Only validates the JSON blocks (5 out of 126 total). Does not check whether the curl command preceding a JSON block would actually produce that response. Does not help with the 46 bash blocks at all.

**Fit for this project:** High. The FastAPI app already has typed Pydantic response models with `response_model` annotations on every data endpoint. Three of the five JSON blocks map to `ParksResponse` and `TrailsResponse` models. The other two (health check and root endpoint) return untyped dicts — those would need either separate handling or added response models.

### Tested-alongside (integration tests that mirror the tutorial)

Write a pytest test that starts Docker services, runs the tutorial's curl commands, and asserts response shape (status codes, key fields present). The test lives alongside the docs, not inside them. When the test breaks, someone knows the docs are stale.

**When this is used in industry:** Most OSS projects with API tutorials. Django, Flask, and FastAPI project docs often have integration tests that mirror the getting-started guide. The docs and tests are separate artifacts kept in sync by convention and CI.

**What it catches that schema validation doesn't:** Commands that don't work. A curl command might reference a removed query parameter, use the wrong endpoint path, or require auth that wasn't mentioned. Schema validation won't catch any of this because it only looks at the JSON blocks, not the bash blocks.

**Limitations:** Requires running services (Docker, database with data). Slower CI. Tests and docs can still drift from each other since they're separate files — someone could update the test without updating the docs, or vice versa. The integration tests in this project already cover most endpoint behavior; a doc-specific test would overlap with those.

**Fit for this project:** Medium. Useful for learning the pattern, but the existing integration test suite already exercises the same endpoints. The marginal value is catching drift between docs and API, but schema validation handles the structural part of that.

### Executable docs (extract and run code from the markdown itself)

Tools like `rundoc`, `mdsh`, or `cog` treat the markdown as executable. They extract code blocks, run them in sequence, and optionally compare output against expected results.

**When this is used in industry:** Language tutorials and library docs where code blocks are self-contained. The Rust Book uses `mdbook test` to compile and run every code block. Python uses `doctest`. Elixir uses `ExUnit.DocTest`. These work well when the code blocks are standalone snippets that don't need external services.

**What it catches:** Everything — if the block runs and produces the expected output, the docs are correct by construction.

**Limitations:** Requires the full runtime environment. For this project, that means Docker with a populated database, which is the same requirement as integration tests but with less control over error handling and test isolation. With 46 bash blocks that are mostly curl commands to `localhost:8000`, you'd need the entire stack running. The tools also struggle with partial examples (the `...` truncation patterns) and commands that depend on prior state (data loaded, profiling modules run).

**When Tier 2 tools become redundant:** `pytest-codeblocks` (Tier 2) is strictly subsumed by `rundoc` (Tier 3) — both extract code from markdown and run it, but `rundoc` also verifies output. If you're going to do either, do `rundoc`. However, the "parallel integration tests" approach from Tier 2 is *not* redundant with Tier 3 because it tests the system independently of the markdown. They complement each other.

**Fit for this project:** Low for now. With only 1 Python block (the one type where extraction works cleanly) and 46 bash blocks that all need Docker, the tooling doesn't match the code block inventory. The partial examples with `...` truncation would also need special handling.

### Generated docs (invert the problem)

Instead of testing that docs match code, generate the docs from code so they can't drift.

**When this is used in industry:** API reference docs are almost always generated (from OpenAPI specs, from code annotations, from docstrings). Stripe generates all response examples from their API. ReadTheDocs projects use autodoc. The tradeoff is that generated docs tend to be reference-style, not tutorial-style. Tutorials with narrative flow are hard to generate.

**Approaches:**
- **Snapshot testing**: A CI step hits each endpoint, captures the response, writes it to a snapshot file. Docs include snapshots via `pymdownx.snippets`. When the API changes, regenerate the snapshot and docs follow.
- **`cog` for output injection**: Embed a Python generator in the markdown that runs a curl command and captures output. `cog` injects the real output. CI runs `cog --check` to verify docs match.
- **OpenAPI-driven examples**: Validate that example responses in the OpenAPI spec match the schema with `openapi-examples-validator`, then reference these validated examples in the docs.

**Fit for this project:** High for JSON response examples specifically. The 5 JSON blocks are exactly the type of content that can be generated or validated from a single source of truth. Not applicable to the bash command blocks or narrative text.

## What we implemented (Schema validation)

Validates that JSON response examples in the docs match the Pydantic response models in the API. No running services needed — imports the Pydantic models directly, generates JSON schemas, and validates doc examples against them.

### How it works

JSON blocks are marked with HTML comment annotations invisible in rendered docs:

```html
<!-- response: GET /parks -->
```

The script:

1. Scans Markdown for `<!-- response: METHOD /path -->` followed by a ` ```json ` block.
2. Maps the endpoint to a Pydantic model via a lookup dict (`GET /parks` → `ParksResponse`).
3. Generates the JSON schema from the model with `model_json_schema()`.
4. Patches the schema for partial doc examples:
   - Removes `required` constraints (doc examples intentionally omit fields).
   - Adds `additionalProperties: false` (catches renamed or bogus fields).
5. Sanitizes the doc JSON (same `...`/`[...]` handling as the syntax checker).
6. Validates with `jsonschema.Draft202012Validator`.

Three of the five JSON blocks in `docs/api-tutorial.md` are annotated. The other two (health check and root endpoint) return untyped dicts and are skipped — Tier 1 syntax checking is sufficient for those.

### What it catches

- **Renamed fields**: If `visit_month` changes to `visited_month` in the Pydantic model, the doc example with the old name fails validation (`additionalProperties: false` rejects unknown fields).
- **Wrong types**: A string where an integer is expected fails.
- **Removed fields**: A field deleted from the model is caught as an unexpected additional property.

### What it does not catch

- Missing required fields. The `required` constraint is removed because doc examples are intentionally partial (e.g., the Trail example omits `geometry_type`).
- Whether the curl command preceding a JSON block would produce that response.
- Drift in the 2 unannotated JSON blocks (health check, root endpoint).

### Where it runs

**Pre-commit hook** (`.pre-commit-config.yaml`):

| Hook ID | Runs on | Behavior |
|---|---|---|
| `validate-json-schema` | Markdown files | Fails on schema mismatches |

**CI** (`.github/workflows/docs-lint.yml`):

| Job | Tool | Dependencies |
|---|---|---|
| `json-schema` | `validate_json_schema.py` | `pydantic`, `jsonschema` |

Unlike the Tier 1 hooks (which use only stdlib), this hook needs `pydantic` to import the models and `jsonschema` for validation. In CI, only these two packages are installed — not the full project requirements.

### Files changed

- `scripts/hooks/validate_json_schema.py` (new)
- `scripts/hooks/__init__.py` (new — makes hooks importable for tests)
- `tests/unit/test_validate_json_schema.py` (new — 28 tests)
- `docs/api-tutorial.md` (3 HTML comment annotations added)
- `.pre-commit-config.yaml` (1 hook added)
- `.github/workflows/docs-lint.yml` (1 job added, trigger paths updated)
- `requirements-dev.in` (added `jsonschema`)
- `requirements-dev.txt` (recompiled)

## Recommended next steps

1. ~~**OpenAPI schema validation**~~ — Done. See above.

2. **Tutorial integration test** — useful for learning the "tested-alongside" pattern. Catches command-level drift (changed endpoints, removed parameters). But overlaps with existing integration tests, so marginal value is lower.

   Recommended shape:

   - Treat this as a **reader-journey regression test**, not another general API correctness test.
   - Start with `docs/api-tutorial.md` only. Add `docs/getting-started.md` later if the goal becomes testing setup instructions rather than API usage.
   - Use FastAPI `TestClient` plus the existing seeded integration-test database fixtures instead of literally starting Docker and running `curl`. This keeps the test deterministic while still exercising the documented endpoint paths and query parameters.
   - Seed canonical docs examples where practical (`acad`, `yose`, and a trail slug such as `jordan_pond_path`) so the test reads like the tutorial.
   - Use medium-strength assertions: response status is `200`, top-level fields exist, and a few reader-visible values match the seeded data. Avoid exact full-response snapshots for the first version because pagination, counts, and optional fields can make the test brittle.
   - Exclude slow or local-only sections in v1: full data collection, profiling-generated images, browser-only visualization inspection, and `/query` with Ollama.
   - Put the test in `tests/integration/test_api_tutorial_docs.py` and mark it with both `integration` and a docs-specific marker such as `docs_integration` if independent selection would be useful.
   - Run it with the existing integration workflow rather than `docs-lint.yml`; it depends on a database and full project dependencies, so it belongs with integration tests.

   The test should answer: "Can a reader follow the stable API-query path in the tutorial and still get the documented kinds of responses?" It should not try to prove that every code block in the tutorial is executable or that the entire local setup pipeline succeeds.

   Narrow implementation questions before building:

   - Should the first pass cover only `docs/api-tutorial.md`, or also the quick verification commands from `docs/getting-started.md`?
   - Should seeded data match the tutorial examples exactly, or is generic seeded data acceptable?
   - Should docs integration tests have a separate pytest marker for targeted local runs?
   - Which tutorial sections are explicitly out of scope for v1 so future failures are interpreted correctly?

3. **Skip executable doc tools for now** — `rundoc`/`cog`/`pytest-codeblocks` don't match the code block inventory. Revisit if the SDK docs grow or if more Python examples are added.

### Remaining Tier 1 improvements

- ~~**YAML validation**~~ — Ruled out. No ` ```yaml ` or ` ```yml ` blocks exist in the docs.
- ~~**Ruff lint for Python blocks**~~ — Done. Extracts Python blocks to temp files and runs `ruff check` for lint rules beyond formatting (unused imports, undefined names, import ordering). Low value with only 1 published Python block, but useful for learning the standard extraction pattern.
- ~~**Link checking**~~ — Done. Implemented with lychee (`lychee.toml`). Pre-commit runs `--offline` (local/relative links only). CI runs full external link checking via `lycheeverse/lychee-action`. Streamlit app URL excluded (303 redirect loop from auth flow).
