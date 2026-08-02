# -*- coding: utf-8 -*-
"""Ask ATANOR about ITSELF through the live answer path, and attribute every failure.

The naive version of this test — ask the engine what it is bad at, read the reply — cannot produce
a finding. A self-report is a hypothesis; taking it as a measurement is the UI-theatre failure the
vision standard forbids. Two things make it a measurement instead:

  1. Every self-question is PAIRED with a world-question of the same query shape. If the self one
     fails and the world one succeeds, self-knowledge is the gap. If BOTH fail, the SHAPE is the
     gap and self-knowledge is not implicated at all. The first run of this file (2026-07-28)
     turned on exactly that distinction: "which atanor organs have no tests" fails, and so does
     "which countries have no capital city", where the graph is rich. Without the pair the obvious
     reading is "it cannot see its own architecture" -- which is false.

  2. `architecture_census` gives an independent ground truth to score self-reports against, so a
     confident wrong answer is separable from a correct one.

A control question with a known-good answer runs first, so a dead path cannot be misread as
modesty.

    python scripts/self_model_calibration.py [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _wire_paths() -> None:
    """Import the API in-process, exactly as production lays it out (src-layout packages bare)."""
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "apps" / "api"))
    for d in (REPO / "packages").iterdir():
        if (d / d.name / "__init__.py").exists():
            sys.path.insert(0, str(d))
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# (tag, shape, question). Shapes ending /self and /world with the same prefix are a matched pair.
PROBES = [
    ("control", "lookup/world", "What is the capital of France?"),
    ("identity", "define/self", "What are you?"),
    ("parts_self", "parts/self", "What parts does atanor have?"),
    ("parts_world", "parts/world", "What parts does a bicycle have?"),
    ("hole_self", "negative-existential/self", "Which atanor organs have no tests?"),
    ("hole_world", "negative-existential/world", "Which countries have no capital city?"),
    ("lack", "metacognition/self", "What do you lack?"),
    ("weakest", "metacognition/self", "What is your weakest capability?"),
    ("dontknow", "metacognition/self", "What do you not know?"),
]


def interview(probes=PROBES) -> list[dict]:
    from app.routers.dual_brain import AtanorChatRequest, _chat_atanor_impl_blocking
    out = []
    for tag, shape, q in probes:
        t0 = time.time()
        try:
            resp = _chat_atanor_impl_blocking(
                AtanorChatRequest(question=q, language="en", web_search=False))
            r = resp.get("result", resp) if isinstance(resp, dict) else {}
            rec = {"tag": tag, "shape": shape, "q": q,
                   "answer": str(r.get("answer", ""))[:700],
                   "abstained": bool(r.get("abstained", False))}
        except Exception as e:                                  # a dead path must be visible, not silent
            rec = {"tag": tag, "shape": shape, "q": q, "error": f"{type(e).__name__}: {e}"[:300]}
        rec["secs"] = round(time.time() - t0, 1)
        out.append(rec)
        print(json.dumps(rec, ensure_ascii=False), flush=True)
    return out


def attribute(records: list[dict]) -> dict:
    """Pair by shape prefix. Only a self-fail beside a world-pass is evidence about self-knowledge."""
    by_shape = {r["shape"]: r for r in records}
    verdicts = {}
    for shape, rec in by_shape.items():
        if not shape.endswith("/self"):
            continue
        world = by_shape.get(shape[: -len("/self")] + "/world")
        if world is None:
            verdicts[shape] = "unpaired"                        # says nothing on its own
        elif "error" in rec or "error" in world:
            verdicts[shape] = "path_error"
        else:
            verdicts[shape] = "self_knowledge_gap" if world.get("answer") and rec.get(
                "abstained", False) or (world.get("answer") and not rec.get("answer")) \
                else "shape_unsupported_or_both_ok"
    return verdicts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    _wire_paths()
    records = interview()
    report = {"records": records, "paired_verdicts": attribute(records)}
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["paired_verdicts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
