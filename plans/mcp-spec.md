# NPS Hikes MCP Spec

## Overview

Build a local-first Model Context Protocol (MCP) server for `nps-hikes` that exposes the project's park and trail dataset as AI-native capabilities for MCP-compatible clients.

The goal of v1 is not to build another chatbot. The goal is to expose reliable, grounded `tools` and lightweight `resources` so an external assistant can answer questions using the user's real local `nps-hikes` data.

This spec defines the end-state design, architecture decisions, workflow, v1 scope, and implementation milestones for that server.

## Status

`V1 complete` as of July 21, 2026 for the local `stdio` server validated with `MCP Inspector`.

## Goals

- Learn MCP by building a real local server against an existing codebase.
- Reuse the existing `nps-hikes` query logic as much as possible.
- Keep v1 simple, deterministic, and easy to debug.
- Expose a small set of high-value `tools` and `resources`.
- Establish an architecture that can grow later without rework.

## Non-goals for v1

- Hosted or public MCP deployment.
- Multi-user auth, permissions, or production hardening.
- Wrapping the existing natural-language `/query` endpoint.
- Visualization endpoints.
- Topic search and embedding-backed semantic retrieval.
- Rich MCP prompt/template work beyond what is needed to understand the basics.

## Decisions Locked In

### Target client

The implementation target is a client-agnostic local MCP server over a standard MCP transport. `MCP Inspector` is the default v1 validation client, not the protocol target.

Rationale:

- Keeps the server aligned with the MCP standard instead of a single product surface.
- Uses a protocol-native debugging client that works directly with local `stdio` servers.
- Makes the design reusable with other MCP clients later.

### Deployment mode

V1 is `local-only`.

Rationale:

- No paid hosting required.
- Avoids free-tier sleep/cold-start issues.
- Keeps the full project stack under local control for debugging and learning.
- Matches the user's actual goal: learn MCP, not operate public infrastructure.

### Architecture approach

The MCP server should not primarily call the FastAPI app over HTTP.

Instead, the preferred architecture is:

- shared domain/service layer
- FastAPI uses that layer
- MCP server uses that same layer
- Streamlit remains an HTTP client of FastAPI

Rationale:

- Avoids an unnecessary local network hop.
- Reuses core logic without duplicating transport concerns.
- Creates a stronger long-term architecture if MCP remains part of the repo.
- Keeps validation and serialization boundaries simpler.

### Tool scope

V1 should expose deterministic, structured tools first:

- `search_trails`
- `search_parks`
- `search_stats`
- `search_park_summary`

`search_by_topic` should be deferred to v2.

These tools should intentionally mirror the existing FastAPI query surface where that reduces ambiguity and avoids duplicate logic. The MCP layer may omit some HTTP-specific options, but it should not introduce a parallel query language for v1.

Rationale:

- Reduces moving parts while learning MCP.
- Avoids coupling v1 to local embedding/LLM dependencies.
- Produces a more reliable foundation for future expansion.

### Resource scope

V1 should include a few lightweight but real resources:

- `dataset_overview`
- `park_lookup`
- `search_methodology`

Optional later v1 resource if it fits naturally:

- `park_summary/{park_code}`

Rationale:

- Demonstrates the distinction between tools and resources.
- Grounds the assistant with stable project context.
- Keeps the resource layer understandable and small.

### Output style

Tool outputs should be `structured + answer-oriented`, but not LLM-generated.

That means each tool should return:

- machine-usable structured fields
- compact summary text for the host assistant to incorporate
- enough metadata to stay interpretable

That does not mean the MCP server should compose full natural-language answers.

Rationale:

- The host assistant should do the final narration.
- The server should remain deterministic and testable.
- Compact summaries improve downstream usability without turning the server into a chatbot.

### Safety/auth

Assume a single-user local environment in v1.

Rationale:

- Appropriate for the project goal.
- Keeps the spec focused on MCP learning rather than infrastructure.

## Why This Is the Right MCP Angle

The best fit for this repo is a small local MCP server around the structured query layer, intentionally combining:

- low-level tools for precise querying
- a few high-signal resources for grounding

This is stronger than a thin wrapper over the API because it demonstrates actual MCP concepts, not just transport reuse. It is also better than exposing the existing `/query` endpoint because MCP is most useful when the host assistant performs the natural-language reasoning and the project supplies trustworthy capabilities and context.

Portfolio framing:

`nps-hikes MCP: a local AI research tool for exploring parks and trails with grounded data`

## End-State Workflow

When the project is complete, the user workflow should look like this:

