# -*- coding: utf-8 -*-
"""Emit the SL-1 self-projection as a graph-mutation PROPOSAL. Writes nothing to the shipped graph.

Measured 2026-07-28 (docs/ATANOR_SELF_MODEL_CALIBRATION_2026-07-28.md): asked "what parts does
atanor have?", the engine abstains -- correctly and honestly, because the graph holds no `has_a`
edge for `atanor`. Asked the same shape about a bicycle it answers. The machinery is present; only
the data is missing. This proposal is that data.

SCOPE -- deliberately just the projection, not the whole census
---------------------------------------------------------------
`(atanor, has_a, <organ>)` only. The per-organ census -- `(deliberator, is_a, atanor_organ)` and
its possessions -- is NOT proposed here, on measurement:

    22 of 130 organ names already exist in the shipped graph as real world concepts, with edges:
      conversation 200 (located_in dinner) · guard 96 (located_in jail)
      model 71 (is_a representation)       · deliberator 2 (defined_as "A person who deliberates")

Adding `(deliberator, is_a, atanor_organ)` bare would put ATANOR's deliberation organ and a person
who deliberates behind one surface string -- the sense-vs-alias conflation the store's own
architecture exists to prevent. The sense registry resolves exactly this, by clustering a term's
`is_a` parents into distinct senses, but it is built over the top-500 hubs and most colliding organ
names are low-degree, so they would fall through as "one reading". Fixing that is a registry-coverage
question, not a reason to namespace the terms -- namespacing would be the adapter this whole line of
work is removing. Tracked as debt; see the calibration doc.

The subject side is clean: `atanor` currently carries no edges at all, so these 130 additions
collide with nothing.

    python scripts/propose_self_projection.py            # write the proposal JSON
    python scripts/create_graph_mutation_batch.py --proposal <that file>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

PROPOSAL_SCHEMA = "atanor.graph-scale.mutation-proposal-input.v1"
PRODUCER = "continuous_self"


def build(run_id: str) -> dict:
    import landing_chain_lib as L
    from packages.continuous_self.architecture_census import organ_roster
    from packages.continuous_self.self_projection import SELF_SUBJECT, project_parts
    from packages.graph_scale.graph_paths import SHIPPED_GRAPH_ROOT

    # `has_a` is checked against the store's own predicate column, as everywhere else -- if the
    # graph did not use it, this proposal would be empty rather than inventing a relation.
    triples = project_parts(organ_roster())
    additions = [
        {
            "subject": s,
            "predicate": p,
            "object": o,
            # Provenance is a filesystem read, and says so. No claim of external corroboration.
            "provenance": "continuous_self.self_projection over architecture_census.organ_roster "
                          "(packages/ directory listing; read-only)",
            "source_refs": [f"repo:packages/{o}"],
        }
        for s, p, o in triples
    ]
    return {
        "schema_version": PROPOSAL_SCHEMA,
        "producer_id": PRODUCER,
        "producer_run_id": run_id,
        "expected_base_digest_sha256": L._tree_sha256(SHIPPED_GRAPH_ROOT),
        "additions": additions,
        "retractions": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=REPO / "runtime" / "graph_mutation_spool" / "proposals"
                    / "self_projection.json")
    ap.add_argument("--run-id", default="sl1_self_projection_v1")
    args = ap.parse_args()
    proposal = build(args.run_id)
    if not proposal["additions"]:
        print(json.dumps({"ok": False, "error": "no projectable triples -- "
                          "the graph does not use `has_a`"}))
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(proposal, indent=2, sort_keys=True), encoding="utf-8")
    subjects = {a["subject"] for a in proposal["additions"]}
    print(json.dumps({
        "ok": True, "proposal": str(args.out),
        "additions": len(proposal["additions"]), "subjects": sorted(subjects),
        "base_digest_sha256": proposal["expected_base_digest_sha256"],
        "production_store_mutated": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
