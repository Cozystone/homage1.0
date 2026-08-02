# ATANOR Contributor Node Alpha

ATANOR Contributor Node Alpha is a local-first preview of future edge contribution. It lets a user's machine process safe, public-only verification jobs while keeping the private Local Brain, Payload Vault, chat logs, and local file paths sealed.

## Current Alpha State

- Runs through the local FastAPI companion.
- Exposes `/api/contribution/*` endpoints for status, registration, heartbeat, public task polling, single-task execution, pause, resume, disable, credits, and recent tasks.
- Uses a `LocalPreviewBroker` stub. This is not the production global Cloud Brain broker.
- Accepts only allowlisted public task types:
  - `public_fragment_validation`
  - `source_noise_check`
  - `duplicate_relation_check`
  - `graph_delta_compression`
  - `public_alias_review`
  - `freshness_check`
- Rejects payloads that request local files, private graphs, arbitrary network access, shell execution, script execution, or suspicious path markers.
- Records Contribution Credit as an internal Alpha score only. In this Alpha build it is not cryptocurrency, not a transferable token, and not a financial asset.

## Privacy Boundary

The Contributor Node must never share:

- Payload Vault records
- Local Brain private graph data
- chat logs
- local file paths
- raw private documents

Only public task payloads produced by a broker are eligible for processing.

## UI Semantics

The product UI must distinguish:

- Local Learning: builds and updates the user's private Local Brain.
- Contribution: optionally processes public verification tasks for the Cloud Brain roadmap.

In Alpha, Contribution is a preview surface. If the local companion is disconnected, the UI should display viewer/standby state instead of pretending that distributed compute is live.

## Production Roadmap

ATANOR is being built as a complete commercial product, not a throwaway demo. The Alpha guardrails exist so the product does not overclaim before the real network is online.

- Production Cloud Brain broker with signed task manifests.
- Real P2P/public-payload transport for approved public fragments.
- Remote attestation, sandboxing, and per-task resource budgets.
- Peer reputation and federated result verification.
- Optional settlement layer for contribution accounting. This may be blockchain-based or non-blockchain depending on legal, security, cost, and user-experience review.
- Clear separation between public contribution tasks and private Local Brain learning.
