# HANDOFF_CLAUDE.md — Milestone 2: DataGate MVP

> Author: Claude (senior architect role)
> Date: 2026-06-11
> Status: DESIGN COMPLETE — ready for Codex implementation
> Depends on: Milestone 1 (repo skeleton, mock pipeline status) — DONE

---

## 1. Architecture Review of Current Skeleton

**What's good:**

- Clean monorepo split: `apps/api` (FastAPI), `apps/web` (Next.js), `docs/`, coordination docs at root. This matches the long-term plan where `packages/` will hold pipeline libraries consumed by `apps/api`.
- The mock `GET /api/pipeline/status` (7 stages) already establishes the contract pattern: backend owns truth, Next proxy mirrors it, BakeBoard renders it. DataGate should follow the exact same pattern rather than inventing a new one.
- Frontend build and Python compile checks pass — we have a green baseline to protect.

**Risks / debts to track (not blockers):**

1. **npm audit (2 moderate, 2 critical):** correct call to defer `audit fix --force`. Log the four advisory IDs in PROJECT_STATE.md so they don't get lost. Revisit at the next Next.js minor bump.
2. **No `packages/` directory yet:** DataGate is the first real library. Decide now: `packages/datagate` is a standalone installable Python package (own `pyproject.toml`), imported by `apps/api` via editable install (`pip install -e packages/datagate`). This keeps pipeline logic testable without FastAPI.
3. **Mock stages vs. real stages:** once DataGate exists, stage 1 of the 7-stage mock should be backed by real data. Don't rewrite the whole status endpoint yet — just let the DataGate stage report real state while the other 6 stay mocked.
4. **No shared run-state store:** MVP can hold run state in process memory (a module-level singleton in the API). Acceptable for single-process dev. Note it as debt; a file-based or SQLite run registry comes later.

---

## 2. DataGate MVP Architecture

**Purpose:** deterministic quality gate that takes raw local text documents and partitions them into `cleaned` and `rejected`, with full per-document metadata and rejection reasons.

```
data/raw/*.{txt,md}
        │
        ▼
 ┌─────────────────────────────┐
 │ PipelineRunner               │
 │  1. discover & load (sorted) │
 │  2. filter chain (ordered):  │
 │     MinLengthFilter          │
 │     DuplicateHashFilter      │
 │     SpecialCharRatioFilter   │
 │     LinkDensityFilter        │
 │  3. QualityScorer (accepted) │
 │  4. write outputs            │
 └─────────────────────────────┘
        │
        ├── data/cleaned/{doc_id}.txt          (accepted, original text)
        ├── data/rejected/{doc_id}.txt         (rejected, original text)
        └── data/metadata/documents.jsonl      (one record per input doc)
```

**Design rules:**

- **Fail-fast filter chain:** a document is rejected by the *first* filter that fails. `rejection_reason` is that filter's reason string. Remaining filters are skipped (simple, deterministic, cheap).
- **Determinism:** files processed in sorted path order; hashing via SHA-256 of normalized text; no randomness, no timestamps in any *decision* path. Re-running on the same input produces byte-identical accept/reject partitions and identical `doc_id`s.
- **Pure library + thin API:** `packages/datagate` has zero FastAPI imports. `apps/api` wraps it.
- **Synchronous-with-background-task execution:** `POST /run` starts a FastAPI `BackgroundTask`; `GET /status` polls in-memory run state. No Celery, no queue.

---

## 3. Python Module Structure — `packages/datagate`

```
packages/datagate/
├── pyproject.toml                 # name="datagate", deps: pydantic>=2 only
├── README.md
├── datagate/
│   ├── __init__.py                # re-export public API
│   ├── config.py                  # DataGateConfig (thresholds, paths)
│   ├── models.py                  # Document, DocumentMetadata, FilterResult, RunReport
│   ├── io.py                      # discover_files(), load_document(), write_outputs()
│   ├── hashing.py                 # normalize_text(), content_hash()
│   ├── scoring.py                 # QualityScorer
│   ├── runner.py                  # PipelineRunner
│   └── filters/
│       ├── __init__.py            # DEFAULT_FILTERS ordered list factory
│       ├── base.py                # BaseFilter (ABC)
│       ├── min_length.py          # MinLengthFilter
│       ├── duplicate_hash.py      # DuplicateHashFilter
│       ├── special_char_ratio.py  # SpecialCharRatioFilter
│       └── link_density.py        # LinkDensityFilter
└── tests/
    ├── conftest.py                # tmp data dirs, fixture corpus
    ├── test_models.py
    ├── test_filters.py
    ├── test_scoring.py
    ├── test_runner.py
    └── fixtures/                  # tiny .txt/.md samples per scenario
```

