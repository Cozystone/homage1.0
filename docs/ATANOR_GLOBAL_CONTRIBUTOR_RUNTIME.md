# ATANOR Global Contributor Runtime

ATANOR Cloud Brain now uses a real brokered contributor runtime. The minimum valid network size is one active peer; adding a second or hundredth peer uses the same protocol without a rewrite.

## Runtime Roles

- Cloudflare Worker Broker: tracker and coordinator.
- KV/R2: public fragment seed cache.
- Contributor Node: peer that performs safe public-only work.
- Content Hash: torrent-like piece hash for fragments.
- Shard Registry: swarm map for topics and fragment hashes.
- Credit Ledger: contribution accounting, not cryptocurrency.
- Atlas/Admin: honest network-state visualization.

## Network States

- `remote_broker_connected`: broker is reachable but no active peer is currently verified.
- `active_single_peer`: one active contributor peer is registered and heartbeating.
- `active_multi_peer`: two or more contributor peers are active.
- `degraded` / `remote_error`: broker or storage is unhealthy.

One peer is operational, but fragments remain `single_peer_pending` and `requires_cross_check=true`. Multi-peer validation is required before any fragment can be treated as strongly verified.

## Required Environment

```powershell
$env:ATANOR_CLOUD_PROVIDER="cloudflare"
$env:ATANOR_CLOUD_MODE="remote"
$env:ATANOR_CLOUD_ENDPOINT="https://<worker>.workers.dev"
$env:ATANOR_CONTRIBUTION_ENABLED="true"
$env:ATANOR_DEV_SEED_PUBLIC_TASKS="true" # dev seeding only
```

## Contributor Commands

```powershell
python -m apps.api.app.workers.contributor_node --status
python -m apps.api.app.workers.contributor_node --dry-run
python -m apps.api.app.workers.contributor_node --once
python -m apps.api.app.workers.contributor_node --loop --interval 30
```

The runner registers a peer, sends heartbeat, polls a public-only task, executes bounded work, submits a content-addressed fragment, and prints the `fragment_id`, `content_hash`, `verification_state`, and storage backend when available.

## Privacy Boundary

The runtime rejects tasks or fragments containing local file paths, Payload Vault data, chat logs, raw private documents, local URLs, localhost/private IP URLs, or executable markers. User UI must not expose raw peer hashes, device names, IP addresses, exact locations, private graph content, or Vault payloads.

