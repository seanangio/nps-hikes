# NPS Hikes MCP V3 Plan

## Overview

This plan defines the agreed next phase for the local `nps-hikes` MCP server after v1 proved the local `stdio` server and v2 stabilized the MCP contract across clients.

The main goal of v3 is not to deploy the MCP server publicly or to chase a ChatGPT integration prematurely. The main goal is to understand the second major MCP transport shape by adding a local-only HTTP transport path while keeping the same grounded MCP surface.

Recommended v3 theme:

`prove that the same local MCP server can run cleanly as an already-running HTTP service, not just as a subprocess launched over stdio`

## Current Status

As of July 22, 2026:

- v1 is complete for the local `stdio` server.
- v2 is complete for:
  - cross-client validation in `MCP Inspector` and `Claude Desktop`
  - MCP contract cleanup around shared `TOOL_DEFINITIONS` and `RESOURCE_DEFINITIONS`
- The current MCP surface includes four tools:
  - `search_trails`
  - `search_parks`
  - `search_stats`
  - `search_park_summary`
- The current MCP surface includes three resources:
  - `dataset_overview`
  - `park_lookup`
  - `search_methodology`
- The current implementation is still centered on local `stdio`.
- The current project does not yet validate the MCP server as a local HTTP service.

## V3 Goals

- Learn the MCP `Streamable HTTP` transport in a concrete local project.
- Keep the current tools and resources unchanged while adding a second transport path.
- Make transport concerns more explicit without pushing the project into paid hosting or multi-user infrastructure.
- Verify that the MCP layer remains client-neutral when the transport changes.

## Non-Goals for V3

- Public hosting or internet-facing deployment.
- Building a tunnel or bridge specifically for ChatGPT.
- Multi-user auth, production hardening, or operations-heavy infrastructure.
- A broad expansion of the MCP surface.
- Replacing the current `stdio` workflow.
- Rewriting the MCP server to call the FastAPI app over local HTTP.

## Recommended V3 Scope

The agreed v3 scope has three required parts, in this order:

1. Local HTTP transport architecture
2. Local HTTP validation
3. Documentation and conceptual cleanup

This order matters. The point of v3 is to isolate the transport lesson while keeping the tool/resource contract stable.

## Part 1: Local HTTP Transport Architecture

### Goal

Add a local `Streamable HTTP` transport path for the existing MCP server while preserving the current `stdio` path.

### Why this is the right v3 focus

The current server already proves:

- how MCP tools and resources work
- how a subprocess-style transport works
- how the MCP contract behaves across two local clients

But it does not yet prove:

- how the same server behaves when it runs as an already-running service
- how startup and configuration differ when the client no longer launches the server
- how to think about `localhost`, ports, and MCP endpoint URLs in the context of this project

That makes local HTTP a real architectural step rather than a cosmetic transport swap.

### Recommended direction

Keep one MCP capability layer and add transport-specific startup paths around it.

Possible direction:

- keep a shared app-construction path for tools and resources
- preserve the current `stdio` entrypoint for existing workflows
- add a local HTTP entrypoint that serves the same MCP app on a local endpoint such as `/mcp`
- bind locally to `127.0.0.1` / `localhost` by default

### Suggested acceptance criteria

- The server can still run successfully over `stdio`.
- The same tools and resources are exposed over local HTTP.
- The local HTTP server can be started independently of the client.
- The HTTP binding is local-only by default.
- Transport-specific setup is isolated from the MCP tool/resource contract as much as practical.

## Part 2: Local HTTP Validation

### Goal

Validate that the local HTTP transport works end to end with a real MCP client.

### Recommended validation client

`MCP Inspector` should be the primary v3 validation client again.

Why:

- it already fits the project’s verification style
- it supports `streamable-http`
- it lets the transport change while keeping the validation client constant

That means the v3 question becomes:

`can Inspector connect to the same server surface by URL instead of by launching the process itself?`

### Recommended deliverable

Document one successful local HTTP workflow, including:

- how to start the server in HTTP mode
- the local MCP endpoint URL
- how to configure `MCP Inspector` for `streamable-http`
- what tools and resources are discoverable
- one or two representative tool calls

### Suggested acceptance criteria

- `MCP Inspector` connects successfully to the local HTTP endpoint.
- `tools/list` shows all current tools.
- `resources/list` shows all current resources.
- At least one call succeeds for:
  - `search_trails`
  - `search_stats`
  - `search_park_summary`
- Empty-result and validation-error behavior remains sensible over HTTP.
- The server can be stopped and restarted independently of the client.

## Part 3: Documentation and Conceptual Cleanup

### Goal

Capture the transport model clearly so future work does not blur:

- MCP protocol vs transport
- `stdio` vs local HTTP
- local HTTP vs remote/public deployment

