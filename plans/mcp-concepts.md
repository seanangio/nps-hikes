# NPS Hikes MCP Concepts

## Overview

This note captures the main MCP concepts clarified during the v3 planning discussion so they are easier to remember later.

The focus here is not on implementation details first. The focus is on the mental model:

- what a client and server are
- what MCP adds
- what tools and resources are
- how the existing NLQ layer compares to MCP
- what transport means
- why `stdio`, local HTTP, and remote HTTP feel different even when the same MCP server is behind them

## Brick 1: Client and Server

At the simplest level:

- a `client` asks for something
- a `server` provides something

In the MCP project:

- `you` are the user
- `Claude Desktop` or `MCP Inspector` acts as the MCP host/client side
- `nps_hikes_mcp` is the MCP server

The MCP server is not the assistant itself. It is the capability provider the assistant can call.

### Restaurant analogy

- user = diner
- client = waiter
- server = kitchen

The diner does not walk into the kitchen directly. The waiter carries the request to the kitchen and brings the result back.

## Brick 2: What MCP Adds

MCP is a standard way for a client and server to talk about tools and resources.

Without MCP, every tool provider could invent:

- different names for the same idea
- different calling shapes
- different ways to describe capabilities

MCP gives a common pattern for:

- listing tools
- calling tools with structured arguments
- listing resources
- reading resources

So MCP is not:

- the LLM
- the database
- the business logic

It is the shared protocol between the client and the server.

## Tools and Resources

### MCP tools

A tool is an action the server exposes for the client to call.

In this project, the MCP tools are:

- `search_trails`
- `search_parks`
- `search_stats`
- `search_park_summary`

They are best understood as:

`public protocol-exposed wrappers around internal application logic`

In practical Python terms, each MCP tool:

1. accepts structured arguments from the client
2. validates those arguments
3. calls the real backend query logic
4. shapes the result into an MCP-friendly payload

So yes, it is fair to think of the MCP tools as functions, and more specifically as wrapper functions around existing backend functions.

### MCP resources

A resource is something the client reads as stable context rather than calls as an action.

In this project, the resources are:

- `dataset_overview`
- `park_lookup`
- `search_methodology`

Even if a resource is produced by Python code under the hood, conceptually it is still “readable named content,” not an action like a tool call.

### Core distinction

- `tool` = do something with arguments
- `resource` = read this existing context

## How the English-to-Tool Step Works

In the MCP path, the user starts with English in a client such as `Claude Desktop`.

The rough flow is:

1. the user asks in English
2. the client sees the available tool names, descriptions, and schemas
3. the model inside the client decides whether to call a tool
4. the client sends a structured tool call to the MCP server
5. the MCP server executes the structured call
6. the client uses the result in its final answer

That means the MCP server does not parse the user’s original English itself.

Instead:

- the `model + client stack` usually performs the English-to-tool step
- the MCP server receives already-structured arguments

This is one of the biggest differences from the project’s earlier NLQ layer.

## MCP Tool Output vs the MCP Protocol

The MCP protocol defines the outer structure for a tool result, but it does not require project-specific fields like `summary`.

So:

- `summary` is a project design choice
- it is not a universal MCP requirement

The MCP result can include structured and/or unstructured content.

In this project, the tool wrappers return compact JSON-like dictionaries because that is a useful shape for:

- deterministic outputs
- client narration
- testing

But “always JSON with a summary” is not itself the MCP rule. It is the local contract chosen for `nps-hikes`.

## Internal Function vs API Endpoint vs NLQ Tool vs MCP Tool

Using `search_trails` as the example:

### Internal function

This is the core Python logic that actually retrieves trail data.

Mental model:

`given structured filters, return trail data`

### API endpoint

This is the HTTP wrapper around internal logic.

Mental model:

`expose the trail search capability to web/API clients`

### NLQ tool

This is a tool schema shown to the local LLM used by the `/query` endpoint.

Mental model:

`help my own app's LLM choose a structured action from English`

It is not a public MCP tool. It is part of the app’s internal NLQ pipeline.

### MCP tool

This is a real public capability exposed by the MCP server.

Mental model:

`publish the trail search capability to external MCP clients`

### Short comparison

- internal function: does the work
- API endpoint: exposes the work over HTTP
- NLQ tool: helps the local LLM decide which work to call
- MCP tool: exposes the work to external MCP clients

## NLQ Tools vs MCP Tools

The project already had “tools” before MCP in the natural-language query stack.

Those NLQ tools and MCP tools are similar in spirit, but they live at different layers.

### NLQ tools

The NLQ tools are:

- internal tool definitions shown to the local LLM
- part of the `/query` flow
- used to translate English into structured parameters

They help produce the call.

### MCP tools

The MCP tools are:

- real externally exposed protocol capabilities
- discoverable by any MCP-compatible client
- callable over MCP transports

They are the call surface.

### Key difference

- NLQ tools help generate structured intent from English
- MCP tools expose structured capabilities to outside clients

## Why Hosted Model Clients Often Feel Better at the English-to-Tool Step

One real tradeoff surfaced clearly:

- frontier clients such as `Claude Desktop` generally do better at interpreting English and selecting tool arguments
- local open-source models can require more prompt tuning and normalization work

That makes hosted or stronger external clients attractive for:

