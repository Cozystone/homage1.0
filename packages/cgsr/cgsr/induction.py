"""Frequency-based construction induction for CGSR Stage 1."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import re
from typing import Iterable

from .canonicalize import canonicalize, dedupe_constructions, family_id
from .models import ConstructionCandidate
from .morphology import analyze


def _slot_for(form: str, tag: str) -> str:
    if tag.startswith("N") or tag in {"SL", "SN"}:
        return "SLOT:NOUN"
    if tag.startswith("V") or tag == "XR":
        return "SLOT:PREDICATE"
    return form


def _candidate_id(surface: tuple[str, ...], tags: tuple[str, ...]) -> str:
    payload = "|".join(surface) + "::" + "|".join(tags)
    return "cx_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _candidate_from_ngram(surface: tuple[str, ...], tags: tuple[str, ...], examples: list[str], frequency: int) -> ConstructionCandidate:
    abstract = tuple(_slot_for(form, tag) for form, tag in zip(surface, tags))
    candidate = ConstructionCandidate(
        construction_id=_candidate_id(surface, tags),
        surface_pattern=surface,
        tag_pattern=tags,
        abstract_pattern=abstract,
        examples=examples[:5],
        frequency=frequency,
    )
    candidate.canonical_form = canonicalize(candidate)
    return candidate


def induce_constructions(
    sentences: Iterable[str],
    *,
    min_frequency: int = 2,
    min_n: int = 2,
    max_n: int = 6,
    dedupe: bool = True,
) -> list[ConstructionCandidate]:
    """Induce construction candidates from POS/morpheme n-grams.

    This is a transparent Stage 1 baseline, not a full TSG/Adaptor Grammar
    learner.  It promotes frequent contiguous morpheme/POS patterns and then
    optionally merges canonical near-duplicates.
    """

    counts: Counter[tuple[tuple[str, ...], tuple[str, ...]]] = Counter()
    examples: dict[tuple[tuple[str, ...], tuple[str, ...]], list[str]] = defaultdict(list)
    for sentence in sentences:
        morphs = analyze(sentence)
        forms = [m.form for m in morphs if m.form.strip()]
        tags = [m.tag for m in morphs if m.form.strip()]
        for n in range(min_n, max_n + 1):
            for start in range(0, max(0, len(forms) - n + 1)):
                surface = tuple(forms[start : start + n])
                tag_pattern = tuple(tags[start : start + n])
                key = (surface, tag_pattern)
                counts[key] += 1
                if len(examples[key]) < 5:
                    examples[key].append(sentence)
    candidates = [
        _candidate_from_ngram(surface, tags, examples[(surface, tags)], frequency)
        for (surface, tags), frequency in counts.items()
        if frequency >= min_frequency
    ]
    candidates.sort(key=lambda row: (-row.frequency, row.canonical_form, row.construction_id))
    if not dedupe:
        return candidates
    return sorted(dedupe_constructions(candidates), key=lambda row: (-row.frequency, row.canonical_form, row.family_id))


CASE_MAP = {
    "JKS": "SUBJ",
    "JX": "TOPIC",
    "JKO": "OBJ",
    "JKB": "ADVL",
}


def _is_argument_token(tag: str) -> bool:
    return tag.startswith("N") or tag in {"SL", "SN", "XR"}


def _predicate_lemma(forms: list[str], tags: list[str], idx: int) -> str:
    form = forms[idx]
    tag = tags[idx]
    if tag in {"XSV", "XSA"} and idx > 0 and _is_argument_token(tags[idx - 1]):
        return forms[idx - 1] + "하다"
    if tag.startswith("VV") or tag.startswith("VA"):
        return form + "다" if not form.endswith("다") else form
    return ""


def _argument_before(forms: list[str], tags: list[str], case_idx: int) -> str:
    parts: list[str] = []
    idx = case_idx - 1
    while idx >= 0 and _is_argument_token(tags[idx]):
        parts.append(forms[idx])
        idx -= 1
    return " ".join(reversed(parts)).strip()


_DATE_UNIT_HEAD = re.compile(r"^\d*\s*(일|월|년|시|분|초|세기|년대|주|요일)$")


def _argument_head(argument: str) -> str:
    """Return a small lexical head for a case argument.

 Conservative head extraction (last token). Two guards prevent a very common noise class:
 a person-bio subject 'NAME(漢字, 1992 8 28 ~ )' whose LAST token is the birthdate unit
 '' — which made thousands of garbage edges ( IS_A //…). Strip parentheticals and
 date ranges first so the head is the real name, and reject a bare date-unit/number head.
 """

    cleaned = re.sub(r"\([^)]*\)", " ", argument)          # drop parentheticals (漢字, birthdate)
    cleaned = re.sub(r"\d{3,4}\s*년[^~]*~\s*\)?", " ", cleaned)
    tokens = [token for token in cleaned.split() if token.strip()]
    if not tokens:
        return ""
    head = tokens[-1].strip(" )(,.~·]")
    if len(head) < 2:
        return ""
    if _DATE_UNIT_HEAD.match(head) or head.isdigit():        # a date unit / number is not a concept
        return ""
    return head


def _valency_candidate_id(cases: tuple[tuple[str, str], ...], predicate: str) -> str:
    payload = "|".join(f"{role}:{marker}" for role, marker in cases) + "::" + predicate
    return "vcx_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _headed_valency_candidate_id(cases: tuple[tuple[str, str, str], ...], predicate: str) -> str:
    payload = "|".join(f"{role}:{marker}:{head}" for role, marker, head in cases) + "::" + predicate
    return "hvcx_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _canonical_case_token(role: str, marker: str) -> str:
    """Canonicalize surface case alternations while preserving adverbial markers."""

    if role in {"SUBJ", "TOPIC", "OBJ"}:
        return role
    return f"{role}:{marker}"


def _headed_canonical_tokens(cases: tuple[tuple[str, str, str], ...]) -> list[str]:
    """Canonicalize a frame while preserving one concrete argument head.

    Plain valency extraction collapsed many frames into broad TOPIC/OBJ shapes.
    For Stage 2.0 we keep a single core-argument head only when no adverbial
    marker already makes the frame specific.
    """

    tokens = [_canonical_case_token(role, marker) for role, marker, _ in cases]
    if any(role == "ADVL" for role, _, _ in cases):
        return tokens
    target = next((row for row in cases if row[0] == "OBJ" and row[2]), None)
    if target is None:
        target = next((row for row in cases if row[0] in {"SUBJ", "TOPIC"} and row[2]), None)
    if target is not None:
        tokens.append(f"HEAD:{target[2]}")
    return tokens


def _valency_candidate(
    cases: tuple[tuple[str, str], ...],
    predicate: str,
    examples: list[str],
    frequency: int,
) -> ConstructionCandidate:
    surface = tuple([item for role, marker in cases for item in (f"SLOT:{role}", marker)] + [predicate])
    tags = tuple([item for role, _ in cases for item in (f"CASE:{role}", "JOSA")] + ["PREDICATE"])
    abstract = tuple([item for role, _ in cases for item in (f"SLOT:{role}", f"CASE:{role}")] + [f"PREDICATE:{predicate}"])
    canonical = " ".join([_canonical_case_token(role, marker) for role, marker in cases] + [f"PREDICATE:{predicate}"])
    candidate = ConstructionCandidate(
        construction_id=_valency_candidate_id(cases, predicate),
        surface_pattern=surface,
        tag_pattern=tags,
        abstract_pattern=abstract,
        examples=examples[:5],
        frequency=frequency,
        canonical_form=canonical,
        family_id=family_id(canonical),
    )
    return candidate


def _headed_valency_candidate(
    cases: tuple[tuple[str, str, str], ...],
    predicate: str,
    examples: list[str],
    frequency: int,
) -> ConstructionCandidate:
    surface = tuple([item for role, marker, _ in cases for item in (f"SLOT:{role}", marker)] + [predicate])
    tags = tuple([item for role, _, _ in cases for item in (f"CASE:{role}", "JOSA")] + ["PREDICATE"])
    abstract = tuple([item for role, _, _ in cases for item in (f"SLOT:{role}", f"CASE:{role}")] + [f"PREDICATE:{predicate}"])
    canonical = " ".join(_headed_canonical_tokens(cases) + [f"PREDICATE:{predicate}"])
    return ConstructionCandidate(
        construction_id=_headed_valency_candidate_id(cases, predicate),
        surface_pattern=surface,
        tag_pattern=tags,
        abstract_pattern=abstract,
        examples=examples[:5],
        frequency=frequency,
        canonical_form=canonical,
        family_id=family_id(canonical),
    )


def _dedupe_valency_constructions(candidates: list[ConstructionCandidate]) -> list[ConstructionCandidate]:
    """Merge valency candidates without rewriting their case-frame canonical form."""

    merged: dict[str, ConstructionCandidate] = {}
    for candidate in candidates:
        key = candidate.canonical_form
        if key not in merged:
            merged[key] = candidate
            continue
        previous = merged[key]
        previous.frequency += candidate.frequency
        previous.examples = list(dict.fromkeys([*previous.examples, *candidate.examples]))[:5]
    return sorted(merged.values(), key=lambda row: (-row.frequency, row.canonical_form, row.family_id))


def _dedupe_headed_valency_constructions(candidates: list[ConstructionCandidate]) -> list[ConstructionCandidate]:
    """Merge headed valency candidates by their enriched canonical form."""

    return _dedupe_valency_constructions(candidates)


def extract_valency_frames(sentence: str) -> list[tuple[tuple[tuple[str, str], ...], str]]:
    """Extract approximate case/valency frames from Kiwi morpheme output.

    Kiwi does not expose dependency arcs in kiwipiepy 0.23.2.  This function
    therefore uses case particles near noun chunks and the nearest predicate as
    a bounded approximation, not a full dependency parser.
    """

    morphs = analyze(sentence)
    forms = [m.form for m in morphs if m.form.strip()]
    tags = [m.tag for m in morphs if m.form.strip()]
    predicates: list[tuple[int, str]] = []
    case_rows: list[tuple[int, str, str, str]] = []
    for idx, (form, tag) in enumerate(zip(forms, tags)):
        predicate = _predicate_lemma(forms, tags, idx)
        if predicate:
            predicates.append((idx, predicate))
        role = CASE_MAP.get(tag)
        if role is None:
            continue
        if tag == "JX" and form not in {"은", "는"}:
            continue
        argument = _argument_before(forms, tags, idx)
        if argument:
            case_rows.append((idx, role, form, argument))
    frames: list[tuple[tuple[tuple[str, str], ...], str]] = []
    for pred_idx, predicate in predicates:
        nearby = [row for row in case_rows if row[0] < pred_idx]
        if not nearby:
            continue
        nearby = nearby[-3:]
        role_markers: list[tuple[str, str]] = []
        seen_roles: set[str] = set()
        for _, role, marker, _ in nearby:
            if role in seen_roles:
                continue
            seen_roles.add(role)
            role_markers.append((role, marker))
        if role_markers:
            frames.append((tuple(role_markers), predicate))
    return frames


def extract_headed_valency_frames(sentence: str) -> list[tuple[tuple[tuple[str, str, str], ...], str]]:
    """Extract valency frames with one lexical argument head retained.

    The added head is a feedback-driven Stage 2.0 signal.  It is used to test
    whether broad manual-review frames become RHFC-worthy when the extraction
    preserves the concrete object/topic that the predicate acts on.
    """

    morphs = analyze(sentence)
    forms = [m.form for m in morphs if m.form.strip()]
    tags = [m.tag for m in morphs if m.form.strip()]
    predicates: list[tuple[int, str]] = []
    case_rows: list[tuple[int, str, str, str, str]] = []
    for idx, (form, tag) in enumerate(zip(forms, tags)):
        predicate = _predicate_lemma(forms, tags, idx)
        if predicate:
            predicates.append((idx, predicate))
        role = CASE_MAP.get(tag)
        if role is None:
            continue
        if tag == "JX" and form not in {"는", "은"}:
            continue
        argument = _argument_before(forms, tags, idx)
        head = _argument_head(argument)
        if argument:
            case_rows.append((idx, role, form, argument, head))
    frames: list[tuple[tuple[tuple[str, str, str], ...], str]] = []
    for pred_idx, predicate in predicates:
        nearby = [row for row in case_rows if row[0] < pred_idx]
        if not nearby:
            continue
        nearby = nearby[-3:]
        role_markers: list[tuple[str, str, str]] = []
        seen_roles: set[str] = set()
        for _, role, marker, _, head in nearby:
            if role in seen_roles:
                continue
            seen_roles.add(role)
            role_markers.append((role, marker, head))
        if role_markers:
            frames.append((tuple(role_markers), predicate))
    return frames


def induce_valency_constructions(
    sentences: Iterable[str],
    *,
    min_frequency: int = 2,
    dedupe: bool = True,
) -> list[ConstructionCandidate]:
    """Induce case/valency-aware construction candidates.

    This complements the POS n-gram baseline.  It does not implement a full
    dependency parser; it promotes recurrent case-frame + predicate patterns.
    """

    counts: Counter[tuple[tuple[tuple[str, str], ...], str]] = Counter()
    examples: dict[tuple[tuple[tuple[str, str], ...], str], list[str]] = defaultdict(list)
    for sentence in sentences:
        for cases, predicate in extract_valency_frames(sentence):
            key = (cases, predicate)
            counts[key] += 1
            if len(examples[key]) < 5:
                examples[key].append(sentence)
    candidates = [
        _valency_candidate(cases, predicate, examples[(cases, predicate)], frequency)
        for (cases, predicate), frequency in counts.items()
        if frequency >= min_frequency
    ]
    candidates.sort(key=lambda row: (-row.frequency, row.canonical_form, row.construction_id))
    if not dedupe:
        return candidates
    return _dedupe_valency_constructions(candidates)


def induce_headed_valency_constructions(
    sentences: Iterable[str],
    *,
    min_frequency: int = 2,
    dedupe: bool = True,
) -> list[ConstructionCandidate]:
    """Induce valency frames with a concrete core-argument head.

    This is an additive Stage 2.0 experiment for manual-review feedback.  It
    does not replace the Stage 1.95 valency extractor.
    """

    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    representatives: dict[str, tuple[tuple[tuple[str, str, str], ...], str]] = {}
    for sentence in sentences:
        for cases, predicate in extract_headed_valency_frames(sentence):
            key = " ".join(_headed_canonical_tokens(cases) + [f"PREDICATE:{predicate}"])
            counts[key] += 1
            representatives.setdefault(key, (cases, predicate))
            if len(examples[key]) < 5:
                examples[key].append(sentence)
    candidates = [
        _headed_valency_candidate(representatives[key][0], representatives[key][1], examples[key], frequency)
        for key, frequency in counts.items()
        if frequency >= min_frequency
    ]
    candidates.sort(key=lambda row: (-row.frequency, row.canonical_form, row.construction_id))
    if not dedupe:
        return candidates
    return _dedupe_headed_valency_constructions(candidates)
