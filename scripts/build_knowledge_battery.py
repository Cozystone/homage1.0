# -*- coding: utf-8 -*-
"""SEALED C2 knowledge holdout — the ①/②-grade gate for the pillar. Draws canonical major-entity
facts (the verified supplementary overlay = Wikidata-sourced) as an ORACLE, splits dev/holdout by a
stable stem hash, and seals with a SHA. eval_knowledge_battery.py then measures whether the resolution
path (store → alias → qid-label sidecar → supplementary overlay) SURFACES each fact correctly, plus a
HALLUCINATION control (made-up subjects that MUST abstain).

Scope is honest: it covers the relations the overlay makes complete (capital/continent/occupation/
country of major entities), so a GREEN here = those domains complete+correct+hallucination-0, sealed
— NOT the whole world-pack. Run: python scripts/build_knowledge_battery.py
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OVERLAY = REPO / "data" / "graph_scale" / "supplementary_facts.jsonl"
OUT = REPO / "data" / "eval"
SEED = 20260718
# per-relation cap so no single relation dominates the sealed battery
CAP = {"capital": 200, "country": 200, "continent": 200, "occupation": 400, "located_country": 400}
# hallucination control: plausible-shaped but non-existent subjects that MUST abstain
CONTROL = [("Zorbland", "capital"), ("Flarnia", "capital"), ("Qwibble City", "country"),
           ("Xenthor Blaverton", "occupation"), ("Plimbo Republic", "continent"),
           ("Grumblewick", "located_country")]


def _split(stem: str) -> str:
    return "holdout" if int(hashlib.sha1(stem.encode("utf-8")).hexdigest(), 16) % 100 < 30 else "dev"


def main() -> int:
    if not OVERLAY.exists():
        print("run backfill_supplementary_facts.py first"); return 1
    rng = random.Random(SEED)
    # collect EN-subject canonical facts from the overlay (english-core keys), dedup, cap per relation
    byrel: dict[str, dict[str, set[str]]] = {}
    for line in OVERLAY.open(encoding="utf-8"):
        r = json.loads(line)
        subj, rel = r["subject"], r["relation"]
        if not subj.isascii():                              # english subject key for the battery stem
            continue
        byrel.setdefault(rel, {}).setdefault(subj, set()).update(r["object"])
    items: list[dict] = []
    for rel, subjmap in byrel.items():
        subs = list(subjmap)
        rng.shuffle(subs)
        for subj in subs[:CAP.get(rel, 200)]:
            accept = sorted(subjmap[subj])
            stem = f"{subj}|{rel}"
            items.append({"subject": subj, "relation": rel, "accept": accept,
                          "control": False, "split": _split(stem)})
    for subj, rel in CONTROL:
        items.append({"subject": subj, "relation": rel, "accept": [], "control": True,
                      "split": _split(f"{subj}|{rel}")})
    items.sort(key=lambda it: (it["relation"], it["subject"]))
    OUT.mkdir(parents=True, exist_ok=True)
    for split in ("dev", "holdout"):
        rows = [it for it in items if it["split"] == split]
        path = OUT / f"seal_knowledge_{split}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for it in rows:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        (OUT / f"seal_knowledge_{split}.manifest.json").write_text(
            json.dumps({"n": len(rows), "controls": sum(1 for it in rows if it["control"]),
                        "sha256": sha, "seed": SEED, "built": "2026-07-18"}, indent=2), encoding="utf-8")
        by = {}
        for it in rows:
            by[it["relation"]] = by.get(it["relation"], 0) + 1
        print(f"[{split}] n={len(rows)} controls={sum(1 for it in rows if it['control'])} "
              f"sha={sha[:12]} by_relation={by}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
