# NPS Hikes MCP V4 Plan

## Overview

This plan defines the agreed next phase for the local `nps-hikes` MCP server after v3 added and validated both local `stdio` and local `Streamable HTTP` transports.

The main goal of v4 is to expand the MCP surface in a meaningful way by adding the first semantic MCP tool:

`search_by_topic`

This phase should promote an already-working semantic trail-search capability into the MCP layer while preserving the MCP server's current design principles:

- local-first
- deterministic
- non-generative
- grounded in shared backend query logic

Recommended v4 theme:

`add semantic trail discovery to the MCP surface without turning the MCP server into a prose-generation layer`

## Current Status

As of July 23, 2026:

- v1 is complete for the local `stdio` server.
- v2 is complete for MCP contract cleanup and cross-client validation.
- v3 is complete for local `Streamable HTTP` transport support and validation.
- The current MCP surface includes four tools:
  - `search_trails`
  - `search_parks`
  - `search_stats`
  - `search_park_summary`
- The current MCP surface includes three resources:
  - `dataset_overview`
  - `park_lookup`
  - `search_methodology`
- The broader project already includes a semantic and hybrid trail-search backend:
  - `fetch_topic_trails()` exists in the shared query layer
  - the API/NLQ surface already uses `search_by_topic`
- The current MCP layer does not yet expose topic-based semantic trail search.

## V4 Goals

- Add `search_by_topic` as a first-class MCP tool.
- Reuse the existing semantic/hybrid backend instead of building a new search path.
- Keep the MCP tool deterministic and non-generative.
- Return structured trail results plus compact semantic context.
- Surface fallback semantic matches when no trails resolve.
- Align the MCP-facing topic-search contract with the existing API/NLQ contract where practical.
- Document the new semantic-search prerequisites clearly for local MCP users.

## Non-Goals for V4

- Adding generative answer synthesis to the MCP server.
- Replacing the existing API/NLQ semantic-search flow.
- Expanding into public hosting or ChatGPT deployment work.
- Introducing geometry-heavy MCP responses for semantic search.
- Broad MCP resource expansion unrelated to `search_by_topic`.
- Reworking the whole MCP tool suite unless consistency cleanup directly supports `search_by_topic`.

## Recommended V4 Scope

The agreed v4 scope has five required parts, in this order:

1. MCP tool contract design for `search_by_topic`
2. MCP wrapper implementation and error handling
3. Cross-surface consistency review
4. MCP resource and documentation updates
5. Validation

This order matters. The contract should be locked before implementation, and the implementation should be checked against the broader API/NLQ surface before the docs are finalized.

## Part 1: MCP Tool Contract Design

### Goal

Define the public MCP-facing contract for `search_by_topic` so it behaves like a real MCP tool rather than a thin accidental copy of the API response.

### Locked contract decisions

`search_by_topic` should:

- remain non-generative
- include `fallback_chunks` when no trails resolve
- include trimmed `topic_context`
- omit full `chunk_text`
- omit geometry from trail results
- support the same hybrid filter set already supported by the API/NLQ topic-search path

### Recommended input shape

The MCP tool should accept:

- `query`
- `park_code`
- `state`
- `hiked`
- `min_length`
- `max_length`
- `source`
- `limit`

### Recommended limit behavior

To resolve the current mismatch between the broader MCP trail tool and the API semantic topic-search path:

- `search_by_topic` should default to `20`
- `search_by_topic` should cap `limit` at `50`

This keeps semantic-topic queries intentionally smaller than fully structured `search_trails` queries and aligns better with the current API/NLQ contract.

### Recommended output shape

The MCP result should include:

- `summary`
- `trail_count`
- `total_miles`
- `applied_filters`
- `trails`
- `topic_context`
- `fallback_chunks`

### Recommended trail shape

Each trail should remain compact and MCP-friendly, similar to the current `search_trails` result shape:

- `trail_id`
- `trail_name`
- `park_code`
- `park_name`
- `states`
- `source`
- `length_miles`
- `hiked`
- `viz_3d_available`
- `viz_3d_slug`

### Recommended topic-context shape

Each topic-context item should be trimmed to:

- `trail_id`
- `trail_name`
- `park_code`
- `park_name`
- `content_title`
- `chunk_text_preview`

### Recommended fallback-chunk shape

Fallback chunks should remain structured and non-generative, carrying the semantic context that failed to resolve to trails:

- `title`
- `chunk_text`
- `park_code`
- `park_name`
- `source_type`
- `similarity_score`

### Suggested acceptance criteria

