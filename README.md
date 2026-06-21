<div align="center">

<img src="https://raw.githubusercontent.com/ITMO-NSS-Team/fedotmas/main/assets/logo.svg" alt="logo" width="180"/>

# `FEDOT.MAS`

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776ab.svg)](https://python.org)

</div>

> [!WARNING]
> Early development (v0.1). The API will change between versions.

A typed dataflow engine for systems that build up a shared state. A thin LLM layer on top turns it into a multi-agent framework.

## Approach

The idea behind the engine is that typed atoms read from and write to a shared memory, scheduled in supersteps until a goal is reached. The core `fedotmas` has no LLM vocabulary and no heavy dependencies. Model-specific code lives in an extension, built on the core's public API. `fedotmas-llm` adds agents, provider backends, and serving, and the engine still never names a model. Like Rust's `crates/`, our `packages/` holds the core and its extensions, so you depend only on the layer you need:

- code-only systems: just `fedotmas`, no provider, nothing to bind.
- agent systems: add `fedotmas-llm` and bind a backend at run time.

## Install

Install from git with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/ITMO-NSS-team/fedotmas-harness.git
cd fedotmas
uv sync --all-packages
```

## Packages

- [`fedotmas`](packages/fedotmas): engine, typed SDK, and JSON DSL.
- [`fedotmas-llm`](packages/fedotmas-llm): the LLM extension. Agents, provider backends, serving. Early.
- [`fedotmas-meta`](packages/fedotmas-meta): the meta-agent that builds systems from a task description. Early.

## Articles

- **Does going multi-agent pay off, and can you auto-pick a pattern per task?** · [EN](https://dev.to/enorth/does-going-multi-agent-pay-off-and-can-you-auto-pick-a-pattern-per-task-15ld) · [RU](https://habr.com/ru/articles/1047422/)


## Planned

- meta-agent M0: match a task to a pattern family, fill the roles, compile; the compiler acts as a deterministic critic
- serving: run a manifest over HTTP/SSE and MCP (`fedotmas-llm`); MCP, file/URI, and A2A capabilities wired by reference
- v0.2: wave epochs for joins, checkpoint-style resume/persistence
- reliability: a middleware seam plus retry/fallback combinators
- richer runtime memory (knowledge graphs) behind a store port
