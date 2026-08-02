# ATANOR Selfhood Runtime Lab UI

## Purpose

Selfhood Runtime Lab is the first user-visible proof surface for Selfhood Runtime v0.
It shows the proof-only autonomous self-model loop that observes input, detects a
deficit, deliberates locally, checks safety gates, proposes an action, and waits
for explicit user approval.

This panel is intentionally a demo/proof summary. It does not call mutation
endpoints and does not promote candidates.

## What The Panel Shows

- runtime state and proof-only badges
- connected proof axes: Autonomy Kernel, Digital Life Kernel, MiroFish,
  Promotion Gate, Tabularis, Atlas Router, Voice Loop, and Logical Sphere
- latest selfhood cycle summary
- privacy, promotion, route, and safety gate results
- a Morning Brief / Morning Gift style summary
- hard limitations and future gate requirements

## What It Does Not Allow

- no production `verified_store_v0` mutation
- no Local Brain write
- no candidate store mutation
- no real candidate promotion
- no real P2P connection
- no cloud upload
- no generated code execution
- no real hot-swap
- no always-on microphone
- no AGI or real consciousness claim

## User Approval Model

The UI represents proposals, not actions. Any future action that writes durable
memory, promotes candidate knowledge, routes peer data, changes code, or enables
voice capture must pass a separate user approval gate.

## Current Data Source

The first implementation uses a local static proof summary object in
`apps/web/app/SelfhoodRuntimePanel.tsx`. This keeps the slice read-only and
avoids adding API surface while the surrounding worktree is mixed.

## Future API Integration

Future work may add read-only endpoints such as:

- `GET /api/selfhood-runtime/status`
- `GET /api/selfhood-runtime/proof-summary`

Those endpoints should only summarize proof state. They must not trigger a
selfhood cycle, write Local Brain, mutate Cloud Brain, promote candidates, or
start background learning.

## Future Voice/Text Interaction

Text remains the primary input path. Voice transcript input may enter the same
runtime bus later, but always-on microphone behavior is out of scope and must
require a separate consent gate.

## Future Local Brain Memory Approval Gate

Selfhood Runtime may eventually propose Local Brain memory writes, but v0 does
not write memory. A future gate must require explicit user review, pre/post hash
checks, privacy review, and rollback metadata before any durable write.
