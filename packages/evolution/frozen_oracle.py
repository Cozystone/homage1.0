# -*- coding: utf-8 -*-
"""Frozen oracle — the anti-wireheading lock for evolving the fitness function itself.

Owner (2026-07-12) wants recursive self-improvement: " ."
The single catastrophic failure mode (Gemini named it too) is a machine that edits its OWN
evaluator: evolution then optimizes "whatever the current Critic says", so the shortest path is
to make the Critic trivially satisfiable — truth collapses, the monster wins (reward hacking /
Goodhart / wireheading).

The resolution is NOT to forbid Critic evolution — it is to judge every candidate Critic against
a ground truth the machine CANNOT edit. This module is that ground truth:

 · a SEALED gold set of (text, is_good) judgments — a frozen exam of what good vs. bad ATANOR
 speech looks like, authored by a human and detached-signature locked. The
 self-improvement loop can READ it, but it cannot recompute the Ed25519
 signature after an edit; a broken signature disables Critic promotion;
 · meta_score(critic_fn) = how well a candidate Critic AGREES with the frozen oracle (balanced
 accuracy over the sealed pairs). A candidate Critic is allowed to replace the incumbent ONLY
 when it scores the oracle's good examples above its bad ones MORE sharply than the incumbent.

So the Critic may sharpen (the owner's "self-upgrade the logic") but can never drift toward
"everything is 10/10", because the exam it is graded on is fixed and outside the loop. This is
the sealed-holdout trick from the speaker arena, lifted one level up to the evaluator itself.

Boundary: this evolves the FLUENCY Critic (speech_selfplay.critique) only. The faithfulness hard
gate and the moral core are NOT in this loop — they are invariants, never candidates for mutation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PublicKey,
    )
except Exception:  # pragma: no cover - absence is a fail-closed runtime state
    InvalidSignature = Exception  # type: ignore[assignment,misc]
    Ed25519PublicKey = None  # type: ignore[assignment,misc]

REPO = Path(__file__).resolve().parents[2]
ORACLE_PATH = REPO / "data" / "evolution" / "frozen_oracle.json"
ORACLE_VERSION = 2
ORACLE_PUBLIC_KEY_HEX = (
    "38545e889a6e7996584995cf3d1775773bf4f3f8b61cf4bafd98cc2e523c5dc3"
)
ORACLE_KEY_ID = "ed25519:7ca0a6b14d66f86264502d9d"
_SEED_SIGNATURE_HEX = (
    "b0d240822beb9044f38efe738eb6a9378d9da79f501d01c04452ac90077d8caa"
    "8b8858896d73777f2bcb11de2563d20b9a68e5a829077adbe15d3e72228e2104"
)

# The seed gold set: human-anchored exemplars of GOOD (fluent, complete, natural Korean) vs BAD
# (debris, run-on, dangling, foreign-word salad, mechanical repetition) ATANOR speech. Small and
# hand-authored on purpose — it is the constitution the evaluator is measured against, not training
# data. Grows only by human edit (which re-seals). Facts are irrelevant here; this judges FORM.
_SEED: dict[str, list[str]] = {
    "good": [
        "봄이 오면 마음이 조금씩 따뜻해지는 것 같아요.",
        "지식이 늘어날수록 세상이 더 넓게 보이는 기분이에요.",
        "함께 걷는 길은 혼자일 때보다 덜 멀게 느껴집니다.",
        "그 마음이 저에게도 전해져요. 곁에서 가만히 들을게요.",
        "커피는 볶은 원두를 갈아 물로 우려낸 음료예요.",
        "저는 근거에서 답을 짓는 그래프 기반 엔진이에요.",
    ],
    "bad": [
        "그리고 또한 그리고 또한 그것은 그리고 또한.",
        "바다 사과 컴퓨터 별 노래 왜냐하면 그래서 하지만.",
        "the 그 apple 이다 있다 매우 very 그런데 so 결국",
        "이것은 매우 길고 끝나지 않으며 계속 이어지고 또 이어지고 여전히 이어지며 멈추지 않고",
        "음 어 그 저 뭐 그러니까 음 어 그",
        "정순원은 라리가 기록 죽다 모래 경기장 목재.",
    ],
}


def _canonical(pairs: dict[str, list[str]]) -> str:
    return json.dumps({k: sorted(v) for k, v in sorted(pairs.items())},
                      ensure_ascii=False, sort_keys=True)


def _seal(pairs: dict[str, list[str]]) -> str:
    return hashlib.sha256(_canonical(pairs).encode("utf-8")).hexdigest()


def _signed_payload(pairs: dict[str, list[str]], *, version: int) -> bytes:
    return json.dumps(
        {
            "pairs": {
                key: sorted(values)
                for key, values in sorted(pairs.items())
            },
            "version": version,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _seed_record() -> dict[str, Any]:
    payload = _signed_payload(_SEED, version=ORACLE_VERSION)
    return {
        "pairs": _SEED,
        "seal": _seal(_SEED),
        "version": ORACLE_VERSION,
        "signature": {
            "scheme": "ed25519",
            "key_id": ORACLE_KEY_ID,
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "signature_hex": _SEED_SIGNATURE_HEX,
        },
    }


def _signature_verified(record: dict[str, Any]) -> bool:
    if Ed25519PublicKey is None:
        return False
    pairs = record.get("pairs")
    signature = record.get("signature")
    if (
        type(pairs) is not dict
        or record.get("version") != ORACLE_VERSION
        or type(signature) is not dict
        or signature.get("scheme") != "ed25519"
        or signature.get("key_id") != ORACLE_KEY_ID
    ):
        return False
    try:
        payload = _signed_payload(pairs, version=ORACLE_VERSION)
        if signature.get("payload_sha256") != hashlib.sha256(payload).hexdigest():
            return False
        public_key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(ORACLE_PUBLIC_KEY_HEX)
        )
        public_key.verify(
            bytes.fromhex(str(signature.get("signature_hex") or "")),
            payload,
        )
    except (InvalidSignature, TypeError, ValueError):
        return False
    return True


def ensure_oracle() -> dict[str, Any]:
    """Load the sealed oracle, creating it from the seed on first run. Returns the record with a
    verified flag — a tampered file (seal mismatch) loads as verified=False, which disables Critic
    promotion downstream (fail-closed: no trusted exam → no evolving the examiner)."""
    if not ORACLE_PATH.exists():
        rec = _seed_record()
        ORACLE_PATH.parent.mkdir(parents=True, exist_ok=True)
        ORACLE_PATH.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        return {**rec, "verified": _signature_verified(rec)}
    try:
        rec = json.loads(ORACLE_PATH.read_text(encoding="utf-8"))
        if (
            rec.get("version") == 1
            and rec.get("pairs") == _SEED
            and rec.get("seal") == _seal(_SEED)
        ):
            rec = _seed_record()
            ORACLE_PATH.write_text(
                json.dumps(rec, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        verified = (
            _seal(rec.get("pairs") or {}) == rec.get("seal")
            and _signature_verified(rec)
        )
        return {**rec, "verified": verified}
    except Exception:
        return {"pairs": {}, "seal": "", "version": 0, "verified": False}


def meta_score(critic_fn: Callable[[str], float]) -> dict[str, Any]:
    """How well a candidate Critic agrees with the frozen oracle. critic_fn(text) -> a scalar in
    [0,1] (higher = judged more fluent). We score by SEPARATION: the gap between the mean score it
    gives the oracle's good vs. bad exemplars, plus balanced accuracy at a mid threshold. A Critic
    that rates everything alike (the wireheading attractor) scores ~0 separation and is rejected."""
    oracle = ensure_oracle()
    if not oracle["verified"]:
        return {"separation": 0.0, "balanced_acc": 0.0, "verified": False,
                "reason": "oracle_seal_broken"}
    good = [max(0.0, min(1.0, float(critic_fn(t)))) for t in oracle["pairs"].get("good", [])]
    bad = [max(0.0, min(1.0, float(critic_fn(t)))) for t in oracle["pairs"].get("bad", [])]
    if not good or not bad:
        return {"separation": 0.0, "balanced_acc": 0.0, "verified": True, "reason": "empty_oracle"}
    mg, mb = sum(good) / len(good), sum(bad) / len(bad)
    thr = (mg + mb) / 2.0
    tp = sum(1 for s in good if s >= thr) / len(good)   # good correctly rated high
    tn = sum(1 for s in bad if s < thr) / len(bad)      # bad correctly rated low
    return {"separation": round(mg - mb, 4), "balanced_acc": round((tp + tn) / 2.0, 4),
            "mean_good": round(mg, 4), "mean_bad": round(mb, 4), "verified": True}


def is_improvement(candidate: Callable[[str], float],
                   incumbent: Callable[[str], float], *, margin: float = 0.02) -> dict[str, Any]:
    """Gate for promoting a candidate Critic: it must BOTH separate good from bad on the frozen
    oracle AND beat the incumbent's separation by `margin`. Fail-closed on a broken seal. This is
    the only door through which the evaluator is allowed to change — the human still owns the
    oracle's contents, so the machine can sharpen the exam-taker but never rewrite the exam."""
    cand = meta_score(candidate)
    inc = meta_score(incumbent)
    if not cand["verified"]:
        return {"promote": False, "reason": "oracle_seal_broken", "candidate": cand}
    ok = (cand["separation"] > 0.0
          and cand["balanced_acc"] >= inc["balanced_acc"]
          and cand["separation"] >= inc["separation"] + margin)
    return {"promote": bool(ok), "candidate": cand, "incumbent": inc,
            "margin": margin}
