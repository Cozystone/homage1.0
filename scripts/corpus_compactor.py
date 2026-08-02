# -*- coding: utf-8 -*-
"""Corpus compactor — the MERGE half of split-then-merge sharding.

Each learner shard process appends to its OWN narrative_corpus.shard<id>.jsonl (the single-
writer contract: two processes never write one file). This single-process, offline compactor
folds every shard into the main narrative_corpus.jsonl with a GLOBAL hash dedup and the same
rotation cap, then truncates the shards. It runs WITHOUT stopping the learners: shard files are
append-only, so it consumes a snapshot (the lines present when it starts) and leaves any lines
appended during compaction in place for the next cycle — no line is lost, at most a few are
seen twice and the global dedup drops them.

  python scripts/corpus_compactor.py            # merge shards -> main, dedup, rotate, truncate
  python scripts/corpus_compactor.py --dry-run  # report only, touch nothing

See docs/ATANOR_multiprocess_sharding_design.md. Promotion stays OFF; this touches only the
surface-language corpus, never the answer pack ([[diet-flood-p0-regression]]).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

# module reference (not a bound import) so tests can monkeypatch nc.CORPUS to a tmp dir
from packages.autonomy_kernel import narrative_corpus as nc  # noqa: E402


def _shard_paths() -> list[Path]:
    return sorted(nc.CORPUS.parent.glob("narrative_corpus.shard*.jsonl"))


def _read_lines(path: Path) -> list[str]:
    try:
        return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception:
        return []


def _entry_hash(line: str) -> str | None:
    try:
        e = json.loads(line)
    except Exception:
        return None
    h = str(e.get("h") or "")
    if not h:
        text = str(e.get("text") or "").strip()
        h = nc._hash(text) if text else ""
    return h or None


def compact(*, dry_run: bool = False) -> dict[str, int]:
    """Fold shard files into main. Returns counts: {shards, merged, duplicates, main_before,
    main_after}. Idempotent: a second run with no new shard lines merges 0."""
    shards = _shard_paths()
    main_lines = _read_lines(nc.CORPUS)
    seen: set[str] = set()
    for ln in main_lines:
        h = _entry_hash(ln)
        if h:
            seen.add(h)
    main_before = len(main_lines)

    merged = 0
    duplicates = 0
    consumed: list[tuple[Path, int]] = []      # (shard, lines consumed) for post-merge truncate
    for shard in shards:
        lines = _read_lines(shard)
        consumed.append((shard, len(lines)))
        for ln in lines:
            h = _entry_hash(ln)
            if h is None:
                continue
            if h in seen:
                duplicates += 1
                continue
            seen.add(h)
            main_lines.append(ln)
            merged += 1

    # rotation cap on the merged main (keep newest)
    if len(main_lines) > nc._MAX_LINES:
        main_lines = main_lines[-nc._MAX_LINES:]

    if not dry_run:
        nc.CORPUS.parent.mkdir(parents=True, exist_ok=True)
        nc.CORPUS.write_text("\n".join(main_lines) + ("\n" if main_lines else ""), encoding="utf-8")
        # truncate ONLY the snapshot we consumed; lines appended during compaction survive
        for shard, n in consumed:
            rest = _read_lines(shard)[n:]
            shard.write_text("\n".join(rest) + ("\n" if rest else ""), encoding="utf-8")

    return {"shards": len(shards), "merged": merged, "duplicates": duplicates,
            "main_before": main_before, "main_after": len(main_lines)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge corpus shards into the main corpus.")
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    args = ap.parse_args()
    result = compact(dry_run=args.dry_run)
    print(json.dumps({"dry_run": args.dry_run, **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
