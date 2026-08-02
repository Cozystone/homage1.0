# -*- coding: utf-8 -*-
"""Intent EXECUTION — the layer that was missing: turn an inferred (subject, intent) into
a TARGETED answer by traversing the graph for the RIGHT relation, instead of dumping a
definition.

Owner (2026-07-09): " ." Exactly — the
inference (intent_inference) cleanly identifies WHAT is asked, but the legacy answer
cascade ignored it and returned generic facts. This module is the bridge: intent →
graph strategy → grounded answer. It runs BEFORE the generic engagement, and returns
None (fall through) when the graph can't fulfill the intent — never fabricates.

Flagship = VERIFICATION reasoning: " ?" is not a definition lookup; it's an
is_a traversal — walk 's type chain, and if isn't on it while has a
conflicting type, answer ", " WITH the reasoning
path. Honest: only what the is_a edges actually say.
"""
from __future__ import annotations

import re
from typing import Any


def _facts(store: Any, term: str, limit: int = 20) -> list[tuple[str, str, str]]:
    try:
        return [(str(s), str(p), str(o)) for s, p, o in (store.facts_about(term, limit=limit) or [])]
    except Exception:
        return []


def _isa_parents(store: Any, term: str) -> list[str]:
    return [o for _s, p, o in _facts(store, term) if p == "is_a" and o and o != term]


def _isa_chain(store: Any, term: str, depth: int = 5) -> list[str]:
    """BFS up the is_a hierarchy — the transitive type chain of `term`."""
    seen: set[str] = set()
    frontier = [term]
    chain: list[str] = []
    for _ in range(depth):
        nxt: list[str] = []
        for t in frontier:
            for parent in _isa_parents(store, t):
                if parent not in seen:
                    seen.add(parent)
                    chain.append(parent)
                    nxt.append(parent)
        frontier = nxt
        if not frontier:
            break
    return chain


def _eun(w: str) -> str:
    w = re.sub(r"[)\]\"'\s]+$", "", str(w or ""))
    if not w or not ("가" <= w[-1] <= "힣"):
        return f"{w}은"
    return f"{w}은" if (ord(w[-1]) - 0xAC00) % 28 != 0 else f"{w}는"


def _ga(w: str) -> str:
    if not w or not ("가" <= w[-1] <= "힣"):
        return f"{w}가"
    return f"{w}이" if (ord(w[-1]) - 0xAC00) % 28 != 0 else f"{w}가"


def _ieyo(w: str) -> str:
    w = re.sub(r"[)\]\"'\s]+$", "", str(w or ""))
    if not w or not ("가" <= w[-1] <= "힣"):
        return "이에요"
    return "이에요" if (ord(w[-1]) - 0xAC00) % 28 != 0 else "예요"


def _cert(kind: str, subject: str, steps: list[str], conf: float) -> dict[str, Any]:
    return {
        "derivation_kind": kind,
        "anchor_concept": {"label": subject},
        "steps": [{"type": "isa_reasoning", "fact": s} for s in steps],
        "evidence_concepts": [subject],
        "confidence": conf,
        "confidence_basis": "graph is_a traversal — grounded, no fabrication",
        "guarantees": {"external_llm": False, "fabricated_facts": False, "reasoned": True},
    }


# Common English taxonomy roots → Korean, so a corroborated direct parent ("Animal") can be
# voiced/matched in Korean without reaching for a deep noise hop. LAD surface mapping only.
_ROOT_KO = {
    "animal": "동물", "plant": "식물", "person": "사람", "human": "사람", "food": "음식",
    "fruit": "과일", "vegetable": "채소", "organization": "조직", "company": "회사",
    "place": "장소", "location": "장소", "country": "국가", "city": "도시", "language": "언어",
    "color": "색", "vehicle": "탈것", "building": "건물", "tool": "도구", "material": "물질",
    "chemical": "화학물질", "mammal": "포유류", "bird": "새", "fish": "물고기", "insect": "곤충",
    "device": "장치", "software": "소프트웨어", "sport": "스포츠", "disease": "질병",
}



# taxon/entity artifact, not the type a person means. Treated as low-trust → hedge instead.
_META_TYPES = {"species", "taxon", "entity", "thing", "object", "concept", "class",
               "instance", "item", "종", "분류군", "개체", "존재", "사물", "대상"}


