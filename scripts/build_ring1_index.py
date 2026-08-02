#!/usr/bin/env python
"""Ring 1 index builder — external-drive aware ( 2TB , 2026-07-16 ).

Run this once the 2TB drive is mounted. It resolves the index root via
packages.atanor_index.storage (which auto-picks the biggest external volume), then builds a
disk-backed BM25 index for every configured corpus THERE — so the ~2 GB (and, as corpora grow,
1-2 TB) index lives on the drive, not on C:. Idempotent: a corpus whose index already carries a
meta.json is skipped unless --force.

 python scripts/build_ring1_index.py --report # just show where things would go
 python scripts/build_ring1_index.py # build all present corpora onto the drive
 python scripts/build_ring1_index.py --force # rebuild even if already built

No LLM, no network — pure corpus indexing. The engine picks up the new index automatically:
retriever.py prefers <root>/wiki_en_full, and storage.index_root() follows the drive.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.atanor_index import storage
from packages.atanor_index.disk_index import DiskIndex, build_index

_REPO = Path(__file__).resolve().parents[1]

# (index_name, source_tsv). First present + largest is what retriever.py opens as the live corpus.
# Ordered biggest-first; extend as Wiktionary / StackExchange / Common-Crawl subsets get harvested.
CORPORA: list[tuple[str, Path]] = [
    ("wiki_en_body", _REPO / "data" / "graph_scale" / "wiki_passages_en_body" / "passages.tsv"),
    ("wiki_en_full", _REPO / "data" / "graph_scale" / "wiki_passages_en_full" / "passages.tsv"),
    ("wiki_en_rich", _REPO / "data" / "graph_scale" / "wiki_passages_en_rich" / "passages.tsv"),
]


def _built(d: Path) -> bool:
    return (d / "meta.json").exists() and (d / "term_hashes.npy").exists()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # Windows cp949 console chokes on em-dashes
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="show storage + corpus plan, build nothing")
    ap.add_argument("--force", action="store_true", help="rebuild even corpora already indexed")
    args = ap.parse_args()

    rep = storage.storage_report()
    root = storage.index_root(refresh=True)
    print("=== ATANOR Ring 1 index build ===")
    print(f"  index root : {root}")
    print(f"  on external: {rep['on_external']}  (external drive: {rep['external_drive']})")
    print(f"  root free  : {rep['root_free_gb']} GB")
    if not rep["on_external"]:
        print("  NOTE: no >=200GB external volume detected — building onto the fallback (system drive).")
        print("        Plug in the 2TB drive and re-run to place the index there.")

    present = [(n, tsv) for n, tsv in CORPORA if tsv.exists()]
    if not present:
        print("  no corpora found; nothing to build.")
        return 1
    print("  corpora:")
    for name, tsv in present:
        dst = root / name
        state = "BUILT" if _built(dst) else "pending"
        size_mb = tsv.stat().st_size / 1e6
        print(f"    - {name:16} {size_mb:8.0f} MB  →  {dst}  [{state}]")

    if args.report:
        return 0

    for name, tsv in present:
        dst = root / name
        if _built(dst) and not args.force:
            print(f"  [skip] {name} already built ({dst})")
            continue
        print(f"  [build] {name} from {tsv} …", flush=True)
        meta = build_index(tsv, dst, progress_every=1_000_000)
        idx = DiskIndex(dst)
        hits = idx.search_topk("what is the speed of light", k=1)
        idx.close()
        probe = hits[0]["title"] if hits else "(no hit)"
        print(f"  [done]  {name}: {meta['n_docs']:,} docs · {meta['n_postings']:,} postings · "
              f"{meta['build_seconds']}s · probe→{probe}")
    print("Ring 1 build complete. The engine will use it on the next request (retriever auto-opens it).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
