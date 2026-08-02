# Pattern #18 checksum migration result

Status: **GREEN — bounded mechanism repair**

## Root fix

`make_graph_cartridge()` now fixes `metadata.size_bytes` while the checksum field
has its final 64-byte width, then calculates the checksum over that finalized
payload. The focused regression test was RED before the fix (`1 failed,
1 passed`) and the final migration suite is GREEN (`8 passed`).

## Existing-artifact migration

The migration was included as a separate, fail-closed step rather than silently
reissuing or reinstalling cartridges:

- Scope: 36 graphpacks across `authored`, `cartridges`, `exported`, and
  `installed`; 11 installed-registry records.
- Precondition: every stored checksum had to equal the legacy digest obtained
  from the same payload with only `metadata.size_bytes` reset to zero.
- Allowed graphpack mutation: the existing 64 hexadecimal checksum bytes only.
- Allowed registry mutation: the derived `checksum_valid` flag only.
- Entitlements: mutation forbidden and byte identity required.
- Unknown checksum lineage, count drift, source drift, or receipt drift:
  fail closed.

The sealed plan was applied exactly once. It changed 36 graphpacks plus the
installed registry, without reinstalling or reissuing anything.

## Post-apply verification

- Valid graphpack checksums: 36/36.
- Installed registry `checksum_valid=true`: 11/11.
- Non-checksum raw-byte mismatches: 0/36.
- Non-checksum JSON mismatches: 0/36.
- Entitlement SHA-256 remained
  `1c82673974a9a1d806844f47ea2a5a021df94a6bae715c91e7fdcaf4a4e42665`.
- A fresh idempotence census reports 36 already-current, 0 legacy, 0 unknown,
  and 0 files requiring another change.

## Evidence

- Plan:
  `reports/graph_hub_checksum_migration_plan_20260727.json`
  (`binding_sha256:688ae857c5c4641fb3ccb0d79797367ea043f5a8464e37ea2de32675cac9c8ea`)
- Apply receipt:
  `reports/graph_hub_checksum_migration_apply_20260727.json`
  (`sha256:28e23ea99518077117ece8204e0e8f2af49a6610795fd5aed46a0df7009a52ff`)

This is a checksum-integrity mechanism result. It does not by itself establish
benchmark or general capability lift.
