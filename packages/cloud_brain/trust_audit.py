"""Trust scaling for the shared brain ( P5-⑧) — layered defence, no bottleneck.

The operator cannot review every promotion (bottleneck) and full auto-promotion
is a poisoning surface. The Wikipedia/OSM survival formula, adapted:

 1. QUARANTINE — already enforced by the consensus ledger (P1);
 2. SYBIL CAP — one source = one voice (P2 truth discovery);
 3. SPOT AUDIT — the operator reviews a RANDOM SAMPLE of promotions, not
 all of them (statistical deterrence beats exhaustive review);
 4. DRIFT FREEZE — a CUSUM monitor on the promotion rate: a sudden surge
 (mass-injection signature) trips a freeze flag that stops
 further promotions until the operator clears it.

The freeze is default-open, trip-on-anomaly — normal learning is untouched.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FREEZE_FLAG = "promotion_freeze.flag"
_DRIFT_STATE = "promotion_drift.json"
_CUSUM_K = 0.5     # slack: ignore drift below mean + K*std
_CUSUM_H = 8.0     # trip threshold in std units (accumulated)
_MIN_TICKS = 10    # never trip before a baseline exists


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sample_for_review(ledger: Any, n: int = 5, *, rng: random.Random | None = None) -> list[dict[str, Any]]:
    """Random promoted claims with their evidence — the operator's spot-audit feed."""
    rng = rng or random.Random()
    promoted = [(k, v) for k, v in ledger._agg.items() if k in ledger._promoted]  # noqa: SLF001
    rng.shuffle(promoted)
    out = []
    for key, slot in promoted[: max(0, n)]:
        row = slot.get("row") or {}
        out.append({
            "consensus_key": key,
            "subject": slot.get("source_label"),
            "relation": row.get("relation"),
            "object": slot.get("target_label"),
            "evidence_count": len(slot.get("sources") or ()),
            "provenance_source": (row.get("provenance") or {}).get("source_id"),
        })
    return out


def is_frozen(ledger_root: str | Path) -> bool:
    return (Path(ledger_root) / FREEZE_FLAG).exists()


def clear_freeze(ledger_root: str | Path) -> bool:
    """Operator action: acknowledge the anomaly and reopen promotion."""
    flag = Path(ledger_root) / FREEZE_FLAG
    if flag.exists():
        flag.unlink()
        return True
    return False


def update_drift(ledger_root: str | Path, promoted_this_tick: int) -> dict[str, Any]:
    """CUSUM over per-tick promotion counts. Trips the freeze flag on a surge.

    Welford-style running mean/var + one-sided CUSUM S+ = max(0, S+ + (x - mean - K*std)).
    S+ > H*std → freeze. State persists as JSON so it survives restarts.
    """
    root = Path(ledger_root)
    root.mkdir(parents=True, exist_ok=True)
    state_path = root / _DRIFT_STATE
    state = {"n": 0, "mean": 0.0, "m2": 0.0, "s_plus": 0.0, "tripped_at": None}
    if state_path.exists():
        try:
            state.update(json.loads(state_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass

    x = float(promoted_this_tick)
    # the CUSUM decision must use the BASELINE (pre-update) statistics — folding the
    # surge into the variance first would inflate the threshold exactly when the
    # anomaly arrives, hiding it.
    baseline_std = (state["m2"] / state["n"]) ** 0.5 if state["n"] > 1 else 0.0
    n = state["n"] + 1
    delta = x - state["mean"]
    mean = state["mean"] + delta / n
    m2 = state["m2"] + delta * (x - mean)
    std = (m2 / n) ** 0.5 if n > 1 else 0.0

    tripped = False
    # count data: a perfectly steady baseline has std=0 — floor at 1 promotion so a
    # surge over a quiet baseline still registers instead of dividing by silence.
    eff_std = max(baseline_std, 1.0)
    if state["n"] >= _MIN_TICKS:
        s_plus = max(0.0, state["s_plus"] + (x - state["mean"] - _CUSUM_K * eff_std))
        if s_plus > _CUSUM_H * eff_std:
            tripped = True
            state["tripped_at"] = _utc_now()
            (root / FREEZE_FLAG).write_text(
                json.dumps({"tripped_at": state["tripped_at"], "s_plus": round(s_plus, 3),
                            "x": x, "mean": round(state["mean"], 3), "std": round(eff_std, 3),
                            "action": "promotion frozen — operator must clear_freeze() after review"},
                           ensure_ascii=False),
                encoding="utf-8")
            s_plus = 0.0  # reset after trip
    else:
        s_plus = 0.0

    state.update({"n": n, "mean": mean, "m2": m2, "s_plus": s_plus})
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return {"n": n, "mean": round(mean, 3), "std": round(std, 3),
            "s_plus": round(s_plus, 3), "frozen": tripped or is_frozen(root)}
