# -*- coding: utf-8 -*-
"""Object re-recognition — the visual signature cells (owner's 2026-07-12 directive).

Spatial memory records WHERE things were; this recognizes WHICH thing — is this the SAME water
bottle I saw before? A live object's feature signature is cross-checked against the signatures of
past object instances, so " ?" can eventually be answered.

No-LLM, pure geometry — cosine over signature vectors, the same currency face_cortex uses. Honest:
a confident match is claimed only above a conservative threshold; an uncertain look stays a gap
(never a fabricated "that's your bottle").

DRIFT DEFENSE (owner's design question):
 * MULTI-VIEW per instance — each instance keeps several signatures (different lighting/angles);
 matching uses the NEAREST view (max cosine), and a confirmed recognition ABSORBS the new view,
 so the instance's representation adapts to drift instead of decaying under it;
 * THRESHOLD — confident same-instance at 0.75, an uncertain band 0.65–0.75 that is NOT claimed
 (a mismatch is worse than a miss), same-label matching so a bottle is only matched to bottles;
 * TIME WEIGHTING — similarity dominates; recency is only a tie-break bonus 0.04·exp(-days/7), so a
 recently-seen instance is gently favored without ever overriding a strong signature match.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

_LEDGER = Path(__file__).resolve().parents[2] / "data" / "perception" / "object_instances.jsonl"
_MATCH = 0.75           # confident: the SAME instance
_MAYBE = 0.65           # uncertain band → looks similar but not claimed
_MAX_VIEWS = 12         # signatures kept per instance (multi-view drift adaptation)
_MAX_INSTANCES = 2000


def _load() -> list[dict[str, Any]]:
    try:
        with _LEDGER.open("r", encoding="utf-8") as fh:
            return [json.loads(ln) for ln in fh if ln.strip()]
    except Exception:
        return []


def _save(instances: list[dict[str, Any]]) -> None:
    try:
        _LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with _LEDGER.open("w", encoding="utf-8") as fh:
            for inst in instances[-_MAX_INSTANCES:]:
                fh.write(json.dumps(inst, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a[:n])) or 1.0
    nb = math.sqrt(sum(x * x for x in b[:n])) or 1.0
    return dot / (na * nb)


def recognize_object(signature: list[float], *, label: str | None = None,
                     update: bool = True) -> dict[str, Any]:
    """Is this a KNOWN object instance? Cross-check the signature against past instances (same label
    preferred), nearest-view cosine + a recency tie-break. On a confident match, absorb the new view
    (drift adaptation) and bump last_seen/times_seen; on a clear miss, mint a new instance."""
    sig = [float(v) for v in (signature or [])]
    if not sig:
        return {"matched": False, "reason": "no_signature"}
    now = time.time()
    instances = _load()

    best: dict[str, Any] | None = None
    for inst in instances:
        if label and str(inst.get("label")) != str(label):
            continue                                        # a bottle is only matched to bottles
        views = inst.get("signatures") or []
        sim = max((_cosine(sig, v) for v in views), default=0.0)
        days = (now - float(inst.get("last_seen", now))) / 86400.0
        score = sim + 0.04 * math.exp(-days / 7.0)          # recency is a tie-break only
        if best is None or score > best["score"]:
            best = {"inst": inst, "sim": sim, "score": score}

    if best and best["sim"] >= _MATCH:                       # RE-RECOGNIZED
        inst = best["inst"]
        if update:
            inst["signatures"] = ((inst.get("signatures") or []) + [sig])[-_MAX_VIEWS:]
            inst["last_seen"] = round(now, 2)
            inst["times_seen"] = int(inst.get("times_seen", 1)) + 1
            _save(instances)
        return {"matched": True, "instance_id": inst.get("id"), "label": inst.get("label"),
                "similarity": round(best["sim"], 4), "times_seen": int(inst.get("times_seen", 1)),
                "first_seen": inst.get("first_seen"), "last_seen": inst.get("last_seen"),
                "days_known": round((now - float(inst.get("first_seen", now))) / 86400.0, 2)}

    if best and best["sim"] >= _MAYBE:                       # similar, but not claimed — honest gap
        return {"matched": False, "uncertain": True, "similarity": round(best["sim"], 4),
                "note": "비슷하지만 같은 물건이라 단정하지 않아요."}

    # a genuinely new object instance
    inst = {"id": f"obj_{int(now * 1000)}", "label": str(label or "물체")[:40],
            "signatures": [sig], "first_seen": round(now, 2), "last_seen": round(now, 2),
            "times_seen": 1}
    if update:
        instances.append(inst)
        _save(instances)
    return {"matched": False, "new": True, "instance_id": inst["id"], "label": inst["label"]}


def instance_stats() -> dict[str, Any]:
    """Read-only summary for /ops: how many distinct objects the eye has learned to recognize."""
    instances = _load()
    from collections import Counter
    by_label = Counter(str(i.get("label")) for i in instances)
    return {"instances": len(instances),
            "top_labels": dict(by_label.most_common(8)),
            "most_seen": max((int(i.get("times_seen", 1)) for i in instances), default=0)}