---

## 4. Core Interfaces / Classes

All models are Pydantic v2. Type hints mandatory. Signatures below are the contract — Codex may add private helpers but must not change public signatures.

```python
# models.py

class DocumentMetadata(BaseModel):
    doc_id: str                      # sha256(normalized_text)[:16]
    source_path: str                 # relative to data/raw
    char_count: int
    word_count: int
    line_count: int
    special_char_ratio: float        # 0.0–1.0
    link_density: float              # 0.0–1.0
    content_hash: str                # full sha256 hex
    status: Literal["accepted", "rejected"]
    rejection_reason: str | None     # REQUIRED (non-null) when rejected
    rejected_by: str | None          # filter name, when rejected
    quality_score: float | None      # 0–100, REQUIRED when accepted
    filters_passed: list[str]
    run_id: str
    processed_at: str                # ISO 8601 UTC (informational only)


class Document(BaseModel):
    doc_id: str
    source_path: str
    text: str                        # original, unmodified
    metadata: DocumentMetadata | None = None


class FilterResult(BaseModel):
    filter_name: str
    passed: bool
    reason: str | None               # human-readable, REQUIRED when passed=False
    metrics: dict[str, float | int]  # e.g. {"char_count": 87, "threshold": 200}


class RunReport(BaseModel):
    run_id: str
    state: Literal["completed", "failed"]
    total: int
    accepted: int
    rejected: int
    rejection_breakdown: dict[str, int]   # filter_name -> count
    started_at: str
    finished_at: str
    error: str | None = None
```

```python
# filters/base.py

class BaseFilter(ABC):
    name: ClassVar[str]

    @abstractmethod
    def apply(self, doc: Document) -> FilterResult: ...
```

**Filter specs (defaults in `DataGateConfig`):**

| Filter | name | Rule (rejects when…) | Default |
|---|---|---|---|
| `MinLengthFilter` | `min_length` | `char_count < min_chars` after `strip()` | `min_chars=200` |
| `DuplicateHashFilter` | `duplicate_hash` | `content_hash` already seen this run (stateful: `self._seen: set[str]`, reset per run) | — |
| `SpecialCharRatioFilter` | `special_char_ratio` | ratio of chars that are not alphanumeric/whitespace/basic punct (`.,!?;:'"()-`) exceeds threshold; Unicode letters (incl. Korean) count as alphanumeric via `str.isalnum()` | `max_ratio=0.30` |
| `LinkDensityFilter` | `link_density` | chars belonging to URL matches (`https?://\S+` + markdown link targets) ÷ total chars exceeds threshold | `max_ratio=0.40` |

Reason strings must embed actual numbers, e.g. `"char_count 87 < min 200"`, `"duplicate of doc_id a1b2c3d4e5f6a7b8"`.

```python
# scoring.py — deterministic, no I/O

class QualityScorer:
    def score(self, doc: Document, metrics: dict[str, float | int]) -> float:
        """Returns 0–100. Weighted, monotonic, documented formula:
        score = 100
                - 40 * special_char_ratio_norm   # ratio / max_ratio, capped at 1
                - 30 * link_density_norm
                - length_bonus_penalty           # +0 if >= 1000 chars, linear down to -10 at min_chars
        Clamped to [0, 100]. Same input -> same output, always.
        """
```

```python
# runner.py

class PipelineRunner:
    def __init__(self, config: DataGateConfig,
                 filters: list[BaseFilter] | None = None,
                 scorer: QualityScorer | None = None): ...

    def run(self) -> RunReport:
        # 1. sorted(discover_files(config.input_dir))  -> deterministic order
        # 2. per doc: chain filters, fail-fast
        # 3. score accepted docs
        # 4. write cleaned/, rejected/, append-safe rewrite of documents.jsonl
        # 5. return RunReport (never raises for per-doc issues; unreadable
        #    files become rejected with reason "read_error: <detail>")
```

`run_id` = `dg-{UTC yyyymmdd-HHMMSS}`. Each run **overwrites** `data/cleaned/`, `data/rejected/`, and `data/metadata/documents.jsonl` (clear-then-write) — MVP is full-batch, not incremental.

---

## 5. Data Output Schema

