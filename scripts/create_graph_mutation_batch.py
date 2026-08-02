"""Compile one reviewed JSON proposal into an immutable GraphMutationBatch.

This command never writes the shipped graph. The proposal must name the exact
shipped-tree digest it was reviewed against; a stale base fails closed. The
result advances only through ``detected`` and ``proposed``. Candidate assembly,
external evaluation, queue confirmation, operator signature, and promotion are
separate authority steps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import landing_chain_lib as L  # noqa: E402
from packages.graph_scale.graph_paths import SHIPPED_GRAPH_ROOT  # noqa: E402
from packages.graph_scale.mutation_batch import (  # noqa: E402
    GraphAddition,
    GraphRetraction,
    create_mutation_batch,
    record_lifecycle_receipt,
)


PROPOSAL_SCHEMA = "atanor.graph-scale.mutation-proposal-input.v1"
_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "producer_id",
        "producer_run_id",
        "expected_base_digest_sha256",
        "additions",
        "retractions",
    }
)
_ADDITION_FIELDS = frozenset(
    {"subject", "predicate", "object", "provenance", "source_refs"}
)
_RETRACTION_FIELDS = frozenset(
    {"subject", "predicate", "object", "reason", "evidence_refs"}
)


def _list_of_objects(
    value: Any,
    *,
    fields: frozenset[str],
    label: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if type(item) is not dict or frozenset(item) != fields:
            raise ValueError(f"{label}[{index}] fields mismatch")
        result.append(item)
    return result


def compile_proposal(
    proposal_path: str | Path,
    *,
    shipped_root: str | Path = SHIPPED_GRAPH_ROOT,
    batches_root: str | Path | None = None,
) -> dict[str, Any]:
    """Validate and seal one proposal without mutating shipped state."""

    proposal_file = Path(proposal_path).resolve(strict=True)
    raw = proposal_file.read_bytes()
    proposal = L._strict_json_object(raw, label="graph mutation proposal")
    if frozenset(proposal) != _ROOT_FIELDS:
        raise ValueError("graph mutation proposal fields mismatch")
    if proposal.get("schema_version") != PROPOSAL_SCHEMA:
        raise ValueError("graph mutation proposal schema mismatch")

    additions_raw = _list_of_objects(
        proposal.get("additions"),
        fields=_ADDITION_FIELDS,
        label="additions",
    )
    retractions_raw = _list_of_objects(
        proposal.get("retractions"),
        fields=_RETRACTION_FIELDS,
        label="retractions",
    )
    additions = tuple(
        GraphAddition(
            subject=item["subject"],
            predicate=item["predicate"],
            object=item["object"],
            provenance=item["provenance"],
            source_refs=tuple(item["source_refs"]),
        )
        for item in additions_raw
    )
    retractions = tuple(
        GraphRetraction(
            subject=item["subject"],
            predicate=item["predicate"],
            object=item["object"],
            reason=item["reason"],
            evidence_refs=tuple(item["evidence_refs"]),
        )
        for item in retractions_raw
    )

    live = Path(shipped_root).resolve(strict=True)
    actual_base_digest = L._tree_sha256(live)
    expected_base_digest = proposal.get("expected_base_digest_sha256")
    if expected_base_digest != actual_base_digest:
        raise ValueError("proposal base digest is stale or invalid")

    reference = create_mutation_batch(
        producer_id=proposal["producer_id"],
        producer_run_id=proposal["producer_run_id"],
        base_digest_sha256=actual_base_digest,
        additions=additions,
        retractions=retractions,
        batches_root=batches_root,
    )
    proposal_sha256 = hashlib.sha256(raw).hexdigest()
    detected_receipt = record_lifecycle_receipt(
        reference.root,
        stage="detected",
        evidence={
            "proposal_input_sha256": proposal_sha256,
            "production_store_mutated": False,
        },
    )
    proposed_receipt = record_lifecycle_receipt(
        reference.root,
        stage="proposed",
        evidence={
            "proposal_input_sha256": proposal_sha256,
            "base_digest_sha256": actual_base_digest,
            "production_store_mutated": False,
        },
    )
    return {
        "batch_id": reference.batch_id,
        "batch_root": str(reference.root),
        "manifest_sha256": reference.manifest_sha256,
        "base_digest_sha256": reference.base_digest_sha256,
        "additions": reference.addition_count,
        "retractions": reference.retraction_count,
        "latest_stage": "proposed",
        "detected_receipt": str(detected_receipt),
        "proposed_receipt": str(proposed_receipt),
        "production_store_mutated": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--shipped", default=str(SHIPPED_GRAPH_ROOT))
    parser.add_argument(
        "--batches-root",
        default="",
        help="optional isolated spool root (tests/scoped workflows)",
    )
    args = parser.parse_args(argv)
    try:
        result = compile_proposal(
            args.proposal,
            shipped_root=args.shipped,
            batches_root=args.batches_root or None,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "production_store_mutated": False,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
