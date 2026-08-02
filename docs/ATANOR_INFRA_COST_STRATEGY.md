# ATANOR Infrastructure Cost Strategy

ATANOR must remain local-first and commercially viable. The cloud provider is
not the brain. It is the control plane, shard registry, public fragment cache,
task broker, and contribution ledger.

## Core Rule

Cloud provider = control plane.

Contributor Nodes = heavy public work.

Local Brain = private user knowledge.

Cloud Brain = shared public world knowledge star.

## Why Not AWS-Centered Heavy Cloud

AWS can become expensive if ATANOR centralizes:

- crawling
- parsing
- embeddings
- large graph traversal
- GPU inference
- full user graph copies
- always-on managed graph databases

These remain non-goals for the initial commercial architecture.

Avoided services:

- Neptune
- OpenSearch
- RDS
- ECS/EKS
- SageMaker
- Bedrock
- large EC2
- centralized GPU workers

## Provider Roles

### Local

Used for development, offline operation, and private Local Brain.

### Cloudflare

Preferred consumer/global edge option:

- Workers for broker API
- R2 for hot/cold public fragment envelopes
- KV/D1 for registries and ledgers
- Queues for contributor task dispatch

### AWS

Preserved as an enterprise-compatible option:

- customer VPC
- compliance-oriented deployments
- backup provider
- optional remote provider path

## Cost Strategy

1. Free gets low-resolution hot Cloud fragments only.
2. Plus is $0 but compute-backed by opt-in Contributor Node work.
3. Pro pays for 24/7 background cloud farming.
4. On-Premise reduces cloud calls with local hot shard snapshots.
5. Director pays for cloud-hosted convenience and contribution exemption.

## Storage Strategy

Do not store a full Cloud Brain copy per user.

Use:

- shared Cloud Brain base
- user overlay metadata
- hot fragment cache
- encrypted snapshot metadata
- optional private cloud namespace for paid tiers

Never upload:

- raw private documents
- private Payload Vault records
- private Local Brain graph dumps
- chat logs
- local file paths

## Cost Model

Code:

- `packages/cost_model/pricing_defaults.json`
- `packages/cost_model/cost_model/model.py`

The model reports infrastructure gross margin separately from company net margin.
Provider price constants are editable assumptions and must be verified against
current bills before commercial launch.
