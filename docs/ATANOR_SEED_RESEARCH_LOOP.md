# ATANOR Seed Graph Research Loop

ATANOR Seed Graph Research is an isolated public research layer for iterating on seed concepts, relation schemas, and benchmark questions before anything is promoted into a runtime brain.

## Boundaries

- Seed Graph is not Local Brain.
- Seed Graph is not a response template system.
- Seed Graph artifacts are public research candidates only.
- Seed Graph does not read or write the user's private Payload Vault.
- Seed Graph output is inspected through a read-only viewer at `/seed-research`.

## Main Commands

```powershell
python -m packages.seed_research.run_seed_iteration
python -m packages.seed_research.apply_feedback --run run_0001
python -m packages.seed_research.freeze_seed --run run_0001 --version seed-core-0.1
```

## Artifact Layout

```text
data/seed_research/
  runs/run_0001/
  feedback/feedback_log.jsonl
  benchmarks/seed_benchmark_questions.jsonl
  current/seed_concepts.jsonl
  current/seed_edges.jsonl
  current/seed_aliases.jsonl
  current/seed_manifest.json
  current/viewer_export.json
data/seed/
```

## Cloud Brain Web Seed Feeder

The Web Seed Feeder is a separate Cloud Brain candidate-input path. It can create public fragment candidates from configured public URLs, but it does not mutate Local Brain and does not fake Cloud Brain growth counts.

```powershell
python -m packages.cloud_brain.web_seed_feeder --once
python -m packages.cloud_brain.web_seed_feeder --once --force-enabled
```

Default state is disabled. Configure sources in:

```text
data/cloud_brain/web_seed_sources.json
data/cloud_brain/web_seed_feeder_state.json
```

Candidate fragments are written only to:

```text
data/cloud_brain/inbox/
```

Cloud Brain node and relation counts should change only after the existing ingestion and verification pipeline consumes those candidates.

