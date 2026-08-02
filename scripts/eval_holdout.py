#!/usr/bin/env python3
"""Score the SEALED holdout battery against the live engine (:8502).

Refuses to run if the seal is broken. Reports answered / abstained / grounded
counts and appends to data/eval/holdout_history.jsonl. The number that matters
long-term is the GAP between the working battery's coverage and this one's —
a widening gap means self_improve is overfitting the working battery (Goodhart).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# cp949 console cannot print an em-dash; this script prints store text. Same fix as
# eval_seal_battery, same day, same trap.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
EVAL_DIR = REPO / "data" / "eval"
BATTERY = EVAL_DIR / "holdout_v1.jsonl"
BATTERY2 = EVAL_DIR / "holdout_v2.jsonl"
HISTORY = EVAL_DIR / "holdout_history.jsonl"
URL = "http://127.0.0.1:8502/api/base-brain/answer"
ABSTAIN = ("근거가 부족", "실시간", "확인된 근거로는", "찾아드릴게요")

# content-word grounding: strip josa/punct, keep tokens >= 2 chars that aren't generic filler
_GROUND_STOP = {"그리고", "그러나", "또는", "다음과", "같은", "있는", "이다", "된다", "한다", "대한",
                "위한", "통해", "라는", "라고", "에서", "으로", "에게", "이나", "따라", "때문"}


def _content_tokens(text: str) -> list[str]:
    import re
    toks = re.findall(r"[가-힣A-Za-z0-9]+", str(text or ""))
    return [t for t in toks if len(t) >= 2 and t not in _GROUND_STOP]


def _is_grounded(answer: str, expected_source: str) -> bool:
    """Correctness PROXY (not human judgement): is the answer supported by the battery's expected
    source passage? True when the answer shares a substantial fraction of the source's content
    words. Reproducible and conservative — it can't certify truth, but it catches 'answered but
    unrelated', which is exactly the gap between a non-abstention rate and a grounded-QA rate."""
    src = _content_tokens(expected_source)
    if not src:
        return False
    ans = str(answer or "")
    hit = sum(1 for t in set(src) if t in ans)
    return (hit / len(set(src))) >= 0.34

sys.path.insert(0, str(REPO / "scripts"))
from build_holdout_battery import check as seal_check  # noqa: E402
from build_holdout_battery import check_v2 as seal_check_v2  # noqa: E402


_LOCAL_CLIENT = None


def _local_client():
    """In-process client running THIS worktree's code — the honest projection of what
    the live engine will score after its operator-gated restart. Same route, same body."""
    global _LOCAL_CLIENT
    if _LOCAL_CLIENT is None:
        import os
        os.chdir(REPO / "apps" / "api")
        sys.path.insert(0, str(REPO / "apps" / "api"))
        sys.path.insert(0, str(REPO))
        from fastapi.testclient import TestClient
        from app.main import app
        _LOCAL_CLIENT = TestClient(app)
    return _LOCAL_CLIENT


def ask(question: str, local: bool = False) -> str:
    if local:
        try:
            r = _local_client().post("/api/base-brain/answer",
                                     json={"query": question, "language": "ko"})
            return str(r.json().get("answer") or "")
        except Exception as exc:  # noqa: BLE001
            return f"__ERR__ {exc}"
    data = json.dumps({"query": question, "language": "ko"}).encode("utf-8")
    req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return str(json.loads(r.read().decode("utf-8")).get("answer") or "")
    except Exception as exc:  # noqa: BLE001 - live probe, report as error string
        return f"__ERR__ {exc}"


def _retired(manifest_path: Path) -> dict | None:
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8")).get("retired")
    except Exception:
        return None


def main(v2: bool = False, local: bool = False) -> int:
    if v2:
        battery, label = BATTERY2, "HOLDOUT-v2"
        if seal_check_v2() != 0:
            print("[EVAL] refusing to score: v2 seal invalid")
            return 2
    else:
        battery, label = BATTERY, "HOLDOUT"
        if seal_check() != 0:
            print("[EVAL] refusing to score: seal invalid")
            return 2
    # Korean batteries are retired under English-only containment (2026-07-17): every Korean
    # answer surface is withheld by design, so scoring one here measures the containment gate,
    # not knowledge — the number would be an honest-looking lie.
    ret = _retired(battery.with_name(battery.stem + ".manifest.json"))
    if ret:
        print(f"[EVAL] {label} is RETIRED ({ret.get('at')}): {ret.get('reason')}")
        print(f"[EVAL] superseded by: {ret.get('supersededBy')} — refusing to score")
        return 3
    rows = [json.loads(l) for l in battery.read_text(encoding="utf-8").splitlines() if l.strip()]
    answered = abstained = errors = grounded = 0
    hard: list[str] = []
    ungrounded_terms: list[str] = []
    for row in rows:
        a = ask(row["question"], local=local)
        if a.startswith("__ERR__"):
            errors += 1
        elif any(m in a for m in ABSTAIN) or not a.strip():
            abstained += 1
            hard.append(row["term"])
        else:
            answered += 1
            # CORRECTNESS PROXY (Codex audit P0: 'answered' alone is only a non-abstention rate).
            # The battery ships the expected source passage — score whether the answer is actually
            # GROUNDED in it (shares the source's content words), not merely that it said something.
            if _is_grounded(a, str(row.get("expect_grounded_in") or "")):
                grounded += 1
            else:
                ungrounded_terms.append(row["term"])
    total = len(rows)
    gr_pct = (grounded / answered) if answered else 0.0
    # HONEST headline: grounded-in-source is the correctness proxy; answered is non-abstention.
    print(f"[{label}] grounded {grounded}/{total} ({grounded/total:.0%}) "
          f"| answered(non-abstention) {answered}/{total} ({answered/total:.0%}) "
          f"| of-answered grounded {gr_pct:.0%} | abstained {abstained} | errors {errors}")
    if ungrounded_terms:
        print(f"[{label}] answered-but-ungrounded: {ungrounded_terms[:15]}")
    if hard:
        print(f"[{label}] abstaining terms: {hard[:15]}")
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "t": datetime.now(timezone.utc).isoformat(), "battery": battery.stem,
            "total": total, "grounded": grounded, "answered": answered,
            "abstained": abstained, "errors": errors,
        }, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--v2", action="store_true", help="score the fair should-answer battery")
    ap.add_argument("--local", action="store_true", help="score THIS worktree's code in-process (restart projection)")
    args = ap.parse_args()
    raise SystemExit(main(v2=args.v2, local=args.local))
