# NPS Hikes MCP V2 Plan

## Overview

This plan defines the agreed next phase for the local `nps-hikes` MCP server now that v1 is complete and verified in `MCP Inspector`.

The main goal of v2 is not to make the server bigger as quickly as possible. The main goal is to make the MCP surface more durable, more portable across clients, and better positioned for a small, low-risk MCP surface improvement.

Recommended v2 theme:

`stabilize the MCP contract and validate it in a second client before deciding whether any further MCP surface expansion is needed`

## Current Status

As of July 22, 2026:

- v1 is complete for the local `stdio` server.
- The server has been validated in `MCP Inspector`.
- The server has also been validated in `Claude Desktop` for tool execution.
- The current MCP surface includes four tools:
  - `search_trails`
  - `search_parks`
  - `search_stats`
  - `search_park_summary`
- The current MCP surface includes three resources:
  - `dataset_overview`
  - `park_lookup`
  - `search_methodology`
- MCP contract duplication has been reduced materially:
  - tools now register from shared `TOOL_DEFINITIONS`
  - resources now register from shared `RESOURCE_DEFINITIONS`
  - drift is protected by unit tests
- `docs/mcp.md` and `plans/mcp-walkthrough.md` have been updated with the observed Claude Desktop behavior.

## V2 Goals

- Prove the server works well outside `MCP Inspector`.
- Reduce MCP contract drift risk before expanding the surface area.
- Keep the server deterministic, grounded, and easy to debug.

## Non-Goals for V2

- Public hosting or multi-user deployment.
- Turning the MCP server into a natural-language answer generator.
- Large visualization payloads by default.
- A broad grab-bag of new tools added all at once.
- Replacing the existing FastAPI or Streamlit workflows.

## Recommended V2 Scope

The agreed v2 scope has two required parts and one optional follow-on, in this order:

1. Cross-client validation
2. MCP contract cleanup
3. Optional small MCP surface expansion

This order matters. It keeps the next version from growing on top of avoidable structural drift.

## Part 1: Cross-Client Validation

### Goal

Validate that the local server behaves well in at least one second MCP client beyond `MCP Inspector`.

### Why this should come first

Right now, v1 proves:

- the protocol surface works in a protocol-native testing client
- the core tools/resources are discoverable
- the current docs match the Inspector workflow

But it does not yet prove:

- tool descriptions are equally usable in a chat-oriented client
- argument shapes are handled consistently across clients
- resource URIs and tool summaries are ergonomic outside Inspector

### Recommended deliverable

Document one successful second-client workflow, including:

- how the client launches or connects to the local `stdio` server
- what tools/resources it discovers
- any client-specific argument-entry or schema quirks
- one or two representative end-to-end queries

### Suggested acceptance criteria

- The second client connects successfully to the local server.
- All current tools are discoverable.
- All current resources are discoverable or otherwise accessible in the client’s MCP UX.
- At least one tool call succeeds for each major tool shape:
  - list/search tool
  - stats tool
  - single-entity summary tool
- Any client-specific quirks are captured in docs.

## Part 2: MCP Contract Cleanup

### Goal

Refactor the MCP layer so tool and resource contracts are defined in fewer places and are less likely to drift.

### Why this should happen before adding new features

The current walkthrough correctly identifies the main maintainability risk:

- tool signatures, metadata, and registration are split across multiple files
- resource definitions and registration follow a similar pattern

This is acceptable in v1, but it becomes more expensive as soon as v2 adds:

- another tool
- another resource
- client-specific validation work
- more tests for schema shape and discoverability

### Recommended direction

Move toward a single-definition pattern for both tools and resources.

For tools, one structured definition should ideally drive:

- public name
- description
- callable wrapper
- registration

For resources, one structured definition should ideally drive:

- URI
- name
- description
- MIME type
- reader function
- registration

### Suggested implementation shape

Possible direction:

- introduce a small spec object or typed dictionary for tools
- introduce a matching spec object or typed dictionary for resources
- update `server.py` to register from those specs instead of repeating names/descriptions by hand

This does not need to become an abstraction-heavy framework. The goal is modest:

- fewer repeated literals
- fewer contract details to keep in sync manually
- easier addition of v2 features

### Suggested acceptance criteria

- Each MCP tool has one primary source of truth for its public contract.
- Each MCP resource has one primary source of truth for its public contract.
- Registration logic in `server.py` becomes thinner and more generic.
- Existing tests continue to pass.
- At least one test explicitly protects against metadata/registration drift.

