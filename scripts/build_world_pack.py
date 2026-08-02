# -*- coding: utf-8 -*-
"""Full Wikidata dump → world pack (PROPHETA L1) — streaming, single-pass, sharded.

Streams latest-all.json.bz2 (one JSON entity per line) straight into a sharded TripleStore —
the dump is never decompressed to disk. What each kept entity contributes:

  (label,  defined_as, ko_description)        the evidence field for KMMLU / open-book benches
  (label,  defined_as, en_description)        MMLU-Pro / GPQA evidence (English)
  (label,  alias,      each ko alias)
  (label,  <relation>, Q-id target)           functional/benchmark relations (capital, population,
                                              author, discoverer, country, is_a, subclass_of …)
  (Q-id,   qlabel,     label)                 one resolution row per entity → Q-id objects become
                                              readable at query time (one extra hop, no 2nd pass)

Filters (honest scale control): entities with neither ko nor en label are skipped; scholarly/
review articles (Q13442814, Q7318358) — tens of millions of citation stubs — are skipped whole.

Resumability: bz2 cannot seek, so a crash means rerun; the store dedups by triple so a rerun
is idempotent-ish (slow but safe). Progress + rate journaled every 100k entities.

  python scripts/build_world_pack.py --limit 200000     # partial-file test / rate measurement
  python scripts/build_world_pack.py                    # full build (run when download completes)
"""
from __future__ import annotations

import bz2
import io
import json
import os
import sys
import time
from pathlib import Path

try:
    import orjson as _fastjson
    _loads = _fastjson.loads
except ImportError:                                    # pragma: no cover
    _loads = json.loads

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
for _d in sorted((REPO / "packages").iterdir(), reverse=True):
    if (_d / "pyproject.toml").exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from packages.graph_scale.triple_store import TripleStore  # noqa: E402

DUMP = Path(os.environ.get("WORLD_PACK_DUMP", "C:/0.ASKIM ALL-VIN/wikidata/latest-all.json.bz2"))
# output dir name overridable (WORLD_PACK_OUT) so a manual partial build can go to a SEPARATE
# path and never collide with the auto-launcher's world_pack_full write.
DST = REPO / "data" / "graph_scale" / os.environ.get("WORLD_PACK_OUT", "world_pack_full")
JOURNAL = REPO / "data" / "graph_scale" / "world_pack_build.jsonl"

# citation-stub classes — skipped whole (tens of millions of entities, no benchmark value)
_SKIP_P31 = {"Q13442814", "Q7318358", "Q591041", "Q871232"}   # scholarly/review article, episode, editorial
# benchmark-relevant relations (PID → readable predicate). Small on purpose; grows via roaming.
_RELS = {
    "P31": "is_a", "P279": "subclass_of", "P36": "capital", "P17": "country",
    "P1082": "population", "P2046": "area", "P571": "inception", "P50": "author",
    "P61": "discovered_by", "P170": "creator", "P19": "born_in", "P569": "birth_date",
    "P106": "occupation", "P361": "part_of", "P527": "has_part", "P828": "caused_by",
}


def _first_claim_ids(claims: dict, pid: str, k: int = 2) -> list[str]:
    out = []
    for c in (claims.get(pid) or [])[:k]:
        try:
            v = c["mainsnak"]["datavalue"]["value"]
            if isinstance(v, dict) and "id" in v:
                out.append(str(v["id"]))
            elif isinstance(v, dict) and "amount" in v:        # quantity (population, area)
                out.append(str(v["amount"]).lstrip("+"))
            elif isinstance(v, dict) and "time" in v:          # time (inception, birth)
                out.append(str(v["time"])[1:11])               # +1961-03-12T.. → 1961-03-12
        except Exception:
            continue
    return out


