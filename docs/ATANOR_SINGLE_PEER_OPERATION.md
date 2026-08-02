# ATANOR Single Peer Operation

ATANOR Cloud Brain can operate with one active contributor peer. This is a real network runtime, not a local mock, as long as the contributor talks to the remote Cloudflare broker.

## What One Peer Can Do

1. Register with the remote broker.
2. Send heartbeat.
3. Poll a public-only task.
4. Execute the task locally within resource limits.
5. Submit a content-addressed fragment.
6. Store the fragment in KV/R2.
7. Query the fragment back by topic or content hash.
8. Update Atlas/Admin counts.

## Honest Limitations

- One peer is not enough for strong verification.
- Fragments stay `single_peer_pending`.
- Atlas may say "single active contributor peer" but must not claim "worldwide network live".
- This release is brokered Cloudflare coordination, not direct libp2p.
- This release is not blockchain and contribution credit is not a financial asset.

## Minimal Proof

```powershell
Invoke-RestMethod "$env:ATANOR_CLOUD_ENDPOINT/cloud/status"
python -m apps.api.app.workers.contributor_node --once
Invoke-RestMethod "$env:ATANOR_CLOUD_ENDPOINT/cloud/status"
Invoke-RestMethod "$env:ATANOR_CLOUD_ENDPOINT/cloud/fragments/query?limit=5"
```

Expected state after a successful `--once`: `network_state=active_single_peer`, `active_peers=1`, `submitted_fragments>=1`, `fragment_store=kv` or `r2`.