def _ko_type(t: str) -> str:
    return _ROOT_KO.get(str(t or "").strip().lower(), str(t or "").strip())


def _is_meta_type(t: str) -> bool:
    s = str(t or "").strip()
    return (s.lower() in _META_TYPES or _ko_type(s).lower() in _META_TYPES
            or bool(re.match(r"^q\d+$", s, re.IGNORECASE)))  # bare Wikidata Q-id


def _type_matches(target: str, node: str) -> bool:
    """Does `node` (a type on the chain) denote the `target` the user named? Compares against
 the node AND its Korean mapping so '' matches an English 'Animal' node (and vice versa)."""
    t = str(target or "").strip().lower()
    if not t:
        return False
    n = str(node or "").strip().lower()
    nk = _ko_type(node).lower()
    return t in n or n in t or t == n or t in nk or nk in t or t == nk


def _best_type(store: Any, subject: str) -> tuple[str, bool]:
    """TRUST GATE (owner 2026-07-10, ): pick a TRUSTWORTHY type to voice, not the first
 Korean node in a flattened chain (which grabbed the '→(Animal→)' noise). A DIRECT
 is_a parent beats a deep transitive hop; among direct parents the most CORROBORATED one
 (highest frequency) wins — a lone noise edge loses to a parent asserted twice. Returns
 (korean_type, trusted); trusted=False means we found no confident type → the caller must
 HEDGE rather than assert noise."""
    from collections import Counter
    direct = _isa_parents(store, subject)
    if direct:
        for cand, _freq in Counter(direct).most_common():
            if _is_meta_type(cand):
                continue              # skip Species/Taxon/Q-id — true but a non-answer
            return _ko_type(cand), True   # a direct, non-meta parent is grounded and trusted
    return "", False                  # no useful type → hedge, don't assert noise/meta


def _verify(store: Any, subject: str, target: str) -> dict[str, Any] | None:
    """Is `subject` a kind of `target`? Answer by is_a traversal, with the reasoning path —
    but only ASSERT when the type is trusted (direct + corroborated), else stay silent so the
    engage/web path hedges instead of voicing a noise edge as a confident fact."""
    chain = _isa_chain(store, subject)
    top_type, trusted = _best_type(store, subject)
    # YES: target is on the type chain (direct or transitive) — match KO-mapped nodes too, so

    matched = next((c for c in chain if _type_matches(target, c)), "")
    if matched:
        upto = chain[:chain.index(matched) + 1]
        voiced = [_ko_type(c) for c in upto if re.search(r"[가-힣A-Za-z]", c)][:3]
        path = " → ".join([subject] + voiced)
        ans = f"네, {_eun(subject)} {target}의 한 종류가 맞아요. ({path})"
        return {"answer": ans, "answer_kind": "verified_isa",
                "reasoning_certificate": _cert("verification_isa_positive", subject,
                                               [f"{subject} is_a … {target}"], 0.7),
                "confidence": 0.7, "grounded": True}
    # NO branch: assert the contrast ONLY with a trusted type. Without one, return None — a

    if not trusted or not top_type or _type_matches(target, top_type):
        return None
    ans = (f"아니요, {_eun(subject)} {_ga(target)} 아니라 {top_type}의 한 종류예요. "
           f"(확인된 분류: {subject} → {top_type})")
    return {"answer": ans, "answer_kind": "verified_isa",
            "reasoning_certificate": _cert("verification_isa_negative", subject,
                                           [f"{subject} is_a {top_type}", f"{target} ∉ chain({subject})"], 0.6),
            "confidence": 0.6, "grounded": True}


def _identity(store: Any, subject: str) -> dict[str, Any] | None:
    """WHO — assemble the person's defining facts (type/role) grounded, not a definition."""
    fs = _facts(store, subject)
    role = next((o for _s, p, o in fs if p in ("is_a", "occupation", "직업") and o), "")
    defn = next((o for _s, p, o in fs if p == "defined_as" and o), "")
    body = defn or (f"{role}의 한 사람" if role else "")
    if not body:
        return None
    return {"answer": f"{_eun(subject)} {body}" + ("" if body.endswith(("다", "요", ".")) else "이에요."),
            "answer_kind": "identity_grounded",
            "reasoning_certificate": _cert("identity_grounded", subject, [f"{subject} → {body}"], 0.6),
            "confidence": 0.6, "grounded": True}


