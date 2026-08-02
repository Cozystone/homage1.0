"""Grounded-Constrained Generation (GCG) — the fusion of a grounded SKELETON and a
generative FLESH, without hallucination.

The user's picture: a No-LLM engine answers definition/fact/compare well but must
ABSTAIN on open-ended / advice / multi-aspect questions, because grounded retrieval
alone cannot COMPOSE a flowing answer. The fix is not to bolt on an LLM (that
reintroduces fabrication) but to fuse two layers we already have:

 BONES (content) — verbatim grounded fact clauses from the pack/graph. Facts are
 NEVER recombined at the token level (that is where hallucination
 lives); each factual clause is emitted whole, exactly as sourced.
 FLESH (surface) — a probabilistic word-transition model (Markov over a discourse
 corpus) GENERATES the connective tissue: openers, transitions,
 framing, and the closing synthesis. This is the " 
 " the user asked for — but confined to discourse scaffolding.

So the answer READS like a composed essay (generated flow) while every fact in it is
traceable to a grounded source. The hallucination guard is structural: the generator
can only ever produce connectives from its discourse lexicon; it can never introduce a
new entity or assert a new relation, because content lives only in the verbatim bones.

Honesty contract: if too few grounded facts back the question, `synthesize` returns
None (the caller abstains) — a thin skeleton gets no flesh. Nothing here calls an
external LLM/sLLM or invents a fact. Every generation decision is deterministic given
the query (seeded), so it is reproducible and auditable.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

# ── discourse: LEARNED, never templated ───────────────────────────────────────────
# The hand-authored opener / bridge / closer / hedge templates were DELETED (owner 2026-07-15:

# comes ONLY from the learned realizer (connectives mined from real prose). When it cannot fuse,
# the answer degrades HONESTLY to the verbatim verified clauses — no faked flow, no scaffolding.

# Speculative/opinion cues → recorded in the certificate so a caller can frame it; no template hedge.
_SPECULATIVE = re.compile(
    r"미래|앞으로|될까|전망|예측|어떻게\s*될|would|will\s+.*be|future|predict|forecast", re.IGNORECASE
)
_HANGUL = re.compile(r"[가-힣]")


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)


def _sentence_case_ok(fact: str) -> str:
    """A grounded clause is emitted whole; just ensure it ends with terminal punctuation
    so the woven essay reads cleanly. Never edits the CONTENT."""
    f = fact.strip()
    if not f:
        return f
    if f[-1] not in ".!?。…":
        f += "." if not _HANGUL.search(f) else "다." if not f.endswith(("다", "요", "음")) else "."
    return f




def synthesize(
    query: str,
    grounded_facts: list[dict[str, Any]],
    language: str = "ko",
    *,
    min_facts: int = 2,
    max_facts: int = 5,
    include_opener: bool = True,
) -> dict[str, Any] | None:
    """Weave grounded fact clauses (BONES) with generated discourse (FLESH) into a
    composed answer. `grounded_facts` = [{name, description, ...}] already retrieved
    and relevance-checked by the caller. Returns {answer, facts_used, generated_spans,
    reasoning_certificate} or None when the skeleton is too thin to support flesh.

    Anti-hallucination: content sentences are the verbatim `description`s; only the
    opener/bridges/closer are generated, and only from the discourse lexicon."""
    facts = [f for f in grounded_facts if str(f.get("description") or "").strip()]
    # de-dup by description; keep the most substantial, cap the count.
    seen: set[str] = set()
    picked: list[dict[str, Any]] = []
    for f in facts:
        d = re.sub(r"\s+", " ", str(f["description"]).strip())
        key = d[:40]
        if key in seen or len(d) < 15:
            continue
        seen.add(key)
        picked.append({**f, "description": d})
        if len(picked) >= max_facts:
            break
    if len(picked) < min_facts:
        return None  # thin skeleton → abstain (honesty contract)

    ko = language != "en"
    seed = _seed(query)
    speculative = bool(_SPECULATIVE.search(query))

    generated_spans: list[str] = []
    parts: list[str] = []
    # NO template opener — the hand-authored openers were deleted. `include_opener` is kept for API
    # compat but no longer prepends scaffolding; an opener, if ever, must be LEARNED, else there is none.


    # ≥2 grounded clauses share a topic, FUSE them into one flowing sentence using discourse grammar


    # fact → falls back to the template path. No LLM, no sLLM, no hand template.
    fused_body = ""
    if ko and len(picked) >= 2:
        try:
            from .learned_realizer import realize_fused, grounding_ok
            _names = [str(f.get("name") or "").strip() for f in picked]
            topic = max((x for x in set(_names) if x), key=_names.count, default="")

            # → multi-subject fusion (keep each subject, no topic prefix, no doubling). Otherwise the

            self_subjected = sum(
                1 for f in picked
                if str(f.get("name") or "") and str(f["description"]).strip().startswith(str(f["name"]))
            ) >= max(2, len(picked) - 1)
            _clauses = []
            for f in picked:
                d = str(f["description"]).strip()                 # RAW (fusion does its own endings)
                if (not self_subjected) and topic and d.startswith(topic):
                    # strip a leading topic ONLY at a word boundary (josa+space or space) — never

                    d = re.sub(rf"^{re.escape(topic)}(?:[은는이가]\s+|\s+)", "", d)
                _clauses.append(d)
            if topic or self_subjected:
                cand = realize_fused(topic, _clauses, seed=seed, prepend_topic=not self_subjected)
                if cand and grounding_ok(cand, _clauses):        # grounding HARD GATE
                    fused_body = cand                            # recorded via discourse_mode below
        except Exception:
            fused_body = ""                                      # any failure → verbatim fallback

    # ENGLISH learned realizer: the analytic-language twin — fuse the verbatim clauses into ONE
    # sentence with clause connectives (grounding-safe), replacing 'A. B. C.' enumeration.
    if (not ko) and not fused_body and len(picked) >= 2:
        try:
            from .learned_realizer import realize_fused_en, grounding_ok_en
            _clauses = [str(f["description"]).strip() for f in picked]
            cand = realize_fused_en("", _clauses, seed=seed)
            if cand and grounding_ok_en(cand, _clauses):        # grounding HARD GATE (EN)
                fused_body = cand
        except Exception:
            fused_body = ""

    if fused_body:
        parts.append(fused_body)
    else:
        # HONEST DEGRADATION (no templates): the learned realizer could not fuse these clauses, so we
        # present the VERIFIED facts plainly — verbatim description, with the name topic-marked (josa
        # is LAD surface, not a template) — and NOTHING generated. No bridges, no closer. This reads
        # rough/list-like on purpose: it shows the flesh is missing rather than faking it (owner).
        for f in picked:
            name = str(f.get("name") or "").strip()
            clause = _sentence_case_ok(str(f["description"]))
            if name and not clause.lower().startswith(name.lower()):
                topic = _topic_marker(name) if ko else name
                body = f"{topic} {clause}" if ko else f"{name}: {clause}"
            else:
                body = clause
            parts.append(body)

    answer = " ".join(p.strip() for p in parts if p.strip())
    return {
        "answer": answer,
        "facts_used": [{"name": f.get("name"), "description": f["description"]} for f in picked],
        "generated_spans": generated_spans,
        "reasoning_certificate": {
            "derivation_kind": "grounded_constrained_generation",
            "discourse_mode": "learned_fusion" if fused_body else "verbatim_no_flesh",
            "anchor_concept": None,
            "steps": [{"type": "grounded_clause", "fact": f["description"][:120]} for f in picked],
            "evidence_concepts": [f.get("name") for f in picked if f.get("name")],
            "confidence": round(min(0.72, 0.4 + 0.08 * len(picked)), 2),
            "confidence_basis": "verbatim_grounded_clauses_woven_by_local_discourse_model",
            "guarantees": {
                "external_llm": False,
                "external_sllm": False,
                "fabricated_facts": False,          # content is verbatim; only discourse is generated
                "content_token_recombination": False,
                "generation_scope": "discourse_scaffolding_only",
            },
        },
        "confidence": round(min(0.72, 0.4 + 0.08 * len(picked)), 2),
        "answer_kind": "grounded_synthesis",
    }


def _has_final_consonant(text: str) -> bool:
    chars = [ch for ch in text if "가" <= ch <= "힣"]
    if not chars:
        return False
    return (ord(chars[-1]) - 0xAC00) % 28 != 0


def _topic_marker(label: str) -> str:
    if not _HANGUL.search(label):
        return label
    return f"{label}{'은' if _has_final_consonant(label) else '는'}"
