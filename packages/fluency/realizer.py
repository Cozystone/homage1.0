# -*- coding: utf-8 -*-
"""The AFTER surface realizer: delexicalize -> select register -> assemble -> copy-fill.

Faithful and hallucination-safe BY CONSTRUCTION, identically to frame_realizer (whose morphology
floor — a/an, plural agreement, demonym capitalization — we reuse), with ONE addition: the register
lever. frame_realizer emits a single compound sentence per subject ("X is a Y, located in Z, and can
W, and ..."); the run-on and the always-"and" connective are its register ceiling. Here the assembler
reads register-spec PARAMETERS (max clauses per sentence, connective pool, opener pool, pronoun
policy, reduced-clause fronting) and groups the SAME copy-filled clauses accordingly — so only the
register surface changes, never the grounded content.

Every entity on the surface is copy-filled from the grounding; connectives/openers/pronouns are the
closed function vocabulary. Empty bones -> "" (the knowing/saying floor holds).
"""
from __future__ import annotations

import re
from typing import Any

from packages.realizer_struct import frame_realizer as fr

from packages.fluency.conversational import contract, expand_contractions
from packages.fluency.delex import (
    ClausePlan,
    Grounding,
    copy_fill,
    delexicalize,
    realize_reduced,
)
from packages.fluency.register import RegisterSpec, load_registers, select_register

# a conversational discourse marker is placed on at most this many continuation sentences per subject
# block — the BOUND that keeps a marker a natural aside instead of a forced tic on every sentence.
_MAX_DISCOURSE_MARKERS = 2

# person-category heads -> a gender-safe referring pronoun (singular 'they'). SURFACE aid only: it
# steers the referring expression (it/they), never content, so it cannot cause fabrication. Unknown
# heads fall back to 'it' (frame_realizer's convention). Small curated list, like the demonym table.
_PERSON_HEAD = {
    "physicist", "scientist", "author", "writer", "poet", "president", "king", "queen", "philosopher",
    "mathematician", "artist", "musician", "composer", "engineer", "doctor", "teacher", "player",
    "actor", "singer", "leader", "politician", "general", "emperor", "painter", "chemist", "biologist",
    "astronomer", "economist", "novelist", "director", "athlete", "inventor", "explorer", "monk",
    "person", "man", "woman", "child",
}


def _pronoun(plural: bool, noun: str | None) -> tuple[str, bool]:
    """Return (referring pronoun, takes_plural_verb). 'they' (plural OR gender-safe singular they)
    takes plural verbs; 'it' takes singular."""
    if plural:
        return "they", True
    if noun and noun.strip().lower() in _PERSON_HEAD:
        return "they", True                                # gender-safe singular they
    return "it", False


def _resolve_spec(register: Any, context: dict[str, Any] | None) -> RegisterSpec:
    specs = load_registers()
    if isinstance(register, RegisterSpec):
        return register
    rid = register if isinstance(register, str) and register else select_register(context, specs)
    return specs.get(rid) or specs.get("simple") or next(iter(specs.values()))


def _grouped(plans: list[ClausePlan]) -> list[tuple[str, list[ClausePlan]]]:
    order: list[str] = []
    by_subj: dict[str, list[ClausePlan]] = {}
    for p in plans:
        if p.subject not in by_subj:
            by_subj[p.subject] = []
            order.append(p.subject)
        by_subj[p.subject].append(p)
    return [(s, by_subj[s]) for s in order]