def _location(store: Any, subject: str) -> dict[str, Any] | None:
    fs = _facts(store, subject)
    loc = next((o for _s, p, o in fs if p in ("located_in", "소재지", "위치", "국가") and o), "")
    if not loc:
        return None
    return {"answer": f"{_eun(subject)} {loc}에 있어요.", "answer_kind": "location_grounded",
            "reasoning_certificate": _cert("location_grounded", subject, [f"{subject} located_in {loc}"], 0.65),
            "confidence": 0.65, "grounded": True}


# measure/attribute predicates whose VALUE answers a "how much/how many" question.
_QTY_PREDS = ("인구", "면적", "높이", "길이", "거리", "무게", "넓이", "깊이", "속도", "온도",
              "가격", "인구수", "population", "area", "height", "length", "distance")


def _quantity(store: Any, subject: str, inf: dict[str, Any]) -> dict[str, Any] | None:
    """" ?" — fetch the SPECIFIC measured relation the question asks about
 (the non-subject attribute noun), not a definition. Grounded, else None (→ web)."""
    fs = _facts(store, subject)
    attrs = [e for e in (inf.get("entities") or []) if e != subject and len(e) >= 2]

    for a in attrs + list(_QTY_PREDS):
        for _s, p, o in fs:
            if o and (a == p or a in p or p in a) and re.search(r"[0-9]", o):
                return {"answer": f"{subject}의 {_eun(p)} {o}{_ieyo(o)}.",
                        "answer_kind": "quantity_grounded",
                        "reasoning_certificate": _cert("quantity_grounded", subject, [f"{subject} {p} {o}"], 0.68),
                        "confidence": 0.68, "grounded": True}
    return None


def _cause(store: Any, subject: str) -> dict[str, Any] | None:
    """" X?" — traverse cause/because edges. Grounded when the graph holds a cause,
 else None (the engagement's intent-aware cue offers the web)."""
    fs = _facts(store, subject)
    cause = next((o for _s, p, o in fs
                  if p in ("원인", "cause", "because", "due_to", "때문", "caused_by", "이유") and o), "")
    if not cause:
        return None
    return {"answer": f"{_eun(subject)} {cause} 때문이에요.", "answer_kind": "cause_grounded",
            "reasoning_certificate": _cert("cause_grounded", subject, [f"{subject} cause {cause}"], 0.6),
            "confidence": 0.6, "grounded": True}


def _key_facts(store: Any, term: str, n: int = 2, prefer_type: str = "") -> list[str]:
    """A couple of the most informative grounded facts about `term` for a contrast —
 deduped. `prefer_type` biases toward the sense sharing the other entity's type
 ( vs : prefer the sense over the sense)."""
    out: list[str] = []
    seen: set[str] = set()
    rows = _facts(store, term)
    if prefer_type:
        rows.sort(key=lambda r: 0 if (r[1] == "is_a" and prefer_type and prefer_type in str(r[2])) else 1)
    for _s, p, o in rows:
        o = str(o or "")
        if p in ("alias", "sense") or not o or len(o) > 50:
            continue
        frag = f"{o}의 한 종류" if p == "is_a" else (o if p == "defined_as"
                else (f"{p} {o}" if (re.search(r"[0-9]", o) or p in _QTY_PREDS) else ""))
        if not frag or frag in seen:
            continue
        seen.add(frag)
        out.append(frag)
        if len(out) >= n:
            break
    return out



# better overall". These map to a measurable predicate; without grounded numbers for BOTH
# sides the honest answer is a hedge, NEVER a dump of the two definitions.
_ATTR_WORDS = ("큰", "커", "크", "작", "무겁", "무거", "가벼", "긴", "길", "짧", "빠르", "빨",
               "느리", "높", "낮", "넓", "좁", "달", "매", "비싸", "싼", "센", "강", "많", "적")
_ATTR_PREDS = {"커": ("크기", "면적", "높이", "길이", "size", "area", "height", "length"),
               "큰": ("크기", "면적", "높이", "길이", "size", "area"),
               "무거": ("무게", "질량", "weight", "mass"), "무겁": ("무게", "질량", "weight"),
               "길": ("길이", "length", "거리"), "긴": ("길이", "length", "거리"),
               "빠르": ("속도", "speed"), "빨": ("속도", "speed"),
               "높": ("높이", "고도", "height"), "많": ("인구", "개수", "수", "population"),
               "비싸": ("가격", "price"), "달": ("당도", "sweetness")}


