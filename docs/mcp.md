---
title: Using the MCP Server
description: Tutorial for running the local nps-hikes MCP server over stdio or local Streamable HTTP, inspecting its tools and resources, and trying representative queries.
---

This guide walks through the `nps-hikes` MCP server from setup to first queries. By the end, you'll know how to run the server locally, connect with `MCP Inspector`, explore the available `tools` and `resources`, and test both structured and topic-based trail search.

The server is designed for MCP-compatible clients. This guide uses `MCP Inspector` for the walkthrough because it is the clearest way to inspect tools and resources directly, but the same local server can also be used with clients such as Claude Desktop.

The tutorial assumes you've completed the [Getting Started](getting-started.md) guide and run the full data collection pipeline. The MCP server reads from the same local project database as the API.

The server supports two local connection styles:

- `stdio`, where an MCP client launches the server as a subprocess
- local `Streamable HTTP`, where you start the server first, and then connect to `http://127.0.0.1:8002/mcp`

> **Tip:** Both modes expose the same MCP capabilities. The only difference is how the client and server exchange MCP messages.

## What the MCP server exposes

Tools:

- `search_trails`
- `search_by_topic`
- `search_parks`
- `search_stats`
- `search_park_summary`

Resources:

- `dataset_overview`
- `park_lookup`
- `search_methodology`

## Prerequisites

This guide assumes:

- Your local `nps-hikes` Python environment is installed and activated.
- The local project database is running and contains the expected park and trail data.
- Node.js and `npx` are available so you can run the `MCP Inspector`.

For `search_by_topic`, your semantic search dependencies must also be ready:

- Query embeddings can be generated locally.
- Semantic embeddings already exist in the database.
- `content_trail_mapping` has already been built.

## Choose a connection style

Use `stdio` when you want `MCP Inspector` to launch the server for you.

Use local `Streamable HTTP` when you want to run the MCP server as its own local service and connect by URL.

The `make` targets below are convenience shortcuts. The underlying Python entrypoints are included too so you can see exactly what is running.

## Option 1: Run over stdio

The underlying server command is:

```bash
python -m nps_hikes_mcp.server
```

The convenience shortcut is:

```bash
make mcp
```

To validate this mode with `MCP Inspector`, let Inspector launch the server directly:

```bash
npx @modelcontextprotocol/inspector python -m nps_hikes_mcp.server
```

When the command starts, the Inspector prints a local URL for its web UI. Open the exact URL shown in the terminal output.

In this mode, the Inspector launches the MCP server as a child process. You do not need to run `make mcp` separately.

## Option 2: Run over local Streamable HTTP

The underlying server command is:

```bash
python -m nps_hikes_mcp.http_server --host 127.0.0.1 --port 8002 --path /mcp
```

The convenience shortcut is:

```bash
make mcp-http
```

By default, the server listens at:

```text
http://127.0.0.1:8002/mcp
```

Start that server in one terminal. Then start the Inspector in a second terminal:

```bash
npx @modelcontextprotocol/inspector
```

Open the Inspector URL printed in that terminal.

In the Inspector UI:

1. Set the transport to `streamable-http`.
2. Enter `http://127.0.0.1:8002/mcp` as the server URL.
3. Connect to the running server.

## Verify the MCP surface

Once the Inspector is connected, start by listing the available tools and resources:

1. Run `tools/list`.
2. Confirm the tools include `search_trails`, `search_by_topic`, `search_parks`, `search_stats`, and `search_park_summary`.
3. Run `resources/list`.
4. Confirm the resources include `dataset_overview`, `park_lookup`, and `search_methodology`.

Next, read each resource once so you can see the static context the server provides:

1. Read `dataset_overview`.
2. Read `park_lookup`.
3. Read `search_methodology`.

Then make a few tool calls:

1. Call `search_stats`.
2. Call `search_parks`.
3. Call `search_trails`.
4. Call `search_by_topic`.
5. Call `search_park_summary`.

If those steps succeed, the MCP server is working correctly in that transport mode.

## Understand the resources

The resources are useful background context for an MCP client before it starts calling tools.