def _flat_subject_sentence(subject: str, plans: list[ClausePlan], grounding: Grounding,
                           spec: RegisterSpec, first_mention: bool) -> str:
    """Assemble one subject's facts into one or more sentences per the register spec — the FLAT/
    aggregated planner (one clause per bone, is_a always the copular head). This is the baseline the
    clause-combining planner is gated against; every non-combining register uses it unchanged."""
    # --- split the subject's plans into: copular head (is_a + adjectives), reduced-capable, other ---
    noun = next((_obj(p) for p in plans if p.relation in ("is_a", "instance_of")), None)
    adjs = [_obj(p) for p in plans if p.relation == "has_property"]
    reduced_plans = [p for p in plans if p.reduced_form and p.relation not in ("is_a", "instance_of")]
    consumed = {id(p) for p in plans if p.relation in ("is_a", "instance_of", "has_property")}
    # aggregate_reduced=True: fold reduced participles onto the head ("X is a Y, made of Z"). False
    # (conversational): leave them for the continuation, where copy_fill emits each as a full pronoun
    # clause ("it is made of Z") — the same facts, segmented the plainer conversational way.
    if spec.aggregate_reduced:
        consumed |= {id(p) for p in reduced_plans}
    other_plans = [p for p in plans if id(p) not in consumed]

    plural = plans[0].plural
    pron, pron_plural = _pronoun(plural, noun)

    # --- HEAD sentence: subject + aggregated copular NP (+ reduced clauses attached or fronted) ------
    reduced_surfaces = ([rs for rs in (realize_reduced(p, grounding) for p in reduced_plans) if rs]
                        if spec.aggregate_reduced else [])
    head = _head_clause(subject, noun, adjs, plural, grounding, other_plans)
    if head is None:
        return ""                                          # nothing grounded -> abstain

    fronted = ""
    if spec.front_reduced and reduced_surfaces and noun is not None:
        fronted = reduced_surfaces.pop(0)                  # "Located in Germany, Einstein is ..."
    head_sentence = (f"{_cap(fronted)}, {head}" if fronted else head)
    for rs in reduced_surfaces:
        head_sentence += ", " + rs

    # continuation plans = the non-head, non-reduced clauses (the ones frame_realizer would ", and")
    cont_plans = [p for p in other_plans if not (p.relation in ("is_a", "instance_of"))]
    # if there was no copular noun, the first "other" plan already became the head — drop it
    if noun is None and cont_plans:
        cont_plans = cont_plans[1:]

    sentences = [head_sentence]
    ref = pron if spec.pronoun_after_first else subject
    sentences += _continuation_sentences(cont_plans, grounding, spec, ref, pron_plural)
    return " ".join(_cap(s.strip().rstrip(".")) + "." for s in sentences if s.strip())


# connectives that COORDINATE a subjectless verb phrase ("... , and have a famous equation").
# Everything else keeps a subject ("... , which is why they have a famous equation").
_DROP_SUBJECT_CONN = {"and", "as well as"}


