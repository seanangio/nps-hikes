# NPS Hikes MCP Walkthrough

This note explains how the current MCP implementation works, how the code is split across three files after the v2 cleanup pass, and what actually happens when a client calls a tool.

> **Status:** As of July 21, 2026, this walkthrough describes the cleaned-up local `stdio` MCP server that was validated with both `MCP Inspector` and `Claude Desktop`.

The three MCP-specific files to understand are:

- `nps_hikes_mcp/server.py`
- `nps_hikes_mcp/resources.py`
- `nps_hikes_mcp/tools.py`

## Big Picture

The MCP layer is an adapter around the existing project logic, not a second backend.

The current flow is:

- `api/queries.py` fetches real data from the database
- `nps_hikes_mcp/tools.py` wraps those query functions and shapes them into MCP-friendly tool outputs
- `nps_hikes_mcp/resources.py` exposes stable, read-only context as MCP resources
- `nps_hikes_mcp/server.py` registers those tools and resources with the MCP library so a client can discover and call them

The key design choice is that the source of truth for the data logic still lives in the existing backend. The MCP code is mostly transport glue plus output shaping.

## What `stdio` means here

In this implementation, `stdio` is the transport between the MCP client and the MCP server process.

That means:

- the client starts the MCP server as a local child process
- the client sends MCP requests to the server over standard input
- the server sends MCP responses back over standard output

So `stdio` is just the communication channel. It is not business logic, not a special query mode, and not a human-facing terminal workflow.

### Why `stdio` is a good v1 choice

For this project, `stdio` is a good default because:

- it stays fully local
- it avoids extra HTTP setup just to learn MCP
- it works naturally with neutral tooling like MCP Inspector
- it keeps the debugging surface smaller while the server is still evolving

### What `stdio` does not mean

It does not mean:

- that you type English requests into the server process manually
- that the server is meant to be used like a normal CLI tool
- that the MCP messages are plain human-readable prompts

The MCP client and server are exchanging protocol messages over the standard input/output streams.

## File 1: `nps_hikes_mcp/tools.py`

This file defines the MCP tool behavior.

Responsibilities:

- import the real query functions from `api.queries`
- define MCP-facing wrappers such as `search_trails`, `search_parks`, `search_stats`, and `search_park_summary`
- shape the raw results into compact MCP responses
- add deterministic `summary` fields
- define `TOOL_DEFINITIONS`, which now hold MCP-oriented metadata and the MCP-facing callable for each tool

This file is doing two jobs:

1. runtime tool behavior
2. tool metadata/schema description

After the v2 cleanup, that split is still present, but the public MCP contract is now more centralized than it was in v1.

### Example: `search_trails`

The wrapper:

- accepts MCP tool arguments such as `park_code`, `state`, `hiked`, and `max_length`
- calls `fetch_trails(...)` from `api.queries`
- removes fields that are not useful for the MCP v1 surface
- preserves the most important trail fields
- adds:
  - `summary`
  - `trail_count`
  - `total_miles`
  - `applied_filters`

So `tools.py` is the translation layer between internal query results and MCP tool outputs.

### Why `tools.py` exists

The raw query results are not quite the same thing as the ideal MCP response.

MCP tools should be:

- compact
- stable
- easy for a client to narrate
- explicit about applied filters

That shaping is transport-specific, so it belongs in the MCP adapter rather than in the shared query layer.

### What "compact" means in this MCP layer

Here, "compact" means intentionally returning the most useful fields for the v1 MCP use case without dumping every available backend field by default.

So compact means:

- enough structure for the client to use reliably
- enough metadata for the result to stay interpretable
- no large or low-signal fields unless they materially help the main v1 workflow

For example, in `search_trails`, the MCP wrapper keeps high-value fields like trail name, park code, miles, source, and hiked status, while leaving out heavier or noisier fields by default, such as geometry-heavy content.

So compact does not mean vague. It means intentionally scoped.

## File 2: `nps_hikes_mcp/resources.py`

