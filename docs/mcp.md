---
title: Local MCP Server
description: Run the local nps-hikes MCP server over stdio and expose park and trail tools and resources to local MCP-compatible clients.
---

The local MCP server is the MCP-facing adapter for `nps-hikes`. It reuses the same project query logic as the FastAPI app, but exposes that logic as MCP `tools` and `resources` for a local MCP-compatible client.

`MCP Inspector` remains the recommended protocol-debugging client because it exposes both MCP tools and MCP resources clearly. `Claude Desktop` is now also a validated local client for the current tool surface.

> **Status:** As of July 21, 2026, the local `stdio` MCP server has been validated in both `MCP Inspector` and `Claude Desktop`. `MCP Inspector` is still the better resource-focused debugging client; `Claude Desktop` has been validated primarily for tool execution.

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

## Recommended clients

Use `MCP Inspector` as the default protocol-debugging client.

Why this is the default:

- it is purpose-built for testing MCP servers
- it works directly with local `stdio` servers
- it lets you inspect tools, resources, schemas, and errors without adding ChatGPT-specific setup

Use `Claude Desktop` as the validated second client for a chat-oriented local workflow.

Why this is useful:

- it confirms the server works outside Inspector
- it shows how the MCP tool descriptions behave in a conversational client
- it helps surface client-specific quirks around permissions, argument normalization, and result rendering

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

## Claude Desktop validation

`Claude Desktop` can launch the local `stdio` server through `claude_desktop_config.json`.

The working local configuration used for validation was conceptually:

```json
{
  "mcpServers": {
    "nps-hikes": {
      "command": "/bin/zsh",
      "args": [
        "-lc",
        "cd '/path/to/nps-hikes' && source ~/.virtualenvs/nps-hikes/bin/activate && python -m nps_hikes_mcp.server"
      ]
    }
  }
}
```

### What worked in Claude Desktop

- Claude Desktop discovered all four MCP tools.
- `search_stats` executed successfully and returned the expected JSON.
- `search_trails` executed successfully and returned the expected JSON.
- `search_park_summary` executed successfully and returned the expected JSON.
- Empty-result cases still behaved correctly.
- Validation errors and not-found errors were surfaced clearly in the chat UX.
- Boolean arguments such as `hiked=false` were passed correctly.

### Claude Desktop quirks

- Claude Desktop asked for permission before using the new MCP tools.
- Claude wrapped the raw JSON response with short conversational text before and after the tool result.
- Claude could often infer the correct tool when the request was phrased clearly, even when the tool name was not specified explicitly.
- For one `search_trails` test, Claude first attempted `source=osm` and received the expected validation error because the MCP tool requires uppercase `OSM` or `TNM`. Claude then retried with `source=OSM` and succeeded.

### Resource behavior in Claude Desktop

During this validation pass, `Claude Desktop` did not expose MCP resources in normal chat use the same way it exposed MCP tools.

Observed behavior:

- `MCP Inspector` could list and read `dataset_overview`, `park_lookup`, and `search_methodology`.
- `Claude Desktop` could use the MCP tools, but did not provide a normal chat path for the model to enumerate or read those resources directly.

Current interpretation:

- this appears to be a client UX limitation or client-surface difference rather than a confirmed server issue
- no additional `nps-hikes` server configuration change was identified that would make those resources automatically accessible in Claude Desktop chat

So the practical split is:

- use `MCP Inspector` to validate resources and protocol details
- use `Claude Desktop` to validate tool execution in a conversational client

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

Once the server is stable in both `MCP Inspector` and `Claude Desktop`, you can optionally explore remote-client integration paths such as `ChatGPT`.

That should still be treated as a separate follow-on project because it changes the connection model from the current local `stdio` workflow.

## Current limitations

- v1 does not expose semantic/topic search through MCP.
- v1 does not expose geometry-heavy payloads by default.
- v1 does not expose the FastAPI natural-language `/query` endpoint.
- v1 currently focuses on local single-user use only.
