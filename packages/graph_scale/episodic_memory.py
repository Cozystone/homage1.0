# -*- coding: utf-8 -*-
"""Episodic memory — the multimodal continuity backbone for ' …'.

Owner's AGI scenario (2026-07-09): mid-conversation about supercars the user
trails off — " …" — and ATANOR finishes the guess
and interjects: " 7 ? 
 ?", pulling in what the SMART GLASSES saw that day. Smart glasses
don't exist yet, so this is built STRUCTURALLY so it plugs in the moment they do:
an episode carries multimodal OBSERVATIONS (text / voice / vision), each with a
salience (how much it impressed the user), and recall ranks by concept overlap,
salience, and time — not recency alone, because the user is reaching into the past.

THE HONESTY INVARIANT (same spine as the prefilter): recall NEVER invents an
episode or an observation. If nothing matches the vague cue it ABSTAINS ("
 "). The completion is a HYPOTHESIS phrased as a question
the user confirms — never asserted as fact. A vision observation is surfaced only
if it was really recorded (the glasses put it there); with no glasses, no vision
slot is filled, so nothing is fabricated.

Local + personal (like the activity journal), not the shared graph.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "episodic_memory.jsonl"

_MODALITIES = ("text", "voice", "vision")


@dataclass
class Observation:
    modality: str          # text | voice | vision  (vision = smart-glasses-ready slot)
    label: str
    salience: float = 0.5  # 0..1 — how much it impressed/was emphasized
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"modality": self.modality, "label": self.label,
                "salience": round(float(self.salience), 3), "detail": self.detail}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rows() -> list[dict[str, Any]]:
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _append(row: dict[str, Any]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def record_episode(title: str, concepts: list[str], *, at: str | None = None,
                   place: str = "", observations: list[Observation] | None = None,
                   salience: float = 0.5, source: str = "conversation") -> dict[str, Any]:
    """Record a lived episode. observations may carry any modality; a vision
    observation is exactly what smart glasses would deposit."""
    ep = {
        "episode_id": uuid.uuid4().hex[:12],
        "at": at or _now().strftime("%Y-%m-%dT%H:%M:%S"),
        "title": title,
        "concepts": [c for c in concepts if c],
        "place": place,
        "observations": [o.to_dict() for o in (observations or [])],
        "salience": round(float(salience), 3),
        "source": source,
    }
    _append(ep)
    return ep


def add_observation(episode_id: str, modality: str, label: str,
                    salience: float = 0.5, detail: dict[str, Any] | None = None) -> bool:
    """Attach a multimodal observation to an existing episode — the entry point a
    smart-glasses / mic stream calls to enrich a remembered moment. Rewrites the
    ledger (small, personal)."""
    if modality not in _MODALITIES:
        return False
    rows = _rows()
    hit = False
    for r in rows:
        if r.get("episode_id") == episode_id:
            r.setdefault("observations", []).append(
                Observation(modality, label, salience, detail or {}).to_dict())
            hit = True
            break
    if hit:
        LEDGER.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                          encoding="utf-8")
    return hit


def salience_from_behavior(dwell_seconds: float, *, revisits: int = 0,
                           gaze_ratio: float = 1.0) -> float:
    """Infer INTEREST from behaviour, not from being told. The owner's key point:
 '' should mean the user LINGERED near the model car / looked at it
 long — dwell time is the signal, not a spoken statement. Saturating curve:
 a glance (~1s) barely registers, ~6s is mild interest, ~15s+ is strong; a
 revisit deepens it; gaze_ratio scales by how much of the dwell was actually
 looking. Returns a salience in [0, 1] the AI can read as 'interested'."""
    import math
    d = 1.0 - math.exp(-max(0.0, float(dwell_seconds)) / 8.0)   # 0s→0, ~5.5s→0.5, ~18s→0.9
    r = min(0.3, 0.1 * max(0, int(revisits)))                   # returning = deeper interest
    g = max(0.0, min(1.0, float(gaze_ratio)))
    return round(min(1.0, d * g + r), 3)


def record_perception(episode_id: str, label: str, *, modality: str = "vision",
                      dwell_seconds: float = 0.0, revisits: int = 0,
                      gaze_ratio: float = 1.0, utterance: str = "",
                      detail: dict[str, Any] | None = None) -> bool:
    """The entry point a smart-glasses / camera / mic stream calls: it reports WHAT
 was seen, the BEHAVIOUR around it (dwell, revisits, gaze), and WHAT WAS SAID
 while looking. Interest MAGNITUDE is inferred from dwell; interest VALENCE from
 the utterance — the same 20s dwell means admiration ('') or doubt ('')
 depending on it. Both are stored (auditable), never a mind-reading claim."""
    sal = salience_from_behavior(dwell_seconds, revisits=revisits, gaze_ratio=gaze_ratio)
    basis = {"inferred_from": "behavior", "dwell_seconds": round(float(dwell_seconds), 1),
             "revisits": int(revisits), "gaze_ratio": round(float(gaze_ratio), 2)}
    if utterance:
        try:
            from .subjective_context import interpret
            sub = interpret(dwell_seconds, utterance)
            basis.update({"stance": sub["stance"], "valence": sub["valence"],
                          "read": sub["read"], "phrase": sub["phrase"], "cues": sub["cues"]})
        except Exception:
            pass
    basis.update(detail or {})
    return add_observation(episode_id, modality, label, salience=sal, detail=basis)


def _relative_ko(at: str, now: datetime) -> str:
    """Human relative time in Korean: ' 7', '', '3 '."""
    try:
        t = datetime.strptime(at[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return "언젠가"
    ym_now = now.year * 12 + now.month
    ym_t = t.year * 12 + t.month
    months = ym_now - ym_t
    if months <= 0:
        return "이번 달"
    if t.year == now.year:
        return f"올해 {t.month}월"
    if t.year == now.year - 1:
        return f"작년 {t.month}월"
    return f"{now.year - t.year}년 전 {t.month}월"


def _age_days(at: str, now: datetime) -> float:
    try:
        t = datetime.strptime(at[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return max(0.0, (now - t).total_seconds() / 86400.0)
    except Exception:
        return 0.0


def consolidate(now: datetime | None = None, *, half_life_days: float = 30.0,
                forget_floor: float = 0.05, min_forget_age_days: float = 7.0) -> dict[str, Any]:
    """Background memory consolidation (osaurus's salience-scored 3-layer memory +
    the brain's salience compression, done HONESTLY): a moment's SALIENCE — set by
    behaviour and felt valence — governs how long it is REMEMBERED, decaying with
    age (half-life). Trivial + old episodes are forgotten; meaningful ones persist.

    HARD BOUNDARY: salience here compresses MEMORY (what to retain), never lowers
    the bar for what the engine ASSERTS as true. Forgetting a dull moment is human;
    asserting a guess because you're 'excited' is the LLM failure we refuse."""
    now = now or _now()
    rows = _rows()
    survivors: list[dict[str, Any]] = []
    forgotten = 0
    for ep in rows:
        age = _age_days(ep.get("at", ""), now)
        sal = float(ep.get("salience", 0.5))
        # vivid memories persist far longer: half-life scales with salience, so a
        # 0.9 moment lasts ~years while a 0.08 glance fades in weeks (consolidation
        # to long-term is salience-gated, as in the brain).
        half_life_eff = max(1e-6, half_life_days) * (1.0 + 9.0 * sal)
        eff = sal * (0.5 ** (age / half_life_eff))
        if eff < forget_floor and age > min_forget_age_days:
            forgotten += 1                     # dull and old -> let it fade
            continue
        survivors.append(ep)
    # merge near-duplicates: same title, concept overlap, within a day (double-logged)
    merged = 0
    out: list[dict[str, Any]] = []
    for ep in survivors:
        hit = None
        for prev in out:
            if prev.get("title") == ep.get("title") and \
               set(prev.get("concepts") or []) & set(ep.get("concepts") or []) and \
               abs(_age_days(prev.get("at", ""), now) - _age_days(ep.get("at", ""), now)) < 1.0:
                hit = prev
                break
        if hit:
            hit["observations"] = (hit.get("observations") or []) + (ep.get("observations") or [])
            hit["salience"] = max(float(hit.get("salience", 0)), float(ep.get("salience", 0)))
            hit["concepts"] = sorted(set(hit.get("concepts") or []) | set(ep.get("concepts") or []))
            merged += 1
        else:
            out.append(ep)
    if forgotten or merged:
        LEDGER.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n",
                          encoding="utf-8")
    return {"kept": len(out), "forgotten": forgotten, "merged": merged,
            "note": "salience-weighted retention (behaviour/valence -> what to keep); "
                    "never touches the truth threshold for assertions"}


