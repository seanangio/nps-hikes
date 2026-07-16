# NPS Hikes MCP Spec

## Overview

Build a local-first Model Context Protocol (MCP) server for `nps-hikes` that exposes the project's park and trail dataset as AI-native capabilities for ChatGPT and other MCP-compatible clients.

The goal of v1 is not to build another chatbot. The goal is to expose reliable, grounded `tools` and lightweight `resources` so an external assistant can answer questions using the user's real local `nps-hikes` data.

This spec defines the end-state design, architecture decisions, workflow, v1 scope, and implementation milestones for that server.

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

The intended user experience is `ChatGPT`, but the implementation target is a client-agnostic local MCP server over a standard MCP transport.

Rationale:

- Keeps the server aligned with the MCP standard instead of a single product surface.
- Reduces churn if ChatGPT-specific setup details change.
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
3. Configure ChatGPT to use the local MCP server.
4. Ask ChatGPT questions about parks, trails, and stats.
5. ChatGPT decides whether to call `nps-hikes` tools or read `nps-hikes` resources.
6. The MCP server runs local project logic against the user's local dataset.
7. ChatGPT answers in natural language using grounded results from the MCP server.

### Example user questions

- "Show me 5 unhiked trails in Utah under 4 miles."
- "Compare Yosemite and Acadia for trail variety."
- "What parks have I visited in October?"
- "Give me an overview of the dataset before we search."

### What the user will be able to do

- Ask ChatGPT structured questions about parks and trails backed by real local project data.
- Let ChatGPT compare parks and summarize stats without relying on memory or generic web knowledge.
- See MCP `tools` and `resources` working together in a concrete project.
- Extend the system later with richer tools, topic search, or hosted adapters without changing the basic architecture.

## Proposed Architecture

### High-level shape

```text
ChatGPT (MCP client)
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

Likely inputs:

- `park_code`
- `state`
- `hiked`
- `min_length`
- `max_length`
- `source`
- `viz_3d`
- `limit`

Output shape:

- `summary`
- `trail_count`
- `total_miles`
- `applied_filters`
- `trails`

Each trail should include the most useful chat-facing fields, not every possible field by default.

#### `search_parks`

Purpose:
Retrieve parks using visit and metadata filters.

Likely inputs:

- `visited`
- `visit_year`
- `visit_month`
- `park_code`
- `state`

Output shape:

- `summary`
- `park_count`
- `visited_count`
- `applied_filters`
- `parks`

#### `search_stats`

Purpose:
Return aggregate trail and park statistics.

Likely inputs:

- `hiked`
- `per_park`

V1 recommendation:
Consider keeping `per_park` out of the first iteration unless it falls out naturally from existing logic. If it is easy to include, keep it aligned with the current project capabilities.

Output shape:

- `summary`
- scalar metrics
- optional grouped breakdowns

#### `search_park_summary`

Purpose:
Return a detailed overview for a specific park.

Likely inputs:

- `park_code`

Output shape:

- `summary`
- `park`
- `trail_stats`
- `source_breakdown`
- `visit_info`

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

This is especially useful if the client chooses to inspect a resource before calling tools.

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

## Data and Logic Reuse Strategy

The MCP server should maximize reuse from the existing codebase.

Preferred order of reuse:

1. existing query/service logic
2. existing Pydantic models, or shared model shapes derived from them
3. existing normalization and validation helpers where transport-neutral

If some logic currently lives too close to FastAPI, factor it into a shared layer rather than duplicating it in the MCP server.

## V1 Implementation Notes

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

Use a local MCP transport suitable for desktop/local client integration.

For v1, favor the simplest transport supported by the chosen MCP framework and by the intended ChatGPT local integration path.

### Framework choice

Choose a Python MCP library/framework that keeps the server implementation small and standards-aligned.

Selection criteria:

- good Python ergonomics
- clear tool/resource primitives
- easy local development
- minimal hidden magic

The spec does not require a framework decision yet, but the implementation should avoid inventing custom protocol handling if a standard library exists.

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

### Milestone 1: Confirm the reusable backend surface

Goals:

- identify the exact existing functions to reuse
- decide whether a small `services/` extraction is needed
- map current FastAPI query capabilities to MCP tools

Deliverables:

- chosen shared-layer entry points
- list of any refactors needed before MCP code is added

### Milestone 2: Define MCP tool and resource schemas

Goals:

- finalize v1 tool names, arguments, and return shapes
- finalize resource identifiers and contents
- define answer-oriented summary fields

Deliverables:

- tool contracts
- resource contracts
- examples of expected payloads

### Milestone 3: Implement the MCP server skeleton

Goals:

- add the local MCP server package/module
- register tools and resources
- verify the server starts locally

Deliverables:

- runnable local MCP server
- local startup instructions

### Milestone 4: Wire tools to shared logic

Goals:

- connect each MCP tool to the shared query/service layer
- shape outputs consistently
- keep error handling deterministic and readable

Deliverables:

- working `search_trails`
- working `search_parks`
- working `search_stats`
- working `search_park_summary`

### Milestone 5: Add lightweight resources

Goals:

- implement `dataset_overview`
- implement `park_lookup`
- implement `search_methodology`

Deliverables:

- working resource reads in the MCP client

### Milestone 6: Local client integration

Goals:

- connect the server to the intended local MCP client path for ChatGPT
- verify tool invocation and resource access end to end

Deliverables:

- local integration instructions
- example prompts that exercise the server

### Milestone 7: Testing and polish

Goals:

- add unit tests around tool result shaping
- test failure paths
- verify the assistant can use the tools coherently

Deliverables:

- test coverage for core MCP behaviors
- concise developer documentation

## Acceptance Criteria

The v1 MCP project is successful when:

- the local MCP server starts reliably
- ChatGPT can use the server as a local MCP tool source
- the assistant can retrieve real `nps-hikes` park/trail/stat data through MCP tools
- the assistant can read at least a few grounding resources
- the MCP server reuses existing project logic rather than duplicating the backend
- no local LLM dependency is required for the core MCP workflow

## Recommended Demo Script for Self-Verification

Even if this is not intended as a formal demo project, these checks confirm the workflow is working:

1. Ask for visited parks in a given month.
2. Ask for trails under a given mileage in a state.
3. Ask for a park summary by name and verify the assistant resolves to the correct park code.
4. Ask the assistant to explain the dataset before searching, so it reads `dataset_overview`.
5. Ask a follow-up comparison question that requires multiple tool calls.

## Summary

V1 should be a small, local, standards-aligned MCP server that exposes `nps-hikes` as a grounded research tool for an external assistant.

The key architectural choice is to share backend logic between FastAPI and MCP rather than layering MCP on top of local HTTP. The key product choice is to expose deterministic structured tools plus lightweight resources, not another NLQ layer. This yields the strongest foundation for learning MCP and for expanding the project later.