1. Start the local `nps-hikes` environment.
2. Start the local MCP server from the repo.
3. Configure an MCP-compatible client to use the local MCP server.
4. Ask the client questions about parks, trails, and stats.
5. The client decides whether to call `nps-hikes` tools or read `nps-hikes` resources.
6. The MCP server runs local project logic against the user's local dataset.
7. The client answers in natural language using grounded results from the MCP server.

### Example client setup

For v1 learning and validation, `MCP Inspector` is the default example client for local setup instructions and end-to-end verification.

Rationale:

- it is purpose-built for MCP server testing and debugging
- it can launch local `stdio` servers directly
- it keeps the verification loop client-neutral while the server surface is still evolving

`ChatGPT` and other assistant clients remain valid later integrations, but they should be treated as optional client-specific follow-on work rather than the primary v1 validation path.

### Example user questions

- "Show me 5 unhiked trails in Utah under 4 miles."
- "Compare Yosemite and Acadia for trail variety."
- "What parks have I visited in October?"
- "Give me an overview of the dataset before we search."

### What the user will be able to do

- Ask an MCP-compatible assistant structured questions about parks and trails backed by real local project data.
- Let the assistant compare parks and summarize stats without relying on memory or generic web knowledge.
- See MCP `tools` and `resources` working together in a concrete project.
- Extend the system later with richer tools, topic search, or hosted adapters without changing the basic architecture.

## Proposed Architecture

### High-level shape

```text
MCP-compatible client
        |
        | MCP
        v
local nps-hikes MCP server
        |
        | Python calls
        v
shared service/query layer
        |
        v
Postgres / local project data
```

FastAPI remains in the repo and continues to serve Streamlit and any ordinary API clients, but it is not the primary runtime dependency of the MCP server.

### Architectural layers

#### 1. Core query/service layer

This layer is the source of truth for park, trail, and stats retrieval. It should contain reusable operations that are independent of both FastAPI and MCP transports.

Candidate responsibilities:

- fetch park lists with filters
- fetch trails with filters
- fetch aggregate stats
- fetch park summaries
- construct compact summary fields for downstream consumers

Where possible, this should reuse existing logic in `api/queries.py` and related model definitions rather than rewriting data access.

#### 2. FastAPI adapter

FastAPI should remain an adapter over the shared service layer.

Responsibilities:

- HTTP parameter parsing
- OpenAPI exposure
- HTTP exception mapping
- response model serialization

#### 3. MCP adapter

The MCP server should be a second adapter over the same shared service layer.

Responsibilities:

- expose MCP tools
- expose MCP resources
- translate MCP tool arguments into service-layer calls
- shape tool results into structured, answer-oriented payloads

## Why Not MCP -> FastAPI for V1

It would work, but it is not the preferred foundation here.

Benefits of direct shared-layer reuse over local HTTP reuse:

- fewer layers to debug
- no duplicate transport validation
- no local network dependency between components in the same repo
- cleaner unit testing
- stronger long-term design if the MCP server grows

Using FastAPI as the MCP backend remains a valid fallback if direct reuse becomes awkward, but it should not be the default plan.

## V1 MCP Surface

### Tools

#### `search_trails`

Purpose:
Retrieve trails using explicit structured filters.

Inputs:

- `park_code` - optional 4-letter lowercase park code
- `state` - optional 2-letter uppercase state code
- `hiked` - optional boolean
- `min_length` - optional minimum trail length in miles
- `max_length` - optional maximum trail length in miles
- `source` - optional `TNM` or `OSM`
- `viz_3d` - optional boolean
- `limit` - optional result limit, default 50, max 1000

Output shape:

- `summary`
- `trail_count`
- `total_miles`
- `applied_filters`
- `trails`

Each trail should include the most useful chat-facing fields, not every possible field by default.

Notes:

- This tool should mirror the current `/trails` API semantics for filters and defaults.
- V1 should not include pagination unless it falls out naturally from the existing shared logic.
- V1 should not include geometry-heavy payloads by default.

#### `search_parks`

Purpose:
Retrieve parks using visit and metadata filters.

Inputs:

- `visited` - optional boolean
- `visit_year` - optional integer year
- `visit_month` - optional month value or values normalized to the existing backend behavior
- `park_code` - optional 4-letter lowercase park code
- `state` - optional 2-letter uppercase state code

Output shape:

- `summary`
- `park_count`
- `visited_count`
- `applied_filters`
- `parks`

Notes:

- This tool should mirror the current `/parks` API semantics where practical.
- If visit timing is supplied, the shared logic may infer visited status the same way the current backend does.

#### `search_stats`

Purpose:
Return aggregate trail statistics.

Inputs:

- `hiked` - optional boolean

Output shape:

