"""Answer-policy EXPERIENCE ledger — self-correction from lived outcomes, not just a battery.

The tuner previously optimised a fixed hand-labelled battery. That is safe but cannot be
' ': a routing mistake the battery never anticipated stays invisible (Goodhart).
This module closes the loop with real experience:

 1. RECORD: every live policy decision appends (query, feature snapshot, chosen mode).
 The snapshot is what the policy actually saw — so later labels judge the decision
 that was made, not a re-imagined one.
 2. LABEL: outcome evidence attaches an expected-mode set to a recorded decision.
 Sources are MEASURED, never guessed: the honesty eval's flagged confident-wrongs
 (expected {engage, abstain}) and its confirmed corrects (reinforce the chosen mode);
 the web-rescue outcome of a locally-abstained query (an anchored cited answer proves
 the query was answerable; a gate-rejected empty proves a confident seek was wrong);
 and the abstain-to-ingest loop grounding a definition for a query it once abstained on.
 3. TRAIN: labelled experience joins the battery in the tuner's margin objective —
 bounded to the latest N so old contexts fade — while the hand battery remains a
 hard accuracy FLOOR the tuner may never regress.

So a trigger-control mistake becomes data, data moves weights, and no human writes a new
rule. Bounded, append-only, deterministic to read."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2] / "data" / "base_brain"
LEDGER = _ROOT / "answer_experience.jsonl"
_MAX_READ = 4000          # bounded ledger scan
_MAX_EXAMPLES = 200       # latest labelled examples used for training


def _append(rec: dict[str, Any]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def record_decision(query: str, features: dict[str, float], mode: str) -> None:
    """Log a live policy decision with its exact feature snapshot. Never raises."""
    try:
        _append({"kind": "decision", "q": (query or "")[:200],
                 "features": {k: round(float(v), 4) for k, v in (features or {}).items()},
                 "mode": mode, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
    except Exception:
        pass


def label_outcome(query: str, expected_modes: list[str] | set[str], source: str) -> bool:
    """Attach measured outcome evidence to the LATEST decision for this query.
    Returns True if a matching decision existed. Never raises."""
    try:
        q = (query or "")[:200]
        lines = LEDGER.read_text(encoding="utf-8").splitlines()[-_MAX_READ:] if LEDGER.exists() else []
        for line in reversed(lines):
            rec = json.loads(line)
            if rec.get("kind") == "decision" and rec.get("q") == q:
                _append({"kind": "label", "q": q, "features": rec.get("features") or {},
                         "chosen": rec.get("mode"), "expected": sorted(set(expected_modes)),
                         "source": source, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
                return True
        return False
    except Exception:
        return False


def latest_decision(query: str, *, contains: bool = False) -> dict[str, Any] | None:
    """Latest recorded decision for this query. Matches exact-or-prefix (the abstain queue
    truncates stored queries to 120 chars); with contains=True, a decision whose query
    CONTAINS the key also matches (term-level lookup). Never raises."""
    try:
        q = (query or "").strip()[:200]
        if not q or not LEDGER.exists():
            return None
        for line in reversed(LEDGER.read_text(encoding="utf-8").splitlines()[-_MAX_READ:]):
            rec = json.loads(line)
            if rec.get("kind") != "decision":
                continue
            rq = str(rec.get("q") or "")
            if rq == q or rq.startswith(q) or (contains and q in rq):
                return rec
        return None
    except Exception:
        return None


_SEEK_MODES = ("compute", "define", "synthesize")


def label_web_rescue_outcome(query: str, *, anchored: bool) -> bool:
    """MEASURED label from the web-rescue outcome of a locally-abstained query.
    anchored=True — the rescue served a subject-anchored, cited answer: the query WAS
    answerable, so a conversational/abstaining routing is corrected toward the seek modes
    and a seek routing is reinforced. anchored=False — neither the local graph nor the
    web relevance gate could anchor anything: a confident seek routing is corrected toward
    {engage, abstain}; an abstain/engage routing is reinforced. Network failures carry no
    evidence and must NOT be labelled. Never raises."""
    dec = latest_decision(query)
    if not dec:
        return False
    chosen = str(dec.get("mode") or "")
    if chosen not in ("compute", "define", "synthesize", "engage", "abstain"):
        return False
    if anchored:
        expected = {"define", "synthesize"} if chosen in ("engage", "abstain") else {chosen}
    else:
        expected = {"engage", "abstain"} if chosen in _SEEK_MODES else {chosen}
    return label_outcome(str(dec.get("q") or query), expected,
                         "web-rescue-anchored" if anchored else "web-rescue-empty")


def label_reingest_success(term: str, query: str = "") -> bool:
    """MEASURED label when the abstain-to-ingest loop later GROUNDED a judge-passed
    definitional fact for a query the policy once routed: the query was definitional
    after all. Corrects an engage/abstain routing toward the seek modes; reinforces a
    seek routing. Never raises."""
    dec = latest_decision(query) if query else None
    if not dec and term:
        dec = latest_decision(term, contains=True)
    if not dec:
        return False
    chosen = str(dec.get("mode") or "")
    if chosen not in ("compute", "define", "synthesize", "engage", "abstain"):
        return False
    expected = {"define", "synthesize"} if chosen in ("engage", "abstain") else {chosen}
    return label_outcome(str(dec.get("q") or query or term), expected, "abstain-reingest")


def training_examples(limit: int = _MAX_EXAMPLES) -> list[tuple[dict[str, float], set[str]]]:
    """Latest labelled experiences as (feature_snapshot, expected_mode_set). Deduped by
    query (newest label wins) so one repeated mistake doesn't dominate the objective."""
    if not LEDGER.exists():
        return []
    by_q: dict[str, tuple[dict[str, float], set[str]]] = {}
    try:
        for line in LEDGER.read_text(encoding="utf-8").splitlines()[-_MAX_READ:]:
            rec = json.loads(line)
            if rec.get("kind") == "label" and rec.get("features") and rec.get("expected"):
                by_q[rec["q"]] = ({k: float(v) for k, v in rec["features"].items()},
                                  set(rec["expected"]))
    except Exception:
        return []
    return list(by_q.values())[-limit:]
