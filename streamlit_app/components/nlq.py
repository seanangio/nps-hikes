"""
Natural language query (NLQ) component.

Provides a form for submitting natural-language queries to the API's
``POST /query`` endpoint, a chips display for the LLM's interpreted
parameters, and helpers to translate those parameters into GUI widget
state so the sidebar filters stay in sync with the LLM's understanding.

The control flow uses a two-rerun pattern to work around the fact that
``st.spinner`` cannot be shown inside ``on_click`` callbacks and that
widget session-state cannot be modified after a widget has been
instantiated in the current run:

    Rerun 1  user submits the form
             -> ``nlq_pending`` is set to the query string
             -> form submit triggers automatic rerun
    Rerun 2  ``process_pending_nlq_query()`` runs at the top of main()
             -> displays spinner, calls POST /query, translates params
                into widget state keys, explicitly calls st.rerun()
    Rerun 3  widgets pick up their new state values
             -> map/table reflect the LLM interpretation
             -> chips render above the map

On error during rerun 2, the error is stashed in ``nlq_error`` and the
script continues without a rerun so the user sees the error beneath the
form in the sidebar.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from streamlit_app.api.client import APIError, post_nlq_query

# ---------------------------------------------------------------------------
# Session state keys (all namespaced under "nlq_")
# ---------------------------------------------------------------------------

_PENDING_KEY = "nlq_pending"
_LAST_RESPONSE_KEY = "nlq_last_response"
_LAST_PARAMS_KEY = "nlq_last_params"
_LAST_QUERY_KEY = "nlq_last_query"
_LAST_FUNCTION_KEY = "nlq_last_function"
_ERROR_KEY = "nlq_error"

# GUI widget state keys the sidebar uses. Kept here so the translation
# layer has a single source of truth that mirrors sidebar.py.
_W_STATE = "filter_state_select"
_W_VISITED = "filter_visited_radio"
_W_PARKS = "park_multiselect"
_W_TRAIL_NAME = "filter_trail_name_input"
_W_HIKED = "filter_hiked_radio"
_W_LENGTH = "filter_length_slider"
_W_SOURCE = "filter_source_select"
_W_VIZ_3D = "filter_viz_3d_radio"


# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------


def initialize_nlq_state() -> None:
    """Ensure all NLQ session-state keys exist with default values."""
    for key in (
        _PENDING_KEY,
        _LAST_RESPONSE_KEY,
        _LAST_PARAMS_KEY,
        _LAST_QUERY_KEY,
        _LAST_FUNCTION_KEY,
        _ERROR_KEY,
    ):
        if key not in st.session_state:
            st.session_state[key] = None


# ---------------------------------------------------------------------------
# Form rendering (sidebar)
# ---------------------------------------------------------------------------


def render_nlq_form() -> None:
    """Render the NLQ input form at the top of the sidebar.

    The form uses ``st.form`` so pressing Enter in the text input or
    clicking Submit triggers a single rerun. On submit the query is
    stashed in ``nlq_pending`` and the rest of the pipeline runs on
    the next rerun.
    """
    st.sidebar.header("💬 Ask a Question")

    with st.sidebar.form("nlq_form", clear_on_submit=False):
        query = st.text_input(
            "Natural language query",
            key="nlq_input",
            placeholder="e.g. long trails I haven't hiked in Utah",
            label_visibility="collapsed",
            help=(
                "Ask in plain English. Examples:\n"
                "- 'Show me trails in Yosemite'\n"
                "- 'Long hikes in California'\n"
                "- 'How many miles have I hiked?'\n"
                "- 'Tell me about Zion'"
            ),
        )
        submitted = st.form_submit_button("Ask", use_container_width=True)

    if submitted and query and query.strip():
        # Flag the pending query for ``process_pending_nlq_query`` to
        # handle on the next rerun. A form submit only triggers a single
        # rerun, and that rerun has already advanced past the top of
        # main() by the time the sidebar renders — so we must explicitly
        # kick off another rerun now, otherwise the pending flag would
        # sit unprocessed until the user interacted again.
        st.session_state[_PENDING_KEY] = query.strip()
        # Clear any previous error so stale error text doesn't linger
        # next to the spinner on the next run.
        st.session_state[_ERROR_KEY] = None
        st.rerun()

    # Render the last error (if any) beneath the form so the user sees
    # why their previous submission failed.
    error = st.session_state.get(_ERROR_KEY)
    if error:
        st.sidebar.error(error)


# ---------------------------------------------------------------------------
# Pending-query processing (top of main())
# ---------------------------------------------------------------------------


def process_pending_nlq_query(all_parks: list[dict[str, Any]]) -> None:
    """Handle a pending NLQ query, if one was submitted on the previous run.

    This should be called near the top of ``main()`` so that any widget
    state updates it performs take effect before the sidebar widgets
    are instantiated.

    Args:
        all_parks: The list of all parks from the API, used to look up
            the park name for display when the LLM returns a park code.
    """
    pending: str | None = st.session_state.get(_PENDING_KEY)
    if not pending:
        return

    # Always clear the pending flag first so that a failure here
    # doesn't loop (clear on the same run the API call is attempted).
    st.session_state[_PENDING_KEY] = None

    with st.spinner(f'Thinking about: "{pending}"...'):
        try:
            response = post_nlq_query(pending)
        except APIError as e:
            st.session_state[_ERROR_KEY] = _format_nlq_error(e)
            # No rerun — fall through so the sidebar/form render with
            # the error beneath it.
            return

    # Success: stash response details and apply to widgets.
    interpreted = response.get("interpreted_as") or {}
    function_called = response.get("function_called") or ""

    st.session_state[_LAST_RESPONSE_KEY] = response
    st.session_state[_LAST_PARAMS_KEY] = interpreted
    st.session_state[_LAST_QUERY_KEY] = pending
    st.session_state[_LAST_FUNCTION_KEY] = function_called
    st.session_state[_ERROR_KEY] = None

    _apply_params_to_widgets(function_called, interpreted, all_parks)

    # Rerun so the sidebar widgets pick up the new state values before
    # any downstream data fetches run. Without this, the current run
    # would continue with stale widget state.
    st.rerun()


def _format_nlq_error(err: APIError) -> str:
    """Return a user-friendly error string for an NLQ APIError."""
    status = err.status_code
    detail = str(err)

    if status == 503:
        return (
            "Natural language search is unavailable. Is Ollama running? "
            "Try `ollama serve`.\n\n"
            f"Details: {detail}"
        )
    if status == 429:
        return "The LLM is busy — please try again in a moment."
    if status == 422:
        return (
            "Couldn't interpret that query. Try being more specific, "
            f"e.g. 'trails in Yosemite'.\n\nDetails: {detail}"
        )
    if status == 404:
        return detail
    if status is None:
        # Connection error, timeout, etc.
        return f"Could not reach the API: {detail}"
    return f"Query failed ({status}): {detail}"


# ---------------------------------------------------------------------------
# Translate interpreted_as params -> widget state keys
# ---------------------------------------------------------------------------


def _apply_params_to_widgets(
    function_called: str,
    params: dict[str, Any],
    all_parks: list[dict[str, Any]],
) -> None:
    """Write interpreted NLQ params into the corresponding widget state keys.

    Only touches widgets that the current tool actually maps to.
    ``search_stats`` intentionally leaves all widgets alone so the map
    and filters keep reflecting whatever the user was already looking
    at while the stats card is overlaid.

    Args:
        function_called: One of 'search_trails', 'search_parks',
            'search_stats', or 'search_park_summary'.
        params: The cleaned ``interpreted_as`` dict from /query.
        all_parks: Used to validate that a park_code actually exists
            in the current dataset before assigning it to the
            multiselect (otherwise Streamlit would drop it silently).
    """
    if function_called == "search_stats":
        # Pure aggregate query — don't mutate GUI state. The stats card
        # will be rendered separately by ``render_nlq_chips_and_results``.
        return

    if function_called == "search_park_summary":
        _apply_park_summary_params(params, all_parks)
        return

    if function_called == "search_parks":
        _apply_park_filter_params(params)
        return

    # Default / search_trails
    _apply_trail_search_params(params, all_parks)


def _valid_park_codes(all_parks: list[dict[str, Any]]) -> set[str]:
    return {p["park_code"] for p in all_parks if p.get("park_code")}


def _apply_trail_search_params(
    params: dict[str, Any], all_parks: list[dict[str, Any]]
) -> None:
    """Translate ``search_trails`` params into widget state."""
    # Park selection handling first, because it drives whether we also
    # need to relax the state/visited filters so the park is visible
    # in the multiselect options.
    park_code = params.get("park_code")
    if park_code:
        valid = _valid_park_codes(all_parks)
        if park_code in valid:
            st.session_state[_W_PARKS] = [park_code]
            # Relax filters that could hide this park from the multiselect
            # options. If the NLQ ALSO specified a state, honor it below
            # (it will overwrite the reset). Visited filter is always
            # relaxed since the LLM tools don't surface it for trails.
            st.session_state[_W_STATE] = "All States"
            st.session_state[_W_VISITED] = "All Parks"
    elif "state" in params:
        # State-only query: clear any stale park selection that may not
        # be in the new state, so the multiselect doesn't show a park
        # outside the freshly-set state.
        st.session_state[_W_PARKS] = []

    # State
    if "state" in params:
        st.session_state[_W_STATE] = params["state"]

    # Hiked status
    if "hiked" in params:
        st.session_state[_W_HIKED] = (
            "Hiked Only" if params["hiked"] else "Not Yet Hiked"
        )

    # Length slider (clamped to the widget's 0-20 range).
    # If only one bound is provided, the other is set to the widget
    # default rather than the user's stale value, so the filter
    # reflects the NLQ intent cleanly.
    min_len = params.get("min_length")
    max_len = params.get("max_length")
    if min_len is not None or max_len is not None:
        new_min = max(0.0, min(20.0, float(min_len))) if min_len is not None else 0.0
        new_max = max(0.0, min(20.0, float(max_len))) if max_len is not None else 20.0
        if new_min > new_max:
            new_min, new_max = new_max, new_min
        st.session_state[_W_LENGTH] = (new_min, new_max)

    # Source
    source = params.get("source")
    if source in ("TNM", "OSM"):
        st.session_state[_W_SOURCE] = source


def _apply_park_filter_params(params: dict[str, Any]) -> None:
    """Translate ``search_parks`` params into widget state."""
    if "visited" in params:
        st.session_state[_W_VISITED] = (
            "Visited Only" if params["visited"] else "Not Yet Visited"
        )
    # visit_year / visit_month have no widget — they'll still be shown
    # as read-only chips via render_nlq_chips_and_results().


def _apply_park_summary_params(
    params: dict[str, Any], all_parks: list[dict[str, Any]]
) -> None:
    """Translate ``search_park_summary`` params into widget state.

    This is always a single-park lookup, so set the multiselect to
    exactly that park and relax state/visited filters so the park is
    visible in the options list.
    """
    park_code = params.get("park_code")
    if not park_code:
        return
    valid = _valid_park_codes(all_parks)
    if park_code not in valid:
        return
    st.session_state[_W_PARKS] = [park_code]
    st.session_state[_W_STATE] = "All States"
    st.session_state[_W_VISITED] = "All Parks"


# ---------------------------------------------------------------------------
# Chips + results display (above the map)
# ---------------------------------------------------------------------------


def render_nlq_chips_and_results(all_parks: list[dict[str, Any]]) -> None:
    """Render the chips + optional stats card above the map.

    Shows what the LLM interpreted from the user's query. Also detects
    whether the user has since modified any filter from the LLM's
    interpretation, and if so renders a small warning icon with a
    tooltip explaining that the chips are historical.
    """
    params: dict[str, Any] | None = st.session_state.get(_LAST_PARAMS_KEY)
    query: str | None = st.session_state.get(_LAST_QUERY_KEY)
    function_called: str | None = st.session_state.get(_LAST_FUNCTION_KEY)

    if not query or function_called is None:
        return

    chip_texts = _build_chip_texts(function_called, params or {}, all_parks)

    # A query that maps to zero chips (e.g. a bare ``search_stats``
    # with no params) should still show a header so the user sees
    # that the query was processed.
    header_col, icon_col, clear_col = st.columns([10, 1, 1])
    with header_col:
        st.caption(f'Interpreted from: "{query}"  — tool: `{function_called}`')
    with icon_col:
        if _nlq_params_diverged(function_called, params or {}):
            # Inline HTML ``title`` attribute gives a true native browser
            # hover tooltip — exactly the unobtrusive affordance the user
            # asked for (icon visible, message on hover).
            tooltip = (
                "Filters have been modified since this query — the chips "
                "below still show the original LLM interpretation, not "
                "the currently active filters."
            )
            st.markdown(
                f'<span title="{tooltip}" '
                'style="cursor: help; font-size: 1.2em;">⚠️</span>',
                unsafe_allow_html=True,
            )
    with clear_col:
        st.button(
            "✕",
            key="nlq_clear_btn",
            on_click=_clear_nlq_state,
            help="Clear the NLQ chips (filters are left untouched)",
        )

    if chip_texts:
        # Render the chips as a single row of small code-styled tags.
        # Using a markdown line is the simplest way to get a compact
        # horizontal layout; Streamlit doesn't have a native pill/tag
        # component.
        chips_md = "  ".join(f"`{text}`" for text in chip_texts)
        st.markdown(chips_md)

    # For search_stats, also render the results payload as an info card
    # since the stats query doesn't change the map/table view.
    if function_called == "search_stats":
        _render_stats_card()


def _build_chip_texts(
    function_called: str,
    params: dict[str, Any],
    all_parks: list[dict[str, Any]],
) -> list[str]:
    """Build the human-readable chip strings for an interpreted query."""
    chips: list[str] = []

    # Park code: show the park name if we can find it
    if "park_code" in params:
        code = params["park_code"]
        park = next(
            (p for p in all_parks if p.get("park_code") == code),
            None,
        )
        label = park.get("park_name", code) if park else code
        chips.append(f"Park: {label}")

    if "state" in params:
        chips.append(f"State: {params['state']}")

    if "hiked" in params:
        chips.append(f"Hiked: {'Yes' if params['hiked'] else 'No'}")

    if "visited" in params:
        chips.append(f"Visited: {'Yes' if params['visited'] else 'No'}")

    if "min_length" in params:
        chips.append(f"Min Length: {params['min_length']} mi")

    if "max_length" in params:
        chips.append(f"Max Length: {params['max_length']} mi")

    if "source" in params:
        chips.append(f"Source: {params['source']}")

    if "trail_type" in params:
        chips.append(f"Trail Type: {params['trail_type']}")

    if "visit_year" in params:
        chips.append(f"Visit Year: {params['visit_year']}")

    if "visit_month" in params:
        raw = params["visit_month"]
        # The parser expands a single month to ``[abbr, full]`` pairs,
        # so display the first entry for brevity.
        if isinstance(raw, list) and raw:
            chips.append(f"Visit Month: {raw[0]}")
        else:
            chips.append(f"Visit Month: {raw}")

    if params.get("per_park"):
        chips.append("Breakdown: per park")

    if "limit" in params:
        chips.append(f"Limit: {params['limit']}")

    # Stats/park summary tools imply an intent the chips alone don't
    # surface; annotate so the user knows why the map didn't change.
    if function_called == "search_stats" and not chips:
        chips.append("(overall stats)")

    return chips


def _render_stats_card() -> None:
    """Render a small info card with the stats returned by search_stats."""
    response = st.session_state.get(_LAST_RESPONSE_KEY) or {}
    results = response.get("results") or {}
    if not results:
        return

    # Show the whole results payload as formatted key/value pairs.
    # This keeps the card generic across both ``search_stats`` shapes
    # (aggregate and per-park) without hard-coding field names.
    with st.container(border=True):
        st.markdown("**Stats results**")
        if isinstance(results, dict):
            _render_stats_dict(results)
        elif isinstance(results, list):
            # per-park stats come back as a list — show as a dataframe.
            st.dataframe(results, use_container_width=True, hide_index=True)
        else:
            st.write(results)


def _render_stats_dict(data: dict[str, Any]) -> None:
    """Render a dict of stats as a compact key/value list."""
    # Separate scalars from nested structures so scalars can be shown
    # as metrics and nested values as JSON.
    scalar_items = []
    nested_items = []
    for key, value in data.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            scalar_items.append((key, value))
        else:
            nested_items.append((key, value))

    if scalar_items:
        # Render scalars as columns of metrics, up to 4 per row.
        per_row = 4
        for row_start in range(0, len(scalar_items), per_row):
            row = scalar_items[row_start : row_start + per_row]
            cols = st.columns(len(row))
            for col, (key, value) in zip(cols, row, strict=False):
                display_value = "—" if value is None else str(value)
                col.metric(label=key.replace("_", " ").title(), value=display_value)

    for key, value in nested_items:
        st.markdown(f"**{key.replace('_', ' ').title()}:**")
        st.json(value, expanded=False)


# ---------------------------------------------------------------------------
# Divergence detection
# ---------------------------------------------------------------------------


def _nlq_params_diverged(function_called: str, params: dict[str, Any]) -> bool:
    """Return True if any widget has changed from the LLM's interpretation.

    Only compares params the translation layer actually wrote to a
    widget. Params with no corresponding widget (trail_type, visit_year,
    visit_month, limit, per_park) are ignored — they're read-only chips
    and can't diverge.
    """
    if function_called == "search_stats":
        # Stats queries never touch widgets, so divergence is never
        # meaningful — the chips describe a standalone result card,
        # not active filters.
        return False

    # search_park_summary writes the park_code + relaxes state/visited.
    # If the user has since changed the park selection, that's divergence.
    if function_called == "search_park_summary":
        stashed_code = params.get("park_code")
        current_parks = st.session_state.get(_W_PARKS) or []
        return bool(stashed_code) and current_parks != [stashed_code]

    # search_parks writes visited (year/month have no widget, so they
    # can never diverge for the purposes of this check).
    if function_called == "search_parks":
        if "visited" in params:
            expected = "Visited Only" if params["visited"] else "Not Yet Visited"
            if st.session_state.get(_W_VISITED) != expected:
                return True
        return False

    # search_trails — check each mapped param.
    if "park_code" in params:
        expected_parks = [params["park_code"]]
        if st.session_state.get(_W_PARKS) != expected_parks:
            return True

    if "state" in params and st.session_state.get(_W_STATE) != params["state"]:
        return True

    if "hiked" in params:
        expected = "Hiked Only" if params["hiked"] else "Not Yet Hiked"
        if st.session_state.get(_W_HIKED) != expected:
            return True

    if "min_length" in params or "max_length" in params:
        new_min = float(params["min_length"]) if "min_length" in params else 0.0
        new_max = float(params["max_length"]) if "max_length" in params else 20.0
        new_min = max(0.0, min(20.0, new_min))
        new_max = max(0.0, min(20.0, new_max))
        if new_min > new_max:
            new_min, new_max = new_max, new_min
        current = st.session_state.get(_W_LENGTH, (0.0, 20.0))
        # Compare with a tolerance since the slider rounds to 0.5.
        if abs(current[0] - new_min) > 1e-6 or abs(current[1] - new_max) > 1e-6:
            return True

    return "source" in params and st.session_state.get(_W_SOURCE) != params["source"]


# ---------------------------------------------------------------------------
# Clear button callback
# ---------------------------------------------------------------------------


def _clear_nlq_state() -> None:
    """Callback to dismiss the NLQ chips without touching filter widgets.

    This preserves whatever filter state the user has set (either from
    the LLM or their own adjustments) while removing the historical
    chips display.
    """
    st.session_state[_LAST_RESPONSE_KEY] = None
    st.session_state[_LAST_PARAMS_KEY] = None
    st.session_state[_LAST_QUERY_KEY] = None
    st.session_state[_LAST_FUNCTION_KEY] = None
    st.session_state[_ERROR_KEY] = None
