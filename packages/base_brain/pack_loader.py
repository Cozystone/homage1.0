from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import PACK_PATH, BaseBrainPack
from .pack_builder import build_base_brain_pack_v0

BASE_PACK_CODE_VERSION = "0.1.5"
# Persisted inverted-index + disk-record store (built by promote_graph_to_pack). When
# present AND matching the loaded pack, get_semantic_context serves lookups from it:
# O(candidates) scoring + bounded RAM instead of an O(N) scan that copies every concept.
SEMANTIC_STORE_DIR = PACK_PATH.parent / "semantic_store"
_STORE_CACHE: dict[str, Any] = {"store": None, "sig": None}
TOKEN_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "for",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "brain",
    "cloud",
    "local",
    "simple",
    "explain",
    "차이",
    "비교",
    "설명",
    "간단",
    "초등학생",
    "중학생",
    "전문가",
    "브레인",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _tokens(text: str) -> set[str]:
    lowered = _norm(text)
    latin = set(re.findall(r"[a-z0-9.+#-]{2,}", lowered))
    korean = set(re.findall(r"[\uac00-\ud7a3]{2,}", text or ""))
    return {token for token in (latin | korean) if token not in TOKEN_STOPWORDS}


def _needs_rebuild(payload: dict[str, Any]) -> bool:
    metadata = payload.get("metadata") or {}
    if metadata.get("base_pack_code_version") != BASE_PACK_CODE_VERSION:
        return True
    text = json.dumps(payload, ensure_ascii=False)
    return any(marker in text for marker in ("荑", "吏", "媛", "占"))


_HANGUL_PACK = re.compile(r"[가-힣]")


def _english_only() -> bool:
    """Read at CALL time, not import time, so a test can exercise either lane."""
    import os
    return os.environ.get("ATANOR_ENGLISH_ONLY", "1") != "0"


def _contain_language(payload: dict) -> dict:
    """English-only containment for the ANSWER PACK — the store's lang_gate.col has a twin here.

 Measured 2026-07-17 (seal battery, holdout): kg_triples is contained but the pack is a
 SECOND store, ungated, and 45% of it is Korean. Subjects the graph can't answer fall to
 base_brain, which composes from Korean short_descriptions; the chat exit gate then replaces
 the whole answer with a refusal. No Korean ever reached a user — but five holdout turns
 scored as refusals that should have engaged, and this is the cause.

 FIELD-LEVEL, not concept-level. The naive filter (drop any concept touching Hangul) would
 delete 4,347 of 9,491 concepts — but the Hangul is mostly in labels.ko (4,170, a proper i18n
 field) and aliases (198), e.g. Kubernetes carries the alias and an entirely English
 description. Killing those costs recall and fixes nothing. The leak is the ANSWER TEXT:
 canonical_name (4,125) and short_description (4,288) — concepts that are Korean, like
 //, not English concepts with Korean labels.

 Filter, never delete: the pack on disk is untouched, ATANOR_ENGLISH_ONLY=0 restores it whole.
 """
    graph = payload.get("semantic_graph") or {}
    concepts = graph.get("concepts") or []
    kept = [c for c in concepts
            if not (_HANGUL_PACK.search(str(c.get("canonical_name") or ""))
                    or _HANGUL_PACK.search(str(c.get("short_description") or "")))]
    if len(kept) == len(concepts):
        return payload
    return {**payload, "semantic_graph": {**graph, "concepts": kept,
                                          "language_contained": len(concepts) - len(kept)}}


def load_base_brain_pack(pack_path: str | Path | None = None) -> BaseBrainPack:
    path = Path(pack_path) if pack_path else PACK_PATH
    if not path.exists():
        build_base_brain_pack_v0()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if _needs_rebuild(payload):
        # In-memory rebuild for THIS load only — never write, so a promoted pack on
        # disk is not clobbered back to curated-only by a version/mojibake trip.
        payload = build_base_brain_pack_v0(write=False)
    if _english_only():
        payload = _contain_language(payload)
    return BaseBrainPack(
        pack_id=payload["pack_id"],
        version=payload["version"],
        metadata=payload["metadata"],
        seed_graph=payload["seed_graph"],
        semantic_graph=payload["semantic_graph"],
        surface_graph=payload["surface_graph"],
        benchmark=payload["benchmark"],
    )


# Korean particle tails come from the single LAD morphology layer (packages/lad_morphology)
# so every module shares one closed-class list instead of drifting copies.
from packages.lad_morphology import JOSA_TAILS as _JOSA_TAILS  # noqa: E402


