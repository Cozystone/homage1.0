# ATANOR DEMO ⁄ ULTIMATE — clean separation plan (방안)

Owner (2026-07-14): ship two public products — **ATANOR DEMO** (text-focused chat) and **ATANOR
ULTIMATE** (4 plugins + aquarium dashboard + everything) — with the learning engine / core AI
SHARED between them (parallel update). Keep the engine at the most recent stable architecture and
make each cleanly separable.

## Corrected diagnosis (measured, not assumed)
The commit counts (`demo` +161, `ultimate` +73) looked like a bad fork. The FILE TREES tell the
real, far calmer story:

- **`apps/web` (the entire Next.js frontend) is IDENTICAL on both branches.** Both faces already
  live in ONE codebase, switched by `NEXT_PUBLIC_ATANOR_PROFILE` (`apps/web/app/lib/profile.ts`,
  `isDemo`): the DemoChat text UI *and* the FullApp orb/3D/aquarium dashboard + 4 plugins. **The
  frontend is already unified — there is nothing to cut apart there.**
- **`demo` is the near-complete engine superset**: it has ~9,648 more engine lines than `ultimate`
  (this session's world pack + reasoning-VM F-ladder + mini engine, plus accumulated work).
  `ultimate` is simply STALE on the engine.
- **0 ultimate-only files.** Everything `ultimate` has, `demo` has too (`code_evolver` lives at
  `packages/evolution/`, shared — an earlier wrong-path check falsely flagged it as ultimate-only).
- Only ~10–12 engine files carry ultimate-UNIQUE lines (~253 total) — small refinements (e.g.
  `packages/base_brain/zero_user_answer.py` particle / `max_relations` tuning) to review-and-salvage,
  not a mass merge.

**Conclusion: there is no conjoined twin to separate in the code — it is already one body with a
profile switch. What's actually broken is only that the `ultimate` BRANCH drifted stale, plus ~253
lines of ultimate refinement to fold into the canonical engine.**

## Target end-state
- **One trunk branch** = the single source of truth. Canonical engine = `demo` (most-recent-stable
  superset) + salvaged `ultimate` refinements.
- **One codebase, two faces by build flag** (already the architecture):
  - `NEXT_PUBLIC_ATANOR_PROFILE=demo` → **ATANOR DEMO** — text-only chat; dashboard = sessions +
    conversation only; no plugins / orb / 3D.
  - `NEXT_PUBLIC_ATANOR_PROFILE=full` → **ATANOR ULTIMATE** — orb / 3D / aquarium dashboard + 4 plugins.
- **Shared engine, parallel update BY CONSTRUCTION** — `apps/api` + `packages` have ONE version;
  both builds inherit every improvement with zero merge-back. (Exactly the owner's requirement.)
- **Two build artifacts** from the one trunk: two Vercel projects (web) + two Tauri builds
  (`ATANOR-DEMO.exe` / `ATANOR-ULTIMATE.exe`), differing only by the profile env.
- **No demo/ultimate BRANCH split** — the branch split is what caused the drift; collapsing to one
  trunk + build flag makes drift structurally impossible.

## Surgical sequence (safe, phased, testable)
**Phase 1 — canonical engine** *(run AFTER the world-pack build finishes, so the full test suite
runs uncontended and any breakage is caught immediately)*
1. Base = `demo` (newest stable, superset).
2. For each of the ~10–12 files with ultimate-unique lines: `git diff demo ultimate -- <file>`,
   review the ultimate-only hunks — port genuine improvements onto `demo`; keep `demo` where its
   approach supersedes. Bounded, file-by-file, verifiable.
3. Full test suite + P0 battery → confirm the canonical engine is green.

**Phase 2 — collapse to one trunk**
4. Bring `ultimate` up to the canonical engine + web (now identical except the profile env).
5. Designate one trunk (keep `demo` as trunk, or cut `main` from it). Retire `ultimate` as a
   divergent branch — ULTIMATE becomes the `full`-profile build of the trunk.
6. Keep the two worktrees (27 = demo-profile local, 28 = full-profile local) pointed at the SAME
   trunk — no divergence, just two `.env.local` profiles.

**Phase 3 — polish the DEMO face to true text-only** *(frontend-only, low-risk, can start anytime)*
7. In `apps/web`, gate the plugin panels / orb / aquarium OFF when `isDemo` (stubbed today → hide
   entirely; dashboard = sessions + conversation).
8. Optional lean bundle: `isDemo`-gated dynamic imports so the demo build omits 3D/plugin code.

**Phase 4 — distribution + cleanup**
9. Landing: two download buttons (ATANOR DEMO / ATANOR ULTIMATE) → the two artifacts.
10. Retire stale branches/worktrees, prune junk (list to finalize with owner before any deletion).

## Why NOT new/separate repos (reaffirmed)
Two repos re-introduce exactly the drift just measured — but with no `git merge` path at all. The
engine is ONE thing; the two products are ONE codebase + a build flag. Keep it that way.