- `dataset_overview` explains what data the project contains, what the MCP server is designed to expose, and the main constraints of the local dataset.
- `park_lookup` returns a structured mapping of park names to canonical 4-letter park codes. This is especially useful when a client needs to turn a name like "Yosemite" into `yose`.
- `search_methodology` explains trail provenance, deduplication, status fields such as `visited` and `hiked`, and how to interpret topic-search fallback results.

## Start with a simple stats query

The easiest first tool call is `search_stats` with no arguments.

This returns aggregate trail statistics across the full local dataset, including:

- `total_trails`
- `parks_count`
- `states_count`
- `total_miles`
- `source_breakdown`

If you want to scope the stats to hikes you have completed or not completed, set `hiked` to `true` or `false`.

## Browse parks

Use `search_parks` to filter parks by visit status or metadata.

A few good starter queries are:

- `visited=true`
- `visit_month="Oct"`
- `visit_year=2024`
- `state="CA"`
- `park_code="yose"`

The response includes:

- `summary`
- `park_count`
- `visited_count`
- `applied_filters`
- `parks`

Each park entry includes the park code, park name, full name, states, visit information, and URL.

## Search trails with structured filters

Use `search_trails` when the request is purely structured, such as:

- trails in one park
- trails in one state
- hiked or unhiked trails
- minimum or maximum mileage
- source-specific filtering with `TNM` or `OSM`
- whether a 3D visualization is available

Common inputs include:

- `park_code="acad"`
- `state="UT"`
- `hiked=false`
- `min_length=3.0`
- `max_length=8.0`
- `source="TNM"`
- `viz_3d=true`

The response includes a compact result set with:

- `summary`
- `trail_count`
- `total_miles`
- `applied_filters`
- `trails`

Each trail includes the trail name, park, state, source, mileage, hiked status, and 3D visualization metadata.

## Search trails by topic

Use `search_by_topic` when the request has a descriptive or semantic component rather than only structured filters.

Good examples include:

- `query="waterfalls"`
- `query="slot canyons"`
- `query="scenic viewpoints"`
- `query="kid-friendly hikes"`

You can combine a topic query with structured filters such as:

- `park_code`
- `state`
- `hiked`
- `min_length`
- `max_length`
- `source`

The response may include:

- `summary`
- `trail_count`
- `total_miles`
- `applied_filters`
- `trails`
- `topic_context`
- `fallback_chunks`

When semantic matches resolve to trails, `trails` contains the structured trail results and `topic_context` includes the matched content snippets that led to those results.

When semantic matches do not resolve to trail rows, the tool still succeeds and returns `trail_count: 0` along with `fallback_chunks`.

## Get a park summary

Use `search_park_summary` when you want a single overview for one park.

For example, call it with:

```text
park_code="yose"
```

The response groups the data into:

- `summary`
- `park`
- `trail_stats`
- `source_breakdown`
- `visit_info`

This is the best one-call option when you want a concise park overview instead of a longer trail or park listing.

## Inspector input tips

`MCP Inspector` does not always render tool inputs the same way.

- For tools with multiple fields such as `search_trails` and `search_parks`, enter raw field values in each input box.
- `search_by_topic.query` is required and should be a plain-text topic string such as `waterfalls`.
- For single-scalar inputs such as `search_park_summary`, enter the raw value such as `yose`.
- For optional booleans such as `hiked`, leave the field blank to omit the parameter, or use `true` / `false` for real boolean values.

If the input form behaves unexpectedly, first check whether Inspector is treating the tool input as individual scalar fields or as a raw JSON payload.

## Browser behavior on the HTTP endpoint

If you open `http://127.0.0.1:8002/mcp` directly in a normal browser tab, you may see a response like:

```json
{"jsonrpc":"2.0","id":"server-error","error":{"code":-32600,"message":"Not Acceptable: Client must accept text/event-stream"}}
```

That is expected. The MCP endpoint is not a normal web page. It expects an MCP client that can negotiate the correct HTTP transport behavior.

## MCP library requirement

This repository expects an MCP server library to be installed in your environment. The entrypoint supports either:

- `fastmcp`
- a compatible package exposing `mcp.server.fastmcp.FastMCP`

If the MCP library is missing, the server entrypoint exits with a clear error.
