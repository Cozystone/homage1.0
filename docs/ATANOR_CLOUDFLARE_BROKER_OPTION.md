# ATANOR Cloudflare Broker Option

Cloudflare is the preferred first candidate for the consumer Cloud Brain edge
control plane.

## Why Cloudflare

ATANOR Cloud Brain traffic is edge-shaped:

- many small public fragment requests
- public JSON envelope fetches
- hot/cold object reads
- lightweight task dispatch
- contributor heartbeat metadata

Cloudflare Workers, R2, KV, D1, and Queues match this shape without requiring an
always-on server or managed graph database.

## Scaffold

Path:

`infra/cloudflare/cloud-brain-broker/`

Files:

- `src/worker.ts`
- `wrangler.toml.example`
- `wrangler.jsonc`
- `schema.sql`
- `README.md`

## Live Dev Broker

Current verified development broker:

```text
https://atanor-cloud-brain-broker-dev.ntranet-store.workers.dev
```

Verified state:

- Worker deploy: success
- `/cloud/status`: `status=ok`
- local FastAPI `/api/cloud-brain/status`: `cloud_provider=cloudflare`, `cloud_mode=remote`, `broker_state=remote_connected`
- Contributor status: `broker_state=remote_connected`
- private payload export: blocked

Cloudflare account note:

- R2 is not enabled on the current account yet.
- The dev Worker therefore uses `ATANOR_FRAGMENTS_KV` as the public fragment store fallback.
- This is acceptable for dev verification, but production should enable R2 for fragment payload envelopes.

## Contract

Same as AWS broker:

- `GET /cloud/status`
- `POST /cloud/register-node`
- `POST /cloud/heartbeat`
- `POST /cloud/tasks/poll`
- `POST /cloud/tasks/submit`
- `POST /cloud/fragments/put`
- `GET /cloud/fragments/query`
- `GET /cloud/shards`
- `GET /cloud/credits`

## Storage Mapping

| Layer | Cloudflare Service |
| --- | --- |
| Broker API | Workers |
| Public fragment envelopes | R2 in production, KV fallback in current dev |
| Node/task/credit registry | KV |
| Relational metadata | D1 optional |
| Task dispatch | Queues optional |

## Local Config

```powershell
$env:ATANOR_CLOUD_PROVIDER="cloudflare"
$env:ATANOR_CLOUD_MODE="remote"
$env:ATANOR_CLOUD_ENDPOINT="https://atanor-cloud-brain-broker-dev.ntranet-store.workers.dev"
$env:ATANOR_CLOUD_API_KEY="<optional>"
$env:ATANOR_NODE_ID="atanor-local-dev-001"
$env:ATANOR_CONTRIBUTION_ENABLED="true"
```

Start local companion in remote mode:

```powershell
$env:PYTHONPATH="apps/api;packages/knowledge_bakery;packages/rag_engine;packages/model;packages/neuro_efficiency;packages/cost_model;packages/guard;packages/datagate;packages/ontology_forge;packages/trainer"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8500
```

## Limits

This is not the full Cloud Brain yet.

It does not implement:

- P2P transport
- global consensus
- token economy
- heavy crawling
- private cloud storage
- external LLM inference

Production gaps before public launch:

- enable R2 and move public fragment envelopes off KV fallback
- add authenticated broker writes
- add rate limits per node and IP
- add durable audit logs for credit verification
- keep rejecting raw text, local paths, chat logs, and private Payload Vault data
