# ATANOR — two worktrees, one shared engine

This repo is checked out as **two git worktrees** of the same repository, so the
**reasoning + utterance engine upgrades together** in both:

| folder | branch | runs | purpose |
| --- | --- | --- | --- |
| `28. ATANOR Ultimate` | `ultimate` | full New ATANOR (orb / particles / 3D) | the latest full build |
| `27., ATANOR DEMO` | `demo` | GPT-style chat demo (`NEXT_PUBLIC_ATANOR_PROFILE=demo` via `apps/web/.env.local`) | the public demo |

Both folders share the **same git history** (`.git`). The frontend differs only by
the runtime profile (`isDemo`) — the engine and all code are otherwise identical.

## The engine (shared — upgrade once, sync to both)

The reasoning + utterance engine lives in:
- `apps/api/` — FastAPI engine (`dual_brain`, `reasoning_vm`, `web_search`, attribution, self-knowledge, …)
- `packages/` — `cgsr` (conversation surface / voice), `base_brain`, `cloud_brain`, …

These are the same files on both branches. **Never copy-paste between folders** —
commit once, then merge.

## Workflow

1. Make changes in either folder and commit (engine or UI — it's one codebase).
2. Sync the other folder with **one command** run *in that other folder*:

   ```sh
   # in 27., ATANOR DEMO  → pull everything from ultimate
   git merge ultimate

   # in 28. ATANOR Ultimate → pull everything from demo
   git merge demo
   ```

   Because the only intentional difference is `apps/web/.env.local` (gitignored,
   demo-only), these merges are clean — no divergence, no conflicts. The engine
   stays byte-identical across both.

   Tip: do engine work in **Ultimate**, then `git merge ultimate` in **DEMO**.

## First-run setup (each new worktree)

`node_modules` is not shared between worktrees. In each folder:

```sh
cd apps/web && npm install      # or pnpm i / yarn, matching the repo
npm run dev                     # full on one port, demo on another (run both at once)
```

The Python engine (`apps/api`) can share one running backend (`:8502`) for both, or
each folder can run its own — they hit the same API contract.
