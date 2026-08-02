# ATANOR Midnight Congress Architecture

Midnight Congress is a proof-only local deliberation layer for ATANOR's
autonomous self-model loop. It is not a consciousness claim, current AGI
capability, peer consensus implementation, or self-modifying agency.

## Local Simulator

The proof implementation in `packages/ego_network` uses deterministic local
roles:

- skeptic;
- builder;
- privacy_guard;
- router;
- domain_expert;
- synthesis_chair.

Inputs are deficit signals, topic proposals, and optional public/synthetic ego
cartridge metadata. Outputs are arguments, a synthesis, proposed actions, and a
morning gift event.

## Deliberation Rules

- privacy_guard blocks `private_local_only` export.
- router references Atlas Router only conceptually; no peer network transport
  is used.
- synthesis always requires user approval.
- production mutation is false.
- Local Brain mutation is false.
- low-confidence topics become research proposals.
- contradiction topics retain skeptic objections.

## Morning Brief

The morning brief is a user-review event. It can summarize a checkout/checkin
proposal, a privacy block, a conflict, or a research recommendation. It never
executes generated code, promotes a candidate, writes Local Brain, or mutates the
production verified store.

## Relationship To Other Systems

- Autonomy Kernel supplies the deficit/self-model loop.
- Tabularis supplies the future privacy gate.
- Atlas Router supplies future route-risk policy.
- Atlas Congress provides a local-only preview shell for deliberation.
- Ego cartridges provide metadata-only proposal packages.

## Future Peer-Network Stages

Peer-network operation requires privacy gate maturity, promotion gate maturity,
audited identity custody, signed cartridge manifests, user-visible conflict
review, and clear rollback semantics. Until those gates mature, every checkin
is proposal-only and every sync plan is dry-run.
