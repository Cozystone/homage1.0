# ATANOR Cloud Brain Real Architecture

This document separates the current runtime states so the product does not pretend that local simulation is the same as a remote Cloud Brain.

## State 1: `local_broker_mode`

Current default.

- The local FastAPI companion plays the Cloud Brain body.
- Cloud Brain UI may visualize local daemon-backed public/shared graph candidates.
- Contributor tasks are served by the local broker.
- No AWS is required.
- No remote API is contacted.
- Private Payload Vault data remains local.

Broker state:

```json
{
  "cloud_mode": "local_broker",
  "broker_state": "local_broker_mode"
}
```

## State 2: `remote_broker_mode`

Implemented for the Cloudflare dev broker.

- `ATANOR_CLOUD_PROVIDER=aws|cloudflare`
- `ATANOR_CLOUD_MODE=remote`
- `ATANOR_CLOUD_ENDPOINT=<API Gateway HTTPS URL>`
- optional `ATANOR_CLOUD_API_KEY`
- local contributor node can register against the remote broker
- heartbeat reaches the remote broker
- task polling and submission reach the remote broker
- small public fragments can be put/query through the remote broker
- failures report `remote_error` honestly

Broker state when connected:

```json
{
  "cloud_mode": "remote",
  "broker_state": "remote_connected"
}
```

Provider guidance:

- `cloudflare`: preferred consumer/global edge broker
- `aws`: enterprise/customer VPC or backup broker
- `local`: development/offline broker

Verified Cloudflare endpoint:

```text
https://atanor-cloud-brain-broker-dev.ntranet-store.workers.dev
```

Current dev storage:

- Workers API: active
- KV registries: active
- KV fragment fallback: active
- R2 fragment bucket: not enabled yet
- D1/Queues: optional and not required for this dev proof

Broker state when failed:

```json
{
  "cloud_mode": "remote",
  "broker_state": "remote_error"
}
```

## State 3: Future Full Cloud Brain

Not implemented yet.

- global shard registry
- many contributor nodes
- P2P payload transport
- proof-of-knowledge consensus
- public fragment reputation
- production contribution credit settlement
- large-scale cloud/edge routing

## Local Integration Contract

The local app keeps local mode and remote mode side by side.

Remote mode touches these local API paths:

- `/api/cloud-brain/status`
- `/api/cloud-brain/query`
- `/api/cloud-brain/ingest`
- `/api/contribution/status`
- `/api/contribution/register`
- `/api/contribution/heartbeat`
- `/api/contribution/poll`
- `/api/contribution/submit`
- `/api/contribution/credits`

When remote mode is configured, these routes call the remote broker. When it fails, they return `remote_error` rather than fake success.

## Privacy Contract

Never send:

- private Local Brain documents
- raw Payload Vault records
- chat logs
- local file paths
- full private graph dumps
- executable tasks

Allowed remote payloads:

- public contributor metadata
- heartbeat telemetry
- bounded public task results
- summary-only public fragments
- hash topology/concept metadata

## Environment Variables

```text
ATANOR_CLOUD_MODE=disabled|local_broker|remote
ATANOR_CLOUD_PROVIDER=local|aws|cloudflare
ATANOR_CLOUD_ENDPOINT=https://...
ATANOR_CLOUD_API_KEY=...
ATANOR_NODE_ID=atanor-local-peer
ATANOR_CONTRIBUTION_ENABLED=true|false
```

Legacy `HOMAGE_*` fallbacks are still supported where compatibility requires them.