- negation
- ambiguity
- recovery from mistakes
- tool selection quality

But the local NLQ approach still has important strengths:

- fully local
- free to run after setup
- privacy-preserving
- under full app control

So the tradeoff is roughly:

- hosted client parsing = stronger out of the box
- local app-owned parsing = more private and controllable

## Brick 3: What Transport Means

A `transport` is just the way MCP messages travel between the client and the server.

Transport is not:

- the tool definition
- the resource definition
- the backend query logic

It is only the communication channel.

Useful analogy:

- MCP = the shared language
- transport = the delivery method

The same MCP server can expose the same tools and resources over different transports.

## `stdio` vs local HTTP vs remote HTTP

### `stdio`

With `stdio`:

- the client launches the server process directly
- the client talks to that process over standard input and standard output

Mental model:

`the client starts the server and talks to it directly`

### local HTTP

With local HTTP:

- the server is already running
- the client connects to it by URL on the same machine
- the server still runs on the user’s laptop

Mental model:

`the client connects to an already-running local service`

### remote HTTP

With remote HTTP:

- the same HTTP-style model applies
- but the server is reachable somewhere beyond the current machine

Examples:

- a deployment on a cloud platform
- a service running inside a company network
- a local/private server exposed through a tunnel

Mental model:

`the client connects to an already-running reachable service`

## The Biggest Transport Distinction

The cleanest contrast is:

- `stdio` = the client starts the server
- `HTTP` = the client connects to a server that is already running

That is why `stdio` feels simpler:

- no URL
- no port
- no host selection

And it is why HTTP feels more like a service architecture:

- choose a host
- choose a port
- expose an endpoint path
- start the server before the client connects

## `localhost`, Port, and URL

These terms matter most once HTTP enters the picture.

### `localhost`

`localhost` means:

- this same machine
- my own laptop
- not some remote internet host

So a local HTTP MCP server can still be completely local and free.

### Port

A port is a numbered service entry point on a machine.

One laptop can run multiple services at once, so they need different ports.

Examples:

- Streamlit on one port
- FastAPI on another port
- MCP server on another port

### URL

A URL is the full address the client uses to reach a service.

Example:

`http://localhost:8000/mcp`

Broken down:

- `http://` = the communication style
- `localhost` = this machine
- `8000` = the service port
- `/mcp` = the endpoint path

## Why `stdio` Does Not Need a URL or Port

With `stdio`, the client already has a direct connection to the exact server process it launched.

There is nothing to find.

So the client does not need:

- a host
- a port
- a URL

With HTTP, the server is already running independently, so the client needs an address telling it where to connect.

That is why HTTP requires:

- host
- port
- path

## Local HTTP Does Not Mean Paid Hosting

One key clarification from the discussion:

`remote-capable` does not automatically mean `deployed` or `paid`.

A local HTTP MCP server can run entirely on:

- the user’s own laptop
- `localhost`
- a local-only port

So adding local HTTP is still:

- local
- free
- useful for learning

What it does not automatically provide is ChatGPT integration.

## Why Local HTTP Is Still a Good Phase 3

Even without immediate ChatGPT payoff, local HTTP is meaningful because it teaches the second major MCP server shape:

- subprocess-style MCP via `stdio`
- service-style MCP via HTTP

That matters because it proves:

- the transport layer is separate from the tool/resource layer
- the same MCP surface can survive a transport change
- the project is not conceptually tied to subprocess launch

So the payoff is architectural understanding rather than instant product reach.

## Restaurant Analogy Extended

The restaurant analogy was useful throughout the discussion.

### Base mapping

- user = diner
- client = waiter
- MCP server = kitchen
- laptop = building
- backend logic/data = pantry, recipes, and ingredients

### `stdio`

`stdio` is like the waiter walking directly into the kitchen and talking to it personally.

The waiter does not need a street address or service window because the waiter already has direct access to the kitchen interaction.

### local HTTP

Local HTTP is like the kitchen being open at a service counter inside the same building.

The waiter does not start the kitchen. The kitchen is already open. The waiter just goes to the right counter and places the order.

### remote HTTP

Remote HTTP is like sending the order to another kitchen location that is reachable from here.

Same menu idea, different location and route.

### `localhost`, port, and URL in the analogy

- `localhost` = this same building
- `port` = which numbered service counter in the building
- `URL` = the full instructions telling the waiter which building, which counter, and which service path to use

## Project-Specific Mapping

The MCP concept diagram maps cleanly to the project like this:

- user = you
- MCP host = `Claude Desktop`, `MCP Inspector`, or another assistant shell
- MCP client = the MCP-speaking part inside that host
- MCP server = `nps_hikes_mcp`
- tools = `search_trails`, `search_parks`, `search_stats`, `search_park_summary`
- resources = `dataset_overview`, `park_lookup`, `search_methodology`

What the simplified MCP concept diagram leaves out is the project’s internal backend:

- `api/queries.py`
- database access
- local dataset

Those are behind the MCP server boundary.

## Final Takeaway

The most useful summary from the discussion is:

- MCP is the protocol
- transport is how messages travel
- `stdio` means the client launches the server
- HTTP means the client connects to an already-running server
- local HTTP is still local
- tools are public callable capabilities
- resources are stable readable context
- the MCP server is a structured capability provider, not the natural-language assistant itself
