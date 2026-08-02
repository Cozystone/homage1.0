#!/usr/bin/env python3
"""Build + SEAL a holdout evaluation battery ( P2: the Goodhart defence).

self_improve measures coverage with a battery and then SEEDS the gaps it found —
which slowly turns the measuring stick into the training target. The standard
defence is a sealed holdout: a probe set that is NEVER seeded, whose file hash is
recorded so any tampering is visible, and whose score is only meaningful as the
GAP against the working battery (gap widening = Goodhart in progress).

What it does
 1. samples N concepts from the live store's verified evidence (definition-bearing
 sentences), stratified randomly with a fixed RNG seed for reproducibility;
 2. writes data/eval/holdout_v1.jsonl (question = "<>?", expected substring
 = the object head from the source sentence, plus the provenance hash);
 3. writes data/eval/holdout_v1.manifest.json with the battery file's sha256 —
 the SEAL. eval runs verify the hash before scoring;
 4. writes data/eval/holdout_exclusions.json — the term list self_improve MUST
 skip when seeding (checked by name, enforced in self_improve.py).

Usage:
 python scripts/build_holdout_battery.py # build v1 if absent (never overwrites)
 python scripts/build_holdout_battery.py --check # verify seal only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EVAL_DIR = REPO / "data" / "eval"
BATTERY = EVAL_DIR / "holdout_v1.jsonl"
MANIFEST = EVAL_DIR / "holdout_v1.manifest.json"
EXCLUSIONS = EVAL_DIR / "holdout_exclusions.json"
STORE = REPO / "data" / "cloud_brain" / "candidate_runs" / "clean_seed_v2"
RNG_SEED = 20260704

# --- holdout_v2: a FAIR "should-answer" battery ---------------------------------
# v1 sampled a concept + ANY sentence mentioning it, so ~90% of its probes are junk

# ABSTENTION is the correct answer — its ~10% score is the honest ceiling, not a
# bottleneck. v2 instead samples concepts that have an UNAMBIGUOUS bare-subject

# so its answer-rate is a real coverage metric: every probe SHOULD be answerable.
BATTERY2 = EVAL_DIR / "holdout_v2.jsonl"
MANIFEST2 = EVAL_DIR / "holdout_v2.manifest.json"
RNG_SEED_V2 = 20260705
_DEF_SUBJ = re.compile(r"^\s*([가-힣][가-힣A-Za-z0-9]{1,19})\s*(?:은|는|이|가)\s")
_DEF_END = re.compile(
    r"(?:이다|입니다|이었다|였다|말한다|말합니다|뜻한다|뜻합니다"
    r"|가리킨다|일컫는다|이라고\s*한다|라고\s*한다|불린다|불립니다)[.\"'”’)\]]*$"
)
_PAREN = re.compile(r"\([^()]*\)")
_NON_ENTITY = {"그것", "이것", "저것", "여기", "거기", "저기", "오늘", "지금", "내일",
               "어제", "요즘", "최근", "이번", "다음", "우리", "저희", "너희", "당신"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check() -> int:
    if not (BATTERY.exists() and MANIFEST.exists()):
        print("[SEAL] missing battery or manifest")
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = _sha256(BATTERY)
    ok = actual == manifest.get("sha256")
    print(f"[SEAL] {'INTACT' if ok else 'BROKEN'}  recorded={manifest.get('sha256','')[:16]}… actual={actual[:16]}…")
    return 0 if ok else 2


def build(sample_size: int = 60) -> int:
    if BATTERY.exists():
        print(f"[SEAL] {BATTERY.name} already exists — a sealed battery is never rebuilt in place.")
        print("       (rotate by creating holdout_v2 instead)")
        return check()
    concepts_path = STORE / "concepts.jsonl"
    evidence_path = STORE / "evidence.jsonl"
    if not concepts_path.exists() or not evidence_path.exists():
        print(f"[SEAL] store not found at {STORE}")
        return 1

    evidence = {}
    for line in evidence_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        evidence[str(row.get("source_hash") or "")] = str(row.get("text") or "")

    # definition-bearing concepts: 2+ char Korean/eng name whose source sentence mentions it
    candidates = []
    for line in concepts_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        name = str(row.get("canonical_name") or "")
        hashes = row.get("source_hashes") or []
        text = next((evidence.get(h, "") for h in hashes if evidence.get(h)), "")
        if len(name) >= 2 and text and name in text and len(text) >= 20:
            candidates.append({"term": name, "source_text": text,
                               "provenance_hash": hashes[0] if hashes else ""})
    if len(candidates) < 10:
        print(f"[SEAL] only {len(candidates)} definition-bearing candidates — store too sparse")
        return 1

    rng = random.Random(RNG_SEED)
    rng.shuffle(candidates)
    picked = candidates[: min(sample_size, len(candidates))]
    rows = [
        {
            "id": f"holdout_v1_{i:03d}",
            "question": f"{c['term']}이란?",
            "term": c["term"],
            "expect_grounded_in": c["source_text"][:240],
            "provenance_hash": c["provenance_hash"],
        }
        for i, c in enumerate(picked)
    ]

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    # LF-only bytes: the seal hash must be identical across OS checkouts
    BATTERY.write_bytes(("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n").encode("utf-8"))
    MANIFEST.write_text(json.dumps({
        "battery": BATTERY.name,
        "sha256": _sha256(BATTERY),
        "items": len(rows),
        "rng_seed": RNG_SEED,
        "sealed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "rule": "NEVER seed these terms; rotate quarterly to holdout_v2; score gap vs working battery = Goodhart signal",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    EXCLUSIONS.write_text(json.dumps({"never_seed_terms": sorted({r["term"] for r in rows})},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[SEAL] built {len(rows)} probes | sha256={_sha256(BATTERY)[:16]}… | exclusions={len(rows)} terms")
    return 0


def check_v2() -> int:
    if not (BATTERY2.exists() and MANIFEST2.exists()):
        print("[SEAL v2] missing battery or manifest")
        return 1
    manifest = json.loads(MANIFEST2.read_text(encoding="utf-8"))
    actual = _sha256(BATTERY2)
    ok = actual == manifest.get("sha256")
    print(f"[SEAL v2] {'INTACT' if ok else 'BROKEN'}  recorded={manifest.get('sha256','')[:16]}… actual={actual[:16]}…")
    return 0 if ok else 2


def build_v2(sample_size: int = 60) -> int:
    if BATTERY2.exists():
        print(f"[SEAL v2] {BATTERY2.name} already exists — a sealed battery is never rebuilt in place.")
        return check_v2()
    evidence_path = STORE / "evidence.jsonl"
    concepts_path = STORE / "concepts.jsonl"
    if not evidence_path.exists() or not concepts_path.exists():
        print(f"[SEAL v2] store not found at {STORE}")
        return 1
    real_names = set()
    for line in concepts_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            nm = str(json.loads(line).get("canonical_name") or "").strip()
            if nm:
                real_names.add(nm)


    best: dict[str, str] = {}
    for line in evidence_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = str(json.loads(line).get("text") or "")
        sent = re.sub(r"\s+", " ", _PAREN.sub("", raw)).strip()
        if not (20 <= len(sent) <= 200):
            continue
        m = _DEF_SUBJ.match(sent)
        if not m or not _DEF_END.search(sent):
            continue
        term = m.group(1)
        if term in _NON_ENTITY or term not in real_names:
            continue
        if term not in best or len(sent) < len(best[term]):
            best[term] = sent
    candidates = [{"term": t, "source_text": s} for t, s in best.items()]
    if len(candidates) < sample_size:
        print(f"[SEAL v2] only {len(candidates)} clean-definable concepts found")
        if len(candidates) < 10:
            return 1
    rng = random.Random(RNG_SEED_V2)
    rng.shuffle(candidates)
    picked = candidates[: min(sample_size, len(candidates))]
    rows = [
        {
            "id": f"holdout_v2_{i:03d}",
            "question": f"{c['term']}란?",
            "term": c["term"],
            "expect_grounded_in": c["source_text"][:240],
        }
        for i, c in enumerate(picked)
    ]
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    BATTERY2.write_bytes(("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n").encode("utf-8"))
    MANIFEST2.write_text(json.dumps({
        "battery": BATTERY2.name,
        "sha256": _sha256(BATTERY2),
        "items": len(rows),
        "rng_seed": RNG_SEED_V2,
        "sealed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "kind": "should-answer: concepts with an unambiguous bare-subject definition",
        "rule": "NEVER seed these terms; answer-rate here IS the coverage metric (v1 is the raw-store baseline)",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    # merge v2 terms into the shared exclusions so self_improve never seeds them
    excl = {"never_seed_terms": []}
    if EXCLUSIONS.exists():
        excl = json.loads(EXCLUSIONS.read_text(encoding="utf-8"))
    merged = sorted(set(excl.get("never_seed_terms", [])) | {r["term"] for r in rows})
    EXCLUSIONS.write_text(json.dumps({"never_seed_terms": merged}, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    print(f"[SEAL v2] built {len(rows)} probes | sha256={_sha256(BATTERY2)[:16]}… | +{len(rows)} exclusions")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--v2", action="store_true", help="build/check the fair should-answer battery")
    ap.add_argument("--size", type=int, default=60)
    args = ap.parse_args()
    if args.v2:
        sys.exit(check_v2() if args.check else build_v2(args.size))
    sys.exit(check() if args.check else build(args.size))