def _named_with_boundary(query_norm: str, name_norm: str) -> bool:
    """True iff the name appears in the query at a MORPHEME BOUNDARY — the maximal-match
 principle. A raw substring test is the measured chronic wrong-referent bug: '' is
 inside '', '' inside '', so the engine confidently defined carbon
 when asked about BTS. A match only counts when (a) nothing Hangul precedes it (else it
 is the interior of a longer word — Korean compounds are left-headed strings) and (b) the
 Hangul run following it is empty or a known particle (else the user named a LONGER term,
 e.g. '' followed by '')."""
    start = 0
    n = len(query_norm)
    while True:
        i = query_norm.find(name_norm, start)
        if i < 0:
            return False
        left_ok = i == 0 or not ("가" <= query_norm[i - 1] <= "힣")
        j = i + len(name_norm)
        k = j
        while k < n and "가" <= query_norm[k] <= "힣":
            k += 1
        run = query_norm[j:k]
        if left_ok and (run == "" or run in _JOSA_TAILS):
            return True
        start = i + 1


# Function words are not evidence that a concept is the topic. TOKEN_STOPWORDS is deliberately
# small because _tokens also builds the PERSISTED index (changing it forces a pack rebuild), so the
# discipline is applied at SCORING time instead — no index change, same effect on the answer.
# Measured 2026-07-17: "What does a polar bear look like?" anchored on the concept "Like his
# father" (match=loose_token_overlap, score 1.5) purely because both contain "like", and answered
# "like is a kind of kind. like relates to unlike." Overlap on a grammatical word is coincidence.
_SCORE_IGNORED_TOKENS = frozenset({
    "like", "look", "looks", "looked", "about", "better", "best", "different", "difference",
    "want", "need", "make", "made", "get", "got", "give", "take", "know", "think", "tell",
    "say", "said", "use", "used", "work", "works", "start", "help", "mean", "means",
    "thing", "things", "way", "ways", "kind", "kinds", "sort", "type", "part", "lot",
    "this", "that", "these", "those", "there", "here", "what", "who", "why", "how", "when",
    "where", "which", "you", "your", "yours", "his", "her", "hers", "its", "their", "our",
    "does", "did", "can", "could", "would", "should", "will", "shall", "may", "might",
    "have", "has", "had", "been", "being", "was", "were", "not", "but", "all", "any",
    "some", "very", "just", "now", "then", "than", "into", "onto", "over", "under", "out",
})


def _content_overlap(query_tokens: set[str], other_tokens: set[str]) -> int:
    """Shared tokens that actually carry meaning — grammar overlap is not a match."""
    return len((query_tokens & other_tokens) - _SCORE_IGNORED_TOKENS)


def _concept_score(query: str, concept: dict[str, Any]) -> float:
    query_norm = _norm(query)
    query_tokens = _tokens(query)
    names = [concept.get("concept_id", ""), concept.get("canonical_name", ""), *(concept.get("aliases") or [])]
    labels = concept.get("labels") or {}
    names.extend(str(value) for value in labels.values())
    score = 0.0
    for name in names:
        name_norm = _norm(str(name))
        if not name_norm:
            continue
        if _named_with_boundary(query_norm, name_norm):
            score += 2.2
        name_tokens = _tokens(str(name))
        score += _content_overlap(query_tokens, name_tokens) * 0.75
    desc_tokens = _tokens(str(concept.get("short_description", "")))
    score += min(_content_overlap(query_tokens, desc_tokens) * 0.25, 1.0)
    return score


def _get_indexed_store(expected_n: int):
    """Return the persisted SemanticConceptStore iff it exists AND matches the loaded
    pack (same concept count) — so a custom/grown pack passed in tests still uses the
    scan. Cached by index mtime; any error falls back to None (scan)."""
    idx = SEMANTIC_STORE_DIR / "index.sqlite"
    if not idx.exists():
        return None
    try:
        sig = (idx.stat().st_mtime, expected_n)
        if _STORE_CACHE["sig"] != sig:
            from .semantic_store import SemanticConceptStore
            store = SemanticConceptStore.open(SEMANTIC_STORE_DIR)
            _STORE_CACHE["store"] = store if store.n == expected_n else None
            _STORE_CACHE["sig"] = sig
        return _STORE_CACHE["store"]
    except Exception:
        return None


def _frame_subject(query: str) -> str:
    """The question's TOPIC via the morpheme frame — retrieval follows understanding (doctrine:
    the frame decides fact routing). Empty on any failure; Korean questions only."""
    try:
        q = str(query or "")
        if len(q) < 4 or not any("가" <= ch <= "힣" for ch in q):
            return ""
        from packages.graph_scale.query_frame import parse as _qparse
        return str(_qparse(q).subject or "")
    except Exception:
        return ""


