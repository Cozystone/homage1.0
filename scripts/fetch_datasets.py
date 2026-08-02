# -*- coding: utf-8 -*-
"""Fetch the corpora the measurements asked for, in the order that unblocks the most.

    python scripts/fetch_datasets.py --hours 8

ORDERED BY WHICH MEASURED GAP EACH ONE CLOSES, not by size or fame:

  1  LibriSpeech dev-clean   already here. Real speech, 40 speakers. It was fetched first because it
                             could FALSIFY the day's work -- speaker normalisation was 71% on
                             synthetic throats that scale uniformly, and real ones do not. It did not
                             falsify it: real voices separate BETTER (0.171 against 0.101), because a
                             real utterance is a whole sentence and the phonemes average within it,
                             while the synthetic test was one sustained vowel where the vowel
                             dominates. The synthetic setup was the harder case, not the kinder one.
  2  FSD50K                  every kind of sound rather than speech, human-labelled, on Zenodo as a
                             direct download so no link rots. This is what the owner's constraint --
                             all sounds, not a taxonomy -- needs to be tested against.
  3  VGGSound                the audio-visual correspondence corpus, and the reason it beats AudioSet
                             here: its curation GUARANTEES the sound source is visible in the frame.
                             U3's free oracle is exactly that co-occurrence, so the oracle is built
                             into the dataset definition. Distributed as YouTube ids, so clips are
                             pulled one at a time and some are gone -- link rot is reported rather
                             than hidden.

EVERYTHING LANDS ON D:. C: has 66 GB free and D: has 1.1 TB, and the episode corpus already lives
there.

Resumable and honest: a file already present and non-trivial in size is skipped, failures are logged
with their reason, and the log is data/perception/fetch_log.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

ROOT = Path(r"D:\atanor_data")
LOG = REPO / "data" / "perception" / "fetch_log.jsonl"

#: The eval split and the labels, deliberately, and NOT the dev split on the first night. dev_audio
#: is a MULTI-PART zip (.z01, .z02, ...) that has to be reassembled before anything can read it, and
#: a half-fetched multi-part archive at 6am is worse than a whole small one -- it looks like data and
#: opens as nothing. eval is a single 3 GB file with 10k clips over the same ontology, which is
#: plenty to find out whether the ear does anything with real varied sound.
FSD50K = [
    ("FSD50K.ground_truth.zip", "https://zenodo.org/records/4060432/files/FSD50K.ground_truth.zip"),
    ("FSD50K.metadata.zip", "https://zenodo.org/records/4060432/files/FSD50K.metadata.zip"),
    ("FSD50K.eval_audio.zip", "https://zenodo.org/records/4060432/files/FSD50K.eval_audio.zip"),
]
VGGSOUND_CSV = "https://www.robots.ox.ac.uk/~vgg/data/vggsound/vggsound.csv"


def _log(rec: dict) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def grab(url: str, dest: Path, minimum: int = 4096) -> dict:
    """One file, skipped if already here. curl handles the resume and the redirects."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > minimum:
        return {"file": dest.name, "skipped": True, "bytes": dest.stat().st_size}
    t0 = time.time()
    try:
        r = subprocess.run(["curl", "-sL", "-C", "-", "--max-time", "5400", "-o", str(dest), url],
                           capture_output=True, timeout=5700)
        size = dest.stat().st_size if dest.exists() else 0
        ok = r.returncode == 0 and size > minimum
        return {"file": dest.name, "ok": ok, "bytes": size,
                "seconds": round(time.time() - t0, 1),
                "why": None if ok else (r.stderr[-200:].decode("utf-8", "replace") or "too small")}
    except Exception as exc:
        return {"file": dest.name, "ok": False, "why": "%s: %s" % (type(exc).__name__, exc)}


def vggsound(n_clips: int, deadline: float) -> dict:
    """Pull a diverse slice by class — breadth beats depth for learning what a sound IS.

    Taking the first N rows would give N clips of whatever is alphabetically first. Round-robin over
    classes gives the same budget spread across the ontology, which is what a co-occurrence learner
    needs."""
    import csv
    import io as _io
    import random
    import urllib.request
    out = ROOT / "vggsound"
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "vggsound.csv"
    if not csv_path.exists() or csv_path.stat().st_size < 4096:
        try:
            with urllib.request.urlopen(VGGSOUND_CSV, timeout=120) as r:
                csv_path.write_bytes(r.read())
        except Exception as exc:
            return {"stage": "vggsound_csv", "ok": False, "why": str(exc)[:200]}
    rows = list(csv.reader(_io.StringIO(csv_path.read_text(encoding="utf-8", errors="replace"))))
    by_class: dict = {}
    for r in rows:
        if len(r) >= 3:
            by_class.setdefault(r[2].strip(), []).append((r[0].strip(), r[1].strip()))
    order = sorted(by_class)
    random.Random(0).shuffle(order)
    got = gone = 0
    i = 0
    while got + gone < n_clips and time.time() < deadline:
        cls = order[i % len(order)]
        i += 1
        pool = by_class.get(cls) or []
        if not pool:
            continue
        vid, start = pool[(i // max(1, len(order))) % len(pool)]
        dest = out / ("%s_%s.mp4" % (vid, start))
        if dest.exists():
            continue
        try:
            r = subprocess.run(
                [sys.executable, "-m", "yt_dlp", "-q", "--no-warnings",
                 "-f", "worst[height<=360]/worst", "--download-sections",
                 "*%s-%s" % (start, int(float(start)) + 10),
                 "-o", str(dest), "https://www.youtube.com/watch?v=" + vid],
                capture_output=True, timeout=180)
            if r.returncode == 0 and dest.exists() and dest.stat().st_size > 8192:
                got += 1
            else:
                gone += 1
        except Exception:
            gone += 1
        if (got + gone) % 25 == 0:
            _log({"stage": "vggsound", "downloaded": got, "unavailable": gone,
                  "at": time.strftime("%H:%M:%S")})
    return {"stage": "vggsound", "ok": got > 0, "downloaded": got, "unavailable": gone,
            "classes_touched": min(i, len(order)),
            "note": "YouTube-hosted, so a fraction of clips are gone; that fraction is reported"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--vgg-clips", type=int, default=1500)
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    deadline = time.time() + a.hours * 3600
    _log({"event": "fetch_begins", "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pid": os.getpid()})

    for name, url in FSD50K:
        if time.time() > deadline:
            break
        rec = grab(url, ROOT / "FSD50K" / name)
        rec["stage"] = "fsd50k"
        _log(rec)
        print(json.dumps(rec), flush=True)

    if time.time() < deadline:
        rec = vggsound(a.vgg_clips, deadline)
        _log(rec)
        print(json.dumps(rec), flush=True)

    _log({"event": "fetch_ends", "at": time.strftime("%Y-%m-%dT%H:%M:%S")})


if __name__ == "__main__":
    main()
