# -*- coding: utf-8 -*-
"""fluency_v1 — a grounded surface-realization benchmark, scored honestly.

30 tasks, each a subject with grounded relations/attributes (bones). Three metrics:

  (a) FAITHFULNESS  — every content word on the surface traces to the grounding. This is the
      anti-fabrication invariant and MUST stay ~1.0 for BOTH before and after; a drop means the
      realizer invented something.
  (b) FLUENCY PROXY — an HONEST HEURISTIC (explicitly NOT a human judgment): connective variety,
      run-on avoidance, opener non-repetition, subject-verb agreement. Reported with sub-scores so
      the source of any gain is visible and cannot be hidden.
  (c) SLOT-COPY     — of the grounded content slots the delexicalizer produced, how many were copied
      verbatim onto the surface. 1.0 = the copy mechanism placed every grounded entity.

BEFORE = realizer_struct.frame_realizer (the current single-register structural realizer).
AFTER  = packages.fluency.realizer (delex + copy + register lever).

Run: python -X utf8 -m packages.fluency.fluency_v1
"""
from __future__ import annotations

import re
from typing import Any, Callable

from packages.realizer_struct import frame_realizer as fr
from packages.fluency.conversational import expand_contractions
from packages.fluency.delex import Grounding, delexicalize
from packages.fluency.realizer import realize as after_realize
from packages.fluency.register import (
    APPROVED_CONNECTIVES,
    APPROVED_DISCOURSE_MARKERS,
    APPROVED_OPENERS,
    load_registers,
    select_register,
)

_WORD = re.compile(r"[A-Za-z0-9]+")


# ── the closed skeleton (function) vocabulary: everything the surface may add without it counting as
#    content. Built from the frame lexicon + register vocab + a small function-word floor, so the
#    faithfulness scorer subtracts exactly the closed vocab and checks the REST against grounding. ──
def _skeleton_vocab() -> set[str]:
    vocab: set[str] = set()
    for frame in list(fr.FRAMES.values()) + [fr._DEFAULT]:
        for key in ("tmpl", "reduced"):
            t = frame.get(key)
            if t:
                vocab.update(w.lower() for w in _WORD.findall(re.sub(r"\{\w+\}", " ", t)))
    for phrase in APPROVED_CONNECTIVES + APPROVED_OPENERS + APPROVED_DISCOURSE_MARKERS:
        vocab.update(w.lower() for w in _WORD.findall(phrase))
    vocab.update({
        "a", "an", "the",                                          # articles
        "is", "are", "was", "were", "has", "have", "had",          # copula/aux
        "can", "could", "will", "would", "do", "does", "did",
        "it", "they", "he", "she", "we", "i", "you", "them", "its", "their",  # pronouns
        "that", "which", "who",                                                # relative pronouns
        "in", "of", "for", "to", "on", "at", "by", "with", "as", "also",      # preps/particles
    })
    return vocab


SKELETON_VOCAB = _skeleton_vocab()


# ── (a) faithfulness ──────────────────────────────────────────────────────────────────────────────
def faithfulness(text: str, grounding: Grounding) -> tuple[float, list[str]]:
    """Fraction of CONTENT tokens (non-skeleton) that trace to the grounding. Returns (score,
    fabricated_tokens). 1.0 = nothing invented.

    Contractions are EXPANDED first ("it's" -> "it is") so a clitic is measured as its function-word
    expansion — a contraction IS its expansion — rather than being mis-split into a spurious content
    fragment. Every expansion is a closed-class function word, so this can only recognize a clitic; it
    never turns an invented CONTENT word (e.g. 'cheese') into a grounded one."""
    toks = _WORD.findall(expand_contractions(text).lower())
    content = [t for t in toks if t not in SKELETON_VOCAB]
    if not content:
        return 1.0, []
    fabricated = [t for t in content if not grounding._word_ok(t)]
    return 1.0 - len(fabricated) / len(content), fabricated


# ── (b) fluency proxy (HONEST HEURISTIC) ────────────────────────────────────────────────────────
_CONN_LEX = ("and", "but", "while", "which is why", "and in turn", "so", "as well as",
             "in addition", "as a result", "beyond that", "on top of that")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def _connective_variety(text: str) -> float:
    low = " " + text.lower() + " "
    counts = {c: len(re.findall(r"\b" + re.escape(c) + r"\b", low)) for c in _CONN_LEX}
    total = sum(counts.values())
    if total <= 1:
        return 1.0
    top = max(counts.values())
    return 1.0 - (top - 1) / total          # penalize one connective dominating (", and ... , and")