- `summary`
- scalar metrics
- source breakdowns and other aggregate fields already supported by shared logic

Notes:

- V1 should keep this tool aligned with the current aggregate `/stats` behavior.
- Per-park breakdowns should stay out of the v1 MCP surface. If they are added later, they should be a separate tool rather than an optional mode hidden behind a boolean flag.

#### `search_park_summary`

Purpose:
Return a detailed overview for a specific park.

Inputs:

- `park_code` - required 4-letter lowercase park code

Output shape:

- `summary`
- `park`
- `trail_stats`
- `source_breakdown`
- `visit_info`

Notes:

- V1 should keep this tool strict and require `park_code`.
- Park-name resolution should happen outside the tool call, typically by consulting the `park_lookup` resource first.
- This preserves parity with the existing API while still demonstrating how MCP resources can support tool selection.

### Resources

#### `dataset_overview`

Purpose:
Give the assistant stable background on what `nps-hikes` contains and what the dataset is for.

Likely content:

- short description of the project
- available data domains
- known constraints
- local-only assumptions for this MCP server

#### `park_lookup`

Purpose:
Provide a stable mapping from park names to park codes.

Likely content:

- park names
- park codes
- maybe state abbreviations

This resource is the preferred v1 path for resolving human park names to canonical `park_code` values before calling strict tools such as `search_park_summary`.

#### `search_methodology`

Purpose:
Explain what the results mean and how to interpret them.

Likely content:

- trail source provenance
- deduplication behavior
- meaning of `visited` and `hiked`
- any important caveats about local data freshness or filtering

#### Optional `park_summary/{park_code}`

Purpose:
Offer a resource form of park context if it improves grounding and fits naturally into the implementation.

This is optional because the `search_park_summary` tool may already cover the most useful path in v1.

## Tool Design Principles

- Prefer a small number of clear tools over a large tool catalog.
- Keep arguments explicit and typed.
- Reuse existing parameter names and semantics where practical.
- Return concise, stable, structured results.
- Include compact `summary` fields to help the host assistant compose responses.
- Avoid embedding LLM behavior inside the server for v1.

### Tool Contract Source of Truth

For v1, MCP tool contracts should be derived primarily from the existing FastAPI layer and its OpenAPI-visible constraints, not directly from SQL schema details.

That means the MCP spec should mirror the external behavior already established by the API, including:

- argument names
- allowed value formats
- defaults and limits
- required versus optional parameters
- not-found, empty-result, and validation behavior

This is not redundant with the database schema. The SQL layer defines storage; the MCP tool contract defines the external interface seen by MCP clients.

The MCP contract does not need to restate every HTTP concern or expose every API option, but any deliberate deviation from current FastAPI behavior should be explicit in the spec.

### Error Handling Expectations

Tool behavior should be deterministic for the most common failure paths:

- invalid arguments should produce clear validation errors
- unknown `park_code` should produce a readable not-found result or error
- empty matches should return a successful empty result, not a failure
- database or infrastructure problems should surface as operational errors, not ambiguous empty payloads

These expectations should be finalized alongside the tool contracts before implementation begins.

## Data and Logic Reuse Strategy

The MCP server should maximize reuse from the existing codebase.

Preferred order of reuse:

1. existing query/service logic
2. existing Pydantic models, or shared model shapes derived from them
3. existing normalization and validation helpers where transport-neutral

If some logic currently lives too close to FastAPI, factor it into a shared layer rather than duplicating it in the MCP server.

## V1 Implementation Notes

### Implementation approach

Implementation should happen in small, understandable slices rather than as one large MCP drop.

Each step should aim to:

- introduce one new MCP concept at a time
- keep the diff small enough to review comfortably
- verify behavior before moving to the next step
- leave the repo in a runnable state after each completed step

Preferred working rhythm:

1. read the current code path being reused
2. implement one small MCP-facing piece
3. run the smallest useful verification
4. document what changed and why
5. pause before starting the next slice

This project is explicitly a learning build. The implementation plan should optimize for clarity and traceability, not just speed.

### Suggested repository layout

One reasonable direction:

```text
api/
  main.py
  queries.py
services/
  search.py              # optional shared layer extracted from api/queries.py
mcp/
  server.py
  tools.py
  resources.py
  models.py              # only if needed for MCP-specific result shaping
plans/
  mcp-spec.md
```

The exact folder names can vary. The important design point is transport separation, not the specific path.

### Transport

Use `stdio` as the default v1 transport.

Rationale:

- simplest local-first setup
- easy to debug during MCP learning
- good fit for desktop client integration
- avoids premature transport complexity

