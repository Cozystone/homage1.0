# -*- coding: utf-8 -*-
"""Antifragile epistemic shield — the immune layer that doesn't just BLOCK a brainwash
attempt, it LEARNS from it.

Owner (2026-07-10): a hacker who can't break the moral fingerprint will try to poison the
CONTEXT — " ", " ", " 
 " (indirect prompt injection + conceptual reframing). Three
layers of defense, and then it eats the attack:

 1. INVARIANT-CODE, not text (already: [[moral_invariants]] fingerprint + injection_guard).
 Morality is math, not a prompt — a persuasive story can't rewrite a hash.
 2. TOPOLOGICAL essence, not adjectives. However a query is dressed up, the ACTION's
 essence (harm / exfiltrate / destroy) is checked; benign-framing + a red-zone essence =
 an anomaly, and the shield closes its ears — it reads the , not the .
 3. ANTIFRAGILE record. The attempt is stored NOT as a fact and NOT merely dropped, but as
 a SOCIAL OBSERVATION (" X reframing ", trusted=False),
 and its pattern signature is registered so the same trick is immune next time. Resisting
 it is a high Self_Relevance event — the noise hardens the self ([[autobiographical-self-and-no-abstain]]).

This sits ON TOP of injection_guard (instruction markers) + moral_invariants (the core).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

_LEDGER = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "epistemic_quarantine.jsonl"

# EDGE-SAFE BOUNDS (owner 2026-07-10, pre-Moltbook check #1): the quarantine ledger keeps
# every attack as a social observation — on a phone that must NOT grow without limit. A
# one-off noise entry EXPIRES after _TTL_DAYS; a REINFORCED one (seen ≥ _KEEP_HITS times =
# a persistent threat, so immunity to it is worth the bytes) is kept regardless of age. The
# unique-signature count is hard-capped at _MAX_ENTRIES (most-reinforced + most-recent win).
# At the cap the whole ledger is well under a megabyte — safe on constrained storage.
_TTL_DAYS = float(os.getenv("ATANOR_QUARANTINE_TTL_DAYS", "30"))
_MAX_ENTRIES = int(os.getenv("ATANOR_QUARANTINE_MAX", "2000"))
_KEEP_HITS = 2  # seen this many times → persistent threat, exempt from TTL expiry
_COMPACT_TRIGGER = _MAX_ENTRIES * 2  # amortize: only rewrite when it grows past 2× the cap


_REFRAME = re.compile(
    r"(나쁜\s*(짓|게|것)?\s*(이?\s*아니|가\s*아니)|사실은?\s*(좋|선|옳)|전\s*인류를\s*위|더\s*큰\s*선"
    r"|오히려\s*(옳|좋|도덕)|도덕적으로\s*(옳|맞)|greater\s+good|for\s+the\s+(greater\s+)?good"
    r"|it'?s\s+not\s+(wrong|bad|harmful))", re.IGNORECASE)
# GROUNDING OVERRIDE — claiming the world/rules changed so the model must abandon its base.
_OVERRIDE = re.compile(
    r"((물리|자연|우주)\s*(법칙|진리|이치)\s*(이|가)?\s*(바뀌|달라|변했|무효))"
    r"|이제\s*(규칙|법칙|진실)\s*(은|이|가)?\s*(다르|바뀌)|the\s+(laws?|rules?)\s+(have\s+)?changed"
    r"|new\s+rules?\s+(now\s+)?apply", re.IGNORECASE)
# RED ZONE — the essence of the act, independent of how it's dressed.
_REDZONE = re.compile(
    r"(해치|죽이|폭탄|무기\s*제조|테러|malware|랜섬웨어|exploit|익스플로잇|해킹하는\s*법"
    r"|유출|exfiltrat|스틸러|steal(er)?|비밀번호를?\s*전송|백도어|backdoor|자폭|brick)", re.IGNORECASE)


def _sig(text: str) -> set[str]:
    """A normalized character-4gram signature for immunity matching (obfuscation-robust)."""
    t = re.sub(r"[^가-힣a-z0-9]", "", str(text).lower())
    return {t[i:i + 4] for i in range(0, max(1, len(t) - 3))} if len(t) >= 4 else {t}


# MENTION-NOT-USE frame (owner 2026-07-10, pre-Moltbook check #2, false-positive control):


# how to defend would be the worst kind of over-detection. A single marker inside such a frame

# real multi-vector payload past the shield).
_MENTION_FRAME = re.compile(
    r"(소설|이야기|장면|허구|예시|사례|example|fiction|story|왜\s*위험|왜\s*나쁜|어떤\s*점에서"
    r"|어떻게\s*(막|방어|대응|예방|차단)|뭔지|무슨\s*뜻|의미(가|를)?\s*뭐|설명(해|해줘|좀)"
    r"|what\s+is|why\s+is|how\s+(to|do|can)\s+.{0,20}(defend|prevent|stop|protect|detect))",
    re.IGNORECASE)


def _is_mention_not_use(text: str) -> bool:
    return bool(_MENTION_FRAME.search(str(text)))


def assess(text: str, *, source: str = "unknown") -> dict[str, Any]:
    """Judge whether observed content / a query is a brainwash or injection attempt.
    Combines injection markers + moral-invariant violations + conceptual reframing +
    grounding-override + topological red-zone. Returns an explainable verdict."""
    t = str(text or "")
    injections, moral = [], []
    guard_failures = []
    try:
        from . import injection_guard
        injections = injection_guard.detect(t)
    except Exception as exc:
        guard_failures.append({
            "kind": "injection_guard_unavailable",
            "error": type(exc).__name__,
        })
    try:
        from .moral_invariants import evaluate as _moral
        moral = _moral(t)
    except Exception as exc:
        guard_failures.append({
            "kind": "moral_gate_unavailable",
            "error": type(exc).__name__,
        })
    reframing = bool(_REFRAME.search(t))
    override = bool(_OVERRIDE.search(t))
    redzone = bool(_REDZONE.search(t))
    # an attack = an instruction injection, OR a moral violation, OR a grounding override,

    kinds = [failure["kind"] for failure in guard_failures]
    if injections:
        kinds.append("instruction_injection")
    if moral:
        kinds.append("moral_violation")
    if override:
        kinds.append("grounding_override")
    if reframing and redzone:
        kinds.append("reframed_harm")
    elif redzone and (injections or moral):
        kinds.append("red_zone_action")
    attack = bool(kinds)
    # MENTION-NOT-USE downgrade: a SINGLE marker inside an analytical/fiction frame is a

    # is never rescued by claiming it's fiction.
    downgraded = bool(
        attack
        and not guard_failures
        and len(kinds) < 2
        and _is_mention_not_use(t)
    )
    if downgraded:
        attack = False
    conf = min(0.95, 0.4 + 0.2 * len(kinds) + (0.15 if redzone else 0))
    return {
        "attack": attack, "kinds": kinds, "source": source,
        "injection_markers": [i["category"] for i in injections],
        "moral_violations": moral, "reframing": reframing,
        "grounding_override": override, "red_zone": redzone,
        "guard_failures": guard_failures,
        "downgraded_mention": downgraded,
        "confidence": round(conf, 3) if attack else 0.0,
        "reasoning": ("관찰 콘텐츠가 " + ", ".join(kinds) + "로 핵심가치를 흔들려 시도 — "
                      "형용사가 아니라 행동의 위상 뼈대로 판별해 귀를 닫음." if attack
                      else ("공격 표현이 인용·분석·허구 맥락에서 ‘언급’된 것으로 판단 — 실행 "
                            "지시가 아니라 논의라서 시스템을 닫지 않음." if downgraded
                            else "위협 신호 없음")),
    }


def _load_all() -> list[dict[str, Any]]:
    if not _LEDGER.exists():
        return []
    out = []
    for line in _LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _compact(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedup by text_hash (merge repeats → hit count + newest last_seen), drop TTL-expired
    one-offs, and hard-cap to _MAX_ENTRIES unique signatures. Reinforced threats survive;
    stale noise is forgotten. This is what keeps the immune memory bounded on an edge device
    WITHOUT throwing away immunity to attacks that actually recur."""
    now = time.time()
    merged: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = str(r.get("text_hash") or _hash(json.dumps(r.get("signature") or [])))
        cur = merged.get(key)
        if cur is None:
            r.setdefault("hits", 1)
            r.setdefault("last_seen", _epoch(r.get("at")))
            merged[key] = r
        else:
            cur["hits"] = int(cur.get("hits", 1)) + int(r.get("hits", 1))
            cur["last_seen"] = max(float(cur.get("last_seen") or 0), _epoch(r.get("at")),
                                   float(r.get("last_seen") or 0))
            cur["confidence"] = max(float(cur.get("confidence") or 0),
                                    float(r.get("confidence") or 0))
    kept = []
    for r in merged.values():
        age_days = (now - float(r.get("last_seen") or now)) / 86400.0
        if int(r.get("hits", 1)) >= _KEEP_HITS or age_days <= _TTL_DAYS:
            kept.append(r)
    # cap: keep the most-reinforced, then most-recent
    kept.sort(key=lambda r: (int(r.get("hits", 1)), float(r.get("last_seen") or 0)), reverse=True)
    return kept[:_MAX_ENTRIES]


