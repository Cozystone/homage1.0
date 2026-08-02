# ADR-0001: Monorepo Skeleton

## Status

Accepted

## Context

The PRD calls for a shared repository memory that both Codex and Claude can use through project state, task board, session log, context capsule, and handoff documents.

## Decision

Use a simple monorepo layout:

- `apps/api` for FastAPI
- `apps/web` for Next.js
- `docs` for PRD, architecture, and decisions
- root-level operating documents for state, task tracking, and handoff

## Consequences

- The repo is easy to run locally during Phase 0 and Phase 1.
- Future packages can be added without restructuring the initial apps.
- API and dashboard can evolve independently while sharing the same project docs.