```
data/
├── raw/                       # INPUT (user-provided .txt / .md, read-only to pipeline)
├── cleaned/
│   └── {doc_id}.txt           # accepted docs, original text verbatim
├── rejected/
│   └── {doc_id}.txt           # rejected docs, original text verbatim
└── metadata/
    └── documents.jsonl        # one DocumentMetadata JSON object per line,
                               # in processing (sorted-path) order, covers ALL docs
```

`documents.jsonl` line example:

```json
{"doc_id":"a1b2c3d4e5f6a7b8","source_path":"notes/intro.md","char_count":1543,"word_count":260,"line_count":42,"special_char_ratio":0.04,"link_density":0.02,"content_hash":"a1b2…","status":"accepted","rejection_reason":null,"rejected_by":null,"quality_score":91.5,"filters_passed":["min_length","duplicate_hash","special_char_ratio","link_density"],"run_id":"dg-20260611-093000","processed_at":"2026-06-11T09:30:02Z"}
```

Invariants (enforced by tests):
- every input file → exactly one jsonl line
- `status=rejected` ⇒ `rejection_reason` and `rejected_by` non-null
- `status=accepted` ⇒ `quality_score` non-null and file exists in `data/cleaned/`
- `len(cleaned) + len(rejected) == total`

---

## 6. API Design (`apps/api`)

New router: `apps/api/app/routers/datagate.py`, mounted under `/api/datagate`. In-memory `RunState` singleton in `apps/api/app/services/datagate_service.py`.

### `POST /api/datagate/run`

Request (all optional):
```json
{ "input_dir": "data/raw", "min_chars": 200, "max_special_char_ratio": 0.3, "max_link_density": 0.4 }
```

- `409 Conflict` if a run is already `running`.
- `202 Accepted` otherwise; executes via FastAPI `BackgroundTasks`:
```json
{ "run_id": "dg-20260611-093000", "state": "running" }
```

### `GET /api/datagate/status`

```json
{
  "state": "completed",            // idle | running | completed | failed
  "run_id": "dg-20260611-093000",
  "total": 120, "accepted": 97, "rejected": 23,
  "rejection_breakdown": { "min_length": 11, "duplicate_hash": 6, "special_char_ratio": 4, "link_density": 2 },
  "started_at": "2026-06-11T09:30:00Z",
  "finished_at": "2026-06-11T09:30:04Z",
  "error": null
}
```

`state=idle` (never run) returns nulls/zeros. Add matching Next.js proxy routes (`apps/web/app/api/datagate/run/route.ts`, `.../status/route.ts`) mirroring the existing pipeline-status proxy pattern.

Also: update `GET /api/pipeline/status` so the DataGate stage reflects real DataGate state (`pending`→`running`→`done`/`failed`); other 6 stages remain mocked.

---

## 7. BakeBoard UI Additions (`apps/web`)

One new section on the existing page (no routing changes): **DataGate panel** under the pipeline stages.

1. **Run button** — POSTs `/api/datagate/run`; disabled while `state=running`; shows spinner.
2. **Status strip** — state badge, run_id, duration.
3. **Summary cards** — Total / Accepted / Rejected (with accept-rate %).
4. **Rejection breakdown** — small table or horizontal bars: filter name → count.
5. **Polling** — while `running`, poll `/api/datagate/status` every 2s; stop on terminal state.
6. **Error surface** — show `error` string verbatim when `state=failed`.

No document-level browsing UI in MVP (metadata jsonl is inspectable on disk). Keep styling consistent with the current stage cards.

---

## 8. Unit Test Plan (`packages/datagate/tests`, pytest)

| Area | Cases |
|---|---|
| `test_models` | rejected metadata without reason fails validation; accepted without score fails; jsonl round-trip |
| `test_filters` / MinLength | below / exactly-at / above threshold; whitespace-only file rejected |
| DuplicateHash | identical content different filenames → second rejected with first's doc_id in reason; whitespace-normalized duplicates caught; state resets between runs |
| SpecialCharRatio | clean prose passes; symbol-soup rejected; Korean text passes (Unicode alnum); boundary at exactly max_ratio passes |
| LinkDensity | prose with one link passes; link-list document rejected; markdown link syntax counted |
| `test_scoring` | deterministic (same input twice → identical score); clamped to [0,100]; monotonic: more special chars ⇒ score ≤ |
| `test_runner` (e2e on fixtures) | partition invariant `cleaned+rejected==total`; every doc in jsonl; rejected ⇒ reason present; **determinism: two consecutive runs → identical jsonl except run_id/processed_at, identical file sets**; unreadable file → rejected with `read_error` reason; empty `data/raw` → completed run, total=0 |
| API tests (`apps/api/tests`) | `POST run` returns 202; second POST while running → 409; status transitions idle→running→completed; failed run surfaces error |

