# ATANOR Local-Cloud Sync Contract

ATANOR does not upload the user's brain to the cloud. It shares only safe graph
deltas when allowed, and receives only bounded public knowledge fragments when
useful.

## Boundary

ATANOR remains local-first. The Local Brain owns private memory, the Payload
Vault, Ghost Shell topology, and final native generation. Cloud Brain is an
assistive public knowledge layer. It may provide public ontology fragments,
evidence summaries, and relation candidates, but it must not generate final
answers or overwrite trusted local memory.

## Patch Sync

Patch Sync sends only safe changes, not raw memory. A patch can include concept
IDs, relation candidates, confidence deltas, edge weight deltas, provenance,
privacy classification, trust score, schema version, snapshot lineage, and
learning-run lineage.

A patch must not include private raw documents, private chat messages, local
file paths, full database content, Payload Vault records, or full Local Brain
graph dumps. The Alpha implementation enforces this in
`apps/api/app/services/brain_sync.py` before a patch preview is returned.

## Graph Delta Compression

Graph Delta Compression sends the difference between snapshots or learning
runs, not the full graph. The current contract emits:

- `nodes_added`
- `edges_added`
- `edges_strengthened`
- `edges_weakened`
- `concepts_merged`
- `aliases_added` as hashes, not raw aliases
- `sources_quarantined` as hashes
- `confidence_delta`
- `trust_delta`

This keeps low-resource devices from pushing uncontrolled graph payloads.

## Trust And Provenance

Every patch or fragment carries trace metadata such as patch ID, fragment ID,
origin brain ID, source type, source hash, checksum, privacy level, trust score,
verification status, creation time, expiration time, and schema version.

Conflict priority is:

1. `local_private`
2. `local_verified`
3. `local_repeated_memory`
4. `cloud_verified`
5. `cloud_unverified`

If a cloud fragment conflicts with trusted Local Brain memory, Local Brain wins.

## Fragment Orchestrator

The Fragment Orchestrator decides how much Local Brain, Cloud Brain, and Working
Memory should participate in a request. It evaluates privacy, local confidence,
graph density, evidence availability, runtime mode, memory pressure, cloud
policy, and whether a bounded fragment is needed.

Private or personal queries set `cloud_weight = 0`. High local confidence
shrinks or disables Cloud Brain assist. Low-confidence public queries may
request a bounded Cloud Brain fragment.

## Bounded Fragment Package

Cloud Brain may only return a small package with explicit limits:

- `max_nodes`
- `max_edges`
- `max_bytes`
- `ttl_seconds`
- `max_depth`
- `allowed_source_types`

Fragments attach to Working Memory first. They are not written to permanent
Local Brain memory unless later verification and policy allow promotion.

## Snapshot And Rollback

Permanent memory changes must be attached to versioned learning runs and
snapshots. Chat should run against a specific snapshot and should not mutate
Local Brain unless explicit learning-from-chat is enabled.

## Alpha Status

Implemented now:

- Safe graph patch preview
- Deterministic graph delta compression
- Fragment orchestration diagnostics
- Bounded fragment assembly
- Working Memory-only fragment attach
- Local-over-cloud conflict priority
- FastAPI endpoints under `/api/brain-sync`
- Unit/API tests for privacy, orchestration, working memory attach, and conflict

Not implemented yet:

- Production Cloud Brain service
- Real P2P payload transport
- Automatic fragment promotion
- Full snapshot rollback UI
- Public marketplace or token economy