def recall(focus_concepts: list[str], *, cue_text: str = "", now: datetime | None = None,
           k: int = 3, min_overlap: int = 1) -> list[dict[str, Any]]:
    """Rank remembered episodes by concept overlap (primary), salience, and — only
    lightly — recency (the user is reaching BACK). Returns matches or []; never a
    fabricated episode."""
    now = now or _now()
    focus = {c for c in focus_concepts}
    if not focus:
        return []
    scored = []
    for ep in _rows():
        concepts = set(ep.get("concepts") or [])

        for o in ep.get("observations") or []:
            concepts.add(o.get("label"))
        overlap = len(focus.intersection(concepts))
        if overlap < min_overlap:
            continue
        try:
            t = datetime.strptime(ep["at"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            days = max(0.0, (now - t).total_seconds() / 86400.0)
        except Exception:
            days = 3650.0
        recency = 1.0 / (1.0 + days / 365.0)         # gentle: a year ~0.5, minor weight
        score = overlap * 1.0 + float(ep.get("salience", 0.5)) * 0.5 + recency * 0.3
        scored.append((score, overlap, ep))
    scored.sort(key=lambda s: -s[0])
    return [{**ep, "_overlap": ov, "_score": round(sc, 3)} for sc, ov, ep in scored[:k]]


def complete(partial_text: str, focus_concepts: list[str], *,
             now: datetime | None = None) -> dict[str, Any] | None:
    """The predictive interjection: from a vague ' …' + the concepts
 typed/spoken so far, recall the most likely episode and voice it AS A QUESTION.
 Surfaces the highest-salience observation (e.g. what the glasses saw). Returns
 None (abstain) when no episode is a confident match — never a guessed memory."""
    now = now or _now()
    hits = recall(focus_concepts, cue_text=partial_text, now=now, k=3)
    if not hits:
        return None
    top = hits[0]
    when = _relative_ko(top["at"], now)
    text = f"{when}에 갔던 {top['title']}요?"
    # the most impressive multimodal observation, if one was really recorded
    obs = sorted((o for o in top.get("observations") or []),
                 key=lambda o: -float(o.get("salience", 0)))
    salient = obs[0] if obs and float(obs[0].get("salience", 0)) >= 0.6 else None
    if salient:
        # be honest about the SUBJECTIVE read: valence (from what was said while
        # looking) picks the phrase — admiring vs skeptical vs neutral dwell —

        det = salient.get("detail") or {}
        how = det.get("phrase") or ("한참 보셨던" if det.get("inferred_from") == "behavior"
                                    else "인상깊어하셨던")
        text += f" 그때 {how} {salient['label']} 말하시려던 거죠?"
    # confidence rises with overlap + top salience; still a hypothesis
    conf = min(0.95, 0.4 + 0.15 * top.get("_overlap", 1)
               + (0.2 if salient else 0.0))
    return {
        "completion": text,
        "episode": {"episode_id": top["episode_id"], "title": top["title"],
                    "at": top["at"], "place": top.get("place", "")},
        "salient_observation": salient,
        "confidence": round(conf, 3),
        "hypothesis": True,
        "note": "a recalled-episode hypothesis phrased as a question — the user confirms; "
                "no episode or observation is invented",
    }
