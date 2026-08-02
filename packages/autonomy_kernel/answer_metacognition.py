# -*- coding: utf-8 -*-
"""Answer metacognition — the self watching its OWN output (Vision #3 deepening + #2 live).

Owner (2026-07-10): metacognition is more than tracking goal metrics — it is the self noticing,
in the moment, when its OWN answer does not fit the question, and saying so. This makes the
compositional SemanticFrame (#2) LIVE: every answer is checked against the frame of the question
it answered. When the answer's SHAPE contradicts the question's ACT (e.g., a correction answered
with a dictionary definition), the self flags it — an honest 'I don't think I answered that'.

Deliberately ADVISORY and non-destructive: it attaches a self-note + logs the mismatch for the
flywheel/goals to learn from. It does NOT rewrite the answer here (that is a separate, gated
change) — this is the self KNOWING, which must come before the self correcting. High precision
over recall: only clear act/shape contradictions are flagged, so the signal stays trustworthy.
"""
from __future__ import annotations

import re
from typing import Any


# wrong for a correction / greeting / affect / opinion, which want engagement, not a glossary.
_DEFINITIONAL = re.compile(r"(이란\s|란\s.{0,4}(말|것)|(이다|입니다|이에요|예요)\s*\.?\s*$"
                           r"|의\s*한\s*종류|를?\s*가리키는|를?\s*뜻하|에\s*대해\s*확인된\s*것)")

# act, and often carries a josa-garbage subject; a clear miss the self should catch.
_DEFLECTION = re.compile(r"지금\s*실시간\s*웹으로\s*교차\s*확인|은\(는\)\s*지금\s*실시간")
_NON_QUERY_ACTS = {"correction", "greeting", "affect", "opinion"}


def reflect(question: str, answer: str, certificate: dict[str, Any] | None = None) -> dict[str, Any]:
    """Judge the answer against the question's compositional frame. Returns a self-critique:
    {act, ok, issues, self_note}. High-precision — only clear shape/act contradictions flag."""
    ans = str(answer or "").strip()
    try:
        from packages.graph_scale.semantic_frame import encode
        f = encode(question)
    except Exception:
        return {"ok": True, "issues": [], "self_note": ""}
    dk = str((certificate or {}).get("derivation_kind") or "")
    issues: list[str] = []

    # (1) act/shape contradiction: a conversational act answered with a definition dump.
    if f.act in _NON_QUERY_ACTS and _DEFINITIONAL.search(ans):
        issues.append(f"‘{f.act}’ 발화인데 사전식 정의로 답한 것 같아요")

    # (1b) a conversational act answered with a bare dead-end deflection (josa-garbage subject).
    if (f.act in _NON_QUERY_ACTS or f.self_directed) and _DEFLECTION.search(ans):
        issues.append(f"‘{f.act}’ 발화인데 알맹이 없이 웹으로 미룬 것 같아요")

    # (2) a NEGATED / correction utterance answered as if it were a fresh factual lookup.
    if f.act == "correction" and dk in (
            "grounded_neighborhood_synthesis", "ontology_graph_derivation", "engaged_fact_inference"):
        issues.append("정정하시는 말씀인데 새 질문처럼 답한 것 같아요")

    # (3) confidence honesty: a high-confidence claim on a shape the router was unsure about.
    conf = float((certificate or {}).get("confidence", 0) or 0)
    if conf >= 0.8 and f.confidence and f.confidence < 0.35:
        issues.append("확신에 비해 제 이해가 흐릿했어요")

    # (4) SUBJECT-ERROR, caught INDEPENDENTLY (Vision jan-yeo #2): the frame and the answer path

    # can't catch it. Two independent signals do: a superlative-RANKING question answered with a
    # DEFINITION (a ranking is not a definition), or an answer that DEFINES a scope/generic word.
    _superlative_rank = re.search(r"(제일|가장|최고|최대|최소|최장|최단|가장\s*(큰|긴|높|많))", str(question or "")) \
        and re.search(r"(뭐|무엇|어디|누구|어느)", str(question or ""))
    if _superlative_rank and _DEFINITIONAL.search(ans):
        issues.append("‘가장/제일 …’ 순위를 묻는데 정의로 답한 것 같아요 (엉뚱한 대상을 잡았을 수 있어요)")
    if re.search(r"(‘|')?(세계|세상|전세계|제일|가장|최고)(’|')?(은|는|이|가)?\s*(에\s*대해|는|은|이란|란)", ans[:20]):
        issues.append("범위를 나타내는 말(세계·제일 등)을 대상으로 잡아 정의한 것 같아요")

    ok = not issues
    return {"act": f.act, "type": f.type, "ok": ok, "issues": issues,
            "self_note": ("스스로 보기에 질문에 맞게 답했어요." if ok
                          else "스스로 점검하니 — " + " / ".join(issues) + ". 다시 여쭤주시면 바로잡을게요.")}


