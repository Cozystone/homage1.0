# Architecture Registry

This package validates the exhaustive, checked-in census at
`data/architecture/catalog/organ_registry_v1.json`.

The catalog separates source presence, runtime wiring, decision authority, and
evidence maturity. A package directory is therefore only evidence that an organ
was built. It is not evidence that the organ is live, authoritative, integrated,
or capable.

The initial V0 census intentionally records wiring as `unknown` and authority as
`none` unless a later change cites direct evidence. Architectural lifecycle and
domain fields describe intended ownership, not benchmark performance.

For a deterministic static-import census, run:

```powershell
python -m packages.architecture_registry.static_graph --json
```

Its production/test references are investigation evidence only. They do not
promote an organ from `unknown` to live, authoritative, integrated, or capable.

The narrower critical runtime-edge manifest is checked separately:

```powershell
python -m packages.architecture_registry.runtime_graph --json
```

`data/architecture/catalog/runtime_edges_v1.json` source-binds selected call
sites and keeps static import, source-confirmed reachability, immutable exercised
trace, and authority as independent fields. A source-confirmed call is still
only M1 mechanism evidence. The manifest rejects E5, benchmark-lift, and
capability claims, and it leaves deployment activity and unrecorded production
traces unknown.

Run the strict gate from the repository root:

```powershell
python -m packages.architecture_registry
```

The command exits with status 2 for malformed data, duplicate JSON keys,
missing or extra package directories, duplicate organs, invalid enums, missing
evidence paths, or unsupported claims without refs.
