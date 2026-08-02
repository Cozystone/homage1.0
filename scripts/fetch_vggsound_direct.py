# -*- coding: utf-8 -*-
"""VGGSound as whole tarballs, not scraped clip by clip.

    python scripts/fetch_vggsound_direct.py --parts 3

WHY THIS REPLACES THE SCRAPER, measured rather than assumed. Pulling clips from YouTube one at a time
started at a 22.6% unavailable rate overnight and reached 81% by morning: 24 downloaded against 101
gone in three minutes. That is not link rot, that is throttling -- thirty-odd failed requests a minute
is exactly the behaviour that earns it -- and pushing harder makes it worse rather than faster. At
511 clips an hour, 25,000 would have taken 49 hours and the rate was falling.

`Loie/VGGSound` on HuggingFace holds the same corpus as twenty tarballs of real mp4 files, verified by
listing one: `.../VGGSound_final/video/---g-f_I2yQ_000001.mp4`, the same ids as the official csv. No
YouTube, so no throttle and no rot. 16.4 GB per part, 338 GB for all twenty, and D: has 1.1 TB.

ONE PART IS ALREADY MORE THAN THE SCRAPER WOULD HAVE MANAGED IN TWO DAYS. Parts are fetched whole and
resumed on interruption; each is extracted as it lands so the measurement can start before the rest
arrives.

The clips are named with a zero-padded start (`_000001`) while the csv and the scraped files use the
bare number (`_1`), so `stem()` normalises them -- the labels have to line up or every class-level
measurement silently scores against nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = r"D:\atanor_data\vggsound_direct"
LOG = os.path.join(REPO, "data", "perception", "fetch_log.jsonl")
BASE = "https://huggingface.co/datasets/Loie/VGGSound/resolve/main/vggsound_%02d.tar.gz"


def stem(name: str) -> str:
    """`---g-f_I2yQ_000001.mp4` and `---g-f_I2yQ_1.mp4` are the same clip. The csv says the latter."""
    n = os.path.basename(name)
    n = n[:-4] if n.endswith(".mp4") else n
    m = re.match(r"^(.*)_(\d+)$", n)
    return "%s_%d" % (m.group(1), int(m.group(2))) if m else n


def _log(rec: dict) -> None:
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def part(i: int, keep_archive: bool) -> dict:
    os.makedirs(ROOT, exist_ok=True)
    tgz = os.path.join(ROOT, "vggsound_%02d.tar.gz" % i)
    done = os.path.join(ROOT, "part_%02d.done" % i)
    if os.path.exists(done):
        return {"part": i, "skipped": True}
    t0 = time.time()
    r = subprocess.run(["curl", "-sL", "-C", "-", "--retry", "5", "--retry-delay", "10",
                        "--max-time", "36000", "-o", tgz, BASE % i], capture_output=True)
    size = os.path.getsize(tgz) if os.path.exists(tgz) else 0
    if r.returncode != 0 or size < 10 ** 9:
        return {"part": i, "ok": False, "bytes": size, "seconds": round(time.time() - t0, 1),
                "why": (r.stderr[-200:].decode("utf-8", "replace") or "too small")}
    got = time.time()
    x = subprocess.run(["tar", "-xzf", tgz, "-C", ROOT], capture_output=True)
    n = 0
    for dirpath, _dn, fn in os.walk(ROOT):
        n += sum(1 for f in fn if f.endswith(".mp4"))
    ok = x.returncode == 0
    if ok:
        open(done, "w").close()
        if not keep_archive:
            try:
                os.remove(tgz)
            except Exception:
                pass
    return {"part": i, "ok": ok, "gb": round(size / 1e9, 2),
            "download_s": round(got - t0, 1), "extract_s": round(time.time() - got, 1),
            "mp4_total": n, "why": None if ok else x.stderr[-200:].decode("utf-8", "replace")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", type=int, default=2)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--keep-archive", action="store_true")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _log({"event": "direct_fetch_begins", "parts": a.parts,
          "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pid": os.getpid()})
    for i in range(a.start, a.start + a.parts):
        rec = part(i, a.keep_archive)
        rec["stage"] = "vggsound_direct"
        rec["at"] = time.strftime("%H:%M:%S")
        _log(rec)
        print(json.dumps(rec), flush=True)
    _log({"event": "direct_fetch_ends", "at": time.strftime("%Y-%m-%dT%H:%M:%S")})


if __name__ == "__main__":
    main()
