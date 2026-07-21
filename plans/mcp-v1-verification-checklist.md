# NPS Hikes MCP V1 Verification Checklist

Use this checklist to decide when the local MCP server is truly "v1 done" rather than only "happy-path working."

This checklist assumes the current default validation client is `MCP Inspector` and the server runs over `stdio`.

## Status

`V1 complete` as of July 21, 2026.

## How to use this checklist

- Treat each item as a concrete verification step.
- Mark an item complete only after the result is observed in Inspector or in the test suite.
- Record any surprises or mismatches with the MCP spec before moving on.

## Section 1: Environment and startup

- [x] The `nps-hikes` virtualenv contains the MCP runtime dependency.
- [x] `python -m nps_hikes_mcp.server` starts successfully.
- [x] `MCP Inspector` can launch the server over `stdio`.
- [x] The local project database is confirmed to be reachable during MCP testing.

## Section 2: Resource discovery and reads

- [x] `resources/list` shows `dataset_overview`.
- [x] `resources/list` shows `park_lookup`.
- [x] `resources/list` shows `search_methodology`.
- [x] Reading `dataset_overview` succeeds.
- [x] Reading `park_lookup` succeeds.
- [x] Reading `search_methodology` succeeds.
- [x] Resource payloads are reviewed for clarity, accuracy, and current wording.

## Section 3: Tool discovery

- [x] `tools/list` shows `search_trails`.
- [x] `tools/list` shows `search_parks`.
- [x] `tools/list` shows `search_stats`.
- [x] `tools/list` shows `search_park_summary`.
- [x] Tool descriptions are reviewed in Inspector for clarity and consistency with the spec.

## Section 4: Happy-path tool calls

- [x] `search_trails` succeeds for at least one known park code.
- [x] `search_parks` succeeds for at least one filter case.
- [x] `search_stats` succeeds with no arguments.
- [x] `search_park_summary` succeeds for at least one known park code.
- [x] Each successful tool response is reviewed for:
  - [x] presence of `summary`
  - [x] correct top-level shape
  - [x] reasonable output size
  - [x] useful field naming

## Section 5: Empty-result behavior

- [x] `search_trails` returns a successful empty result for filters that should match nothing.
- [x] `search_parks` returns a successful empty result for filters that should match nothing.
- [x] `search_stats` is checked for a sensible zero-result response when filters exclude all matching trails.
- [x] Empty results remain structured and do not surface as transport or server errors.

## Section 6: Validation and not-found behavior

- [x] `search_park_summary` with an invalid `park_code` shows the intended not-found behavior.
- [x] `search_trails` rejects an invalid `park_code` format.
- [x] `search_trails` rejects an invalid `state` format.
- [x] `search_parks` rejects an invalid `state` format.
- [x] `search_stats` rejects invalid argument types cleanly.
- [x] Validation failures are readable in Inspector and consistent with the spec.

## Section 7: Multi-step MCP workflow

- [x] Read `park_lookup`, then call `search_park_summary` using a code obtained from that resource.
- [x] Read `dataset_overview`, then call `search_stats`.
- [x] Confirm the tool/resource split feels meaningful rather than redundant.

## Section 8: Test coverage

- [x] MCP tool/resource shaping tests exist.
- [x] Current MCP unit tests pass.
- [x] Add tests for empty-result behavior where missing.
- [x] Add tests for validation failures where missing.
- [x] Add tests for not-found behavior where missing.
- [x] Add tests for operational error handling where missing.

## Section 9: Documentation review

- [x] `docs/mcp.md` explains how to run the local server.
- [x] `docs/mcp.md` explains how to launch Inspector.
- [x] `plans/mcp-walkthrough.md` explains how the implementation works.
- [x] `docs/mcp.md` is reviewed once more against the actual Inspector workflow.
- [x] Any Inspector-specific input quirks are documented if they are likely to confuse future use.

## Section 10: V1 sign-off

V1 is ready to call complete when all of the following are true:

- [x] Startup works reliably.
- [x] All four tools are discoverable and usable.
- [x] All three resources are discoverable and readable.
- [x] Happy-path checks are complete.
- [x] Empty-result behavior is verified.
- [x] Validation and not-found behavior are verified.
- [x] MCP-specific tests are in place for the main behaviors.
- [x] The documentation matches the real local workflow.

## Suggested concrete checks to run next

The main recommended follow-on checks are now optional polish rather than core v1 blockers:

1. Re-run the Inspector flow after any dependency or MCP library upgrade.
2. Add a second MCP client later if you want cross-client confidence.
3. Keep the walkthrough and MCP docs in sync with any future UI or schema changes.

## Current status summary

As of now, the server appears to be:

- started successfully
- connected successfully in `MCP Inspector`
- returning real data for tools and resources
- handling empty results cleanly
- handling validation and not-found behavior cleanly
- covered by MCP-specific unit tests for the current v1 behaviors

That means the local `stdio` MCP server has reached a reasonable v1 sign-off state for this project.
