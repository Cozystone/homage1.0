#!/usr/bin/env python3
"""P1 ② — grounding.jsonl sidecar writer for a candidate store (RED, reversible).

Per Codex's P1-absorption review (Contract C1):
  - the RMMVe grounding result is written to a SEPARATE `grounding.jsonl` sidecar
    (NOT a fact-row subfield), so fact rows are never modified;
  - `grounding.jsonl` is NOT one of verified_fact_retrieval.STORE_FILES, so the
    answer path can never read a grounding score as evidence ("score != evidence");
  - it carries only eligibility scores/decisions — answer-bearing keys are
    asserted absent before every write;
  - append-only; revert = delete the sidecar.

This module is BOTH the writer (append_grounding) and a runner that demonstrates
it end-to-end on a FROZEN scratch clone of the live candidate store, so fact files
are provably byte-identical before/after.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
for p in (str(REPO_ROOT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import derivation_p0_audit as dp0          # noqa: E402
import rmmve_shadow_scorer as rss          # noqa: E402
import shadow_attach_ingest as sai         # noqa: E402
from packages.cgsr.cgsr.verified_fact_retrieval import STORE_FILES                 # noqa: E402
from packages.cgsr.cgsr.ingestion.verification_gate import verify_sentence         # noqa: E402
from packages.cgsr.cgsr.ingestion.decomposer import decompose_sentence             # noqa: E402
from packages.cloud_brain.continuous_learning import source_sentence_from_payload  # noqa: E402

GROUNDING_SIDECAR = "grounding.jsonl"
ALLOWED_DECISIONS = ("would_promote", "would_flag", "would_abstain")

# Module-load firewall: the grounding sidecar must never be an answer-path file.
assert GROUNDING_SIDECAR not in STORE_FILES, "grounding sidecar must NOT be in STORE_FILES"


def _iter_keys(obj: Any):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, (list, tuple)):
        for it in obj:
            yield from _iter_keys(it)


def append_grounding(store_dir: Path, entry: dict[str, Any]) -> None:
    """Append one grounding entry to <store>/grounding.jsonl (Contract C1)."""
    leaked = sorted(set(_iter_keys(entry)) & rss._FORBIDDEN)
    if leaked:
        raise RuntimeError(f"C1 firewall: grounding entry carries answer keys: {leaked}")
    dec = entry.get("grounding", {}).get("decision")
    if dec not in ALLOWED_DECISIONS:
        raise RuntimeError(f"grounding decision not in allowed enum: {dec}")
    path = store_dir / GROUNDING_SIDECAR
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def _hashes(store_dir: Path) -> dict[str, str]:
    out = {}
    for fn in STORE_FILES:
        p = store_dir / fn
        out[fn] = hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "absent"
    return out


def run(limit: int) -> dict[str, Any]:
    # frozen scratch clone of the live candidate store (daemon-free, clean proof)
    scratch = Path(
        "C:/Users/anseo/AppData/Local/Temp/claude/C--0-ASKIM-ALL-VIN-24-Homage1-0/"
        "eef4898d-620d-43ca-8c5a-0d17f79bb181/scratchpad/p1_2_scratch_store")
    if scratch.exists():
        shutil.rmtree(scratch)
    shutil.copytree(sai.LIVE, scratch)

    before = _hashes(scratch)
    store = dp0.load_store_predicates(scratch)
    names = rss._load_concept_names(scratch)
    payloads = sai.build_payloads(limit)

    written = 0
    decisions: dict[str, int] = {}
    dedupe: set[str] = set()
    for pl in payloads:
        s = source_sentence_from_payload(pl)
        dec = verify_sentence(s, existing_dedupe_keys=dedupe)
        if dec.status != "verified":
            continue
        result = decompose_sentence(s, dec, ingest_run_id="p1_2_grounding")
        scored = [sai._score_frame(f, store, names) for f in result.case_frames]
        best = max(scored, key=lambda x: x["ctotal"]) if scored else None
        decision, ctotal = sai._decide(best)
        decisions[decision] = decisions.get(decision, 0) + 1
        entry = {
            "candidate_id": hashlib.sha256(pl.text.encode("utf-8")).hexdigest()[:16],
            "scored_at": datetime.now(timezone.utc).isoformat(),
            "grounding": {                      # separate namespace; NOT fact fields
                "decision": decision,
                "ctotal": ctotal,
                "module_scores": best,
                "score_scope": "implemented_shadow_slice_not_full_rmmve",
                "answer_eligible": False,
            },
        }
        append_grounding(scratch, entry)
        written += 1

    after = _hashes(scratch)
    fact_unchanged = before == after
    grounding_path = scratch / GROUNDING_SIDECAR
    grounding_lines = sum(1 for _ in grounding_path.open(encoding="utf-8")) if grounding_path.exists() else 0

    return {
        "p1_2": "grounding_sidecar_v0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scratch_store": str(scratch),
        "grounding_entries_written": written,
        "grounding_jsonl_lines": grounding_lines,
        "decisions": decisions,
        "fact_files_unchanged(before==after)": fact_unchanged,
        "grounding_in_STORE_FILES(must_be_false)": GROUNDING_SIDECAR in STORE_FILES,
        "store_files": list(STORE_FILES),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="P1 ② grounding sidecar writer (scratch demo)")
    ap.add_argument("--limit", type=int, default=120)
    args = ap.parse_args()
    rep = run(args.limit)
    print(f"[P1-2] grounding entries written={rep['grounding_entries_written']} "
          f"jsonl_lines={rep['grounding_jsonl_lines']} decisions={rep['decisions']}")
    print(f"[P1-2] fact files unchanged (before==after): {rep['fact_files_unchanged(before==after)']}")
    print(f"[P1-2] grounding in STORE_FILES (must be False): {rep['grounding_in_STORE_FILES(must_be_false)']}")
    print(f"[P1-2] scratch: {rep['scratch_store']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
