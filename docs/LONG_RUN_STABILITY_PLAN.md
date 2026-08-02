# ATANOR Long-Run Stability Plan

ATANOR is designed to run for long local learning sessions without forcing the
browser or backend to hold the entire graph in memory.

## Stability Principles

1. Store long-term memory in SQLite WAL or a future vault driver.
2. Keep only active graph windows in RAM.
3. Render representative graph chunks in the browser, not the whole graph.
4. Use lazy retrieval for GraphRAG queries.
5. Commit ingestion work frequently so a reboot loses minutes, not days.
6. Apply synaptic decay and pruning to stale low-value edges.
7. Stop or throttle work before RAM, VRAM, or thermal limits are exceeded.

## Runtime Guardrails

- Backend graph queries must use limits tied to hardware tier.
- Frontend graph views should use chunking, sampling, or instanced rendering.
- Learning daemons must checkpoint state.
- Contributor Node work must remain opt-in and resource-limited.
- Cloud Brain tasks must be public-only and bounded.

## Failure Behavior

If ATANOR detects repeated resource pressure, API failures, SSE disconnects, or
graph render resets, it should record the failure, pause heavy work, and expose
the state honestly instead of pretending the run is healthy.