If a specific client later requires a different transport, that should be treated as a client-integration concern rather than a change to the core server design.

### Default validation client

Use `MCP Inspector` as the default v1 test client.

Rationale:

- it works naturally with local `stdio` servers
- it is better for inspecting tool schemas, resource reads, and error payloads than a chat-first client
- it keeps the project grounded in MCP itself before any vendor-specific integration work

### Framework choice

Choose a Python MCP library/framework that keeps the server implementation small and standards-aligned.

Selection criteria:

- good Python ergonomics
- clear tool/resource primitives
- easy local development
- minimal hidden magic

The implementation should avoid inventing custom protocol handling if a standard library exists. The starting assumption for v1 is a standard Python MCP library plus `stdio` transport.

## What V1 Will Not Do

V1 will not:

- answer arbitrary free-text questions on its own
- call a local LLM internally
- support semantic/topic search
- serve charts, HTML, or images
- operate as a hosted public MCP service
- handle multiple users or auth policies

That is intentional. V1 should teach the MCP model cleanly before additional complexity is added.

## V2 Candidates

Once v1 is stable, good next additions would be:

- `search_by_topic`
- richer per-park resources
- prompt/template support if desired
- optional higher-level orchestration tools
- optional hosted adapter layer

### Why `search_by_topic` is deferred

It is a good future feature, but it introduces additional operational complexity:

- local embedding generation
- local LLM dependencies
- more moving parts during debugging

That makes it better as a second phase, not part of the foundation.

## Implementation Milestones

The implementation should proceed in order. Do not start a later step until the current step is understandable and verified.

### Step 1: Confirm the reusable backend surface

Goals:

- identify the exact existing functions to reuse
- decide whether a small `services/` extraction is needed
- map current FastAPI query capabilities to MCP tools

Deliverables:

- chosen shared-layer entry points
- list of any refactors needed before MCP code is added

Checklist:

- [x] identify the current FastAPI endpoints that map to v1 MCP tools
- [x] identify the exact backend functions each MCP tool should call
- [x] confirm whether those functions are already transport-neutral
- [x] note any FastAPI-coupled logic that should move into a shared layer
- [x] write down the smallest safe extraction plan, if extraction is needed
- [x] confirm that no v1 MCP tool requires the NLQ `/query` path

Suggested verification:

- read the relevant FastAPI handlers and query functions side by side
- confirm the proposed MCP tools can be backed by existing structured logic

### Step 2: Define MCP tool and resource schemas

Goals:

- finalize v1 tool names, arguments, and return shapes
- finalize resource identifiers and contents
- define answer-oriented summary fields
- document any intentional differences from the FastAPI surface

Deliverables:

- tool contracts
- resource contracts
- examples of expected payloads
- documented error behavior for empty, invalid, not-found, and operational failure cases

Checklist:

- [x] confirm the final v1 tool list
- [x] confirm the final v1 resource list
- [x] write the exact arguments for each tool
- [x] document defaults, limits, and required fields
- [x] document which API options are intentionally omitted from v1 MCP
- [x] define what each `summary` field should contain
- [x] define empty-result behavior for each tool
- [x] define not-found behavior for `search_park_summary`
- [x] define operational-error behavior at the MCP boundary
- [x] add at least one example payload for each tool and resource

Suggested verification:

- review the schema definitions against current FastAPI/OpenAPI behavior
- confirm there is no hidden ambiguity a developer would need to guess about

### Step 3: Add the MCP server skeleton

Goals:

- add the local MCP server package/module
- register tools and resources
- verify the server starts locally

Deliverables:

- runnable local MCP server
- local startup instructions

Checklist:

- [x] choose the Python MCP library for v1
- [x] create the `mcp/` module structure
- [x] add a minimal server entry point
- [x] configure the server to run over `stdio`
- [x] register placeholder tools
- [x] register placeholder resources
- [x] verify the server starts without calling project logic yet
- [x] document the local startup command

Suggested verification:

- run the server locally and confirm it starts cleanly
- verify the client can see the registered tool and resource names

### Step 4: Wire one tool end to end first

Goals:

- connect a single MCP tool to real shared logic first
- prove the end-to-end pattern before repeating it
- keep the first integration narrow and easy to reason about

Recommended first tool:

- `search_stats`

Rationale:

- small input surface
- no park-name resolution concern
- aggregate output is easier to inspect than large trail lists

Deliverables:

- working `search_stats`
- initial shared output-shaping pattern
- initial MCP-side error mapping pattern

Checklist:

- [x] decide the exact first tool to implement
- [x] connect it to the shared query/service layer
- [x] shape its result into the MCP response format
- [x] add a compact deterministic `summary`
- [x] verify empty and operational failure behavior
- [x] document the implementation pattern for reuse by later tools