# safe substitutes for the CLEAR conversational-act mismatches — used only when the self has
# flagged its own answer as wrong-shaped. High precision: only these few acts, and only replacing
# a definition/deflection answer. Never overrides a grounded factual answer.
_SUBSTITUTE = {
    "correction": "아, 제가 잘못 짚었네요. 어떤 걸 여쭤보신 건지 한 번만 더, 조금 더 구체적으로 말씀해 주시겠어요?",
    "greeting":   "안녕하세요! 무엇이든 편하게 물어보세요.",
    "affect":     "혹시 제 답이 서운하거나 불편하셨다면 미안해요. 어떤 점이 그러셨는지 말씀해 주시면 제대로 헤아려서 답할게요.",
    "opinion":    "이건 정답이 하나가 아니라 관점에 따라 갈리는 물음이에요. 저는 근거 없이 단정하진 않을게요 — 당신은 어느 쪽에 마음이 기우세요?",
}


def suggest_correction(question: str, answer: str, certificate: dict[str, Any] | None) -> str | None:
    """When the self has flagged a CLEAR conversational-act mismatch AND the current answer is a
    definition/deflection (not a grounded fact), return a better-fitting response. Else None —
    silence over meddling. This is the self CORRECTING, gated to only the unambiguous cases."""
    r = reflect(question, answer, certificate)
    if r.get("ok", True):
        return None
    act = r.get("act")
    dk = str((certificate or {}).get("derivation_kind") or "")
    # never touch a grounded factual answer; only replace definition/deflection/abstain shapes
    safe_to_replace = (_DEFINITIONAL.search(str(answer or "")) or _DEFLECTION.search(str(answer or ""))
                       or dk in ("grounded_neighborhood_synthesis", "ontology_graph_derivation",
                                 "engaged_fact_inference", "abstained"))
    if act in _SUBSTITUTE and safe_to_replace:
        return _SUBSTITUTE[act]
    # SUBJECT-ERROR / superlative-ranking: the answer defined a scope word or answered a ranking
    # with a definition — replace with an HONEST 'I can't rank this from the graph' (no fabrication).
    issues = " ".join(r.get("issues") or [])
    if ("순위" in issues or "범위를 나타내는" in issues) and safe_to_replace:
        return ("그건 '가장/제일'을 가리는 순위 질문인데, 지금 로컬 그래프에는 그 순위를 딱 잘라줄 "
                "근거가 없어요 — 엉뚱한 걸 정의하느니 솔직히 말씀드릴게요. 웹 검색을 켜 주시면 정확한 "
                "값을 찾아 알려드릴게요.")
    return None


def note_for_certificate(question: str, answer: str, certificate: dict[str, Any] | None) -> dict[str, Any]:
    """A compact self-reflection to attach to the reasoning certificate (transparency) and,
    when it flags an issue, to log for the flywheel/goals. Never raises."""
    try:
        r = reflect(question, answer, certificate)
        out = {"self_reflection": {"answered_well": r["ok"], "issues": r["issues"],
                                   "note": r["self_note"], "read_act": r.get("act")}}
        # frame's compositional read attached for transparency + downstream fact routing (#3).
        try:
            from packages.graph_scale.semantic_frame import encode
            f = encode(question)
            out["self_reflection"]["read_type"] = f.type
            out["self_reflection"]["polarity"] = f.polarity
        except Exception:
            pass
        return out
    except Exception:
        return {}
