#!/usr/bin/env python3
"""Re-train a CLEAN candidate store with the fixed pipeline (Cloud Brain Step 4, build half).

Re-decomposes the EXISTING verified evidence text through the now-fixed decomposer
(Step 1: no {ROLE}_OF flooding the relations store; Step 2: unified concept schema)
into a NEW store directory. The live store is never touched; revert = delete the
new dir. After building, it reports the relation-type distribution to prove the
95.5% grammatical-noise is gone.

This does NOT swap the live engine over — that is a separate, explicit step once
the new store passes validation.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.cgsr.cgsr.ingestion.accumulator import VerifiedStore                 # noqa: E402
from packages.cgsr.cgsr.ingestion.decomposer import decompose_sentence             # noqa: E402
from packages.cgsr.cgsr.ingestion.verification_gate import verify_sentence         # noqa: E402
from packages.cloud_brain.continuous_learning import source_sentence_from_payload  # noqa: E402
from packages.cloud_brain.verified_payload_feeder import LearningPayload           # noqa: E402

LIVE = REPO_ROOT / "data" / "cloud_brain" / "candidate_runs" / "wikipedia_grounded_live"


def _payload(text: str) -> LearningPayload:
    ph = hashlib.sha256(("retrain::" + text).encode("utf-8")).hexdigest()
    lang = "ko" if any("가" <= c <= "힣" for c in text) else "en"
    return LearningPayload(
        payload_id=ph[:24], source_type="approved_public_corpus", source_id=f"retrain_{ph[:12]}",
        text=text, normalized_text=text, language=lang, provenance_hash=ph,
        source_url_or_path="retrain://wikipedia_grounded_live/evidence",
        license_hint="public", collected_at="2026-06-30T00:00:00Z",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-train a clean store with the fixed pipeline")
    ap.add_argument("--out", type=Path,
                    default=REPO_ROOT / "data" / "cloud_brain" / "candidate_runs" / "clean_retrain_v1")
    ap.add_argument("--limit", type=int, default=0, help="0 = all evidence rows")
    args = ap.parse_args()

    new_store = args.out
    if new_store.exists():
        shutil.rmtree(new_store)
    new_store.mkdir(parents=True, exist_ok=True)
    # seed schema/manifest so VerifiedStore initializes against the same contract
    for fn in ("schema.json", "manifest.json"):
        src = LIVE / fn
        if src.exists():
            shutil.copy(src, new_store / fn)

    store = VerifiedStore(new_store)

    texts: list[str] = []
    seen: set[str] = set()
    with (LIVE / "evidence.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = str(row.get("text") or row.get("source_text") or row.get("sentence") or "").strip()
            if 8 < len(t) < 400 and t not in seen:
                seen.add(t)
                texts.append(t)
    if args.limit:
        texts = texts[: args.limit]

    accepted = rejected = 0
    batch = []
    for t in texts:
        s = source_sentence_from_payload(_payload(t))
        dec = verify_sentence(s, existing_dedupe_keys=store.existing_dedupe_keys())
        if dec.status != "verified":
            rejected += 1
            continue
        accepted += 1
        batch.append(decompose_sentence(s, dec, ingest_run_id="clean_retrain_v1"))
        if len(batch) >= 200:
            store.accumulate(batch)
            batch = []
    if batch:
        store.accumulate(batch)

    # report relation-type distribution on the NEW store
    rtypes = collections.Counter()
    rel_path = new_store / "relations.jsonl"
    if rel_path.exists():
        with rel_path.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    rtypes[str(json.loads(line).get("relation", ""))] += 1
                except json.JSONDecodeError:
                    pass
    n_rel = sum(rtypes.values())
    grammatical = sum(v for k, v in rtypes.items() if k.endswith("_OF") or k in ("SUBJ", "OBJ", "TOPIC", "ADVL"))
    n_concepts = sum(1 for _ in (new_store / "concepts.jsonl").open(encoding="utf-8")) if (new_store / "concepts.jsonl").exists() else 0
    n_cf = sum(1 for _ in (new_store / "case_frames.jsonl").open(encoding="utf-8")) if (new_store / "case_frames.jsonl").exists() else 0

    print(f"[RETRAIN] evidence sentences: {len(texts)} | accepted: {accepted} | rejected: {rejected}")
    print(f"[RETRAIN] NEW store: {new_store}")
    print(f"[RETRAIN] concepts={n_concepts} relations={n_rel} case_frames={n_cf}")
    print(f"[RETRAIN] relation types: {dict(rtypes.most_common(8))}")
    print(f"[RETRAIN] grammatical-role relations: {grammatical} ({round(grammatical/n_rel*100,1) if n_rel else 0}%)  <- target: ~0% (was 95.5%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