def _continuation_sentences(plans: list[ClausePlan], grounding: Grounding, spec: RegisterSpec,
                            ref: str, ref_plural: bool) -> list[str]:
    """Group continuation clauses into sentences of `max_clauses_per_sentence`, varying the
    connective within/across a sentence and (explanatory) opening with a discourse connective."""
    # realize each clause once WITH the subject ref and correct agreement (so 'they have', not
    # 'they has'); additional clauses in the same sentence either drop the subject (coordinating
    # connective) or keep it (subjectful connective) — never invented, only function words added.
    clauses = [copy_fill(p, grounding, subject_ref=ref, agree_plural=ref_plural) for p in plans]
    clauses = [c for c in clauses if c]                    # drop abstained (ungrounded) clauses
    per = max(1, spec.max_clauses_per_sentence)
    out: list[str] = []
    conn_i = 0
    made = 0
    for i in range(0, len(clauses), per):
        group = clauses[i:i + per]
        parts = [group[0]]                                 # first clause keeps the subject ref
        for c in group[1:]:
            conn = _pick(spec.connective_pool, conn_i) or "and"
            conn_i += 1
            body = _drop_lead(c) if conn in _DROP_SUBJECT_CONN else c
            parts.append(f"{conn} {body}")
        sent = ", ".join(parts)
        if spec.opener_pool:
            opener = _pick(spec.opener_pool, made)
            if opener:
                sent = f"{opener}, {_lower_first(sent)}"
        out.append(sent)
        made += 1

    # conversational discourse-marker openers ("So, ...", "Now, ...") — applied BOUNDEDLY: never on a
    # lone continuation sentence, at most _MAX_DISCOURSE_MARKERS per block, spaced every other sentence
    # and varied across the pool. This is the anti-"forced marker" bound: a marker is a natural aside,
    # not a tic stamped on every line. Markers are function words (no content), so faithfulness holds.
    markers = spec.discourse_marker_pool
    if markers and len(out) >= 2:
        cap = min(len(markers), _MAX_DISCOURSE_MARKERS, (len(out) + 1) // 2)
        placed = 0
        for idx in range(0, len(out), 2):
            if placed >= cap:
                break
            out[idx] = f"{markers[placed % len(markers)]}, {out[idx]}"
            placed += 1
    return out


# ── helpers ───────────────────────────────────────────────────────────────────────────────────────
def _obj(plan: ClausePlan) -> str:
    for s in plan.slots():
        if s.role == "OBJ":
            return s.value
    return ""


def _head_clause(subject: str, noun: str | None, adjs: list[str], plural: bool,
                 grounding: Grounding, other_plans: list[ClausePlan]) -> str | None:
    """Build the head sentence stem. Copular head when there is an is_a; otherwise the first grounded
    'other' clause. Copy-gated: content pieces must trace to the grounding."""
    if noun is not None and grounding.has(noun):
        good_adjs = [fr._proper(a) for a in adjs if grounding.has(a)]
        head_noun = fr._pluralize(noun) if plural else noun
        np = " ".join(good_adjs + [head_noun]) if good_adjs else head_noun
        cop = "are" if plural else "is"
        det = "" if plural else fr._det(np) + " "
        return f"{subject} {cop} {det}{np}".replace("  ", " ").strip()
    # no copular noun: use the first grounded 'other' clause as the head
    for p in other_plans:
        s = copy_fill(p, grounding, subject_ref=subject)
        if s:
            return s
    return None


def _pick(pool: tuple[str, ...], index: int) -> str:
    if not pool:
        return ""
    return pool[index % len(pool)]


def _drop_lead(clause: str) -> str:
    return re.sub(r"^(it|they|he|she|[A-Z][\w'-]*)\s+", "", clause).strip()


def _cap(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


def _lower_first(s: str) -> str:
    # lowercase the leading pronoun after a discourse opener ("In addition, it can ..."); keep a
    # proper name's capital.
    if not s:
        return s
    first = s.split(" ", 1)[0]
    if first in ("It", "They", "He", "She"):
        return s[0].lower() + s[1:]
    return s


# ══ the CLAUSE-COMBINING planner (R4 next lever) ════════════════════════════════════════════════════
# Deeper fluency than the register surface (contractions/markers) needs syntactic RE-PACKAGING: the flat
# planner emits one clause per bone with is_a always the copular head ("X is a Y. It is made of Z. It can
# W."), so the "It … It … It …" parallel signature and a flat clause count are its ceiling. This layer
# combines a subject's bones into VARIED structure — apposition (demote is_a to a nominal modifier so a
# real predicate becomes the main clause), coordination (join same-subject predicates), relative
# subordination ("… a Y that can W") — but a wrong combination is worse than a flat clause, so EVERY
# combined sentence is FAITHFULNESS-GATED against the flat baseline and rejected -> flat on any failure.
#
# Faithful by construction AND by gate: the appositive is always the subject's own is_a predicate-nominal
# and every predicate is rendered by copy_fill (which preserves each bone's s/o roles and the copy gate),
# so no relationship the bones don't state can be invented and no subject/object role can be swapped. The
# gate is defense-in-depth on top of that: (1) the faithfulness verifier must read 1.0 (no fabricated
# content token), (2) the combined content-token multiset must EQUAL the flat baseline's (no fact added
# or dropped), (3) the sentence must not run on (readability bound). Any failure -> the flat clause stands.

_MAIN_PROMOTABLE = ("capable_of", "has_a")   # predicates that read cleanly as a main VP after an appositive
_COMBINE_MAX_SENTENCE_WORDS = 26             # an appositive/relative sentence longer than this -> reject
_COMBINE_MAX_CONNECTIVES = 3                 # mirrors verifier.MAX_CONNECTIVES (the run-on hard floor)
_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_CONN_RE = re.compile(
    r"\b(?:and|but|or|so|yet|nor|because|although|though|while|which|that|when|since|as)\b", re.I)


def _subject_sentence(subject: str, plans: list[ClausePlan], grounding: Grounding,
                      spec: RegisterSpec, first_mention: bool) -> tuple[str, str]:
    """Realize one subject's facts, returning (text, structure_label). structure_label is
    'apposition' | 'relative' when a combined structure was ADOPTED, else 'flat' (combining off, not
    applicable, or the combination was rejected by the faithfulness gate and the flat clause stands)."""
    flat = _flat_subject_sentence(subject, plans, grounding, spec, first_mention)
    if not spec.combine or not flat:
        return flat, "flat"
    return _composed_subject_sentence(subject, plans, grounding, spec, flat)


def _composed_subject_sentence(subject: str, plans: list[ClausePlan], grounding: Grounding,
                               spec: RegisterSpec, flat: str) -> tuple[str, str]:
    """Try to re-package this subject's bones into a varied structure; gate against `flat`."""
    noun = next((_obj(p) for p in plans if p.relation in ("is_a", "instance_of")), None)
    if noun is None or not grounding.has(noun):
        return flat, "flat"                            # no copular head to demote -> nothing to combine
    adjs = [_obj(p) for p in plans if p.relation == "has_property"]
    reduced_plans = [p for p in plans if p.reduced_form and p.relation not in ("is_a", "instance_of")]
    main_plans = [p for p in plans if p.relation in _MAIN_PROMOTABLE]
    if not main_plans:
        return flat, "flat"                            # no predicate to promote -> don't force (bound)

    plural = plans[0].plural
    pron, pron_plural = _pronoun(plural, noun)

    # RELATIVE niche — is_a (+adjectives) + exactly ONE capability, nothing else combinable: subordinate
    # the capability as a restrictive relative clause ("Mice are small rodents that can climb."). Reserved
    # for this clean shape so the "that"-clause never attaches ambiguously after a reduced modifier.
    if (spec.relativize and not reduced_plans and len(main_plans) == 1
            and main_plans[0].relation == "capable_of"):
        rel = _relative_sentence(subject, noun, adjs, plural, grounding, main_plans[0], pron_plural)
        if rel and _accept_combined(rel, flat, grounding):
            return rel, "relative"

    if not spec.appose_is_a:
        return flat, "flat"

    # APPOSITION — "Subject, <appositive NP [reduced]>, <main VP [and VP]>." + continuation for the rest.
    np_reduced = realize_reduced(reduced_plans[0], grounding) if reduced_plans else ""
    np = _appositive_np(noun, adjs, plural, grounding, np_reduced)
    if not np:
        return flat, "flat"
    main, used_main = _main_clause(main_plans, grounding, pron_plural, spec.combine_max_main)
    if not main:
        return flat, "flat"
    head = f"{_cap(subject)}, {np}, {main}"
    # everything the head consumed: is_a (-> appositive noun), has_property (-> NP adjectives), the
    # first reduced clause (-> NP post-modifier), and the promoted main-VP predicates. EVERYTHING else —
    # extra reduced clauses, un-promoted predicates, AND unknown-relation bones — goes to the
    # continuation so no fact is dropped (a dropped fact would fail the content-multiset gate anyway).
    consumed_ids = {id(p) for p in plans if p.relation in ("is_a", "instance_of", "has_property")}
    consumed_ids |= {id(p) for p in used_main}
    if reduced_plans:
        consumed_ids.add(id(reduced_plans[0]))         # the NP consumed the first reduced clause
    cont_plans = [p for p in plans if id(p) not in consumed_ids]
    ref = pron if spec.pronoun_after_first else subject
    cont = _continuation_sentences(cont_plans, grounding, spec, ref, pron_plural)
    candidate = " ".join(_cap(s.strip().rstrip(".")) + "." for s in ([head] + cont) if s.strip())
    if _accept_combined(candidate, flat, grounding):
        return candidate, "apposition"
    return flat, "flat"                                # combination failed the gate -> flat clause stands


def _appositive_np(noun: str, adjs: list[str], plural: bool, grounding: Grounding,
                   reduced_surface: str) -> str:
    """The appositive noun phrase: det + proper-cased adjectives + (pluralized) noun + an optional
    reduced post-modifier ("a playful mammal located in rivers", "flightless birds", "an ancient mass
    made of ice"). Copy-gated: only grounded adjectives/noun survive; the reduced surface is already
    copy-gated by realize_reduced."""
    good_adjs = [fr._proper(a) for a in adjs if grounding.has(a)]
    head_noun = fr._pluralize(noun) if plural else noun
    np = " ".join(good_adjs + [head_noun]) if good_adjs else head_noun
    det = "" if plural else fr._det(np) + " "
    core = f"{det}{np}".replace("  ", " ").strip()
    if reduced_surface:
        core = f"{core} {reduced_surface}"
    return core


def _main_clause(main_plans: list[ClausePlan], grounding: Grounding, plural: bool,
                 max_main: int) -> tuple[str | None, list[ClausePlan]]:
    """Coordinate up to `max_main` promotable predicates into one subjectless main VP ("can whistle and
    has a spout", "can rotate and slide"). Each tail is copy_fill'd with the subject dropped (still not
    invented — a function-word drop). Consecutive same-auxiliary VPs share the auxiliary ("can W1 and
    W2", "has a X and a Y"). Returns (main_vp, plans_consumed)."""
    tails: list[str] = []
    used: list[ClausePlan] = []
    for p in main_plans:
        if len(tails) >= max_main:
            break
        t = copy_fill(p, grounding, subject_ref="", agree_plural=plural)   # subjectless VP tail
        if not t:
            continue                                    # ungrounded -> abstain this predicate
        tails.append(t)
        used.append(p)
    if not tails:
        return None, []
    joined = tails[0]
    prev_can = tails[0].startswith("can ")
    prev_have = tails[0].startswith(("has ", "have "))
    for t in tails[1:]:
        body = t
        if t.startswith("can ") and prev_can:
            body = t[4:]                                # share the modal: "can whistle and rotate"
        elif t.startswith("has ") and prev_have:
            body = t[4:]                                # share have: "has a river and a lamp"
        elif t.startswith("have ") and prev_have:
            body = t[5:]
        joined += " and " + body
        prev_can = t.startswith("can ")
        prev_have = t.startswith(("has ", "have "))
    return joined, used


def _relative_sentence(subject: str, noun: str, adjs: list[str], plural: bool, grounding: Grounding,
                       cap_plan: ClausePlan, plural_verb: bool) -> str:
    """A relative-clause combination: "Subject is/are det <adjs> <noun> that <can W>." Keeps is_a as the
    main copula and subordinates the capability. Copy-gated throughout."""
    good_adjs = [fr._proper(a) for a in adjs if grounding.has(a)]
    head_noun = fr._pluralize(noun) if plural else noun
    np = " ".join(good_adjs + [head_noun]) if good_adjs else head_noun
    tail = copy_fill(cap_plan, grounding, subject_ref="", agree_plural=plural_verb)   # "can climb"
    if not tail:
        return ""
    cop = "are" if plural else "is"
    det = "" if plural else fr._det(np) + " "
    return f"{_cap(subject)} {cop} {det}{np} that {tail}.".replace("  ", " ")


def _accept_combined(candidate: str, flat: str, grounding: Grounding) -> bool:
    """The faithfulness gate: accept a combined surface ONLY if it (1) reads 1.0 on the faithfulness
    verifier (no fabricated content token), (2) carries the EXACT same content-token multiset as the flat
    baseline (no fact added or dropped), and (3) does not run on (readability bound). Any failure -> the
    combination is rejected and the caller falls back to the flat clause."""
    if not candidate.strip():
        return False
    from packages.fluency.fluency_v1 import faithfulness  # lazy: avoids the fluency_v1<->realizer cycle
    faith, fab = faithfulness(candidate, grounding)
    if faith < 1.0 or fab:                              # (1) nothing invented
        return False
    if _content_multiset(candidate) != _content_multiset(flat):   # (2) exact fact set preserved
        return False
    for s in _sentences(candidate):                    # (3) readability: no run-on
        if len(_WORD_RE.findall(s)) > _COMBINE_MAX_SENTENCE_WORDS:
            return False
        if len(_CONN_RE.findall(s)) > _COMBINE_MAX_CONNECTIVES:
            return False
    return True


def _content_multiset(text: str) -> list[str]:
    """The sorted multiset of CONTENT tokens (non-skeleton function words removed, contractions expanded)
    — the fact carriers. Two surfaces with the same content multiset carry the same fact set."""
    from packages.fluency.fluency_v1 import SKELETON_VOCAB  # lazy: same cycle-avoidance
    toks = _WORD_RE.findall(expand_contractions(text).lower())
    return sorted(t for t in toks if t not in SKELETON_VOCAB)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]


def realize(bones: list, register: Any = None, context: dict[str, Any] | None = None) -> str:
    """Bones (list of [s, r, o]) -> fluent, faithful, copy-safe English in the selected register.
    `register` may be a register id, a RegisterSpec, or None (selected from `context`, default
    'simple'). Empty bones -> ''."""
    return _realize_core(bones, register, context)[0]


def realize_with_trace(bones: list, register: Any = None,
                       context: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    """As :func:`realize`, plus the per-subject clause-structure labels ('apposition' | 'relative' |
    'flat') — the combination fire-trace, so a caller can measure how often a combination was ADOPTED
    vs fell back to the flat clause. HONEST reporting surface; not used by the answer path."""
    return _realize_core(bones, register, context)


def _realize_core(bones: list, register: Any,
                  context: dict[str, Any] | None) -> tuple[str, list[str]]:
    if not bones:
        return "", []
    plans = delexicalize(bones)
    if not plans:
        return "", []
    grounding = Grounding.from_bones(bones)
    spec = _resolve_spec(register, context)
    sentences: list[str] = []
    structures: list[str] = []
    for i, (subject, subj_plans) in enumerate(_grouped(plans)):
        s, structure = _subject_sentence(subject, subj_plans, grounding, spec, first_mention=(i == 0))
        if s:
            sentences.append(s)
            structures.append(structure)
    text = " ".join(sentences).strip()
    # conversational contraction pass — a FORM-only rewrite of copula/aux function words ("it is" ->
    # "it's"). It touches no content word, so the fact set is byte-for-byte preserved (verified by the
    # faithfulness gate, which expands contractions before scoring).
    if spec.contractions:
        text = contract(text)
    return text, structures
