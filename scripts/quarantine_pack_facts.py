#!/usr/bin/env python3
"""Retroactive pack sweep: quarantine facts the honesty eval flagged as WRONG.

The forward path is already gated (curated judge blocks contradicted promotions), but facts
that entered the pack BEFORE the gate keep getting served (→, is_a ).
This script applies a DATA-driven quarantine list — the knowledge of what is wrong lives in
data/base_brain/pack_quarantine.json (operator-curated, evidence-backed), never in code.

Safety: full pack backup before touching anything; every action appended to a ledger;
idempotent (already-applied entries are skipped). Removing a wrong-only concept makes the
engine ABSTAIN on it — which queues it on the abstain-to-ingest loop, so the next feeder
run re-learns the term from a grounded source. The system heals: wrong fact out, honest
abstain, correct fact back in.

 python scripts/quarantine_pack_facts.py # apply
 python scripts/quarantine_pack_facts.py --dry-run # show what would change
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from packages.base_brain.models import PACK_PATH  # noqa: E402

QUARANTINE_LIST = REPO / "data" / "base_brain" / "pack_quarantine.json"
LEDGER = REPO / "data" / "base_brain" / "pack_quarantine_ledger.jsonl"


def _log(entry: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**entry, "at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                            ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    directives = json.loads(QUARANTINE_LIST.read_text(encoding="utf-8"))["entries"]
    pack = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    concepts = pack["semantic_graph"]["concepts"]
    by_id = {c.get("concept_id"): c for c in concepts}
    changed = 0

    for d in directives:
        cid, action = d["concept_id"], d["action"]
        concept = by_id.get(cid)
        if concept is None:
            print(f"  skip (already gone): {cid} {d.get('name')}")
            continue
        if action == "remove_concept":
            match = d.get("match", "")
            if match and match not in str(concept.get("short_description") or ""):
                print(f"  skip (description changed since flag): {cid} {d.get('name')}")
                continue
            if not args.dry_run:
                concepts.remove(concept)
                _log({"action": action, "concept_id": cid, "name": d.get("name"),
                      "removed_description": concept.get("short_description"),
                      "reason": d["reason"]})
            print(f"  REMOVE concept {d.get('name')} ({cid}): {concept.get('short_description')!r}")
            changed += 1
        elif action == "remove_relation":
            rels = concept.get("relations") or []
            hit = [r for r in rels
                   if r.get("relation") == d["relation"] and str(r.get("target")) == d["target"]]
            if not hit:
                print(f"  skip (relation already gone): {d.get('name')} {d['relation']}->{d['target']}")
                continue
            if not args.dry_run:
                concept["relations"] = [r for r in rels if r not in hit]
                _log({"action": action, "concept_id": cid, "name": d.get("name"),
                      "removed": [f"{d['relation']}->{d['target']}"] , "reason": d["reason"]})
            print(f"  REMOVE relation {d.get('name')}: {d['relation']} -> {d['target']}")
            changed += 1
        else:
            print(f"  unknown action {action!r} — skipped")

    if args.dry_run or changed == 0:
        print(f"dry-run={args.dry_run}, changes={changed} (pack untouched)")
        return 0

    backup = PACK_PATH.with_suffix(f".bak-{time.strftime('%Y%m%d-%H%M%S')}.json")
    backup.write_bytes(PACK_PATH.read_bytes())
    tmp = PACK_PATH.with_suffix(PACK_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PACK_PATH)                       # atomic, like the promoter
    print(f"applied {changed} quarantine(s); backup: {backup.name}; ledger: {LEDGER.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
