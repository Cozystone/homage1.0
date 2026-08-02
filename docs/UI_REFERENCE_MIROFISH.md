# UI Reference: MiroFish Console

Date: 2026-06-11

Reference links:

- Repository: https://github.com/666ghj/MiroFish
- Demo inspected: https://666ghj.github.io/mirofish-demo/console/process/proj_f95898d38529

## What Was Observed

- The MiroFish demo uses a console layout with a top layout switcher:
  `Graph`, `Split`, `Workbench`.
- In split mode, the left half is a large graph/memory visualization and the
  right half shows the active build/process panel.
- The graph panel has a light canvas, node-link visualization, type legend,
  refresh/maximize controls, and selected node/edge detail affordances.
- The process side uses numbered cards, API labels, status badges, build
  metrics, and a bottom black system log.
- In later interaction screens, the same left graph can be retained while the
  right workbench changes into interaction/chat mode.

## License Decision

MiroFish is licensed under AGPL-3.0. To avoid importing AGPL obligations into
this repository, no MiroFish code was copied verbatim. ATANOR borrows the
interaction structure and visual hierarchy only:

- top graph/split/workbench switcher
- left ontology-memory graph
- right process-or-chat workbench
- bottom system dashboard log

The implementation in `apps/web/app/page.tsx` and `apps/web/app/globals.css`
is original React/CSS tailored to ATANOR.
