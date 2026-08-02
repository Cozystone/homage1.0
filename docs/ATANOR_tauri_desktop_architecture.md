# ATANOR Tauri Desktop Architecture

Status: design plan only.

ATANOR Desktop should wrap the existing web UI in a local-first Tauri shell and
run a local FastAPI sidecar when explicitly enabled. It must not bundle large
runtime data, model weights, candidate stores, or generated audit outputs.

## Shell

- Tauri hosts the web UI as the desktop surface.
- Text chat remains the primary input.
- Voice is optional and requires explicit push-to-talk or file input consent.
- No always-on microphone.

## Sidecar

- FastAPI sidecar is local-only by default.
- Startup performs health checks for API, verified store, candidate store, and
  optional voice runtime availability.
- Sidecar startup must not start long learning jobs.
- Sidecar startup must not promote candidate data.

## Data Policy

- Use an explicit local data directory outside packaged app assets.
- Do not bundle `data/cloud_brain`, model weights, candidate stores, payload
  shards, dumps, logs, or proof outputs.
- Model cache is opt-in and user-visible.
- Production `verified_store_v0` is never mutated by packaging logic.

## Update Strategy

- App update and model/cache update are separate flows.
- Schema migrations require dry-run report and user confirmation.
- Any future hot-swap remains proposal-only and review-gated.

## Safety Defaults

- no Local Brain writes during startup
- no cloud upload
- no real P2P unless explicitly enabled through reviewed runtime gates
- no generated code execution
- no always-on microphone
