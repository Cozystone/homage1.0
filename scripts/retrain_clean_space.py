# -*- coding: utf-8 -*-
"""Retrain the CLEAN phase space on all clean sources — ConceptNet (EN+KO) plus the
newly harvested Korean taxonomy (Wikidata + Korean Wikipedia categories).

Goal (owner, 2026-07-09): clean Korean geometry so →, → resonate
the way dog→hound already does in the English ConceptNet space. Reads the gated
candidate ledgers, trains RotatE-lite on GPU (train_from_triples — no production
touch), and saves to data/graph_scale/phase_space_conceptnet/ ATOMICALLY with a
timestamped backup so a bad retrain can be rolled back (as we did before).

Never writes production. The clean space is a read-only reasoning aid.
"""
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")   # Korean/em-dash safe on Windows console
except Exception:
    pass

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages"))
from graph_scale import gpu_phase_space as gps  # noqa: E402

LEDGER = REPO / "data" / "cloud_brain" / "derived_candidates"
OUT = REPO / "data" / "graph_scale" / "phase_space_conceptnet"

# Which ledgers feed the clean space. ConceptNet (broad, EN-heavy + some KO) plus
# the two diverse Korean sources. is_a_closure is EXCLUDED — it's the derived
# transitive closure (noisy for geometry); we train on asserted edges only.
SOURCES = ("conceptnet_", "wikidata_ko_", "wikipedia_ko_", "extracted_")

# Wikipedia maintenance/faceting markers that are NOT taxonomy — drop even if a
# stale ledger still holds them (defense-in-depth for the geometry).
_JUNK = ("토막글", "관한 ", "토론", "위키", "프로젝트", "포털", "목록", "일람",
         "동음이의", "따른", "별 ")


def _junk(s: str, o: str) -> bool:
    for m in _JUNK:
        if m in o or m in s:
            return True
    return False


def load_triples(english_only: bool = False) -> list[tuple[str, str, str]]:
    """english_only (surgery Phase 4, 2026-07-17): the store went English-only, so the
 geometry should be trained on the same world — drop every KO ledger file and every row
 touching Hangul. Honest scope note: this removes CROSS-LINGUAL mixing from the space
 (the science/ class); it cannot remove ConceptNet's own intra-English sense mixing
 (gravity is_a show, the film sense) — that pollution is in the asserted source itself.
 """
    import re as _re
    _HAN = _re.compile(r"[가-힣]")
    triples: list[tuple[str, str, str]] = []
    by_src: dict[str, int] = {}
    for path in sorted(LEDGER.glob("*.jsonl")):
        if not any(path.name.startswith(p) for p in SOURCES):
            continue
        if "closure" in path.name:
            continue
        if english_only and (_HAN.search(path.name) or path.name.startswith(("wikidata_ko_", "wikipedia_ko_"))):
            continue
        n = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            s, p, o = r.get("s"), r.get("p"), r.get("o")
            if s and p and o and s != o and len(s) <= 40 and len(o) <= 40:
                if _junk(s, o):
                    continue
                if english_only and (_HAN.search(s) or _HAN.search(o) or _HAN.search(str(p))):
                    continue
                triples.append((s, p, o))
                n += 1
        by_src[path.name] = n
    print(f"loaded {len(triples):,} triples from {len(by_src)} ledgers"
          f"{' (english-only)' if english_only else ''}")
    for k in sorted(by_src, key=lambda x: -by_src[x])[:12]:
        print(f"   {by_src[k]:>8,}  {k}")
    return triples


def save_atomic(space: dict, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    # backup current
    if (out / "phases.npy").exists():
        bak = out.parent / f"phase_space_conceptnet.bak.{time.strftime('%Y%m%d_%H%M%S')}"
        shutil.copytree(out, bak)
        print(f"backed up current space -> {bak.name}")
    # write to temp names then replace (clean_space mmaps phases.npy by mtime)
    np.save(out / "_phases.npy", space["phases"])
    np.save(out / "_relations.npy", space["rel"])
    (out / "_terms.json").write_text(
        json.dumps({"terms": space["terms"], "preds": space["preds"]}, ensure_ascii=False),
        encoding="utf-8")
    import os
    os.replace(out / "_phases.npy", out / "phases.npy")
    os.replace(out / "_relations.npy", out / "relations.npy")
    os.replace(out / "_terms.json", out / "terms.json")
    print(f"saved clean space -> {out}  ({space['terms_n']:,} terms, dim {space['dim']})")


def verify(space: dict):
    checks = ["자동차", "사과", "커피", "서울", "동물", "개", "컴퓨터",
              "dog", "apple", "doctor", "coffee"]
    print("\n=== neighbor spot-check ===")
    for term in checks:
        nb = gps.neighbors_of(term, space, k=6)
        if nb:
            print(f"  {term:>8} -> " + ", ".join(f"{t}({s})" for t, s in nb))
        else:
            print(f"  {term:>8} -> (not in space)")


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    # 40 epochs trains in ~1s on GPU at this scale, so the sharper final run can
    # afford many more epochs (tighter clusters for thinly-connected Korean terms).
    epochs = 120
    for a in sys.argv:
        if a.startswith("--epochs="):
            epochs = int(a.split("=", 1)[1])
    triples = load_triples(english_only="--english-only" in sys.argv)
    ko = sum(1 for s, _p, o in triples if any('가' <= c <= '힣' for c in s))
    print(f"   (Korean-subject edges: {ko:,})")
    if dry:
        print("dry run — not training")
        sys.exit(0)
    t0 = time.time()
    space = gps.train_from_triples(triples, dim=64, epochs=epochs, min_degree=2)
    if "error" in space:
        print("TRAIN ERROR:", space)
        sys.exit(1)
    print(f"trained in {int(time.time()-t0)}s  hits@10={space['hits_at_10']}  "
          f"terms={space['terms_n']:,}")
    verify(space)
    save_atomic(space, OUT)
    print("\ndone.")
