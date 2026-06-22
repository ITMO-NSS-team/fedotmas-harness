<div align="center">

<img src="https://raw.githubusercontent.com/ITMO-NSS-Team/fedotmas/main/assets/logo.svg" alt="logo" width="180"/>

# `FEDOT.MAS`

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776ab.svg)](https://python.org)

</div>

> [!WARNING]
> Early development (v0.1). The API will change between versions.

A tiny typed dataflow engine for systems that build up a shared state. A thin LLM layer on top turns it into a multi-agent framework.

## Install

Install from git with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/ITMO-NSS-team/fedotmas-harness.git
cd fedotmas-harness
uv sync --all-packages
```

## Packages

- [`fedotmas`](packages/fedotmas): engine, typed SDK, and JSON DSL.
- [`fedotmas-llm`](packages/fedotmas-llm): the LLM extension. Agents, provider backends, serving. Early.
- [`fedotmas-meta`](packages/fedotmas-meta): the meta-agent that builds systems from a task description. Early.

## Articles

- **Does going multi-agent pay off, and can you auto-pick a pattern per task?** · [EN](https://dev.to/enorth/does-going-multi-agent-pay-off-and-can-you-auto-pick-a-pattern-per-task-15ld) · [RU](https://habr.com/ru/articles/1047422/)
