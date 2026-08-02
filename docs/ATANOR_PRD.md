# ATANOR Product Requirements

## Product Promise

ATANOR is a local-first AI OS where private memory stays on-device, while
public knowledge grows through a contributor-powered Cloud Brain.

## Current Release Target

This repository is converging on a public alpha that is honest, runnable,
privacy-safe, and technically interesting. It is not yet a finished replacement
for mainstream LLM products.

## Core Product Surfaces

| Surface | Purpose | Current status |
| --- | --- | --- |
| Local Brain | Private Ghost Shell and Payload Vault on the user's machine | PARTIAL |
| Cloud Brain | Public, content-addressed graph fragments through a Cloudflare broker | PARTIAL |
| Unified Brain | Local and public graph context routed together inside Working Memory when explicitly enabled | PARTIAL |
| Atlas | Privacy-safe global relay visualization | PARTIAL/PREVIEW |
| Contributor Node | Opt-in public task execution and fragment submission | PARTIAL |
| Admin/Operator | Runtime, broker, task, fragment, and credit observability | PARTIAL |

## Required Architecture Boundaries

- External LLM answer generation remains disabled.
- ATANOR has no separate Dual Graph; Local Brain and Cloud Brain are source
  layers inside one Unified Ontology Graph.
- Private Local Brain data must not be uploaded.
- Payload Vault raw records must not be uploaded.
- Cloud fragments must be public-only and content-addressed.
- Atlas must not expose raw IP, exact location, device name, node ID, local
  file path, private graph data, or chat logs.
- UI must distinguish REAL, PARTIAL, PREVIEW, SCAFFOLD, and NOT_IMPLEMENTED
  states honestly.

## Three-Step Engine Flow

1. Collect: ingest local or public text, split it, and filter noise through
   DataGate.
2. Learn: extract concepts and relationships through Ontology Forge and store
   them in Knowledge Bakery / Ghost Shell.
3. Output: retrieve a lazy graph context and produce local native synthesis
   from that context.

## Cloud Brain Runtime Flow

1. Contributor Node opts in.
2. Local runtime registers with the Cloudflare remote broker.
3. Broker assigns safe public-only tasks.
4. Node validates and executes bounded public work.
5. Node submits a content-addressed public fragment.
6. Broker stores the fragment in KV or R2.
7. Fragment remains `single_peer_pending` until cross-check verification.
8. Atlas/Admin reflect the honest network state.

## Release Gates

- Trust: license, contributing guide, security guide, env example, clean README.
- Runtime: Cloudflare status, active peer proof, task submit, fragment query.
- UI: coherent terminology, no broken text, no preview/live confusion.
- Privacy: no raw IP, secrets, local paths, device names, or private data.
- Build: backend tests, web build, py_compile, and UI audit.

## Not Yet

- Production multi-peer verification.
- Full ChatGPT-level decoder.
- Direct libp2p payload transport.
- Blockchain/token economy.
- Production R2/D1/Queue hardening.
- Broadly trusted signed desktop distribution.