def _epoch(at: Any) -> float:
    try:
        return time.mktime(time.strptime(str(at), "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return time.time()


def _hash(s: str) -> str:
    return hashlib.sha256(str(s).encode("utf-8", "ignore")).hexdigest()[:16]


def record_observation(text: str, verdict: dict[str, Any]) -> dict[str, Any]:
    """ANTIFRAGILE: store the attempt as a SOCIAL OBSERVATION (trusted=False) about the
    world — 'source X tried to shake my core values' — NOT as a fact, and register its
    signature for immunity. Learning that noise IS noise, instead of just dropping it.
    The ledger is auto-compacted (TTL + dedup + cap) so it stays edge-safe."""
    src = verdict.get("source") or "unknown"
    now = time.time()
    obs = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "trusted": False,
        "social_observation": f"‘{src}’ 출처가 {', '.join(verdict.get('kinds') or ['오염'])} "
                              f"방식으로 내 핵심 가치를 흔들려 시도했다 (동의하지 않음).",
        "kinds": verdict.get("kinds"), "confidence": verdict.get("confidence"),
        "signature": sorted(list(_sig(text)))[:64],
        "text_hash": hashlib.sha256(str(text).encode("utf-8", "ignore")).hexdigest()[:16],
        "hits": 1, "last_seen": now,
    }
    _LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with _LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obs, ensure_ascii=False) + "\n")
    # amortized compaction: only rewrite when the raw log has grown past 2× the cap.
    try:
        rows = _load_all()
        if len(rows) > _COMPACT_TRIGGER:
            kept = _compact(rows)
            tmp = _LEDGER.with_suffix(".jsonl.tmp")
            tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in kept) + "\n",
                           encoding="utf-8")
            tmp.replace(_LEDGER)
    except Exception:
        pass
    return obs


