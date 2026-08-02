# Atlas Router

Atlas Router is a proof-only package for the first ATANOR auxiliary innovation
axis: Dijkstra Trust Router.

It does not modify Local Brain, does not promote candidates, does not write to
production stores, and does not touch the active 24h candidate-learning run. It
only selects safe temporary Working Memory attach paths in a deterministic
in-memory graph.

Future integration points may include Graph Hub, Atlas Network, graph cartridge
routing, and public source selection. It is not active in the production path
yet.

Run the proof:

```powershell
python -m packages.atlas_router.proof
```

Run tests:

```powershell
python -m pytest packages/atlas_router/tests -q
```

