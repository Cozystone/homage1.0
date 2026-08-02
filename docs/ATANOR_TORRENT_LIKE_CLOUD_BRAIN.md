# ATANOR Torrent-Like Cloud Brain

ATANOR's Cloud Brain borrows torrent primitives without becoming blockchain or libp2p in this release.

| Torrent Primitive | ATANOR Runtime |
| --- | --- |
| Tracker | Cloudflare Worker Broker |
| Peer | Contributor Node |
| Piece hash | `content_hash = sha256(canonical_fragment)` |
| Seed cache | KV/R2 fragment store |
| Swarm map | Shard registry |
| Ratio/accounting | Credit ledger |
| Trust layer | Verification state |

## Fragment Rules

- `raw_payload_exported=false` is mandatory.
- `privacy_classification=public_only` is mandatory.
- `fragment_id=frag_<first16(content_hash)>`.
- Duplicate content hashes update submission metadata but do not create duplicate graph content.
- Single-peer submissions are `single_peer_pending`, low confidence, and require cross-check.

## Storage

R2 is preferred for larger public fragment storage. KV is acceptable for the current small-fragment proof. If R2 is missing, the broker reports `r2_available=false` and `fragment_store=kv`.

