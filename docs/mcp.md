---
title: Local MCP Server
description: Guide for running the local nps-hikes MCP server over stdio or local Streamable HTTP and validating it with MCP Inspector.
---

This guide shows how to run the `nps-hikes` MCP server locally and inspect it with `MCP Inspector`. The server exposes the project's park and trail query layer as MCP `tools` and `resources`.

The guide covers two local connection styles:

- `stdio`: `MCP Inspector` launches the server as a subprocess
- local `Streamable HTTP`: you start the server first, then `MCP Inspector` connects to `http://127.0.0.1:8002/mcp`

Both modes expose the same MCP surface. The difference is only how the client and server exchange messages.

## What the server exposes

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

- you have completed [Getting Started](getting-started.md)
- your local `nps-hikes` Python environment is installed and activated
- the local project database is running and contains the expected park and trail data
- Node.js and `npx` are available so you can run `MCP Inspector`

If you are following the recommended local workflow, the same database used by the API is the main runtime dependency here too.

## Choose a connection style

Use `stdio` when you want `MCP Inspector` to launch the server for you.

Use local `Streamable HTTP` when you want to run the MCP server as its own local service and connect to it by URL.

The `make` targets shown below are convenience shortcuts. The underlying Python entrypoints are included too so the guide reflects the real commands.

## Option 1: Run with stdio

The underlying server command is:

```bash
python -m nps_hikes_mcp.server
```

The convenience shortcut is:

```bash
make mcp
```

To validate this mode with Inspector, start `MCP Inspector` and let it launch the server:

```bash
npx @modelcontextprotocol/inspector python -m nps_hikes_mcp.server
```

If you prefer not to rely on an activated shell environment, point Inspector at the Python executable inside your virtualenv:

```bash
npx @modelcontextprotocol/inspector /path/to/your/virtualenv/bin/python -m nps_hikes_mcp.server
```

The first time you run this command, `npx` may prompt to install the Inspector package. That package belongs to the Node/npm toolchain, not your Python environment.

After the command starts, Inspector prints a local URL for its web UI. Open the exact URL shown in the terminal output.

In this mode, Inspector launches `nps_hikes_mcp.server` as a child process. You do not need to run `make mcp` separately.

## Option 2: Run with local Streamable HTTP

The underlying server command is:

```bash
python -m nps_hikes_mcp.http_server --host 127.0.0.1 --port 8002 --path /mcp
```

The convenience shortcut is:

```bash
make mcp-http
```

By default, the server binds locally at:

```text
http://127.0.0.1:8002/mcp
```

Start that server in one terminal.

Then start Inspector in a second terminal:

```bash
npx @modelcontextprotocol/inspector
```

Open the Inspector URL printed in that terminal.

In the Inspector UI:

1. Set the transport to `streamable-http`.
2. Enter `http://127.0.0.1:8002/mcp` as the server URL.
3. Connect to the running server.

In this mode, Inspector does not launch the MCP server. The server must already be running in the other terminal.

If you already have an Inspector tab open, you can usually reuse that same UI and switch the transport from `stdio` to `streamable-http` or back again. You do not always need a brand-new Inspector browser session for each transport.

## Quick note about browsers

If you open `http://127.0.0.1:8002/mcp` directly in a normal browser tab, you may see a response like:

```json
{"jsonrpc":"2.0","id":"server-error","error":{"code":-32600,"message":"Not Acceptable: Client must accept text/event-stream"}}
```

That is expected. The MCP endpoint is not a normal web page. It expects an MCP client that can negotiate the correct HTTP transport behavior.

## Verify the server in MCP Inspector

Once Inspector is connected, validate the MCP surface with these checks:

1. Run `tools/list`.
2. Confirm the tools include `search_trails`, `search_parks`, `search_stats`, and `search_park_summary`.
3. Run `resources/list`.
4. Confirm the resources include `dataset_overview`, `park_lookup`, and `search_methodology`.
5. Read `dataset_overview`.
6. Read `park_lookup`.
7. Read `search_methodology`.
8. Call `search_stats`.
9. Call `search_trails`.
10. Call `search_park_summary`.

If those steps succeed, the local MCP server is working correctly in that transport mode.

## Suggested first tool calls

These are good first checks in Inspector:

1. Call `search_stats` with no arguments.
2. Call `search_parks` with a month filter.
3. Call `search_trails` with a state and mileage filter.
4. Call `search_park_summary` with a known `park_code` such as `yose`.

## Inspector input quirks

`MCP Inspector` does not always render inputs the same way.

- For tools with multiple fields such as `search_trails` and `search_parks`, enter raw field values in each input box.
- Do not paste a full JSON object into a single field unless the UI explicitly asks for raw JSON.
- For single-scalar inputs such as `search_park_summary`, enter the raw value such as `yose`.
- For optional booleans such as `search_stats.hiked`, leave the field blank to omit the parameter, or use `true` / `false` for real boolean values.

If input behavior seems odd, first check whether Inspector is treating the field as a scalar input or as a raw JSON payload editor.

## Running stdio and HTTP side by side

Yes, you can run both local transport modes at the same time.

- The HTTP server uses its own local port, by default `8002`.
- The `stdio` server does not bind to that port.

If you see an Inspector message like `Proxy Server PORT IS IN USE at port 6277`, that message is coming from Inspector itself. It usually means an Inspector process is already running, and the existing browser tab at the URL Inspector printed earlier may still work.

If that happens:

1. first check whether an existing Inspector tab is already open and usable
2. if it is, reuse that UI and switch transports there if needed
3. if you want a fresh Inspector session, stop the earlier Inspector process and start it again

## Claude Desktop

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

Observed behavior:

- Claude Desktop discovered all four MCP tools.
- `search_stats`, `search_trails`, and `search_park_summary` executed successfully.
- empty-result and validation-error cases surfaced clearly
- MCP resources were not exposed in normal chat use the same way they were in `MCP Inspector`

That makes the practical split:

- use `MCP Inspector` for protocol and resource validation
- use `Claude Desktop` for conversational tool validation

## MCP library requirement

This repo expects an MCP server library to be installed in your environment. The entrypoint supports either:

- `fastmcp`
- a compatible package exposing `mcp.server.fastmcp.FastMCP`

If the MCP library is missing, the server entrypoint exits with a clear error.
