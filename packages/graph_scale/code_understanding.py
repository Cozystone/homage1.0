# -*- coding: utf-8 -*-
"""Code self-understanding — ATANOR answers questions about its OWN source (owner 2026-07-12:
" … ").

The prerequisite for vibe-coding is that the machine can READ its own body. codebase_ingest
already distills the tree into structural triples (module has_function fn, fn calls other,
fn documented_as "…"). This turns that graph into a spoken answer: given a question that names
a module / function / class, it says what that thing IS (its documented purpose, what it holds
or calls) and what REFERENCES it — grounded entirely in the AST graph, never invented.

Honest scope, unchanged from codebase_ingest: this is STRUCTURE + docstrings, not a semantic
model of what the code MEANS. It answers "what is realize_thought / what calls trust_score /
what does speaker_arena.py hold", not "is this code correct". Read-only: it has no path to
edit code — self-modification stays human-gated (code_self_modification, staging only).

TWO REPAIRS, 2026-07-31, both found by auditing rather than by anything failing loudly:

  * The answers were composed in Korean and the "is this a code question" cue list was Korean, in a
    system that has thought in English since 2026-07-18. The lane could not fire on its own cues.
  * Its one caller gated it on `language == "ko"` (dual_brain), which in an English-only system is a
    condition that is never true. The organ was built, its graph was ingested, and it was walled off
    behind a permanently false test — the built-but-unwired pathology this project keeps finding.

The gate was removed rather than flipped to "en", and the distinction matters. A language switch is a
second lane that turns on for certain inputs; the doctrine is one mind that recognises context and
returns None when a question is not its business. This function ALREADY did that — it returns None
when no known code entity is named — so the gate was never protection, only a wall.

Answers now carry `defined_at` locations (path.py:LINE), so naming a function and POINTING at it are
the same act, and the reader can check the answer in one click instead of taking it on faith.
"""
from __future__ import annotations

import re
from typing import Any

#: surface cues that a question is ABOUT code. English, because ATANOR thinks in English (2026-07-18);
#: the Korean cue list this replaced could never match in an English-only system, which is how the whole
#: lane came to be silently unreachable. This regex is a training wheel and is marked as one -- the
#: durable version is a learned router. It is also not load-bearing on its own: `_looks_like_code`
#: catches identifier-shaped questions with no cue word at all, and both are only ADMISSION tests. What
#: actually decides is whether the named entity exists in the graph.
_CODE_Q = re.compile(
    r"\b(code|source|function|method|module|class|file|caller|callers|defined|definition|"
    r"implement(?:s|ed|ation)?|calls?|imports?|docstring|refactor|signature)\b|\.py", re.I)
# a token that looks like a code identifier: snake_case, CamelCase, dotted path, or file.py
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*(?:\.py)?")

_NAMES_CACHE: dict[str, Any] = {"mtime": None, "by_leaf": None, "all": None}


def _known_names() -> tuple[dict[str, list[str]], set[str]]:
    """All names in the code graph, indexed by their LEAF (last dotted segment) so a bare
    'realize_thought' or 'speaker_arena' resolves to the full dotted subject.

    The index is BUILT AT INGEST and read from disk. It used to be derived here by walking every
    row of the ledger on first use — the same scan-everything habit that made `about()` cost 167 ms
    a question. Resolution is a lookup now, and the cache key is the index's own mtime, so a
    re-ingest invalidates it."""
    from packages.graph_scale.codebase_ingest import NAMES, leaf_index
    try:
        mtime = NAMES.stat().st_mtime
    except OSError:
        return {}, set()
    if _NAMES_CACHE["mtime"] == mtime and _NAMES_CACHE["by_leaf"] is not None:
        return _NAMES_CACHE["by_leaf"], _NAMES_CACHE["all"]
    by_leaf = leaf_index()
    allnames = {n for names in by_leaf.values() for n in names}
    _NAMES_CACHE.update({"mtime": mtime, "by_leaf": by_leaf, "all": allnames})
    return by_leaf, allnames