def get_semantic_context(query: str, pack: BaseBrainPack, limit: int = 12) -> list[dict[str, Any]]:
    concepts = pack.semantic_graph.get("concepts") or []
    # SUBJECT-FIRST retrieval: token/boundary scoring can NEVER find a 1-char Hangul concept


    # frame's subject names a pack concept exactly, that concept IS the topic — head of the list.
    subj = _frame_subject(query)
    if subj and _norm(subj) != _norm(query):
        exact = [c for c in concepts if _norm(str(c.get("canonical_name") or "")) == _norm(subj)]
        if exact:
            # explicit flag, NOT a score sentinel — the indexed store emits its own score scale,
            # and a magic-number gate misfired on loose English matches (caught by the precision-
            # gate test: 'capital of France' answered API at 0.45).
            head = [{**c, "match_score": 9.0, "frame_subject_named": True} for c in exact[:2]]
            seen = {c.get("concept_id") for c in exact[:2]}
            tail = [c for c in get_semantic_context(subj, pack, limit=limit)
                    if c.get("concept_id") not in seen]
            return (head + tail)[:limit]
    store = _get_indexed_store(len(concepts))
    if store is not None:
        try:
            return store.lookup(query, limit=limit)
        except Exception:
            pass  # any store failure falls back to the exact in-RAM scan below
    scored = [{**concept, "match_score": _concept_score(query, concept)} for concept in concepts]
    ranked = sorted(
        scored,
        key=lambda item: (float(item.get("match_score") or 0.0), float(item.get("confidence") or 0.0)),
        reverse=True,
    )
    high_confidence = [item for item in ranked if float(item.get("match_score") or 0.0) >= 4.0]
    selected = [item for item in ranked if float(item.get("match_score") or 0.0) >= 1.0][:limit]
    if high_confidence:
        selected = [
            item
            for item in selected
            if item.get("concept_id") not in {"korean_language", "english_language"}
            or any(marker in query.lower() for marker in ["한국어", "영어로", "번역투", "language"])
        ][:limit]
    if selected:
        selected_ids = {item["concept_id"] for item in selected}
        relation_targets = {
            relation.get("target")
            for item in selected
            for relation in item.get("relations", [])
            if relation.get("target")
        }
        for item in ranked:
            if len(selected) >= limit:
                break
            if item["concept_id"] in selected_ids:
                continue
            if item["concept_id"] in relation_targets:
                selected.append(item)
                selected_ids.add(item["concept_id"])
    return selected[:limit]


def _classify_intent(query: str, seed_graph: dict[str, Any]) -> str:
    lower = _norm(query)
    if any(token in lower for token in ["compare", "versus", " vs ", "difference", "차이", "비교"]):
        return "compare"
    if any(token in lower for token in ["summarize", "요약", "정리"]):
        return "summarize"
    if any(token in lower for token in ["what is", "define", "뭐야", "무엇", "정의"]):
        return "define"
    if any(token in lower for token in ["how", "why", "explain", "설명", "왜", "어떻게"]):
        return "explain"
    return "explain" if "explain" in seed_graph.get("reasoning_primitives", []) else "clarify"


def get_surface_candidates(
    query: str,
    semantic_context: list[dict[str, Any]],
    language: str,
    audience_level: str,
    limit: int = 8,
    pack: BaseBrainPack | None = None,
) -> list[dict[str, Any]]:
    pack = pack or load_base_brain_pack()
    intent = _classify_intent(query, pack.seed_graph)
    candidates = []
    for item in pack.surface_graph.get("constructions", []):
        if item.get("language") != language:
            continue
        fit = 0.55
        if item.get("function") in {intent, "definition" if intent == "define" else intent}:
            fit += 0.28
        if item.get("audience_level") == audience_level:
            fit += 0.12
        if semantic_context:
            fit += 0.05
        candidates.append(
            {
                **item,
                "id": item.get("construction_id"),
                "pattern_family": item.get("construction_id"),
                "semantic_function": item.get("function"),
                "fit_score": min(fit, 1.0),
                "style_score": 0.78 if item.get("tone") in {"clear", "friendly", "compact"} else 0.62,
                "language_score": 1.0,
                "prior_success_weight": item.get("prior_weight", 0.5),
                "user_preference_weight": 0.72,
                "repetition_penalty": 0.0,
            }
        )
    return sorted(candidates, key=lambda item: item["fit_score"], reverse=True)[:limit]


def classify_intent(query: str, pack: BaseBrainPack | None = None) -> str:
    pack = pack or load_base_brain_pack()
    return _classify_intent(query, pack.seed_graph)
