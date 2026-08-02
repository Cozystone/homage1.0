# Ego Network Proof Kernel

`packages/ego_network` is a proof-only package for ATANOR's constellation
ego-sync and Midnight Congress architecture.

It models:

- proof-only seed/DID-like identity;
- metadata-only ego cartridges;
- a local in-memory relay simulator;
- deterministic local Midnight Congress deliberation;
- proposal-only checkout/checkin;
- multi-device constellation sync planning;
- in-memory morning gift events.

It does not implement production DID/Web3 custody, cloud checkout, peer-network
transport, Local Brain replication, production mutation, production code
replacement, or generated code execution. Raw private data is not exported by
the proof relay. All checkin and merge results are proposal-only and require
user approval.

The seed identity accepts a 12-word phrase only for deterministic fixtures. It
stores a salted hash and a public fingerprint, never the raw phrase. Production
identity must use audited cryptographic libraries and explicit user custody.

Midnight Congress is a deterministic local simulator. The fixed speaker roles
are skeptic, builder, privacy_guard, router, domain_expert, and synthesis_chair.
No external LLM, peer network, or cloud relay is used.

Run tests:

```powershell
python -m pytest packages/ego_network/tests -q
```

Run proof:

```powershell
python -m packages.ego_network.proof
```

Generated proof outputs are audit data under `data/audits/ego_network` and
should not be committed.
