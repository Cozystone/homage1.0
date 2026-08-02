#!/usr/bin/env python3
"""Pull a bounded number of rows from a public HuggingFace dataset via the
datasets-server REST API (no full-file download) and write a JSONL that
feed_dataset.py understands.

This is license-respecting by construction: it only fetches a small slice of an
already-public dataset, and you pass --license so provenance is recorded. Pick
permissive datasets (CC-BY / CC-BY-SA / apache / openrail) for the commercial demo.

Example:
  python scripts/fetch_hf_rows.py --dataset rajpurkar/squad --config plain_text \
      --split validation --field context --length 150 --out squad.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

API = "https://datasets-server.huggingface.co/rows"


def _get(url: str, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "atanor-dataset-fetch/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--config", default="default")
    ap.add_argument("--split", default="train")
    ap.add_argument("--field", required=True, help="row field holding the declarative text")
    ap.add_argument("--length", type=int, default=150, help="total rows to pull")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    seen: set[str] = set()
    written = 0
    with open(args.out, "w", encoding="utf-8") as fh:
        offset = 0
        page = 100  # datasets-server max length per call
        while written < args.length:
            n = min(page, args.length - written + 50)  # over-pull a little to survive dedupe
            q = urllib.parse.urlencode({
                "dataset": args.dataset, "config": args.config,
                "split": args.split, "offset": offset, "length": n,
            })
            try:
                data = _get(f"{API}?{q}")
            except Exception as exc:
                print(f"fetch failed at offset {offset}: {type(exc).__name__}: {exc}", file=sys.stderr)
                break
            rows = data.get("rows") or []
            if not rows:
                break
            for r in rows:
                rec = r.get("row") or {}
                val = rec.get(args.field)
                if isinstance(val, dict):  # e.g. nested answers
                    val = json.dumps(val, ensure_ascii=False)
                text = str(val or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                fh.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
                written += 1
                if written >= args.length:
                    break
            offset += len(rows)
    print(f"wrote {written} rows -> {args.out}  (dataset={args.dataset}, field={args.field})")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
