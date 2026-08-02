# ATANOR Browser Read Gate

Status: proof-only public snapshot reader.

`packages/agentic_micro_os/browser_read.py` implements the first Browser Read
connector. It accepts a URL and already-visible text snapshot from an allowlisted
host, then returns a hashed `AgentObservation`.

## Boundaries

- Allowed hosts: `127.0.0.1`, `localhost`, `docs.local`.
- No network fetch is performed by the connector.
- No browser is controlled.
- No JavaScript is evaluated.
- Private markers such as `raw_private_memory`, `private_*`, `authorization`,
  `cookie`, and `token` are rejected.

## Purpose

This gate lets future ATANOR agents inspect a safe summary of what the UI already
shows, while keeping browser control and private data upload out of scope.

## Current API

- `GET /api/agentic-os/browser-read/status`
- `POST /api/agentic-os/browser-read`

The response keeps `browser_automation=false`, `arbitrary_js_eval=false`, and
`private_payload_sent=false`.
