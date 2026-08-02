"""Strict, unsigned benchmark measurement receipts.

These receipts bind measurements to exact source and dataset bytes.  They are
not external evaluator signatures and therefore grant no promotion authority.
"""

from .receipt import (
    BENCHMARK_EVIDENCE_KIND,
    BENCHMARK_EVIDENCE_SCHEMA,
    BenchmarkEvidenceError,
    aggregate_items,
    bind_files,
    canonical_json_bytes,
    finalize_manifest,
    item_id,
    outcome_digest,
    verify_manifest,
    write_manifest_exclusive,
)

__all__ = [
    "BENCHMARK_EVIDENCE_KIND",
    "BENCHMARK_EVIDENCE_SCHEMA",
    "BenchmarkEvidenceError",
    "aggregate_items",
    "bind_files",
    "canonical_json_bytes",
    "finalize_manifest",
    "item_id",
    "outcome_digest",
    "verify_manifest",
    "write_manifest_exclusive",
]