Target: ≥ 90% coverage on `packages/datagate`. Run via `pytest packages/datagate apps/api`.

---

## 9. Acceptance Criteria

1. `pip install -e packages/datagate` succeeds; package importable with no FastAPI dependency.
2. Placing sample `.txt`/`.md` files in `data/raw` and clicking **Run** in BakeBoard produces populated `data/cleaned/`, `data/rejected/`, `data/metadata/documents.jsonl`.
3. Every rejected document has a non-null `rejection_reason` and `rejected_by`; every accepted document has metadata including `quality_score`.
4. Running twice on identical input yields identical accept/reject partitions and identical `doc_id`s.
5. `POST /api/datagate/run` and `GET /api/datagate/status` behave per §6, including the 409 guard.
6. BakeBoard shows live status, summary counts, and rejection breakdown without page reload.
7. All pytest suites pass; frontend build passes; Python compile check passes (green baseline preserved).
8. `PROJECT_STATE.md` and `HANDOFF_CODEX.md` updated after implementation.

## 10. Non-Goals (explicitly out of scope)

- LLM-based quality judging or any model inference
- Web crawling / remote ingestion (local `data/raw` only)
- Incremental / resumable runs, run history, or persistence beyond the latest run
- PDF/HTML/docx parsing (only `.txt`, `.md`)
- Text *transformation* (DataGate filters, it does not rewrite content)
- Multi-process concurrency, queues, websockets
- Document-level browsing UI in BakeBoard
- Fixing the 4 npm audit advisories (tracked separately)

---

## 11. Codex Implementation Brief

> Paste-ready task for Codex. Implement in order; commit per step.

**Step 1 — Package scaffold.** Create `packages/datagate` exactly per §3 tree. `pyproject.toml`: name `datagate`, requires-python `>=3.11`, deps `pydantic>=2`. Add editable install to API dev setup docs/requirements.

**Step 2 — Models (`models.py`).** Implement the four Pydantic models from §4 verbatim, plus a model validator: `status=="rejected"` requires `rejection_reason` and `rejected_by`; `status=="accepted"` requires `quality_score`.

**Step 3 — Hashing + IO.** `normalize_text(text) -> str` (strip, collapse internal whitespace runs to single space, NFC-normalize). `content_hash = sha256(normalized)`, `doc_id = hash[:16]`. `discover_files` returns sorted relative paths matching `*.txt|*.md` recursively. `write_outputs` clears and rewrites output dirs atomically enough for dev (write to temp names, then replace dir contents).

**Step 4 — Filters.** `BaseFilter` ABC, then the four filters per the table in §4, each with config-injected thresholds and metric-bearing reason strings. `filters/__init__.py` exposes `default_filters(config) -> list[BaseFilter]` in the canonical order: min_length, duplicate_hash, special_char_ratio, link_density.

**Step 5 — Scorer + Runner.** `QualityScorer.score` per the documented formula (put the formula in the docstring). `PipelineRunner.run` per §4 — fail-fast chain, read-error handling, full-batch overwrite, `RunReport` return. No prints; use `logging`.

**Step 6 — API.** `datagate_service.py` (in-memory RunState + thread-safe guard), `routers/datagate.py` with the two endpoints per §6 incl. 409 logic, wire into `main.py`, update pipeline status stage 1 to reflect real DataGate state.

**Step 7 — Frontend.** Two proxy routes mirroring the existing pattern; DataGate panel per §7 with 2s polling.

**Step 8 — Tests + fixtures.** Implement §8 fully. Create fixture corpus: 1 clean long doc, 1 short doc, 2 identical-content docs, 1 symbol-heavy doc, 1 link-list doc, 1 Korean-language doc, 1 empty file.

**Step 9 — Docs.** Update `PROJECT_STATE.md` (milestone 2 status, npm advisory IDs noted as debt), `HANDOFF_CODEX.md` (what was built, how to run: `uvicorn`, `npm run dev`, `pytest`), append `SESSION_LOG.md`.

**Guardrails for Codex:**
- Do not change public signatures in §4. Do not add dependencies beyond pydantic (stdlib `re`, `hashlib`, `unicodedata` for everything else).
- Determinism is the prime invariant — if a choice trades determinism for convenience, choose determinism.
- Keep the existing 7-stage mock endpoint working; only stage 1 becomes real.
- If `data/raw` doesn't exist, create it empty rather than erroring.

— End of HANDOFF_CLAUDE.md —
