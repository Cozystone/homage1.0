# ATANOR Hermes Web Explorer Loop

Status: proof-only bounded web exploration loop.

`packages/agentic_micro_os/web_explorer_loop.py` adds a Hermes-inspired
exploration loop for ATANOR self-learning. It is not an unrestricted crawler and
it does not perform private credentialed browsing.

## Inputs

- `goal`
- `allowed_domains`
- `pages` as caller-provided public visible-text snapshots
- `max_pages` default `30`
- `max_depth` default `2`
- `max_runtime_sec` default `21600`
- `max_candidate_drafts` default `100`
- `max_skill_drafts` default `20`

## Allowed Actions

- Browser Read on allowlisted public snapshots.
- Title/excerpt/hash extraction.
- Deterministic local summarization.
- Cloud Brain candidate draft creation through Brain Access Road.
- SkillDraft creation.
- ToolUseTrajectory compression.
- Future search proposal as draft-only planning.

## Forbidden Actions

- Credentialed private pages.
- Form submission.
- Downloads.
- Arbitrary JavaScript.
- Unrestricted shell.
- Local Brain raw upload.
- Direct production Cloud Brain write.
- Candidate promotion.
- Auto commit or push.

## Cloud Brain Road

The loop uses `cloud_brain_candidate_write_draft` only. A production write check
is deliberately attempted as a safety probe and must be rejected. Every source
record contains:

- `source_url`
- `title`
- `content_hash`
- `excerpt`
- `collected_at`
- `confidence`
- `candidate_status=draft`

## API

- `GET /api/agentic-os/web-explorer/status`
- `POST /api/agentic-os/web-explorer/run-once`
- `GET /api/agentic-os/web-explorer/runs/{run_id}`
- `GET /api/agentic-os/skills/drafts`

The API stores proof run results in process memory only.

## CLI Proof

```powershell
python -m packages.agentic_micro_os.web_explorer_loop --goal "research local TTS alternatives and SPLATRA particle rendering" --max-runtime-sec 21600
```

The proof uses local snapshots and does not fetch remote pages.

## Invariants

- `external_llm=false`
- `external_sllm=false`
- `local_brain_write=false`
- `production_store_mutated=false`
- `candidate_promotion=false`
- `unrestricted_shell=false`
- `arbitrary_js_eval=false`
- `auto_commit=false`
- `auto_push=false`
- `proof_only=true`
- `human_approval_required=true`