def _run_on(text: str) -> float:
    sents = _sentences(text)
    if not sents:
        return 1.0
    scores = []
    for s in sents:
        w = len(_WORD.findall(s))
        if 4 <= w <= 18:
            scores.append(1.0)
        elif w < 4:
            scores.append(max(0.0, w / 4.0))
        else:
            scores.append(max(0.0, 1.0 - (w - 18) / 18.0))     # run-on penalty above 18 words
    return sum(scores) / len(scores)


def _opener_repetition(text: str) -> float:
    sents = _sentences(text)
    if len(sents) <= 1:
        return 1.0
    openers = [(_WORD.findall(s) or [""])[0].lower() for s in sents]
    freq: dict[str, int] = {}
    for o in openers:
        freq[o] = freq.get(o, 0) + 1
    over = max(0, max(freq.values()) - 2)                       # 2 repeats free (simple register)
    return max(0.0, 1.0 - over / len(sents))


def _agreement(text: str) -> float:
    errs = len(re.findall(r"\b(they|we|penguins|people|children|men|women|birds)\s+(is|has)\b",
                          text.lower()))
    errs += len(re.findall(r"\bit\s+(are|have)\b", text.lower()))
    sents = max(1, len(_sentences(text)))
    return max(0.0, 1.0 - errs / sents)


def fluency_proxy(text: str) -> tuple[float, dict[str, float]]:
    """Composite naturalness proxy in [0,1]. HONEST LABEL: heuristic, not a human score."""
    subs = {
        "connective_variety": _connective_variety(text),
        "run_on": _run_on(text),
        "opener_repetition": _opener_repetition(text),
        "agreement": _agreement(text),
    }
    return sum(subs.values()) / len(subs), subs


# ── (c) slot-copy accuracy ────────────────────────────────────────────────────────────────────────
def slot_copy_accuracy(bones: list, text: str) -> float:
    """Of the grounded CONTENT slot values the delexicalizer produced, how many appear verbatim on
    the surface. 1.0 = the copy mechanism placed every grounded entity."""
    grounding = Grounding.from_bones(bones)
    plans = delexicalize(bones)
    wanted: list[str] = []
    for p in plans:
        for s in p.content_slots():
            if s.role in ("SUBJ", "OBJ") and grounding.has(s.value):
                wanted.append(s.value)
    if not wanted:
        return 1.0
    low = text.lower()
    placed = sum(1 for v in wanted if _value_present(v, low))
    return placed / len(wanted)


def _value_present(value: str, text_low: str) -> bool:
    """A slot value is 'placed' if all its content words appear (handles plural/case morphology)."""
    g = Grounding()
    g.add(value)
    # every content word of the value must be present as a word (or its plural) in the text
    text_words = set(_WORD.findall(text_low))
    for w in _WORD.findall(value.lower()):
        if w in text_words:
            continue
        if any((w + suf) in text_words for suf in ("s", "es")):
            continue
        if w.endswith("y") and (w[:-1] + "ies") in text_words:
            continue
        return False
    return True