This file defines the MCP resources.

Resources are different from tools. A tool is something the client calls with arguments. A resource is something the client can read as stable context.

Current resources:

- `dataset_overview`
- `park_lookup`
- `search_methodology`

Responsibilities:

- generate each resource's content
- define `RESOURCE_DEFINITIONS`
- provide a small `read_resource(uri)` lookup helper backed by those definitions

### Resource examples

`get_dataset_overview()`

- returns markdown text
- explains what the project contains and what v1 MCP is meant to do

`get_search_methodology()`

- returns markdown text
- explains TNM vs OSM, deduplication, and status meanings

`get_park_lookup_resource()`

- returns structured JSON-like data
- builds a park lookup mapping from the existing `get_park_lookup()` helper

`read_resource(uri)`

- looks up the matching resource definition
- calls the reader function already attached to that definition

### Why resources exist separately

One of the main MCP concepts is the distinction between:

- tools: parameterized actions
- resources: stable documents or data blobs

This is why the lookup table is exposed as a resource rather than a tool call.

## File 3: `nps_hikes_mcp/server.py`

This file is the MCP bootstrap and registration layer.

Responsibilities:

- load the MCP library
- create the server object
- register tools
- register resources
- start the server over `stdio`

This file is mostly wiring, not business logic.

### Tool registration

After the v2 cleanup:

- `server.py` loops through `TOOL_DEFINITIONS`
- registers each tool's public `name`
- registers each tool's public `description`
- uses the callable stored in the definition itself

This means the MCP runtime now learns the public tool contract from one shared definition list rather than from separate hand-written wrappers in `server.py`.

### Resource registration

For each resource:

- `server.py` loops through `RESOURCE_DEFINITIONS`
- creates a tiny serialization wrapper around the resource's attached reader
- wraps it in a `FunctionResource`
- registers it with `app.add_resource(...)`

This is the fixed-resource path used by the current `fastmcp` version.

### `main()`

`main()` creates the server and starts it.

The startup mode is `stdio`, which means:

- the client launches the Python process
- the client sends MCP messages over standard input/output
- the server does not need to bind to an HTTP port

That is why this is a good local-first v1 setup.

## What the cleanup changed

The main v2 cleanup goal was to reduce MCP contract drift.

Before the cleanup:

- `server.py` hand-registered each tool separately
- resource metadata and resource dispatch were more manually split

After the cleanup:

- each tool definition now includes the MCP-facing callable
- each resource definition now includes the reader function
- `server.py` registers both tools and resources generically from those shared definitions
- registration drift is covered by explicit unit tests

## What duplication is still acceptable vs risky

Some duplication is expected because FastAPI and MCP are different interfaces.

Reasonable duplication:

- MCP-specific summaries
- MCP-specific resource descriptions
- MCP registration glue

Risky duplication:

- repeating tool names in too many places
- repeating signatures and schema-like definitions by hand
- repeating contract details that can drift over time

So the current code is in a better place than v1, but the basic maintenance concern was real and the cleanup was worthwhile.

## What still remains true

Some separation still exists by design:

- business/query logic lives in `api/queries.py`
- MCP output shaping lives in `nps_hikes_mcp/tools.py`
- MCP resource content lives in `nps_hikes_mcp/resources.py`
- MCP transport wiring lives in `nps_hikes_mcp/server.py`

That separation is healthy. The v2 cleanup was not about collapsing everything into one file. It was about making the public MCP contract easier to keep consistent.

## Client behavior note

The same cleaned-up MCP server behaves differently across the two validated clients:

- `MCP Inspector` exposes tools and resources clearly and remains the best debugging client
- `Claude Desktop` exposed the tools successfully in chat, but did not expose MCP resources to the model in the same direct way during this validation pass

That difference appears to be a client-surface difference rather than a problem with the `nps-hikes` server itself.

## The likely cleanup direction later

A cleaner next version would probably define each tool in one structured spec object and use that spec for:

- registration
- schema metadata
- description

while keeping the actual implementation function separate.

Something similar could be done for resources.

The goal is not zero duplication. The goal is:

- one source of truth for business logic
- minimal duplication for transport metadata

The most important architectural win is already in place: the database/query logic still lives outside the MCP layer.

## What MCP Inspector actually is

MCP Inspector is a protocol test client.

It is:

- not your server
- not part of your Python application
- not a chat assistant

It is a developer tool that can:

- launch or connect to an MCP server
- list tools
- list resources
- call tools manually
- read resources manually
- show raw requests and responses

It plays a role similar to:

- Swagger UI for REST APIs
- Postman for HTTP APIs
- a database client for SQL

but for MCP.

That is why it is a better neutral first client than a chat product. It lets you validate the protocol surface directly before worrying about assistant behavior.

## End-to-end walkthrough: `search_trails("yose")`

This section traces one concrete request from the client all the way through the current implementation.

### Step 1: the client calls the tool

In MCP Inspector:

- you open the `search_trails` tool
- you enter `yose` into the `park_code` field
- Inspector sends a tool call request to the MCP server

At this point, the MCP client does not know anything about the database. It only knows:

- the tool name: `search_trails`
- the argument value: `park_code = "yose"`

### Step 2: MCP dispatch reaches `server.py`

The MCP runtime has already registered `search_trails` in `server.py`.

So when the request arrives, the MCP library invokes:

- `trails_tool(...)` in `nps_hikes_mcp/server.py`

That function is intentionally thin. It mostly passes the arguments through to the MCP wrapper in `tools.py`.

### Step 3: `server.py` calls the wrapper in `tools.py`

`trails_tool(...)` calls:

- `search_trails(...)` in `nps_hikes_mcp/tools.py`

This is where the MCP-specific behavior starts.

The wrapper:

- builds a `filters` dictionary
- calls the existing query function

Specifically:

- `fetch_trails(park_code="yose", ...)`

### Step 4: the shared query layer fetches real data

Inside `api.queries.fetch_trails(...)`:

- SQL is constructed
- the database engine is used
- matching trail rows are fetched
- results are formatted into the existing API-style response shape

At this stage, the data is still in the query-layer format, not the final MCP format.

### Step 5: `tools.py` reshapes the response

Back in `nps_hikes_mcp/tools.py`, the wrapper receives the result from `fetch_trails(...)`.

It then:

- builds a human-readable `summary`
- constructs `applied_filters`
- converts each trail into a smaller MCP-facing shape via `_compact_trail(...)`
- returns the final MCP tool payload

The goal here is to give the client:

- structured data it can use programmatically
- enough context to narrate the result cleanly
- no unnecessary geometry-heavy or low-signal fields

### Step 6: `server.py` returns the result to the MCP runtime

The wrapper result flows back through `trails_tool(...)` in `server.py`.

The MCP library serializes the returned Python dictionary into the MCP tool result format and sends it back over `stdio`.

### Step 7: Inspector shows the result

MCP Inspector receives the tool response and displays:

- the raw request
- the raw structured response

So when you see a successful `search_trails` result in Inspector, you are seeing the output of this full chain:

1. Inspector UI
2. MCP tool call
3. `server.py` registered tool function
4. `tools.py` wrapper
5. `api.queries.fetch_trails(...)`
6. database
7. response shaped in `tools.py`
8. serialized by the MCP runtime
9. shown back in Inspector

## Short mental model

If you want a quick way to remember the roles:

- `tools.py` = what operations exist and how results are shaped
- `resources.py` = what stable context exists and how it is read
- `server.py` = how those things are exposed over MCP
- Inspector = how you manually test the exposed MCP surface

## Final takeaway

The current implementation is already on the right side of the most important architectural boundary:

- shared data logic lives outside the MCP adapter
- MCP mostly adds transport registration plus result shaping

The biggest future risk is metadata duplication, not duplicated query logic.

That is a good place to be for a first working version.
