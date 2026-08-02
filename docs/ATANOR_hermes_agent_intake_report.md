# ATANOR Hermes Agent Intake Report

Status: proof-only intake, no Hermes runtime execution.

Repository: `https://github.com/nousresearch/hermes-agent`

Observed clone commit during intake: `b1b20270c4e4dd9e179a9318543db061f49e5bd6`

License: MIT detected from `LICENSE`. Reuse is possible only with preserved
notice/provenance and per-file review. This slice copies no Hermes source code
into ATANOR.

## Architecture Signals

Hermes exposes useful architecture patterns:

- tool registry and toolset distribution;
- gateway and TUI separation;
- MCP as an edge extension mechanism;
- provider abstraction;
- cron/scheduled automation;
- skills and optional skills;
- trajectory compression;
- memory provider plugins;
- browser and terminal integrations.

## High Risk Components

These are not imported into ATANOR core:

- external model provider adapters;
- unrestricted terminal/shell execution;
- persistent memory provider implementations;
- gateway secrets and messaging connectors;
- real browser automation side effects;
- auto-install/setup flows.

## ATANOR Integration Recommendation

Use `clone_architecture_only` for v0. Reimplement concepts behind ATANOR
capability gates:

- model slot becomes ATANOR's own local model path;
- tools are capability-token gated;
- browser/API/MCP/cloud access is allowlisted and proof-only at first;
- Local Brain and Cloud Brain access goes through audited access roads;
- SPLATRA work happens inside a bounded Cosmos Cell;
- every mutation becomes a proposal requiring human approval.

## Non-claims

- Hermes code is not fully integrated.
- Hermes runtime was not executed.
- External LLM/sLLM providers are not enabled.
- Real browser automation and MCP servers are not connected.