#: words that are never the code entity being asked about. The wh-words matter more than they look:
#: "where is author defined" resolved to the identifier `where` until they were listed here, because
#: `where` happens to be a real function name in this repo. A question word that shadows a real symbol
#: is the failure mode this set exists for, so it covers the whole wh-family rather than the few seen.
_STOP = {"is", "in", "py", "self", "def", "the", "and", "for", "what", "does", "how",
         "where", "when", "which", "who", "whom", "whose", "why", "was", "are", "were",
         "can", "could", "should", "would", "will", "did", "do", "done", "get", "got",
         "this", "that", "these", "those", "from", "with", "into", "about", "there",
         "here", "it", "its", "they", "them", "you", "your", "me", "my", "tell", "show",
         "explain", "find", "look", "give", "some", "any", "all", "not", "but", "out"}


def resolve_entity(question: str) -> str | None:
    """The code entity a question is asking about, or None. Prefers an exact dotted name in the
    graph; else matches a bare identifier against a known leaf (the function/module short name)."""
    by_leaf, allnames = _known_names()
    if not allnames:
        return None
    # normalize each candidate: a trailing '.py' is a file suffix, not a dotted segment
    # question words are dropped BEFORE any lookup. This repo really does define functions named
    # `where`, `show` and `get`, so an unfiltered exact-name match answers "where is author defined"
    # with facts about `where` -- confidently, groundedly, and about the wrong thing. Filtering only
    # in the fallback loop (as this did) leaves the exact-match path exposed, which is where it bit.
    cands = [c for c in (c.removesuffix(".py") for c in _IDENT.findall(str(question or "")))
             if c.rsplit(".", 1)[-1].lower() not in _STOP]
    for c in cands:  # 1) exact full dotted name present in the graph
        if c in allnames:
            return c
    best: str | None = None
    for c in cands:  # 2) bare leaf → its dotted subject
        leaf = c.rsplit(".", 1)[-1]
        if len(leaf) < 3 or leaf.lower() in _STOP:
            continue
        hits = by_leaf.get(leaf)
        if hits:
            # a subject (module/fn we have facts FOR) beats a name only referenced by others
            subj_hits = [h for h in hits if _has_facts(h)]
            best = (subj_hits or hits)[0]
            if leaf.lower() in str(question or "").lower():
                return best
    return best


def _looks_like_code(question: str) -> bool:
    """A token shaped like a code identifier (snake_case, CamelCase, or a .py file) — so a clear
 'holographic_speaker ?' counts as a code question even without a keyword like /.
 A plain word (' ?') has none of these, so fact questions are never hijacked."""
    for tok in _IDENT.findall(str(question or "")):
        base = tok.removesuffix(".py")
        leaf = base.rsplit(".", 1)[-1]
        if leaf.lower() in _STOP or len(leaf) < 3:
            continue
        if tok.endswith(".py") or "_" in leaf or re.search(r"[a-z][A-Z]", leaf) or "." in base:
            return True
    return False


def _has_facts(name: str) -> bool:
    from packages.graph_scale.codebase_ingest import about
    return bool(about(name)["is"])


def _doc_of(facts: list[dict[str, Any]]) -> str | None:
    for f in facts:
        if f["predicate"] == "documented_as":
            return str(f["object"]).strip()
    return None