def _is_attr_compare(query: str) -> str:
    m = re.search(r"더\s*(" + "|".join(_ATTR_WORDS) + r")", str(query or ""))
    return m.group(1) if m else ""


def _num(o: str) -> float | None:
    m = re.search(r"[-+]?\d[\d,\.]*", str(o or "").replace(",", ""))
    try:
        return float(m.group(0)) if m else None
    except Exception:
        return None


def _compare(store: Any, a: str, b: str, query: str = "") -> dict[str, Any] | None:
    """"A B /?" — GROUNDED contrast. A " <attribute>" question is answered
 ONLY from grounded numbers for that attribute on both sides; if they aren't in the graph we
 hedge (return None → web), never dumping the two definitions (which trailed wrong senses —
 =, =). A plain " /" still gets the honest fact contrast."""
    attr = _is_attr_compare(query)
    if attr:
        preds = _ATTR_PREDS.get(attr, ())
        fa = _facts(store, a)
        fb = _facts(store, b)
        va = next((o for _s, p, o in fa if any(k in p for k in preds) and _num(o) is not None), "")
        vb = next((o for _s, p, o in fb if any(k in p for k in preds) and _num(o) is not None), "")
        if va and vb and _num(va) is not None and _num(vb) is not None:
            bigger = a if _num(va) >= _num(vb) else b
            ans = (f"{_eun(a)} {va}, {_eun(b)} {vb}라서, {bigger}가 더 {attr}요. "
                   f"(확인된 수치로 비교)")
            return {"answer": ans, "answer_kind": "compare_attribute_grounded",
                    "reasoning_certificate": _cert("compare_attribute_grounded", f"{a}|{b}",
                                                   [f"{a}={va}", f"{b}={vb}"], 0.7),
                    "confidence": 0.7, "grounded": True}
        return None  # attribute not grounded for both → honest hedge, never a definition dump

    a_types = [o for _s, p, o in _facts(store, a) if p == "is_a"]
    b_types = [o for _s, p, o in _facts(store, b) if p == "is_a"]
    shared = bool(set(a_types) & set(b_types))
    npf = 1 if shared else 2
    fa = _key_facts(store, a, n=npf, prefer_type=(b_types[0] if b_types else ""))
    fb = _key_facts(store, b, n=npf, prefer_type=(a_types[0] if a_types else ""))
    if not fa or not fb:
        return None
    fa_s, fb_s = ", ".join(fa), ", ".join(fb)
    ans = (f"{_eun(a)} {fa_s}이고, {_eun(b)} {fb_s}{_ieyo(fb_s)}. "
           f"어느 쪽이 나은지는 무엇을 중요하게 보시느냐에 달려 있어요 — 원하시면 기준을 정해 비교해 드릴게요.")
    return {"answer": ans, "answer_kind": "compare_grounded",
            "reasoning_certificate": _cert("compare_grounded", f"{a}|{b}",
                                           [f"{a}: {fa}", f"{b}: {fb}"], 0.6),
            "confidence": 0.6, "grounded": True}


def execute(query: str, inf: dict[str, Any], store: Any) -> dict[str, Any] | None:
    """Dispatch the inferred intent to a graph strategy. Returns a grounded answer or
    None (fall through to the generic engagement). Never fabricates."""
    if store is None:
        return None
    subject = str(inf.get("subject") or "")
    intent = str(inf.get("intent") or "")
    if not subject:
        return None
    try:
        if intent == "verify" and inf.get("verify_target"):
            return _verify(store, subject, str(inf["verify_target"]))
        if intent == "identity":
            return _identity(store, subject)
        if intent == "location":
            return _location(store, subject)
        if intent in ("quantity", "safe_quantity"):
            return _quantity(store, subject, inf)
        if intent == "cause":
            return _cause(store, subject)
        if intent == "compare":
            tg = inf.get("compare_targets") or []
            if len(tg) >= 2:
                return _compare(store, tg[0], tg[1], query)
    except Exception:
        return None
    return None
