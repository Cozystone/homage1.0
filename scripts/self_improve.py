#!/usr/bin/env python3
"""Self-improvement loop — automates the coverage cycle we were doing by hand.

One cycle:
  1. MEASURE  — ask a concept pool, classify each answer (answered / abstain / hallucination-ish).
  2. DIAGNOSE — the abstained answer-expected concepts are COVERAGE GAPS.
  3. ACT      — auto-fetch each gap's KO-Wikipedia definition and durably ingest it
                (worker stopped to avoid a write race), then re-promote.
  4. VERIFY   — re-measure; compute the coverage delta.
  5. LOG      — append metrics to self_improve_history.jsonl so improvement is tracked.

Gaps that have a definition but STILL abstain after seeding are reported as "hard"
(decomposer TOPIC-extraction / promotion edge cases) — NOT auto-fixable, flagged for a
systematic pass. So the loop clears the easy long tail automatically and surfaces the
genuinely hard cases, which is exactly the manual labor to remove.

Run repeatedly (or wrap in a scheduler) to keep closing coverage over time.
"""
from __future__ import annotations
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (str(REPO_ROOT), str(REPO_ROOT / "apps" / "api"), str(REPO_ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import coverage_seed as cov          # noqa: E402  (fetch + ingest pipeline)
import durable_ingest as di          # noqa: E402
import promote_graph_to_pack as promo  # noqa: E402

ANSWER_URL = "http://127.0.0.1:8502/api/base-brain/answer"
LEARN_BASE = "http://127.0.0.1:8502/api/cloud-brain/learning/continuous"
HISTORY = REPO_ROOT / "data" / "self_improve_history.jsonl"
ABSTAIN = ("근거가 부족", "실시간")


def _post(url: str, payload: dict | None = None, timeout: float = 20.0):
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ask(term: str) -> str:
    q = f"{term}란?" if term and ("가" <= term[-1] <= "힣") and term[-1] not in "" else f"{term}란?"
    try:
        return str(_post(ANSWER_URL, {"query": f"{term}란?", "language": "ko"}).get("answer") or "")
    except Exception as exc:
        return f"__ERR__ {exc}"


def measure(terms: list[str]) -> tuple[int, list[str]]:
    answered, gaps = 0, []
    for t in terms:
        a = ask(t)
        if any(m in a for m in ABSTAIN) or a.startswith("__ERR__"):
            gaps.append(t)
        else:
            answered += 1
    return answered, gaps


def _holdout_exclusions() -> set[str]:
    """Terms in the SEALED holdout battery must never be seeded (Goodhart defence,
 P2). Built by scripts/build_holdout_battery.py."""
    path = REPO_ROOT / "data" / "eval" / "holdout_exclusions.json"
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("never_seed_terms", []))
    except Exception:
        return set()


def main() -> int:
    terms = cov.TERMS
    print(f"[SELF-IMPROVE] pool = {len(terms)} concepts")
    before_ans, gaps = measure(terms)
    print(f"[MEASURE] answered {before_ans}/{len(terms)} ({before_ans/len(terms):.0%}) | gaps: {len(gaps)}")
    sealed = _holdout_exclusions()
    blocked = [t for t in gaps if t in sealed]
    if blocked:
        print(f"[SEAL] {len(blocked)} gap terms are in the sealed holdout — NOT seeding: {blocked[:10]}")
        gaps = [t for t in gaps if t not in sealed]
    if not gaps:
        print("[DONE] no coverage gaps.")
        return 0

    # ACT: seed definitions for the gap concepts (worker stopped) then re-promote.
    print(f"[ACT] fetching + ingesting KO-Wikipedia definitions for {len(gaps)} gap concepts...")
    try:
        _post(f"{LEARN_BASE}/stop")
    except Exception:
        pass
    rows = []
    for term in gaps:
        try:
            r = cov._wiki_rest_summary(term, cov.HOST)
        except Exception:
            r = None
        if r:
            sent = cov._first_sentence(r.get("snippet", ""))
            if 15 < len(sent) < 240:
                rows.append((sent, r.get("url") or f"https://{cov.HOST}/wiki/{term}", "reference_only", "public_web_feed"))
    ing = di.ingest(cov.LIVE, rows) if rows else {"new_facts": 0}
    print(f"[ACT] fetched {len(rows)} defs, ingested {ing.get('new_facts')} new")
    promo.promote()
    try:
        _post(f"{LEARN_BASE}/start")
    except Exception:
        pass

    # VERIFY
    after_ans, gaps2 = measure(terms)
    newly = set(gaps) - set(gaps2)
    hard = sorted(set(gaps) & set(gaps2))          # had a def attempt but still abstain
    print(f"\n[VERIFY] answered {before_ans} -> {after_ans}  (+{after_ans - before_ans})")
    print(f"[VERIFY] newly answered ({len(newly)}): {sorted(newly)[:20]}")
    print(f"[HARD] still abstain after seeding ({len(hard)}) — decomposer/promotion edge cases: {hard[:20]}")

    # LOG
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "t": datetime.now(timezone.utc).isoformat(), "pool": len(terms),
            "answered_before": before_ans, "answered_after": after_ans,
            "gained": after_ans - before_ans, "hard_remaining": len(hard),
        }, ensure_ascii=False) + "\n")
    print(f"[LOG] appended to {HISTORY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
