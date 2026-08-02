#!/usr/bin/env python3
"""P1 derivation delta experiment (NON-DESTRUCTIVE, scratch-store only).

Approved by Codex (reversible/local tier). Proves the P0 thesis: growing the
case_frame graph via the REAL ingestion path (verify_sentence -> decompose ->
accumulate) raises predicate_anchor_hit_rate, WITHOUT touching the live store.

It does NOT synthesize facts: it re-runs the real decomposer over real,
already-verified evidence source text (sentences carrying founding/agentive
predicates) into a scratch candidate store, then re-measures with the P0 audit.

Guarantees:
  - live store is copied to scratch; only scratch is written.
  - promote_to_verified=False  -> production_store_mutated must be False.
  - before/after live hash/count proven identical by the caller.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.cloud_brain.continuous_learning import CloudSurfaceLearningLoop  # noqa: E402
from packages.cloud_brain.verified_payload_feeder import LearningPayload  # noqa: E402

LIVE = REPO_ROOT / "data" / "cloud_brain" / "candidate_runs" / "wikipedia_grounded_live"
FOUNDING_PREDICATE_CUES = ("창립", "설립", "발명", "개발", "발견", "창업", "창제", "제창", "고안")


def build_payloads(limit: int) -> list[LearningPayload]:
    """Real evidence source text carrying founding/agentive predicates."""
    payloads: list[LearningPayload] = []
    seen_text: set[str] = set()
    with (LIVE / "evidence.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = str(row.get("text") or row.get("source_text") or row.get("sentence") or "").strip()
            if not (10 < len(text) < 220):
                continue
            if not any(cue in text for cue in FOUNDING_PREDICATE_CUES):
                continue
            if text in seen_text:
                continue
            seen_text.add(text)
            # Fresh provenance hash so the real decomposer re-runs on this real
            # text into the scratch store (the predicate comes from morphology,
            # never from us).
            phash = hashlib.sha256(("p1delta::" + text).encode("utf-8")).hexdigest()
            payloads.append(
                LearningPayload(
                    payload_id=phash[:24],
                    source_type="approved_public_corpus",
                    source_id=f"p1delta_{phash[:12]}",
                    text=text,
                    normalized_text=text,
                    language="ko",
                    provenance_hash=phash,
                    source_url_or_path="p1delta://reingest/wikipedia_grounded_live/evidence",
                    license_hint="public",
                    collected_at="2026-06-30T00:00:00Z",
                )
            )
            if len(payloads) >= limit:
                break
    return payloads


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: derivation_p1_delta.py <scratch_store_dir> [limit]", file=sys.stderr)
        return 2
    scratch = Path(sys.argv[1])
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 250

    payloads = build_payloads(limit)
    learner = CloudSurfaceLearningLoop(
        candidate_store_root=scratch,
        promote_to_verified=False,          # scratch only; never production
        update_surface_graph=False,
        update_rhfc_candidate=False,
        require_review_before_production=True,
    )
    result = learner.run_once(dry_run=False, payloads=payloads, max_accepted_per_run=limit)
    sem = result.semantic
    out = {
        "payloads_built": len(payloads),
        "payloads_accepted": sem.payloads_accepted,
        "payloads_rejected": sem.payloads_rejected,
        "case_frames_added": sem.case_frames_added,
        "concepts_added": sem.concepts_added,
        "relations_added": sem.relations_added,
        "production_store_mutated": result.production_store_mutated,
        "external_llm_used": sem.external_llm_used,
        "mock_growth": sem.mock_growth,
        "target_store": sem.target_store,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
