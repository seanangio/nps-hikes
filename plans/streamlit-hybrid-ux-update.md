# Streamlit Hybrid Search UX Update

## Status

**Status**: Complete.

**Current repo state (reviewed 2026-07-05)**:

- Streamlit now treats NLQ trail responses from `search_trails` and `search_by_topic` as a real active result set rather than only translating filters.
- NLQ trail results now render directly on both the map and the trail table without requiring manual park selection first.
- The sidebar `Select Park(s)` control is auto-populated from the parks represented in the active NLQ trail result set.
- Topic queries now show a `Topic: ...` chip alongside any applied structured-filter chips.
- Topic-query `generated_answer` content now renders in a collapsible summary panel beneath the chips and above the map.
- Manual sidebar edits and park-marker clicks break away from the NLQ-driven result state cleanly; the generated summary disappears once divergence occurs.
- State-scoped hybrid queries frame the map using the selected/result parks rather than fitting to trail geometries.
- Zero-result semantic queries leave the current browseable map state intact and use unified trail-table empty-state messaging.
- The app does not auto-set park `Visit Status` from trail-level `hiked=true`.
- The remaining gap is verification depth rather than implementation scope: compile checks passed, but automated tests were not rerun in this environment because `pytest` is not installed here.

## Files implemented

| File | Change |
|------|--------|
| `api/main.py` | `/query` now returns geometry-ready `search_trails` results and preserves the semantic topic in `interpreted_as` for topic queries |
| `streamlit_app/components/nlq.py` | Added active NLQ trail-result state, park auto-population, divergence detection, topic chip rendering, and collapsible generated summary |
| `streamlit_app/app.py` | Uses active NLQ trail results to drive the map/table while NLQ state remains authoritative, then falls back cleanly to manual browsing |
| `streamlit_app/components/data_table.py` | Unified empty-state messaging for manual and NLQ zero-result flows |
| `tests/test_api.py` | Added regression coverage for the `/query` response shape relied on by the Streamlit UX |

## Purpose

This spec captures the agreed UX behavior for Step 9 of the hybrid search work: integrating semantic + structured trail queries cleanly into the Streamlit app without making the interface feel like a separate product mode.

The goal is to support hybrid queries such as:

- "waterfall hikes I completed over 5 miles in California"
- "short trails in Texas"
- "slot canyons I haven't hiked yet"

while keeping manual browsing and map exploration simple and reliable.

## UX Principles

- Natural language search should feel native to the existing app, not bolted on.
- Sidebar controls should remain structurally separate and visible.
- NLQ should populate visible app state so users can understand and refine what happened.
- Manual filter edits should break away from NLQ mode cleanly.
- The map should always remain browseable, even when semantic search returns no trail results.

## Core Interaction Model

### 1. NLQ drives a real results state

When a natural-language query resolves to `search_by_topic` or `search_trails`, the app should treat the returned trails as a real active result set, not just as interpreted filters.

Expected behavior:

- Returned trails should appear on the map.
- Returned trails should appear in the table.
- The app should not require the user to manually select parks before results can render.

### 2. Park selection auto-populates from NLQ results

When NLQ returns trail results across one or more parks, the sidebar `Select Park(s)` control should auto-populate with the parks represented in the returned result set.

Intent:

- Make the visible UI state match what the app is actually showing.
- Avoid the confusing case where trails are conceptually filtered but park selection appears empty.

Notes:

- This auto-population is a reflection of active results, not a hidden inference.
- Clicking park markers later is still a separate manual selection action.

### 3. Sidebar sections stay separate and visible

The sidebar should keep its current high-level structure:

- park-related controls
- trail-related controls
- NLQ input

The app should not hide or collapse unrelated controls just because an NLQ query is active.

Rationale:

- The interface should remain stable.
- Users should always be able to understand where to browse manually.
- The app should avoid feeling like NLQ creates a temporary alternate UI.

## Chips and Query Context

### 4. Show topic chip when a topic exists

If the interpreted query includes a semantic topic, show it explicitly as a chip.

Examples:

- `Topic: waterfall hikes`
- `Topic: slot canyons`

### 5. Show applied structured filters as chips

For hybrid queries, continue showing applied filters as chips alongside the topic chip.