## Part 3: Optional Small MCP Surface Expansion

### Goal

Only add one small MCP surface improvement in v2 if it still looks clearly useful after cleanup and cross-client validation.

### Previous v2 candidate

An earlier v2 candidate was:

- `park_summary/{park_code}` as a resource

### Why this candidate was dropped

- It blurred the conceptual boundary between MCP tools and resources more than expected.
- The existing `search_park_summary` tool already provides a clear park-level access path.
- The current resource set works better as stable background/reference context than as dynamic per-entity summaries.

### Current v2 decision

For now, v2 does not require a new tool or resource beyond the cleaned-up v1 MCP surface.

If a later small MCP addition is proposed, it should only be added if it solves a clear problem and fits the tool/resource distinction more naturally.

## Recommended Work Sequence

### Phase 1: Validation

- Choose and connect one second MCP client.
- Record the setup and observed behavior.
- Capture any schema or argument quirks.

### Phase 2: Cleanup

- Refactor MCP definitions to reduce duplication.
- Keep behavior unchanged while the contract shape is cleaned up.
- Add or tighten tests around discoverability and registration.

### Phase 3: Expansion

- Reassess whether any MCP surface expansion is still necessary.
- If yes, choose a clearly justified small addition.
- If no, treat cleanup plus cross-client validation as sufficient for v2.
- Update docs after behavior is confirmed in real client flows.

### Phase 4: V2 Verification

- Re-run the full Inspector flow.
- Re-run the second-client flow.
- Verify docs against the actual client behavior.

## Suggested Deliverables

By the end of v2, the repo should ideally have:

- one new v2 implementation note or walkthrough
- updated `docs/mcp.md` with second-client guidance or compatibility notes
- tightened MCP tests around registration and public contract shape
- end-to-end verification notes for the cleaned-up MCP surface

## Verification Checklist for V2

The following should be true before calling v2 complete:

- A second MCP client has been tested successfully.
- Existing v1 tools and resources still work after the cleanup refactor.
- Contract duplication has been reduced materially.
- `docs/mcp.md` and any new plan/walkthrough docs match real local usage.

## Locked Scope Decisions

The following decisions are now locked for v2:

- Learning MCP matters more than showing off a larger feature surface.
- Architecture cleanup should take priority over capability expansion.
- V2 should remain structured-first and avoid adding `search_by_topic` for now.
- V2 should stay on local `stdio`.
- The overall posture should remain as client-neutral as practical.
- `Claude Desktop` is the chosen second validation client because it can connect to local MCP servers without forcing a transport change.
- V2 should aim for one client-neutral validation pass rather than a polished client-specific product workflow.
- Cleanup and cross-client validation are sufficient for v2 unless a clearly better small MCP addition emerges.

## Client Constraint

As of July 21, 2026, these client choices are not equivalent for a local `stdio` server:

- `MCP Inspector` already fits the current local `stdio` workflow.
- `Claude Desktop` supports local MCP servers directly.
- `ChatGPT` does not connect directly to a local MCP server; it connects to remote MCP servers, and a local/private server would need an additional bridge such as a secure tunnel.

That means:

- if the goal is to stay local and keep learning focused on MCP itself, `Claude Desktop` is the best second-client choice
- if the goal is specifically to integrate with `ChatGPT`, that becomes a separate follow-on project because it changes the connection model

## Final V2 Recommendation

The v2 execution path is:

1. Keep the server local and `stdio`-based.
2. Prioritize MCP contract cleanup and registration cleanup.
3. Stay client-neutral in the design and docs.
4. Validate the cleaned-up server in `Claude Desktop` as the second client.
5. Only add another MCP surface element if a clearly useful and conceptually clean candidate emerges.
6. Treat `ChatGPT` integration as an optional later phase if you decide you want to learn remote MCP app deployment and tunneling.

This path is the best balance of:

- learning value
- architectural cleanliness
- low-risk MCP surface growth
- manageable scope

## Revised V2 Success Criteria

V2 should be considered complete when:

- the MCP contract is materially less duplicated
- the current tools/resources still work in `MCP Inspector`
- the server is validated in one additional client that supports the existing local model
- the docs clearly distinguish local-client support from remote-client follow-on options

## Implementation Checklist

This section translates the agreed v2 direction into a concrete execution sequence.

### Phase 1: Audit the current MCP contract

- [x] Inventory every place each tool’s public contract is currently defined.
- [x] Inventory every place each resource’s public contract is currently defined.
- [x] Identify repeated literals and hand-maintained mappings across:
  - `nps_hikes_mcp/tools.py`
  - `nps_hikes_mcp/resources.py`
  - `nps_hikes_mcp/server.py`
