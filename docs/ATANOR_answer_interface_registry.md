# Answer-Interface Registry (experimental)

Some questions are answered best not as a sentence but as an **interface**: a
geometry question wants a labeled figure (GeoGebra-style), an arithmetic question
wants a clean formula, a function question wants a plot. ATANOR treats "which
interface answers this class of question" as **data**, not hard-coded branches —
so the mapping can grow, and one day ATANOR can grow it itself.

## How it works today

1. A deterministic solver (`apps/api/app/services/reasoning_vm.py`) computes the
   answer and attaches an `answer_visual` spec:

   ```jsonc
   // formula card
   { "kind": "formula", "title": "거듭제곱", "formula": "2^10 = 1024",
     "registry_hint": "arithmetic_power" }

   // GeoGebra-like figure
   { "kind": "geometry_figure", "shape": "square", "params": { "side": 7 },
     "metric": "perimeter", "result": 28, "formula": "둘레 = 4 × 7 = 28",
     "registry_hint": "geometry_square_perimeter" }
   ```

2. The router (`dual_brain.py`) passes `answer_visual` through on the chat result.

3. The dashboard (`apps/web/app/AnswerExperimentSurface.tsx`) renders **one
   renderer per `kind`**. `formula` → a formula card; `geometry_figure` → an SVG
   figure per `shape`.

`registry_hint` is the stable key naming the question-class → interface mapping
(`geometry_square_perimeter`, `arithmetic_power`, …). It is the seam.

## The self-editing path (vision)

The point of keeping this data-driven is that **adding a new way to answer is two
small, local edits**, not a rewrite:

- **Engine side**: a solver emits a new `answer_visual` with a new `kind` /
  `registry_hint`.
- **UI side**: `AnswerExperimentSurface` gains a branch for that `kind`.

Because both ends are small, declarative, and isolated, a future ATANOR can:
1. notice a recurring question-class it currently answers only in prose,
2. propose a `registry_hint` + an `answer_visual` shape for it,
3. draft the matching renderer branch,
4. and submit it through the existing operator-gated promotion flow (the same
   default-deny gate used for verified-store writes) for human review.

No autonomous code execution is enabled here — this file documents the seam so
that capability, when built, has a safe, reviewable surface to act on.

## Self-layout (the AI reads its own screen)

Surfaces must not collide. `AtanorUserStatusCard` measures the rendered boxes of
the answer card and the orb (`getBoundingClientRect`) after paint and, if they
intersect, slides the orb down by exactly the overlap (`--orb-dodge-y`) so nothing
covers anything. This is the deterministic seam for "ATANOR sees its own dashboard
and re-arranges": today a fixed rule (measure → dodge the orb); later the agent can
choose *where* each surface goes (corner, side, shrink) from the same measured
geometry, and propose new placement policies through the operator-gated flow.

## Adding a kind by hand (until then)

1. In `reasoning_vm.py`, return `answer_visual` from your solver.
2. In `AnswerExperimentSurface.tsx`, handle the new `kind`.
3. Add a regression test in `apps/api/tests/test_reasoning_vm.py`.

Current kinds: `formula`, `geometry_figure` (square / rectangle / circle /
triangle). Natural next: `function_plot` (y = f(x) over a range).