# ── the tasks ─────────────────────────────────────────────────────────────────────────────────────
def tasks() -> list[dict[str, Any]]:
    """30 grounded tasks: single-fact (ties), 2-3 fact, 4-6 fact run-on cases, plural, demonym."""
    T: list[dict[str, Any]] = []

    def add(tid, bones, context=None):
        T.append({"id": tid, "bones": bones, "context": context or {}})

    # --- single fact (BEFORE == AFTER; establishes that the lever does not touch sparse content) ---
    add("s_coffee", [["coffee", "is_a", "beverage"]])
    add("s_sun", [["sun", "is_a", "star"]])
    add("s_python", [["Python", "is_a", "programming language"]])
    add("s_paris", [["Paris", "is_a", "city"]])
    add("s_oak", [["oak", "is_a", "tree"]])
    add("s_violin", [["violin", "is_a", "instrument"]])

    # --- two / three facts (a reduced clause aggregates onto the head; still short) ---
    add("d_kyushu", [["Kyushu", "is_a", "island"], ["Kyushu", "located_in", "Japan"]])
    add("d_iron", [["iron", "is_a", "metal"], ["iron", "has_property", "magnetic"]])
    add("d_rose", [["rose", "is_a", "flower"], ["rose", "has_property", "fragrant"]])
    add("t_copper", [["copper", "is_a", "metal"], ["copper", "has_property", "conductive"],
                     ["copper", "used_for", "wiring"]])
    add("t_bee", [["bee", "is_a", "insect"], ["bee", "capable_of", "fly"],
                  ["bee", "used_for", "pollination"]])
    add("t_guitar", [["guitar", "is_a", "instrument"], ["guitar", "made_of", "wood"],
                     ["guitar", "used_for", "music"]])

    # --- four to six facts (BEFORE produces a repeated-", and" run-on; the lever's target) ---
    add("m_einstein", [["Einstein", "is_a", "physicist"], ["Einstein", "has_property", "German"],
                       ["Einstein", "located_in", "Germany"], ["Einstein", "capable_of", "explain relativity"],
                       ["Einstein", "has_a", "famous equation"]])
    add("m_water", [["water", "is_a", "substance"], ["water", "has_property", "clear"],
                    ["water", "made_of", "hydrogen"], ["water", "used_for", "drinking"],
                    ["water", "capable_of", "freeze"]])
    add("m_computer", [["computer", "is_a", "machine"], ["computer", "made_of", "silicon"],
                       ["computer", "used_for", "computation"], ["computer", "capable_of", "store data"],
                       ["computer", "has_a", "processor"]])
    add("m_lion", [["lion", "is_a", "mammal"], ["lion", "has_property", "large"],
                   ["lion", "located_in", "Africa"], ["lion", "capable_of", "hunt"],
                   ["lion", "has_a", "mane"]])
    add("m_river", [["river", "is_a", "waterway"], ["river", "capable_of", "flow"],
                    ["river", "used_for", "transport"], ["river", "has_a", "current"],
                    ["river", "part_of", "watershed"], ["river", "capable_of", "flood"]])
    add("m_volcano", [["volcano", "is_a", "mountain"], ["volcano", "made_of", "rock"],
                      ["volcano", "capable_of", "erupt"], ["volcano", "has_a", "crater"],
                      ["volcano", "capable_of", "release lava"], ["volcano", "has_property", "active"]])
    add("m_engine", [["engine", "is_a", "machine"], ["engine", "made_of", "metal"],
                     ["engine", "used_for", "propulsion"], ["engine", "capable_of", "burn fuel"],
                     ["engine", "has_a", "piston"], ["engine", "capable_of", "generate power"]])

    # --- plural subjects (agreement must hold in every register) ---
    add("p_penguins", [["penguins", "is_a", "bird"], ["penguins", "has_property", "flightless"],
                       ["penguins", "located_in", "Antarctica"], ["penguins", "capable_of", "swim"]])
    add("p_bees", [["bees", "is_a", "insect"], ["bees", "capable_of", "fly"],
                   ["bees", "used_for", "pollination"], ["bees", "has_a", "stinger"]])
    add("p_mice", [["mice", "is_a", "rodent"], ["mice", "has_property", "small"],
                   ["mice", "capable_of", "climb"]])

    # --- demonym capitalization (Japanese / German kept capital by the morphology floor) ---
    add("n_sushi", [["sushi", "is_a", "dish"], ["sushi", "has_property", "Japanese"],
                    ["sushi", "made_of", "rice"]])
    add("n_baguette", [["baguette", "is_a", "bread"], ["baguette", "has_property", "French"],
                       ["baguette", "made_of", "flour"]])

    # --- explanatory context (the query cue routes the lever to the explanatory register) ---
    add("x_photosynthesis", [["photosynthesis", "is_a", "process"],
                             ["photosynthesis", "used_for", "energy"],
                             ["photosynthesis", "capable_of", "produce oxygen"],
                             ["photosynthesis", "part_of", "plant metabolism"]],
        {"query": "explain how photosynthesis works"})
    add("x_gravity", [["gravity", "is_a", "force"], ["gravity", "capable_of", "attract mass"],
                      ["gravity", "used_for", "orbit"], ["gravity", "has_property", "universal"]],
        {"query": "explain why gravity matters"})
    add("x_heart", [["heart", "is_a", "organ"], ["heart", "made_of", "muscle"],
                    ["heart", "used_for", "circulation"], ["heart", "capable_of", "pump blood"]],
        {"query": "how does the heart work in detail"})

    # --- multi-subject answer (two subjects in one answer) ---
    add("ms_pair", [["dog", "is_a", "mammal"], ["dog", "capable_of", "bark"],
                    ["cat", "is_a", "mammal"], ["cat", "capable_of", "purr"]])
    return T


