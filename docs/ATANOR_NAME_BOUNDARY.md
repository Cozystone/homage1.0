# ATANOR / Homage Name Boundary

This repo is in the ATANOR 1.0 Alpha freeze phase.

ATANOR is the public product and research brand. Homage remains the original
internal engine namespace where changing names would create compatibility risk.

## A. Must Keep For Compatibility

- `homage.db`, `homage_memory.sqlite3`, and related backup filenames.
- `homage-api` sidecar binary names and Tauri external binary references.
- Existing `HOMAGE_*` environment variables as legacy fallbacks beside new
  `ATANOR_*` aliases.
- Existing internal Python package/import names such as `homage-model`,
  `homage-trainer`, `homage-guard`, and compatibility aliases like
  `HomageCoreModel`.
- Existing AppData/runtime folders. The product may say ATANOR, but the Alpha
  runtime keeps the original Homage data namespace so installed users do not
  lose local memory.
- Existing Store/package identity such as `AnseokKim.Homage` until a new Store
  product identity and migration path are formally created.
- Existing schema IDs such as `homage.graph-fragment.v1` where they identify
  serialized fragment contracts.
- Existing legacy deployment aliases may continue to redirect, but the verified
  public ATANOR deployment and updater endpoint is `https://atanor.vercel.app`.

## B. Safe To Change To ATANOR

- README, public docs, and project philosophy text.
- Visible UI labels, page titles, product copy, and public metadata.
- New `ATANOR_*` environment variable aliases.
- FastAPI title/description and response labels that are user-facing.
- Tauri `productName`, visible window titles, and desktop marketing copy.
- Sample/demo text that is not part of a persisted runtime contract.

## C. Needs Migration Plan Later

- Repository name and GitHub release namespace.
- Any old public Vercel aliases that still mention Homage.
- Windows Store identity and package family name.
- Full internal package rename from `homage-*` to `atanor-*`.
- Database filename migration from `homage.db` to an ATANOR-named storage
  contract.
- Existing AppData folder migration.
- Historical method names or serialized IDs that external clients may already
  consume.

## D. Historical Log; Leave Unchanged

- `PROJECT_STATE.md`, `SESSION_LOG.md`, `CONTEXT_CAPSULE.md`, and
  `docs/night_log_0612.md` entries that describe work performed under the old
  name.
- Old Vercel deployment URLs and GitHub artifact names in logs.
- PRD excerpts and experiment logs that preserve project history.