### Why this matters

This phase surfaced a real conceptual gap that is easy to carry forward incorrectly:

- `stdio` can make MCP feel like “a helper process a client launches”
- local HTTP makes it clearer that an MCP server can also be “a local service a client connects to”

Documenting that distinction is part of the value of the phase.

### Recommended deliverables

- update `docs/mcp.md` with a local HTTP run/test path
- add a v3 implementation note or walkthrough if transport-specific details deserve their own note
- add a conceptual note that captures the project’s MCP vocabulary and architecture lessons

### Suggested acceptance criteria

- The docs explain the difference between `stdio` and local HTTP in project-specific terms.
- The docs make clear that local HTTP is still local and does not require paid hosting.
- The docs make clear that local HTTP is not equivalent to ChatGPT integration.
- The local HTTP setup instructions match the real verification flow.

## Recommended Work Sequence

### Phase 1: App Construction Review

- Identify the current MCP app-construction path in `server.py`.
- Separate transport-neutral registration from transport-specific startup where needed.
- Keep the public MCP contract unchanged.

### Phase 2: HTTP Transport Implementation

- Add a local `Streamable HTTP` startup mode or entrypoint.
- Choose a local default host and port.
- Expose one MCP endpoint path.
- Keep `stdio` support intact.

### Phase 3: Validation

- Start the server locally in HTTP mode.
- Connect with `MCP Inspector` using `streamable-http`.
- Re-run the core tool/resource checks.
- Confirm behavior matches the existing MCP surface.

### Phase 4: Documentation

- Update `docs/mcp.md` with local HTTP guidance.
- Record any Inspector-specific HTTP setup quirks.
- Capture conceptual transport notes for future reference.

## Suggested Deliverables

By the end of v3, the repo should ideally have:

- a local HTTP MCP startup path in addition to the existing `stdio` path
- updated docs for running and testing the server over local HTTP
- end-to-end verification notes for the local HTTP transport
- a concise conceptual note about MCP client/server roles, tools/resources, and transports

## Verification Checklist for V3

The following should be true before calling v3 complete:

- The same MCP surface works over both `stdio` and local HTTP.
- `MCP Inspector` can connect successfully to the local HTTP endpoint.
- Existing tools and resources remain discoverable and usable.
- The server stays local-only and does not require paid hosting.
- The documentation matches the real local HTTP workflow.

## Locked Scope Decisions

The following decisions are now locked for v3:

- V3 should remain local-only.
- V3 should focus on `Streamable HTTP`, not public deployment.
- `stdio` should remain supported.
- The current tool/resource surface should remain stable unless a transport-related issue forces a small change.
- The MCP server should continue to call shared backend logic directly rather than routing through FastAPI.
- `MCP Inspector` is the primary v3 validation client because it keeps the transport experiment client-neutral.
- ChatGPT integration is explicitly out of scope for v3.

## Why Local HTTP Still Matters Without ChatGPT

As of July 22, 2026, moving to local HTTP does not by itself unlock a practical ChatGPT integration path for this project.

That is acceptable because the value of v3 is different:

- it teaches the second major MCP transport shape
- it proves the server can run as a service instead of only as a subprocess
- it clarifies the difference between protocol and transport
- it reduces the conceptual jump to any future tunnel, remote bridge, or hosted path

So the main payoff of v3 is architectural understanding, not immediate product reach.

## Possible V4: Remote HTTP Experiment

If a later phase explores remote MCP hosting, treat it as a separate v4 experiment rather than part of v3.

As of July 22, 2026, there are free or near-free hosting options, but they add a different category of work than the local HTTP lesson:

- public endpoint and TLS
- auth and origin validation
- SSE / streaming behavior through proxies
- cold starts, uptime quirks, and free-tier limits
- possible runtime changes depending on the host

Two realistic options to revisit later are:

- `Render`, which still offers free web services and is the most natural fit for a Python/ASGI deployment, but free services spin down after idle time and can wake slowly
- `Cloudflare Workers`, which has a real free plan, but pushes the project toward a different runtime and deployment model than the current local Python MCP server

The recommended sequencing is:

1. finish local `Streamable HTTP` in v3
2. confirm the transport and docs feel clean locally
3. only then decide whether a hosted remote MCP path is worth a dedicated v4

If v4 happens, `Render` is the simplest first remote experiment because it is closer to the current project shape, even if its free-tier behavior may be imperfect for a polished always-on MCP experience.

## Final V3 Recommendation

The v3 execution path is:

1. Keep the current MCP surface stable.
2. Preserve the working `stdio` path.
3. Add a second local-only `Streamable HTTP` path.
4. Validate it in `MCP Inspector`.
5. Update docs so the local vs subprocess distinction is clear and reusable for future work.
