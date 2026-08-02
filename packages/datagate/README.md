# DataGate

Deterministic, rule-based quality gate for ATANOR. DataGate takes raw local
text documents from `data/raw`, runs them through an ordered fail-fast filter
chain, scores the survivors, and partitions everything into `cleaned` and
`rejected` with full per-document metadata.

DataGate is a **pure library**: it has zero FastAPI / web imports and depends
only on `pydantic>=2` plus the Python standard library. `apps/api` wraps it.

## Install (editable)

```bash
pip install -e packages/datagate
```

## Usage

```python
from datagate import DataGateConfig, PipelineRunner

config = DataGateConfig(
    input_dir="data/raw",
    cleaned_dir="data/cleaned",
    rejected_dir="data/rejected",
    metadata_dir="data/metadata",
)
report = PipelineRunner(config).run()
print(report.total, report.accepted, report.rejected)
```

## Pipeline

```
data/raw/*.{txt,md}
        -> discover & load (sorted, deterministic order)
        -> filter chain (fail-fast):
             min_length          (char_count < min_chars after strip)
             duplicate_hash      (content already seen this run)
             special_char_ratio  (non-text symbol ratio > max)
             link_density        (URL-char ratio > max)
        -> QualityScorer (accepted docs only, 0-100)
        -> write outputs
```

### Outputs (full-batch overwrite every run)

- `data/cleaned/{doc_id}.txt` ??accepted docs, original text verbatim
- `data/rejected/{doc_id}.txt` ??rejected docs, original text verbatim
- `data/metadata/documents.jsonl` ??one `DocumentMetadata` JSON object per
  input file, in processing order

### Invariants

- every input file ??exactly one jsonl line
- `status="rejected"` ??`rejection_reason` and `rejected_by` are non-null
- `status="accepted"` ??`quality_score` is non-null and a `cleaned/` file exists
- `report.accepted + report.rejected == report.total`

## Determinism

Files are processed in sorted path order; `doc_id` is `sha256(normalized_text)[:16]`;
no randomness or timestamps enter any decision path. Re-running on identical
input yields byte-identical accept/reject partitions and identical `doc_id`s
(only `run_id` and `processed_at` differ between runs).

## Config defaults

| Setting | Default |
|---|---|
| `min_chars` | 200 |
| `max_special_char_ratio` | 0.30 |
| `max_link_density` | 0.40 |

## Tests

```bash
pip install -e "packages/datagate[dev]"
pytest packages/datagate
```
