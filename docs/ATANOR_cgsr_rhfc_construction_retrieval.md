# CGSR/RHFC Construction Retrieval v0

Status: local cleanup scoring adapter.

The construction bank exposes an RHFC-compatible retrieval adapter. Full RHFC
memory integration is not required for v0. The local cleanup scorer ranks
candidate constructions by:

- route/act compatibility;
- grounding score;
- naturalness score;
- novelty and usefulness;
- repeated opening penalty;
- generic fallback/template smell penalty;
- unsafe or ungrounded claim penalty.

The adapter reports `adapter_status=local_cleanup_scoring` until full RHFC
cleanup memory storage is explicitly wired.

Product mode retrieves reviewed candidates only. Lab mode may preview raw
candidate constructions with metadata. In both modes, `production_active=false`
and `construction_auto_promoted=false`.