- [x] Decide the smallest viable shared spec shape for tools and resources.

### Phase 2: Refactor tool definitions

- [x] Create one primary definition object per tool.
- [x] Ensure each tool definition includes at least:
  - public name
  - description
  - callable wrapper or callable reference
- [x] Update server registration to derive tool registration from those definitions.
- [x] Remove repeated hand-written tool metadata where practical.
- [x] Keep runtime behavior unchanged during this phase.

### Phase 3: Refactor resource definitions

- [x] Create one primary definition object per resource.
- [x] Ensure each resource definition includes at least:
  - URI
  - name
  - description
  - MIME type
  - reader function
- [x] Update server registration to derive resource registration from those definitions.
- [x] Remove repeated hand-written resource metadata where practical.
- [x] Keep resource payload behavior unchanged during this phase.

### Phase 4: Strengthen tests around public contract shape

- [x] Add or update tests that assert expected tool discoverability metadata.
- [x] Add or update tests that assert expected resource discoverability metadata.
- [x] Add at least one test that would fail if names/descriptions/registration drift apart again.
- [x] Re-run existing MCP wrapper tests after the refactor.

### Phase 5: Validate in `MCP Inspector`

- [x] Re-run the current v1 verification flow after the cleanup.
- [x] Confirm all existing tools still execute successfully.
- [x] Confirm all existing resources still read successfully.
- [x] Note any schema or discoverability changes introduced by the refactor.

### Phase 6: Validate in `Claude Desktop`

- [x] Add the local `nps-hikes` MCP server to `Claude Desktop`.
- [x] Verify the client can launch the local `stdio` server successfully.
- [x] Confirm tool discovery works.
- [x] Confirm resource discovery or access works as expected in the client UX.
- [x] Run representative checks for:
  - `search_trails`
  - `search_stats`
  - `search_park_summary`
- [x] Record any Claude-specific quirks, limitations, or UX differences.

### Phase 7: Documentation update

- [x] Update `docs/mcp.md` with second-client guidance for `Claude Desktop`.
- [x] Keep `MCP Inspector` as the primary protocol-debugging workflow.
- [x] Clearly explain that `Claude Desktop` is a validated local client option.
- [x] Clearly explain that `ChatGPT` is a separate follow-on integration because it does not directly consume the same local `stdio` workflow.
- [x] Update `plans/mcp-walkthrough.md` if the cleanup materially changes code organization.

## Remaining Work To Finish V2

At this point, the implementation work is effectively complete. The remaining work is release/closure work:

- [x] Decide whether to call v2 complete with the current scope.
- [x] Optionally run the broader project test suite again, not just `tests/unit/test_mcp_tools.py`, if you want a stronger pre-merge signal.
- [ ] Review the docs wording once more for tone and clarity before merging.
- [x] Optionally update this plan again with a short final completion note after merge or release.

## Final Completion Note

V2 is complete as of July 22, 2026.

Completed outcomes:

- the MCP contract was cleaned up so tools and resources register from shared definitions
- registration drift is protected by unit tests
- the cleaned-up server was re-verified in `MCP Inspector`
- the local `stdio` server was validated in `Claude Desktop` as a second client for tool execution
- docs were updated to capture the observed client behavior and the current local-client guidance

Notable v2 conclusion:

- no additional MCP surface expansion was added
- `park_summary/{park_code}` was intentionally dropped as a v2 candidate because it blurred the tool/resource boundary more than it helped
- `MCP Inspector` remains the best client for resource-focused protocol debugging
- `Claude Desktop` is a validated client for conversational tool use, but did not expose MCP resources to the model in the same direct way during this validation pass

## Task Breakdown

The recommended task order inside the repo is:

1. Refactor tool definitions first.
2. Refactor resource definitions second.
3. Add contract-shape tests.
4. Re-run local verification in `MCP Inspector`.
5. Validate in `Claude Desktop`.
6. Reassess whether any small MCP surface expansion is still warranted.
7. Update docs last, based on the real observed workflow.

Current status:

1. Done
2. Done
3. Done
4. Done
5. Done
6. Decided no further expansion is needed for v2
7. Done

## Suggested First PR Scope

To keep v2 learning-focused and low-risk, the first implementation slice should be:

- no new tools
- no transport changes
- MCP contract cleanup plus test tightening

That gives you a clean checkpoint without broadening the MCP surface unnecessarily.