Examples:

- `Topic: waterfall hikes`
- `State: CA`
- `Hiked: Yes`
- `Min Length: 5 mi`

### 6. Chips are the primary explanation of what NLQ did

The chips should provide the clearest lightweight explanation of the interpreted query.

This should be preferred over trying to repurpose unrelated sidebar widgets as the only explanation.

## Generated Summary

### 7. Show the generated summary in a collapsible panel beneath the chips

If the API returns a `generated_answer` for a topic query, render it in a collapsible UI section placed beneath the chips and above the map.

Desired behavior:

- Visible enough to discover
- Easy to ignore
- Does not dominate the map/table workflow

### 8. Remove the summary when the user diverges from NLQ state

If the user manually changes filters or otherwise breaks away from the interpreted NLQ state, the generated summary should disappear rather than remain as stale explanatory content.

Rationale:

- Prevent the summary from implying it still describes the current visible results.
- Keep divergence behavior simple and unambiguous.

## Divergence Behavior

### 9. Manual edits break away from NLQ mode

If the user changes sidebar filters after an NLQ query, treat that as a transition back into manual browsing rather than as a refinement of the same semantic query.

Expected behavior:

- divergence is detected
- NLQ summary disappears
- active NLQ result framing is no longer treated as authoritative

The UI does not need to preserve a "stale NLQ mode" beyond the existing interpreted-query indicator if that remains useful.

### 10. Simpler handling is acceptable

Where there are two reasonable options for divergence handling, prefer the simpler implementation, provided it is predictable to the user.

This specifically applies to whether any residual NLQ indicator remains after divergence; either behavior is acceptable if the experience is clear.

## Map Behavior

### 11. State-level hybrid queries should frame to the state's parks

For state-scoped hybrid queries, the map should center/zoom based on the parks in that state rather than the returned trail geometries.

This preserves the current browsing mental model and keeps state queries visually oriented around park geography.

### 12. Zero-result semantic queries should leave the map alone

If a semantic query returns no trail results, the map should stay unchanged or revert to the default browsing state.

The map should not switch into a confusing "empty result" visual mode.

This allows the user to keep browsing even when the semantic layer did not find matching trails.

### 13. Park marker clicks remain manual actions

Clicking a park marker during or after an NLQ result should be treated as a separate manual browsing action, not as an implicit refinement of the semantic query.

## Sidebar Control Semantics

### 14. Do not auto-set park visit status from `hiked=true`

Even though "if I hiked a trail, then I visited that park" is logically true, the app should not automatically set `Visit Status` to `Visited Only` when NLQ interprets a trail query as `hiked=true`.

Rationale:

- `Visit Status` is a park-level filter, not a trail-level filter.
- Auto-setting it may create surprising side effects in the visible park list.
- Simpler and safer behavior is to leave that control unchanged.

## Empty-State Messaging

### 15. Use unified empty-state language

The trail-table empty state should work for both:

- manual browsing with no selected parks
- NLQ flows that currently yield no visible trails

The app should avoid messages that incorrectly instruct the user to "Select one or more parks" when an NLQ search is active or was just run.

## Recommended Implementation Direction

This spec implies a Streamlit flow where:

1. NLQ response data can directly drive the active trail result set.
2. The returned parks are mirrored into sidebar park selection.
3. Chips explain topic + applied filters.
4. A collapsible generated summary appears only while the NLQ interpretation is still active.
5. Manual user changes cleanly return the app to standard browsing behavior.

## Non-Goals

- Do not redesign the sidebar into a new mode-specific layout.
- Do not hide controls based on NLQ interpretation.
- Do not make park-marker clicks alter semantic query meaning.
- Do not auto-set `Visit Status` from trail-level `hiked=true`.

## Open Implementation Choice

One implementation detail remains intentionally flexible:

- After divergence, the app may either fully clear NLQ context or keep a lightweight interpreted-query indicator, as long as the summary disappears and the experience is clearly manual again.

## Outcome

This implementation chose the simpler allowed divergence path:

- After divergence, the app keeps a lightweight interpreted-query indicator/chip row.
- The NLQ-generated summary is removed immediately.
- The active map/table result source falls back to ordinary manual browsing behavior.
