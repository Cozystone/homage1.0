# ATANOR 1.0 Alpha Freeze Report

Generated: 2026-06-14 KST
Updated: 2026-06-14 KST, native Alpha honesty and self-corpus stabilization pass

## Repository State

- Branch: `feature/datagate-v0`
- HEAD commit: `8ca06c4531b736bab5d2b5eae62dd8c2581cd8aa`
- Safety backup branch: `backup/homage-era-pre-atanor-freeze`
- Safety bundle: `backups/homage-era-head-20260614-011432.bundle`
- Working-tree backup patch: `backups/working-tree-before-atanor-freeze-20260614-011432.patch`

The working tree is intentionally not clean because this freeze pass is stabilizing an already active Alpha workspace with many pre-existing Homage-era edits.

## What Changed

- Public identity was aligned to **ATANOR 1.0 Alpha** in the README and visible product copy.
- Added `docs/ATANOR_NAME_BOUNDARY.md` to document the safe naming boundary between ATANOR and the retained Homage engine namespace.
- Preserved compatibility-sensitive internal names where renaming would risk runtime breakage.
- Restored internal Tauri/Rust compatibility names while keeping visible product naming as ATANOR.
- Added ATANOR environment aliases while retaining legacy `HOMAGE_*` fallbacks.
- Updated the main 3D graph viewport so the root UI uses the same dark 3D canvas treatment as the current ATANOR shell.
- Adjusted 3D graph contrast:
  - base nodes: cool slate instead of white
  - base edges: darker slate instead of washed-out white
  - active graph signals: neon orange remains reserved for active packets and new-node pulses
- Added Adaptive Local-Cloud Ratio Control:
  - computes `local_brain_strength_score`
  - exposes `fusion_ratio.local_weight` and `fusion_ratio.cloud_weight`
  - forces local-only behavior for private queries and invalid cloud fragments
  - clamps Cloud Brain fragment size for low-memory and survival modes
  - preserves local private memory priority over cloud context during weighted RRF
- Removed legacy canned answer shortcuts from the active GraphRAG path:
  - greeting/control/inspection answers no longer bypass native retrieval/generation
  - web fallback rejects older conversation and inspection router results
  - no-evidence output remains raw native output with diagnostics instead of a polished replacement
- Added first-class `self_corpus` ingestion:
  - `scripts/ingest_self_corpus.py`
  - routes README and ATANOR docs through DataGate, Ontology Forge, Knowledge Bakery, Ghost Shell, Payload Vault, GraphRAG, and native decoding
  - tags self documentation payloads as `source_type = self_corpus`
- Added deterministic native generation evaluation:
  - `scripts/evaluate_native_generation.py`
  - reports evidence count, source cluster, local/cloud ratio, repetition metrics, loop state, stop reason, and self-corpus usage
- Added local generation trace and correction paths:
  - `data/memory/generation_traces.jsonl`
  - `data/memory/corrections.jsonl`
  - traces preserve raw native output and degeneration diagnostics for later native training
- Bumped the deployment candidate to `0.1.1` to avoid collision with the existing `0.1.0.0` Partner Center package.
- Verified `http://127.0.0.1:3022/` after restart:
  - page title: `ATANOR`
  - visible navigation: `로컬 브레인 [LOCAL BRAIN]`, `클라우드 브레인 [CLOUD BRAIN]`
  - 3D canvas present
  - browser console warnings/errors: none observed

## Intentionally Not Changed

These names remain for compatibility and must not be blindly renamed:

- `homage.db`
- `homage-api`
- existing `homage` internal package/import names
- existing AppData paths that already store local memory
- existing Microsoft Store/package identity until a planned migration is ready
- existing `HOMAGE_*` environment variables as legacy fallbacks
- current Tauri sidecar binary names unless a signed migration build verifies the rename
- historical logs and session files

## Remaining Homage Compatibility Names

See `docs/ATANOR_NAME_BOUNDARY.md`.

Summary:

- **Must keep:** database names, sidecar/runtime names, import/package names, AppData paths, Store identity, legacy env vars.
- **Safe to change:** README/docs/UI labels/page titles/public copy/new `ATANOR_*` aliases.
- **Needs migration later:** repository name, full package namespace migration, DB/AppData migration, and Store identity migration.
- **Migrated in alpha:** public Vercel alias and desktop updater endpoint now use `https://atanor.vercel.app`.
- **Historical:** project logs, session logs, old handoff docs.

## Verification

### Python Compile

Command:

```powershell
python -m py_compile apps/api/app/main.py apps/api/app/services/network_config.py packages/rag_engine/rag_engine/retriever.py packages/rag_engine/rag_engine/synthesizer.py packages/knowledge_bakery/knowledge_bakery/memory.py packages/knowledge_bakery/knowledge_bakery/learning_daemon.py scripts/ingest_self_corpus.py scripts/evaluate_native_generation.py
```

Result: passed.

### Python Tests

Command:

```powershell
$env:PYTHONPATH='apps/api;packages/rag_engine;packages/guard;packages/ontology_forge;packages/datagate;packages/knowledge_bakery;packages/neuro_efficiency;packages/trainer;packages/model'
python -m pytest apps/api/tests packages/rag_engine/tests packages/model/tests -q
```

Result:

```text
55 passed in 11.57s
```

### Web Build

Command:

```powershell
npm --workspace apps/web run build
```

Result: passed.

Key output:

```text
✓ Compiled successfully
✓ Generating static pages using 31 workers (40/40)
```

### Local Web Runtime

Command:

```powershell
npm --workspace apps/web run start:local -- --port 3022
```

Result:

- `http://127.0.0.1:3022/` returned HTTP 200.
- Browser page title: `ATANOR`.
- Canvas count: 1.
- Browser warnings/errors: none observed.

## Deployment Candidate Artifacts

Directory:

```text
dist/ATANOR_0.1.1
```

Files:

```text
ATANOR_0.1.1_x64-setup.exe
ATANOR_0.1.1_x64_en-US.msi
ATANOR_0.1.1.0_x64.msix
ATANOR_0.1.1.0_x64.msixupload
SHA256SUMS.txt
```

SHA256:

```text
3054E476F974862B50D70CA9A08D1E7A27DA8E18826288FBF19052C1B9B909CA  ATANOR_0.1.1.0_x64.msix
1B97FFF7AB8FBC763FA2DB58DF365DE063EA188038D001A999A54937E5ABFD94  ATANOR_0.1.1.0_x64.msixupload
8F76C80B9CFF3710D7F5A569FD651753D43342E2548F341D456162C815AF420D  ATANOR_0.1.1_x64-setup.exe
14E8550479749801CFD5B8A777FB4C5C14F771C4CACC42E05401C1DBAE596D12  ATANOR_0.1.1_x64_en-US.msi
```

Partner Center upload file:

```text
dist-artifacts/windows-store/ATANOR_0.1.1.0_x64.msixupload
```

Partner Center status observed:

- Product page reachable: `https://partner.microsoft.com/ko-kr/dashboard/products/9PBN2HNPWQ7V/submissions/1152921505701228779/packages`
- Existing package on page: `Homage_0.1.0.0_x64.msixupload`
- Automated file picker upload was attempted but the current browser automation surface does not expose `setInputFiles`, and Windows file picker input did not attach the new package.
- Existing package removal was reverted; no destructive page save was performed.

## Known Limitations

- Production Cloud Brain is not complete.
- Real libp2p payload transport is not complete.
- Production token economy is not implemented.
- Local decoder is not ChatGPT-level; current generation may be broken, repetitive, or ugly by design.
- ATANOR Alpha must not hide bad output with canned identity replies, regex summaries, external LLMs, pretrained local models, or deterministic template fallbacks.
- Self identity answers should improve only after ATANOR documentation has been ingested as native `self_corpus`.
- Full internal namespace migration from Homage to ATANOR is intentionally deferred.
- GitHub official ATANOR repository creation is blocked until GitHub CLI or connector authentication is available.
- Partner Center package upload is blocked by browser file-upload automation limitations; the final `.msixupload` is ready for manual upload.
- Microsoft Store/App identity migration should be handled as a separate release task to avoid breaking updates and installed user data.

## GitHub / Release Status

- Existing Homage-era repository should remain as backup.
- A new official ATANOR repository has not been created from this session because `gh auth status` reports no logged-in GitHub host.
- Recommended next action after authentication:

```powershell
gh auth login
gh repo create Cozystone/atanor --private --source . --remote atanor --push
```

Change `--private` to `--public` only when the Alpha freeze is ready for public exposure.

## Recommended Next Milestone

1. Commit this freeze pass.
2. Create the official ATANOR repository after GitHub authentication is restored.
3. Configure ATANOR release/update endpoints separately from legacy Homage endpoints.
4. Plan a signed migration build for Store identity, AppData path, updater manifest, and executable names.
5. Keep Cloud Brain, P2P payload transfer, and full decoder research documented as Alpha/Future Work rather than presenting them as production-complete.

## Recommended Commit Message

```text
Stabilize ATANOR alpha branding and preserve Homage engine compatibility
```