- `search_by_topic` appears in `tools/list`.
- The input schema reflects the agreed hybrid filter set.
- The tool enforces the agreed `limit` semantics.
- Successful topic queries return compact trail results.
- Successful topic queries include trimmed `topic_context`.
- Zero-trail topic queries return structured `fallback_chunks`.
- No prose generation is added to the MCP layer.

## Part 2: MCP Wrapper Implementation And Error Handling

### Goal

Add the MCP-facing wrapper around the existing semantic query path while preserving the MCP server's current predictable behavior.

### Recommended direction

Follow the same design pattern as the existing MCP tool wrappers:

- validate inputs in `nps_hikes_mcp.tools`
- call shared backend logic
- wrap operational failures in MCP-specific errors
- reshape results into MCP-friendly compact payloads

### Semantic dependencies that should be made explicit

Unlike the current MCP tools, `search_by_topic` depends on more than the structured trail tables. It also depends on:

- embedding generation succeeding for the query text
- semantic embeddings existing in the local database
- `content_trail_mapping` being populated
- the semantic indexing pipeline having already been run locally

These are not optional conceptual details. They are real runtime prerequisites for the tool.

### Recommended embedding flow

The MCP wrapper should:

1. validate the public parameters
2. request an embedding for `query`
3. fail cleanly if embedding generation fails or returns no usable vector
4. call `fetch_topic_trails()`
5. reshape the response into the locked MCP output shape

### Recommended error-handling behavior

The wrapper should surface clear MCP errors for:

- empty or invalid `query`
- invalid `park_code`
- invalid `state`
- invalid `source`
- invalid `limit`
- invalid length range
- embedding-generation failures
- shared query-layer operational failures

Recommended principle:

`semantic-search failures should read like actionable runtime errors, not like mysterious MCP or transport failures`

### Suggested acceptance criteria

- Embedding-generation failure produces a clear MCP tool error.
- Query-layer failures are wrapped consistently with existing MCP tools.
- Input validation mirrors the existing MCP validation style.
- The implementation stays non-generative and transport-neutral.

## Part 3: Cross-Surface Consistency Review

### Goal

Use the v4 addition to reduce avoidable drift between:

- MCP tool definitions
- API semantic-search behavior
- NLQ tool definitions and guidance

### Why this matters

`search_by_topic` already exists conceptually in the broader project. Adding it to MCP creates a good opportunity to make sure the public contract does not quietly diverge across surfaces.

### Recommended review areas

- parameter names
- supported filter set
- default `limit`
- maximum `limit`
- summary semantics
- fallback behavior
- compact versus verbose context fields
- descriptive text in docs and tool descriptions

### Important boundary

The goal is not to force every surface to return identical payloads. The goal is to ensure that the same conceptual tool means roughly the same thing everywhere, with surface-specific shaping only where justified.

### Suggested acceptance criteria

- The MCP contract does not conflict with the API/NLQ topic-search contract.
- The `limit` mismatch is intentionally resolved and documented.
- Any remaining differences across surfaces are deliberate and explained.

## Part 4: MCP Resources And Documentation Updates

### Goal

Update the existing MCP-facing docs and resources so the new semantic tool is understandable and usable in local workflows.

### Resources to update

The existing resources should be updated rather than expanded with a new semantic-specific resource:

- `dataset_overview`
- `search_methodology`

### Recommended resource updates

`dataset_overview` should explain that the MCP surface now includes both:

- structured filters over parks and trails
- topic-based semantic trail discovery

`search_methodology` should explain:

- semantic search uses locally generated embeddings
- semantic hits are resolved to trails through `content_trail_mapping`
- topic results remain deterministic tool outputs
- fallback semantic chunks may appear when semantic matches do not resolve to trail records

### Documentation updates

`docs/mcp.md` should be updated to cover:

- the new `search_by_topic` tool in the exposed MCP surface
- example Inspector calls for semantic search
- the local runtime prerequisites for semantic search
- how semantic topic search differs from `search_trails`
- what `topic_context` and `fallback_chunks` mean

### Required prerequisites to document clearly

The docs should explicitly say that `search_by_topic` assumes:

- the local embedding/semantic-search stack is configured
- the local database contains semantic embeddings
- `content_trail_mapping` has been generated
- the relevant indexing/linking pipeline has already been run

### Suggested acceptance criteria

- Existing MCP resources reflect the new semantic capability.
- `docs/mcp.md` documents the new tool and its prerequisites.
- The docs keep the MCP layer clearly non-generative.
- The docs explain the difference between structured filters and topic search in project-specific terms.

## Part 5: Validation

### Goal

Verify that the new tool works end to end and fits naturally into the existing MCP validation workflow.

### Recommended validation layers

