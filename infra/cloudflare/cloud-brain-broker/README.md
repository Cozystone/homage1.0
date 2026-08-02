# ATANOR Cloudflare Cloud Brain Broker

This is the preferred low-cost consumer/global edge path for ATANOR Cloud Brain.

It keeps the cloud provider as a control plane and hot-fragment store. Heavy
public work must be performed by opt-in Contributor Nodes.

## Components

- Cloudflare Workers: broker API and validation
- R2: public fragment envelopes and graph delta objects
- KV: node registry, task registry, credit ledger, hot metadata
- D1: optional relational metadata once needed
- Queues: optional public task dispatch

## Routes

The Worker implements the same Cloud Brain contract as AWS:

- `GET /cloud/status`
- `POST /cloud/register-node`
- `POST /cloud/heartbeat`
- `POST /cloud/tasks/poll`
- `POST /cloud/tasks/submit`
- `POST /cloud/fragments/put`
- `GET /cloud/fragments/query`
- `GET /cloud/shards`
- `GET /cloud/credits`

## Privacy Boundary

The Worker rejects:

- `raw_text`
- private Payload Vault contents
- local file paths
- private graph dumps
- chat logs
- arbitrary executable payloads

Cloud fragments must set:

```json
{
  "raw_payload_exported": false
}
```

## Deployment

Install Wrangler and authenticate manually:

```powershell
npm install -g wrangler
wrangler login
```

Create storage:

```powershell
wrangler kv namespace create ATANOR_NODES
wrangler kv namespace create ATANOR_TASKS
wrangler kv namespace create ATANOR_CREDITS
wrangler r2 bucket create atanor-cloud-fragments-dev
```

Copy `wrangler.toml.example` to `wrangler.toml` and fill in the KV namespace IDs.

Optional:

```powershell
wrangler d1 create atanor-cloud-brain-dev
wrangler d1 execute atanor-cloud-brain-dev --file schema.sql
wrangler queues create atanor-public-tasks-dev
```

Set the broker secret before enabling any mutating route:

```powershell
wrangler secret put ATANOR_BROKER_API_KEY
```

Deploy:

```powershell
wrangler deploy
```

Local ATANOR env:

```powershell
$env:ATANOR_CLOUD_PROVIDER="cloudflare"
$env:ATANOR_CLOUD_MODE="remote"
$env:ATANOR_CLOUD_ENDPOINT="https://atanor-cloud-brain-broker-dev.<account>.workers.dev"
$env:ATANOR_CLOUD_API_KEY="<broker-secret>"
$env:ATANOR_CONTRIBUTION_ENABLED="true"
```

`GET /cloud/status` and `GET /cloud/network` remain readable without the
secret. All mutation and contributor-state routes fail closed when the Worker
secret is missing or the caller does not supply the matching key.

## Why Cloudflare First

Cloudflare is a better first candidate for consumer Cloud Brain because public
fragments are edge-shaped: many tiny requests, small public JSON envelopes, and
hot/cold object access. AWS remains valuable for enterprise VPC/customer
deployment, but should not become the default centralized compute plane.

## Non-goals

- No full Cloud Brain copy per user
- No private data upload
- No centralized heavy crawler
- No GPU workloads
- No external LLM
- No blockchain or token transfer