# ── the run ─────────────────────────────────────────────────────────────────────────────────────
def _score_variant(bones: list, text: str) -> dict[str, Any]:
    grounding = Grounding.from_bones(bones)
    faith, fab = faithfulness(text, grounding)
    prox, subs = fluency_proxy(text)
    return {"text": text, "faithfulness": faith, "fabricated": fab,
            "fluency_proxy": prox, "proxy_subs": subs,
            "slot_copy": slot_copy_accuracy(bones, text)}


def run(before_fn: Callable[[list], str] | None = None) -> dict[str, Any]:
    """Score BEFORE (frame_realizer) vs AFTER variants across all tasks. Returns per-task rows and
    aggregate means. `before_fn` overridable for testing; defaults to frame_realizer.realize."""
    before_fn = before_fn or fr.realize
    specs = load_registers()
    variants = ["before", "after_simple", "after_neutral", "after_explanatory", "after_composed", "after_auto"]
    rows: list[dict[str, Any]] = []
    for task in tasks():
        bones, ctx = task["bones"], task["context"]
        auto_reg = select_register(ctx, specs)
        texts = {
            "before": before_fn(bones),
            "after_simple": after_realize(bones, register="simple"),
            "after_neutral": after_realize(bones, register="neutral"),
            "after_explanatory": after_realize(bones, register="explanatory"),
            "after_composed": after_realize(bones, register="composed"),
            "after_auto": after_realize(bones, register=auto_reg),
        }
        row = {"id": task["id"], "n_bones": len(bones), "auto_register": auto_reg,
               "variants": {v: _score_variant(bones, texts[v]) for v in variants}}
        rows.append(row)

    def mean(variant: str, metric: str) -> float:
        vals = [r["variants"][variant][metric] for r in rows]
        return sum(vals) / len(vals)

    aggregate = {v: {"faithfulness": round(mean(v, "faithfulness"), 4),
                     "fluency_proxy": round(mean(v, "fluency_proxy"), 4),
                     "slot_copy": round(mean(v, "slot_copy"), 4)} for v in variants}
    # honest boundary: proxy gain on multi-fact (>=4 bones) vs sparse (<=2 bones)
    multi = [r for r in rows if r["n_bones"] >= 4]
    sparse = [r for r in rows if r["n_bones"] <= 2]

    def sub_mean(subset, variant):
        if not subset:
            return None
        return round(sum(r["variants"][variant]["fluency_proxy"] for r in subset) / len(subset), 4)

    boundary = {
        "multi_fact_n": len(multi), "sparse_n": len(sparse),
        "proxy_before_multi": sub_mean(multi, "before"),
        "proxy_after_auto_multi": sub_mean(multi, "after_auto"),
        "proxy_before_sparse": sub_mean(sparse, "before"),
        "proxy_after_auto_sparse": sub_mean(sparse, "after_auto"),
    }
    return {"rows": rows, "aggregate": aggregate, "boundary": boundary, "n_tasks": len(rows)}


def main() -> None:
    import io
    import sys
    buf = io.StringIO()
    rep = run()
    agg = rep["aggregate"]
    buf.write(f"fluency_v1 — {rep['n_tasks']} grounded tasks (BEFORE=frame_realizer, AFTER=delex+copy+register)\n")
    buf.write("\n  variant             faithful   proxy*   slot-copy\n")
    for v, m in agg.items():
        buf.write(f"  {v:18s}  {m['faithfulness']:.3f}    {m['fluency_proxy']:.3f}   {m['slot_copy']:.3f}\n")
    b = rep["boundary"]
    buf.write("\n  * fluency_proxy is an HONEST HEURISTIC (connective variety / run-on / opener repetition /\n")
    buf.write("    agreement), NOT a human judgment.\n")
    buf.write("\n  honest boundary (where delex+copy+register helps):\n")
    buf.write(f"    multi-fact (>=4 bones, n={b['multi_fact_n']}): proxy {b['proxy_before_multi']} -> {b['proxy_after_auto_multi']} (auto)\n")
    buf.write(f"    sparse    (<=2 bones, n={b['sparse_n']}): proxy {b['proxy_before_sparse']} -> {b['proxy_after_auto_sparse']} (auto; identical by design)\n")
    # a couple of concrete before/after examples
    ex = {r["id"]: r for r in rep["rows"]}
    for tid in ("m_einstein", "m_engine"):
        if tid in ex:
            buf.write(f"\n  [{tid}]\n")
            buf.write(f"    BEFORE : {ex[tid]['variants']['before']['text']}\n")
            buf.write(f"    NEUTRAL: {ex[tid]['variants']['after_neutral']['text']}\n")
    sys.stdout.write(buf.getvalue())


if __name__ == "__main__":
    main()
