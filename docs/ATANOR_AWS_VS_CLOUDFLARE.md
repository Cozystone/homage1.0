# ATANOR AWS vs Cloudflare

ATANOR supports provider-agnostic Cloud Brain broker modes.

```text
ATANOR_CLOUD_PROVIDER=local | aws | cloudflare
ATANOR_CLOUD_MODE=disabled | local_broker | remote
```

## Recommendation

Consumer/global edge:

- Cloudflare first. The current dev broker is live at
  `https://atanor-cloud-brain-broker-dev.ntranet-store.workers.dev`.

Enterprise/customer VPC:

- AWS optional

Local development:

- local broker

## Cloudflare Strengths

- edge-native public fragment serving
- R2 for object storage without building a storage server
- Workers for tiny validation/broker API
- KV/D1/Queues options for progressive scaling
- good fit for hot fragment cache and low-latency global reads

## AWS Strengths

- enterprise familiarity
- customer VPC patterns
- IAM and organizational compliance controls
- predictable Lambda/API Gateway/DynamoDB/S3 serverless path
- easier integration with enterprise AWS customers

## Cost Hazard

AWS becomes risky if ATANOR turns into:

- centralized crawler
- centralized parser
- centralized graph database
- centralized GPU service
- centralized per-user storage clone

Cloudflare can also become expensive if R2 operations, Worker invocations, or D1
writes are unbounded. Both providers require plan-aware Cloud Budget limits.

## Shared Rule

Provider handles control plane and public hot fragments.

Contributor Nodes perform heavy public work.

No provider stores raw private Local Brain data.

## Current Verification

As of the Cloudflare remote-provider integration pass:

- FastAPI local companion runs with `ATANOR_CLOUD_PROVIDER=cloudflare`.
- `/api/cloud-brain/status` returns `broker_state=remote_connected`.
- `/api/contribution/status` returns `broker_state=remote_connected`.
- `/cloud/fragments/put` rejects raw private payload markers.
- Cloudflare R2 is not enabled yet, so public fragment envelopes use a KV fallback for dev only.

This means ATANOR has crossed from `local_broker_mode` into an actual remote
provider connection for the control plane. It does not yet mean production P2P,
blockchain settlement, or global Cloud Brain consensus are complete.