1. Unit tests for the MCP wrapper
2. MCP app-construction tests
3. Local manual validation with `MCP Inspector`
4. Documentation verification against the actual workflow

### Recommended unit-test coverage

Add or extend tests for:

- successful topic result shaping
- inclusion of trimmed `topic_context`
- fallback behavior when no trails resolve
- invalid input validation
- `limit` validation
- embedding-generation failure
- wrapped backend operational errors
- presence of the tool in shared `TOOL_DEFINITIONS`

### Recommended manual validation in Inspector

Validate at least these flows:

1. `tools/list` shows `search_by_topic`
2. a successful semantic topic query returns compact trail results
3. a hybrid semantic query with filters works as expected
4. a no-trail semantic query returns `fallback_chunks`
5. an embedding-related failure surfaces clearly if prerequisites are missing

### Suggested first manual calls

- `search_by_topic` with `query="waterfalls"`
- `search_by_topic` with `query="slot canyons", state="UT"`
- `search_by_topic` with `query="scenic viewpoints", hiked=true`
- a query expected not to resolve to trails, to confirm `fallback_chunks`

### Suggested acceptance criteria

- The tool works in local MCP validation flows.
- The docs match the actual Inspector experience.
- The new tool behaves consistently across `stdio` and local HTTP transport modes.

## Recommended Work Sequence

### Phase 1: Contract Lock

- Add the new MCP tool definition.
- Lock input schema, `limit` behavior, and output shape.
- Confirm compact-field decisions in code and tests.

### Phase 2: Wrapper Implementation

- Add a `search_by_topic` MCP wrapper in `nps_hikes_mcp.tools`.
- Reuse shared embedding and semantic-query logic.
- Add MCP-friendly error handling for embedding failures and backend issues.

### Phase 3: Cross-Surface Review

- Compare MCP behavior with API/NLQ `search_by_topic`.
- Resolve mismatched defaults or descriptions where practical.
- Document any justified differences.

### Phase 4: Resource And Doc Updates

- Update MCP resources for the new semantic capability.
- Update `docs/mcp.md`.
- Add semantic-search prerequisites and example calls.

### Phase 5: Validation

- Extend unit tests.
- Re-run MCP server registration tests.
- Validate in `MCP Inspector`.
- Confirm docs against the real flow.

## Suggested Deliverables

By the end of v4, the repo should ideally have:

- a new MCP `search_by_topic` tool
- compact semantic topic-search result shaping in the MCP layer
- clear MCP error handling for embedding-related failures
- updated MCP resources reflecting semantic search
- updated local MCP docs and Inspector examples
- tests covering the new tool contract and failure modes
- a documented cross-surface consistency pass for topic search

## Verification Checklist For V4

The following should be true before calling v4 complete:

- `search_by_topic` is discoverable in the MCP tool list.
- The tool is non-generative.
- The tool supports the agreed hybrid filter set.
- The tool returns compact trails without geometry.
- Successful results include trimmed `topic_context`.
- Empty trail resolutions include `fallback_chunks`.
- The `limit` behavior is intentionally aligned with the API topic-search path.
- Embedding-generation failures produce clean MCP errors.
- Existing MCP resources and docs reflect the new capability and prerequisites.
- Validation succeeds in both `stdio` and local HTTP workflows.

## Locked Scope Decisions

The following decisions are now locked for v4:

- v4 should focus on adding `search_by_topic` to the MCP surface.
- The MCP tool should remain non-generative.
- `fallback_chunks` should be included when no trails resolve.
- `topic_context` should be included in trimmed form.
- Full `chunk_text` should be omitted from MCP `topic_context`.
- Geometry should be omitted from MCP topic-search trail results.
- The tool should support the full current hybrid filter set:
  - `query`
  - `park_code`
  - `state`
  - `hiked`
  - `min_length`
  - `max_length`
  - `source`
  - `limit`
- `search_by_topic` should use API-style limit behavior:
  - default `20`
  - maximum `50`
- Existing MCP resources should be updated instead of adding a new resource.
- v4 should include a broader cross-surface consistency check, not just a narrow MCP-only change.
- Semantic-search prerequisites should be explicitly documented.
- Embedding-generation failures should surface as clean MCP tool errors.

## Why This Is The Right V4

This phase is a better next step than remote deployment because it deepens the MCP server's actual capability surface before adding hosting complexity.

It also fits the current project shape well:

- the semantic backend already exists
- the API/NLQ layer already proves the concept
- the MCP server can now expose a richer, more distinctive tool without abandoning its local-first design

That makes v4 a real product-level improvement to the MCP contract rather than a transport-only or hosting-only experiment.
