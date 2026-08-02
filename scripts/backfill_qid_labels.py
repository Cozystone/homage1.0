# -*- coding: utf-8 -*-
"""C2 fix (owner-approved 2026-07-18, read-only-sidecar path): resolve the world-pack's DANGLING
Q-id objects (referenced as objects but never ingested as subjects → no label) to labels, via the
Wikidata API, into a READ-ONLY sidecar `data/graph_scale/qid_labels.jsonl`. This does NOT write to
the triple store ( respected) — it is a label lookup the resolver consults at read time,
the same discipline as the isa_verdict.col / lang_gate.col sidecars.

Prioritises Q-ids that are objects of KEY relations (the ones that make fact-QA answerable), so a
bounded run already lifts the C2 audit. Resumable: skips Q-ids already in the sidecar.

 python scripts/backfill_qid_labels.py [--limit N] [--count-only]
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np                                                     # noqa: E402
from packages.graph_scale.triple_store import TripleStore             # noqa: E402

SIDECAR = REPO / "data" / "graph_scale" / "qid_labels.jsonl"
_QID = re.compile(r"^Q\d+$")
KEY_RELATIONS = ("capital", "country", "born_in", "occupation", "author", "discovered_by",
                 "defined_as", "is_a", "creator", "part_of", "located_in")
_UA = "ATANOR-C2-label-backfill/1.0 (research; blueyjkim@gmail.com)"


def _dangling_key_qids(st: TripleStore) -> list[str]:
    cols = st.open_columns()
    s_col, p_col, o_col = cols["s"], cols["p"], cols["o"]
    subjects = np.unique(s_col)                             # sorted term-ids that appear as subject
    term = st.terms.term
    dangling_ids: set[int] = set()
    for rel in KEY_RELATIONS:
        rid = st.terms.lookup(rel)
        if rid is None:
            continue
        objs = np.unique(o_col[p_col == rid])
        dangling = objs[~np.isin(objs, subjects, assume_unique=True)]   # vectorised set-difference
        dangling_ids.update(int(x) for x in dangling.tolist())
    # term() only the (far fewer) dangling ids, keep the Q-ids
    want = {lab for lab in (term(i) for i in dangling_ids) if _QID.match(lab)}
    return sorted(want, key=lambda q: int(q[1:]))


def _load_done() -> set[str]:
    done = set()
    if SIDECAR.exists():
        for line in SIDECAR.open(encoding="utf-8"):
            try:
                done.add(json.loads(line)["qid"])
            except Exception:
                pass
    return done


def _fetch(ids: list[str]) -> dict[str, dict]:
    url = ("https://www.wikidata.org/w/api.php?action=wbgetentities&props=labels"
           "&languages=en|ko&format=json&ids=" + urllib.parse.quote("|".join(ids)))
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    out = {}
    for qid, ent in (d.get("entities") or {}).items():
        labs = ent.get("labels") or {}
        en = (labs.get("en") or {}).get("value")
        ko = (labs.get("ko") or {}).get("value")
        if en or ko:
            out[qid] = {"en": en, "ko": ko}
    return out


def main() -> int:
    limit = None
    count_only = "--count-only" in sys.argv
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
    st = TripleStore(REPO / "data" / "graph_scale" / "world_pack_full",
                     dict_backend="sharded", write_src=False)
    qids = _dangling_key_qids(st)
    print(f"dangling Q-ids on KEY relations: {len(qids)}", flush=True)
    if count_only:
        return 0
    done = _load_done()
    todo = [q for q in qids if q not in done]
    if limit:
        todo = todo[:limit]
    print(f"already resolved: {len(done)}  to fetch this run: {len(todo)}", flush=True)
    SIDECAR.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with SIDECAR.open("a", encoding="utf-8") as f:
        for i in range(0, len(todo), 50):                   # wbgetentities: up to 50 ids/request
            batch = todo[i:i + 50]
            try:
                labs = _fetch(batch)
            except Exception as exc:
                print(f"  batch {i} error {type(exc).__name__}; backing off 5s", flush=True)
                time.sleep(5)
                continue
            for qid in batch:
                rec = labs.get(qid) or {"en": None, "ko": None}
                f.write(json.dumps({"qid": qid, **rec}, ensure_ascii=False) + "\n")
            f.flush()
            written += len(batch)
            if written % 500 == 0:
                print(f"  fetched {written}/{len(todo)}", flush=True)
            time.sleep(0.2)                                 # polite rate limit
    print(f"done: wrote {written} records → {SIDECAR.name} (sidecar, no store write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
