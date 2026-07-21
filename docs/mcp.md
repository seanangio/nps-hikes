---
title: Local MCP Server
description: Run the local nps-hikes MCP server over stdio and expose park and trail tools to an MCP-compatible client.
---

The local MCP server is the MCP-facing adapter for `nps-hikes`. It reuses the same project query logic as the FastAPI app, but exposes that logic as MCP `tools` and `resources` for a local MCP-compatible client.

For v1, the recommended validation client is `MCP Inspector` rather than a chat-first assistant. That keeps the workflow local, protocol-native, and client-neutral while the MCP surface is still evolving.

> **Status:** The local `stdio` MCP v1 described on this page has been implemented and verified with `MCP Inspector`. This page documents the completed v1 workflow.

## Current v1 surface

Tools:

- `search_trails`
- `search_parks`
- `search_stats`
- `search_park_summary`

Resources:

- `dataset_overview`
- `park_lookup`
- `search_methodology`

## Prerequisites

This guide assumes:

- you have completed the project setup from `getting-started.md`
- your local `nps-hikes` Python environment is installed and activated
- the local project database is running and contains the expected park and trail data
- Node.js and `npx` are available so you can launch `MCP Inspector`

If you are following the recommended day-to-day workflow, the main prerequisite is the same local database used by the API.

## Run the server locally

Start the local project database the same way you would for the API. Then run:

```bash
make mcp
```

This starts the server over `stdio`, which is the default local transport for v1.

## Recommended client

Use `MCP Inspector` as the default local test client for v1.

Why this is the default:

- it is purpose-built for testing MCP servers
- it works directly with local `stdio` servers
- it lets you inspect tools, resources, schemas, and errors without adding ChatGPT-specific setup

### Launch MCP Inspector

With your `nps-hikes` environment active, run:

```bash
npx @modelcontextprotocol/inspector python -m nps_hikes_mcp.server
```

The first time you run this command, `npx` may prompt to install the Inspector package. That package is part of the Node/npm toolchain, not part of your Python virtualenv.

The Inspector should launch your MCP server as a child process and print a local URL for the UI. Open the exact URL shown in the terminal output, rather than guessing the base port manually, because the Inspector may include a session token in the URL.

If you prefer not to rely on an activated shell environment, you can instead point Inspector at the Python executable inside your virtualenv:

```bash
npx @modelcontextprotocol/inspector /path/to/your/virtualenv/bin/python -m nps_hikes_mcp.server
```

## MCP library requirement

This repo now includes the MCP wrapper code and server entrypoint, but it expects an MCP server library to be installed in your environment. The entrypoint supports either:

- `fastmcp`
- a compatible package exposing `mcp.server.fastmcp.FastMCP`

If neither package is installed, `make mcp` will exit with a clear error telling you what is missing.

## Verify the connection

In `MCP Inspector`, verify:

1. `tools/list` shows:
   - `search_trails`
   - `search_parks`
   - `search_stats`
   - `search_park_summary`
2. `resources/list` shows:
   - `dataset_overview`
   - `park_lookup`
   - `search_methodology`
3. Reading `dataset_overview` succeeds.
4. Reading `park_lookup` succeeds.
5. A simple tool call like `search_stats` or `search_parks` returns local project data.

## Suggested first checks

Use these in order:

1. List resources.
2. Read `dataset_overview`.
3. Call `search_stats`.
4. Call `search_parks` with a month filter.
5. Call `search_trails` with a state and mileage filter.
6. Call `search_park_summary` with a known `park_code`.

## Inspector input quirks

`MCP Inspector` does not always render tool inputs the same way.

- For tools with multiple fields such as `search_trails` and `search_parks`, enter the raw field values in each input box.
  Example:
  - `park_code` -> `yose`
  - `state` -> `UT`
- Do not paste a full JSON object into a single field input.
- Do not add quotes or backticks unless the UI is explicitly asking for raw JSON.
- For single-scalar inputs, Inspector may render just the value input rather than an object-shaped form.
  Example:
  - for `search_park_summary`, enter `yose`
  - not `{"park_code": "yose"}`
  - and not quoted variants unless the UI explicitly expects JSON
- For optional booleans such as `search_stats.hiked`:
  - leave the field blank to omit the parameter
  - use `true` or `false` for actual boolean values
  - do not type `none`, because Inspector will send the literal string `"none"` and validation will fail

If validation behavior seems inconsistent, first check whether Inspector is treating the field as a scalar input or as a raw JSON payload editor.

## Recommended verification flow

Once Inspector is connected, a good v1 walkthrough is:

1. Run `resources/list`.
2. Read `dataset_overview`.
3. Read `park_lookup`.
4. Read `search_methodology`.
5. Run `tools/list`.
6. Call `search_stats` with no arguments.
7. Call `search_parks` with a month filter.
8. Call `search_trails` with a known `park_code`.
9. Call `search_park_summary` with a known `park_code`.
10. Try one invalid input and one empty-result case to verify failure behavior.

## Optional later clients

Once the server is stable in `MCP Inspector`, you can optionally connect it to a chat-oriented MCP client such as ChatGPT or another desktop assistant.

That should be treated as a follow-on client integration step, not as the primary v1 validation path.

## Current limitations

- v1 does not expose semantic/topic search through MCP.
- v1 does not expose geometry-heavy payloads by default.
- v1 does not expose the FastAPI natural-language `/query` endpoint.
- v1 currently focuses on local single-user use only.