def build(limit: int | None = None) -> dict:
    if not DUMP.exists():
        print("dump not found:", DUMP)
        return {}
    DST.mkdir(parents=True, exist_ok=True)
    st = TripleStore(DST, dict_backend="sharded", write_src=False)
    t0 = time.time()
    seen = kept = skipped_article = triples = 0
    # DECOMPRESSION is the bottleneck (measured: serial bz2 = 2,642 lines/s even with NO parsing;
    # full build 1,891/s — decompression is ~72% of the cost). indexed_bzip2 decompresses the
    # independent bzip2 blocks across all cores: measured 26,030 lines/s = 9.9x on 32 cores.
    # Falls back to serial bz2 if the package is absent, so the build always runs.
    try:
        import indexed_bzip2 as _ibz2
        raw = _ibz2.open(str(DUMP), parallelization=0)     # 0 = all cores
        backend = "indexed_bzip2(parallel)"
    except Exception:
        raw = bz2.BZ2File(str(DUMP), "rb")
        backend = "bz2(serial)"
    prescreened = 0
    try:
        for line in raw:
            if limit and seen >= limit:
                break
            line = line.strip()
            if len(line) < 10:                                 # "[", "]" wrapper lines
                continue
            # BYTE PRESCREEN (measured necessity: full-parse rate ~1.9k/s → ~17h for the dump).
            # A substring check is ~100x cheaper than parsing a 5-50KB entity. Safe directions:
            #  - no b'"ko"' AND no b'"en"' anywhere → certainly no ko/en label → skip.
            #  - scholarly-article marker with no Korean anywhere → skip (tens of millions of
            #    citation stubs; Korean-labeled ones — effectively none — still get parsed).
            if (b'"ko"' not in line and b'"en"' not in line) or \
                    (b"Q13442814" in line and b'"ko"' not in line):
                seen += 1
                prescreened += 1
                continue
            if line.endswith(b","):
                line = line[:-1]
            try:
                e = _loads(line)
            except Exception:
                continue
            seen += 1
            if e.get("type") != "item":
                continue
            claims = e.get("claims") or {}
            p31 = set(_first_claim_ids(claims, "P31", 3))
            if p31 & _SKIP_P31:
                skipped_article += 1
                continue
            labels = e.get("labels") or {}
            lab_ko = (labels.get("ko") or {}).get("value")
            lab_en = (labels.get("en") or {}).get("value")
            label = lab_ko or lab_en
            if not label:
                continue
            kept += 1
            qid = str(e.get("id") or "")
            descs = e.get("descriptions") or {}
            d_ko = (descs.get("ko") or {}).get("value")
            d_en = (descs.get("en") or {}).get("value")
            if d_ko:
                st.add(label, "defined_as", d_ko)
                triples += 1
            if d_en:
                st.add(label, "defined_as", d_en)
                triples += 1
            if lab_ko and lab_en and lab_ko != lab_en:         # cross-language alias
                st.add(lab_ko, "alias", lab_en)
                triples += 1
            for al in ((e.get("aliases") or {}).get("ko") or [])[:4]:
                v = al.get("value")
                if v and v != label:
                    st.add(label, "alias", v)
                    triples += 1
            if qid:
                st.add(qid, "qlabel", label)                   # resolution row
                triples += 1
            for pid, pred in _RELS.items():
                for tgt in _first_claim_ids(claims, pid):
                    st.add(label, pred, tgt)
                    triples += 1
            if kept % 100_000 == 0:
                st.flush()
                dt = time.time() - t0
                rate = seen / max(1, dt)
                row = {"at": time.strftime("%H:%M:%S"), "seen": seen, "kept": kept,
                       "prescreened": prescreened, "skipped_articles": skipped_article,
                       "triples": triples, "rate_entities_s": round(rate, 1), "backend": backend}
                print(json.dumps(row), flush=True)
                JOURNAL.parent.mkdir(parents=True, exist_ok=True)
                with JOURNAL.open("a", encoding="utf-8") as jf:
                    jf.write(json.dumps(row) + "\n")
    except (EOFError, OSError) as exc:
        # a PARTIAL download ends mid-stream — flush what we have and report honestly
        print(f"stream ended early ({exc.__class__.__name__}) — partial file; flushed progress")
    finally:
        raw.close()
        st.flush()
    dt = time.time() - t0
    disk = sum(f.stat().st_size for f in DST.rglob("*") if f.is_file()) / 1e9
    rep = {"seen": seen, "kept": kept, "prescreened": prescreened,
           "skipped_articles": skipped_article, "triples": triples,
           "elapsed_s": round(dt, 1), "rate_entities_s": round(seen / max(1, dt), 1),
           "disk_gb": round(disk, 2), "backend": backend}
    print("\nDONE", json.dumps(rep))
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as jf:
        jf.write(json.dumps({"kind": "done", **rep}) + "\n")
    return rep


if __name__ == "__main__":
    lim = None
    for a in sys.argv[1:]:
        if a.startswith("--limit"):
            lim = int(a.split("=", 1)[1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])
    raise SystemExit(0 if build(lim) else 1)
