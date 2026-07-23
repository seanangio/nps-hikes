# MCP V4 Validation Follow-Up: Park Visit Month Normalization

## Context

During MCP v4 validation on Thursday, July 23, 2026, `search_by_topic` validation passed in:

- `MCP Inspector` over `stdio`
- `MCP Inspector` over local `Streamable HTTP`
- `Claude Desktop`

However, a separate issue surfaced while testing the existing `search_parks` tool conversationally in `Claude Desktop`.

Example user query:

`What parks have I visited in October?`

Observed behavior:

- `Claude Desktop` chose the correct MCP tool: `search_parks`
- the tool-level filter returned zero matches for `October`
- Claude then inferred the answer manually from broader visited-park results

This strongly suggests a month-normalization mismatch between user-facing month terms and the stored visit-month values in the dataset.

## Problem Summary

The current system appears to store visit months in abbreviated form such as:

- `Oct`

But user-facing queries and tool expectations may naturally use:

- `October`

That means a query which is semantically correct at the product level can still miss at the tool/query level because the month value is treated too literally.

## Why This Is Not An MCP-V4-Specific Bug

This surfaced during MCP validation, but it does not appear to be fundamentally an MCP transport or MCP tool-contract problem.

It is more likely a broader domain/input-normalization issue because:

- month alias handling is domain behavior, not transport behavior
- the same normalization expectation is useful across MCP, API, and NLQ surfaces
- fixing it only in the MCP wrapper would likely create more cross-surface drift

## Recommended Scope Decision

Do not treat this as blocking MCP v4 validation completion.

Reason:

- v4 validation was focused on adding and validating MCP `search_by_topic`
- the new semantic MCP tool passed validation
- the month-normalization issue belongs to a broader input-normalization pass, not to the core v4 MCP semantic-search implementation

## Proposed Solution Options

### Option 1: Fix In Shared Query/Input-Normalization Logic

Recommended default.

Add shared normalization so user-facing month values map to the stored dataset representation before the park query executes.

Possible behavior:

- `October` → `Oct`
- `October` and `Oct` both work
- multiple aliases can normalize to a canonical stored value

Why this is preferred:

- benefits MCP, API, and NLQ together
- keeps domain behavior below the transport layer
- reduces future cross-surface inconsistencies

### Option 2: Expand Month Matching In The Shared Data Query

Instead of normalizing only at input time, allow the shared park-query layer to match multiple known aliases.

Possible behavior:

- if user asks for `October`, query can match `October` and `Oct`
- if user asks for `Sep`, query can match `Sep` and `September`

Why this may help:

- robust against mixed historical data formatting
- useful if the database is not fully normalized

Tradeoff:

- query logic becomes slightly more complex

### Option 3: MCP-Only Adapter

Not recommended except as a temporary stopgap.

The MCP wrapper could normalize month names before calling shared logic.

Why this is weaker:

- fixes the symptom only for MCP
- creates another behavior difference between MCP and other project surfaces
- places domain normalization too high in the stack

## Recommended Next Step

Treat this as a separate follow-up task after MCP v4 closure:

1. inspect how visit months are stored in the dataset
2. inspect where API/NLQ month normalization already exists, if anywhere
3. choose a shared normalization strategy
4. add tests covering:
   - `Oct`
   - `October`
   - other month aliases
   - season inputs, if supported as a product expectation

## Status

As of July 23, 2026:

- this issue is documented
- it is intentionally excluded from MCP v4 validation scope
- MCP v4 semantic-search validation can still be considered complete
