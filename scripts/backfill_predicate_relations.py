#!/usr/bin/env python3
"""Backfill: materialize predicate-anchored association edges for the EXISTING graph.

The decomposer now emits subject--<predicate>-->object edges for NEW learning, but the
already-learned store (clean_seed_v2) holds those associations only inside case_frames.
This derives them into real relation rows (the same schema the store uses), weighted by
neuroplasticity.predicate_informativeness (data-derived, no rule list), and writes them as
a standalone staging artifact ready to merge at go-live. Read-only on the live store.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.cgsr.cgsr.ingestion.decomposer import digest_id, normalize_concept   # noqa: E402
from packages.cloud_brain.neuroplasticity import plasticity_tick                    # noqa: E402

STORE = REPO_ROOT / "data" / "cloud_brain" / "candidate_runs" / "clean_seed_v2"
OUT = REPO_ROOT / "data" / "cloud_brain" / "staging" / "clean_seed_v3_predicate_relations.jsonl"


def _read(fn: str):
    p = STORE / fn
    if p.exists():
        for line in p.open(encoding="utf-8"):
            try:
                yield json.loads(line)
            except Exception:
                pass


def main() -> int:
    name2id = {normalize_concept(c["canonical_name"]): c["concept_id"] for c in _read("concepts.jsonl")}
    now = datetime.now(timezone.utc).isoformat()

    seen = set()
    raw = []
    for fr in _read("case_frames.jsonl"):
        pred = fr.get("predicate")
        if not pred:
            continue
        pr = normalize_concept(pred) or str(pred)
        subs = [r["head"] for r in (fr.get("case_roles") or []) if r.get("role") in ("TOPIC", "SUBJ")]
        objs = [r["head"] for r in (fr.get("case_roles") or []) if r.get("role") in ("OBJ", "ADVL")]
        for s in subs:
            si = name2id.get(normalize_concept(s))
            if not si:
                continue
            for o in objs:
                oi = name2id.get(normalize_concept(o))
                if not oi or oi == si:
                    continue
                key = (si, pr, oi)
                if key in seen:
                    continue
                seen.add(key)
                dk = digest_id("relation_key", f"{si}:{pr}:{oi}:backfill")
                raw.append({
                    "relation_id": digest_id("vsr", dk),
                    "source_concept_id": si, "relation": pr, "target_concept_id": oi,
                    "dedupe_key": dk, "seen_count": 1, "updated_at": now,
                    "provenance": {"source": "predicate_backfill", "store": STORE.name},
                })

    # apply data-derived informativeness weight + bounded plasticity (no decay yet: fresh)
    tick = plasticity_tick(raw, datetime.now(timezone.utc), half_life_days=3650.0, prune_floor=0.0)
    rows = tick["kept"]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # report
    rows.sort(key=lambda r: r["weight"], reverse=True)
    print(f"[BACKFILL] existing IS_A edges: ~1410")
    print(f"[BACKFILL] materialized predicate association edges: {len(rows)} ({tick['stats']['distinct_predicates']} predicates)")
    print(f"[BACKFILL] artifact: {OUT}  (staging, ready to merge at go-live)")
    id2n = {c["concept_id"]: c["canonical_name"] for c in _read("concepts.jsonl")}
    print("[BACKFILL] highest-weight (most informative) associations:")
    shown = 0
    for r in rows:
        s, t = id2n.get(r["source_concept_id"], "?"), id2n.get(r["target_concept_id"], "?")
        if any("가" <= ch <= "힣" for ch in s) and shown < 10:
            print(f"   w={r['weight']:.2f}  {s} --[{r['relation']}]--> {t}")
            shown += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