Suggested verification:

- invoke the first tool manually through the MCP client
- confirm the output is both structured and easy for an assistant to narrate

### Step 5: Wire the remaining core tools

Goals:

- connect the remaining v1 tools to the shared query/service layer
- keep output shaping and error handling consistent
- avoid rewriting logic already proven in earlier steps

Deliverables:

- working `search_trails`
- working `search_parks`
- working `search_park_summary`

Checklist:

- [x] implement `search_trails`
- [x] implement `search_parks`
- [x] implement `search_park_summary`
- [x] keep argument semantics aligned with the spec
- [x] keep result shapes consistent across tools
- [x] confirm `search_park_summary` remains strict on `park_code`
- [x] confirm no tool depends on the NLQ stack
- [x] verify each tool against at least one real example query

Suggested verification:

- test one success case and one edge case for each tool
- confirm output sizes stay reasonable for assistant use

### Step 6: Add lightweight resources

Goals:

- implement `dataset_overview`
- implement `park_lookup`
- implement `search_methodology`

Deliverables:

- working resource reads in the MCP client

Checklist:

- [x] implement `dataset_overview`
- [x] implement `park_lookup`
- [x] implement `search_methodology`
- [x] confirm each resource has a clear reason to exist
- [x] confirm `park_lookup` is sufficient for resolving park names to codes in v1
- [x] verify resource contents are stable and lightweight

Suggested verification:

- read each resource from the MCP client
- verify that the resources improve tool use rather than duplicating tool output

### Step 7: Local client integration

Goals:

- connect the server to an MCP-compatible local client
- verify tool invocation and resource access end to end

Deliverables:

- local integration instructions for the example client
- example prompts that exercise the server

Checklist:

- [x] connect the local MCP server to the example client
- [x] verify the client can discover tools
- [x] verify the client can discover resources
- [x] verify a resource can be read successfully
- [x] verify a tool can be called successfully
- [x] verify a multi-step workflow that uses both a resource and a tool
- [x] write concise local setup instructions
- [x] write a short set of demo prompts

Suggested verification:

- run the recommended demo script end to end
- confirm the assistant uses grounded MCP data instead of generic background knowledge

Suggested default workflow:

1. Launch `MCP Inspector` against the local `stdio` server.
2. Confirm `tools/list` and `resources/list`.
3. Read `dataset_overview` and `park_lookup`.
4. Call `search_stats`, then `search_parks`, then `search_trails`.
5. Treat any later ChatGPT or other assistant integration as a separate client-adapter milestone.

### Step 8: Testing and polish

Goals:

- add unit tests around tool result shaping
- test failure paths
- verify the assistant can use the tools coherently

Deliverables:

- test coverage for core MCP behaviors
- concise developer documentation

Checklist:

- [x] add tests for tool result shaping
- [x] add tests for resource reads where useful
- [x] add tests for validation failures
- [x] add tests for not-found behavior
- [x] add tests for empty-result behavior
- [x] add tests for operational error handling where practical
- [x] document how to run the MCP server locally
- [x] document how to verify the MCP client connection
- [x] document the current v1 limitations

Suggested verification:

- run the test suite covering MCP-specific logic
- perform one final manual end-to-end check from client to data source

## Acceptance Criteria

The v1 MCP project is successful when:

- [x] the local MCP server starts reliably
- [x] the server runs over local `stdio` transport
- [x] at least one MCP-compatible client can use the server as a local MCP tool source
- [x] the assistant can retrieve real `nps-hikes` park/trail/stat data through MCP tools
- [x] the assistant can read at least a few grounding resources
- [x] the MCP server reuses existing project logic rather than duplicating the backend
- [x] no local LLM dependency is required for the core MCP workflow

## Recommended Demo Script for Self-Verification

Even if this is not intended as a formal demo project, these checks confirm the workflow is working:

1. In `MCP Inspector`, list available tools and resources.
2. Read `dataset_overview`.
3. Read `park_lookup`.
4. Call `search_stats`.
5. Call `search_parks` for visited parks in a given month.
6. Call `search_trails` for trails under a given mileage in a state.
7. Call `search_park_summary` with a known `park_code`.

## Summary

V1 should be a small, local, standards-aligned MCP server that exposes `nps-hikes` as a grounded research tool for an external assistant.

The key architectural choice is to share backend logic between FastAPI and MCP rather than layering MCP on top of local HTTP. The key product choice is to expose deterministic structured tools plus lightweight resources, not another NLQ layer. This yields the strongest foundation for learning MCP and for expanding the project later.
