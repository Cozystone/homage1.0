# Pattern #18 Graph Hub checksum diagnosis

Date: 2026-07-27
Scope: read-only diagnosis; no Graph Hub code, cartridge, registry, staging, or graph mutation

## Verdict

The 11 installed cartridges are not checksum-less legacy fixtures. Every one
contains a non-empty 64-character SHA-256 value. All 11 fail verification for
one shared reason:

1. `make_graph_cartridge()` initializes `metadata.size_bytes` to `0`;
2. it computes and stores `metadata.checksum`;
3. it then changes `metadata.size_bytes`;
4. verification removes only `metadata.checksum`, so the post-hash
   `size_bytes` mutation changes the verified payload.

For all 11 installed cartridges, the stored checksum exactly matches the
current payload after setting only `metadata.size_bytes` back to `0`.

| Check | Result |
|---|---:|
| Installed cartridges inspected | 11 |
| Non-empty 64-character checksums | 11/11 |
| Current `verify_cartridge_checksum()` PASS | 0/11 |
| Stored checksum matches payload with `size_bytes=0` | 11/11 |

The defect has existed in `packages/graph_hub/cartridge_format.py` since the
Graph Hub builder was introduced. It is not an algorithm mismatch between
packing and verification: both call the same canonical `checksum_payload()`.
That helper parses the object, removes the checksum field, sorts keys, and
uses compact JSON before SHA-256. Whitespace, indentation, and JSON key order
therefore do not explain the failures.

## Synthetic controls

A fresh cartridge produced by the current builder and written through
`write_cartridge()` returned:

```text
current_builder_valid=False
```

An otherwise equivalent synthetic cartridge whose mutable metadata was
finalized before recomputing `metadata.checksum` returned:

```text
corrected_valid=True
```

The corrected object also verified after compact and deliberately different
pretty JSON serializations, confirming whitespace independence.

## Broader census

The same read-only check found 36 local `*.graphpack.json` files across
`authored`, `cartridges`, `exported`, and `installed`; all 36 carry a checksum
and all 36 fail for the same builder-order defect. Only 11 are installed, but a
durable repair should regenerate every local copy rather than leaving invalid
source/export artifacts that can be reinstalled later.

`metadata.size_bytes` also does not currently equal physical file length,
because it is measured from compact in-memory JSON while `write_json()` emits
pretty JSON and Windows text output may use CRLF. This is a metadata-semantics
issue, not the cause of checksum failure; the checksum is over parsed canonical
JSON rather than file bytes.

## Revised implementation estimate

Checksum-integrity closure is estimated at **14–24 hours**:

- finalize builder metadata before hashing and add focused controls;
- fail closed at install, mount, and Local Brain import boundaries;
- regenerate/reseal the 36 local packs and refresh the 11 installed records;
- prove normal install/import compatibility and reject post-install mutation.

This estimate covers checksum integrity only. A caller can author a malicious
pack and calculate a matching unkeyed checksum. Establishing publisher
identity, signature authority, or a non-caller-controlled trust root is a
separate security boundary and is not claimed by this diagnosis.