def answer_code_question(question: str) -> dict[str, Any] | None:
    """A grounded answer about ATANOR's own code, or None if the question isn't about code / no
    known entity is named. Everything stated is read from the AST graph — no invention."""
    q = str(question or "").strip()
    if not q or not (_CODE_Q.search(q) or _looks_like_code(q)):
        return None
    name = resolve_entity(q)
    if not name:
        return None
    from packages.graph_scale.codebase_ingest import about
    a = about(name, limit=60)
    if not a["known"]:
        return None

    facts = a["is"]
    fns = [f["object"] for f in facts if f["predicate"] == "has_function"]
    methods = [f["object"] for f in facts if f["predicate"] == "has_method"]
    classes = [f["object"] for f in facts if f["predicate"] == "has_class"]
    calls = sorted({f["object"] for f in facts if f["predicate"] == "calls"})
    in_mod = next((f["object"] for f in facts if f["predicate"] == "in_module"), None)
    sites = sorted({f["object"] for f in facts if f["predicate"] == "defined_at"})
    file_of = next((f["object"] for f in facts if f["predicate"] == "defined_in_file"), None)
    doc = _doc_of(facts)
    refs = sorted({r["subject"] for r in a["referenced_by"] if r["predicate"] == "calls"})
    leaf = name.rsplit(".", 1)[-1]

    # WHERE it lives, said once and said first -- a location is what turns naming a thing into
    # pointing at it, and it is the only part of this answer the reader can check in one click.
    where = ""
    if sites:
        where = sites[0] if len(sites) == 1 else f"{sites[0]} (and {len(sites) - 1} more of that name)"
    elif file_of:
        where = file_of

    parts: list[str] = []
    if fns or classes:                                    # a MODULE
        head = f"`{name}` is a module in my source"
        if where:
            head += f", at {where}"
        parts.append(f"{head}. {doc}" if doc else head + ".")
        holds = []
        if classes:
            holds.append(f"{len(classes)} class{'es' if len(classes) != 1 else ''} "
                         f"({_listing(classes, 4)})")
        if fns:
            holds.append(f"{len(fns)} function{'s' if len(fns) != 1 else ''} ({_listing(fns, 5)})")
        if holds:
            parts.append("It holds " + " and ".join(holds) + ".")
    else:                                                 # a FUNCTION / METHOD / CLASS
        kind = "class" if methods else "function"
        opening = f"`{leaf}` is a {kind}"
        if in_mod:
            opening += f" in `{in_mod}`"
        if where:
            opening += f", at {where}"
        parts.append(f"{opening}. {doc}" if doc else opening + ".")
        if methods:
            parts.append(f"It defines {_listing(sorted(set(methods)), 6)}.")
        if calls:
            parts.append(f"Internally it calls {_listing(calls, 5)}.")
    if refs:
        parts.append(f"It is called from {_listing(refs, 4)}.")
    if not doc and not calls and not refs and not (fns or classes):
        # the graph knows the name exists and almost nothing else; say so rather than pad
        parts.append("Beyond that the structural graph holds nothing more about it — "
                     "no docstring, no recorded callers.")

    answer = " ".join(parts)
    return {
        "answer": answer,
        "answer_kind": "code_self_understanding",
        "can_speak": True,
        "confidence": 0.82,
        "citations": [{"where": s} for s in sites[:6]] or ([{"where": file_of}] if file_of else []),
        "reasoning_certificate": {
            "derivation_kind": "code_self_understanding",
            "anchor_concept": {"id": name, "label": leaf, "match": "codebase_ast_graph"},
            "steps": [{"type": "ast", "source": "codebase_ingest",
                       "fact": f"{len(facts)} structural triples"}],
            "evidence_concepts": (fns or methods or [])[:8],
            "cited_locations": sites[:6],
            # EVERY fact this answer drew on, not a sample. The round-trip faithfulness check
            # compares what the prose asserts against what it was given, and an incomplete
            # certificate makes honest sentences look like fabrications -- which is exactly what
            # happened the first time the check was run against this lane. A certificate that
            # cannot account for its own answer is not a certificate.
            "propositions": ([{"s": name, "p": f["predicate"], "o": f["object"]} for f in facts]
                             + [{"s": r["subject"], "p": "calls", "o": name}
                                for r in a["referenced_by"]]),
            "confidence": 0.82,
            "confidence_basis": "own_source_ast_graph",
            "guarantees": {"external_llm": False, "fabricated_facts": False, "web_used": False},
        },
    }


def _listing(items: list[str], cap: int) -> str:
    """A readable English list, truncated honestly rather than trailing off in an ellipsis.

    'a, b and c' reads as a sentence; 'a, b, c…' reads as a dump. When there are more than fit, the
    count of what was left out is stated, because a silent truncation lets a partial list pass for a
    complete one."""
    items = [str(i) for i in items]
    shown = items[:cap]
    rest = len(items) - len(shown)
    if len(shown) == 1:
        body = f"`{shown[0]}`"
    else:
        body = ", ".join(f"`{s}`" for s in shown[:-1]) + f" and `{shown[-1]}`"
    return body + (f", plus {rest} more" if rest > 0 else "")
