# Handoff: Claude Code

> Author: Claude Code
> Date: 2026-06-11
> Milestone: 2 — DataGate (core package only)
> Scope of this handoff: `packages/datagate` and its tests. **No** API wiring,
> **no** frontend changes, **no** crawling, **no** LLM judging.

## Change Report

### New Files

```
packages/datagate/
├── pyproject.toml                  # name=datagate, deps: pydantic>=2, py>=3.11
├── README.md
├── datagate/
│   ├── __init__.py                 # public API re-exports
│   ├── config.py                   # DataGateConfig (thresholds + paths)
│   ├── models.py                   # Document, DocumentMetadata, FilterResult, RunReport
│   ├── hashing.py                  # normalize_text, content_hash, doc_id_for
│   ├── io.py                       # discover_files, load_document, write_outputs
│   ├── scoring.py                  # QualityScorer
│   ├── runner.py                   # PipelineRunner
│   └── filters/
│       ├── __init__.py             # default_filters(config) -> ordered chain
│       ├── base.py                 # BaseFilter (ABC) + reset()
│       ├── min_length.py
│       ├── duplicate_hash.py
│       ├── special_char_ratio.py   # + compute_special_char_ratio()
│       └── link_density.py         # + compute_link_density()
└── tests/
    ├── conftest.py                 # temp dirs + fixture corpus (8 scenarios)
    ├── test_models.py
    ├── test_filters.py
    ├── test_scoring.py
    └── test_runner.py
```

### What Was Built

- **Deterministic core.** Files processed in sorted path order. `doc_id =
  sha256(normalize_text(text))[:16]`. `normalize_text` = NFC → `strip()` →
  collapse internal whitespace runs to a single space. No randomness, no
  timestamps in any decision path (`processed_at`/`run_id` are informational
  and the determinism test ignores them).
- **Pure library.** Zero FastAPI / web imports (verified by grep + an import
  smoke test). Depends only on `pydantic>=2` and the stdlib (`re`, `hashlib`,
  `unicodedata`, `pathlib`, `shutil`, `logging`, `datetime`).
- **Fail-fast filter chain** in canonical order: `min_length` →
  `duplicate_hash` → `special_char_ratio` → `link_density`. A document is
  rejected by the *first* failing filter; remaining filters are skipped.
  `DuplicateHashFilter` is stateful and is `reset()` by the runner at the start
  of every run.
- **Model invariants enforced** so an invalid record cannot be constructed:
  rejected ⇒ `rejection_reason` + `rejected_by` non-null; accepted ⇒
  `quality_score` non-null; failed `FilterResult` ⇒ `reason` non-null.
- **Outputs** (full-batch overwrite each run): `data/cleaned/{doc_id}.txt`,
  `data/rejected/{doc_id}.txt`, `data/metadata/documents.jsonl` (one line per
  input file, processing order).
- **Read errors** (e.g. non-UTF-8 bytes) become `rejected` records with
  `rejected_by="read_error"` and reason `read_error: <detail>`; the run still
  completes.

### Public API (re-exported from `datagate`)

`DataGateConfig`, `Document`, `DocumentMetadata`, `FilterResult`, `RunReport`,
`QualityScorer`, `PipelineRunner`, `BaseFilter`, `MinLengthFilter`,
`DuplicateHashFilter`, `SpecialCharRatioFilter`, `LinkDensityFilter`,
`default_filters`, `normalize_text`, `content_hash`, `doc_id_for`,
`discover_files`, `load_document`, `write_outputs`.

Public signatures match HANDOFF_CLAUDE.md §4 (e.g. `PipelineRunner(config,
filters=None, scorer=None)`, `QualityScorer.score(doc, metrics) -> float`).

### Quality Score Formula (deterministic)

```
score = 100
        - 40 * min(special_char_ratio / max_special_char_ratio, 1)
        - 30 * min(link_density / max_link_density, 1)
        - length_penalty            # 0 if char_count >= 1000,
                                     #   linear up to 10 at min_chars
clamped to [0, 100], rounded to 2 decimals
```

## How to Run

```bash
# editable install (with test deps)
pip install -e "packages/datagate[dev]"

# run the suite
pytest packages/datagate -q

# use the library
python -c "from datagate import DataGateConfig, PipelineRunner; print(PipelineRunner(DataGateConfig()).run())"
```

(In this repo the interpreter is `.venv/Scripts/python.exe`; e.g.
`./.venv/Scripts/python.exe -m pytest packages/datagate -q`.)

## Verification

- `pytest packages/datagate -q` → **36 passed**.
- `import datagate` succeeds with no `fastapi` in `sys.modules`.
- `pip install -e packages/datagate` succeeds.

## Remaining Issues / Suspected Design Points for Review

- **doc_id collisions on identical content are intentional** (`doc_id` is the
  content hash). Two rejected docs with identical content therefore write the
  same `rejected/{doc_id}.txt` filename (last write wins), so the on-disk file
  *count* can be < `total`. The partition invariant is asserted on RunReport
  counts (`accepted + rejected == total`), and the jsonl always has one line per
  input file. Flagging in case a per-file UI later wants unique filenames.
- **`read_error` doc_id** is derived from the source path (`read_error:<path>`),
  not from content (which is unreadable). Deterministic, but distinct namespace
  from content hashes.
- `special_char_ratio` / `link_density` are computed over the **original** text
  (length includes whitespace); `min_length` measures `len(text.strip())`.

## Out of Scope (NOT done — next handoff)

- `apps/api` DataGate router + service, the `/api/pipeline/status` stage-1
  hookup, BakeBoard panel, and Next.js proxy routes (HANDOFF_CLAUDE.md §6–§7).
- No crawling, no LLM judging, no persistence beyond the latest run.
