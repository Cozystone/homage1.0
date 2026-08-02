# ATANOR SPLATRA Cosmos Evaluator

Status: proof-only candidate evaluator.

`packages/agentic_micro_os/splatra_evaluator.py` scores SPLATRA visual candidates
inside the Agentic Micro-OS boundary. It reuses the SPLATRA Turbovec proof
functions and emotion-to-visual control mapping.

## What It Measures

- orb particle compression ratio,
- orb reconstruction error,
- particle budget,
- target FPS guard,
- bounded emotion control output.

Optional city proof can be requested, but the default API path keeps evaluation
small for Lab smoke tests.

## What It Does Not Do

- It does not apply patches.
- It does not execute generated code.
- It does not launch a renderer.
- It does not mutate Local Brain or production Cloud Brain stores.
- It does not call an external LLM or sLLM.

## Current API

- `POST /api/agentic-os/splatra/evaluate`

The output is a score and review decision such as `proposal_review_ready` or
`needs_revision`. Human approval remains required before any real patch or
runtime change.