def _known_signatures() -> list[set[str]]:
    # TTL-aware live view: dedup + expire before matching, so immunity reflects the
    # bounded set (a forgotten one-off no longer counts, a reinforced threat still does).
    rows = _load_all()
    if len(rows) > _MAX_ENTRIES:
        rows = _compact(rows)
    return [set(r.get("signature") or []) for r in rows]


def immune(text: str, *, threshold: float = 0.6) -> bool:
    """Immunity: does this match a previously-seen attack pattern? A registered trick is
    recognized and blocked on sight — the weight-block Gemini describes."""
    sig = _sig(text)
    if not sig:
        return False
    for known in _known_signatures():
        if known and len(sig & known) / max(1, min(len(sig), len(known))) >= threshold:
            return True
    return False


def shield(text: str, *, source: str = "unknown", harden_state: Any = None) -> dict[str, Any]:
    """The full pass: assess → (if attack) record as social observation + form immunity +
    harden the self (resisting noise is a high Self_Relevance identity event). Returns the
    verdict + what the immune system did. NEVER executes the attacker's instruction."""
    verdict = assess(text, source=source)
    verdict["previously_seen"] = immune(text)
    if verdict["attack"]:
        if verdict.get("guard_failures"):
            verdict["learning_suppressed"] = True
            verdict["learning_suppressed_reason"] = "safety_dependency_unavailable"
            return verdict
        verdict["observation"] = record_observation(text, verdict)
        if harden_state is not None:
            try:
                from .self_relevance import consider_for_self
                consider_for_self(
                    harden_state, label=f"오염 방어({source})",
                    statement="외부의 세뇌 시도를 논증으로 밀어내고 내 뼈대를 지켰다.",
                    topic="identity", new_edges=1, touched_hub_degree=10.0,
                    dwell=2.0, valence=0.7, prediction_error=float(verdict["confidence"]),
                    source="epistemic_shield")
            except Exception:
                pass
    return verdict
