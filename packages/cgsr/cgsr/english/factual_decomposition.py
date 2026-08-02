"""Deterministic English factual decomposition for narrow CGSR quality slices."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Iterable


GENERIC_PREDICATES = {"be", "is", "are", "was", "were", "have", "has", "do", "use"}
SPECIFIC_VERBS = {
    "add": "added",
    "adds": "adds",
    "added": "added",
    "automate": "automates",
    "automates": "automates",
    "avoid": "avoids",
    "avoiding": "avoiding",
    "enable": "enables",
    "enables": "enables",
    "increase": "increases",
    "increases": "increases",
    "introduce": "introduced",
    "introduces": "introduced",
    "introduced": "introduced",
    "package": "packages",
    "packages": "packages",
    "prevent": "prevents",
    "prevents": "prevents",
    "provide": "provides",
    "provides": "provides",
    "reduce": "reduces",
    "reduces": "reduces",
    "release": "released",
    "released": "released",
    "support": "supports",
    "supports": "supports",
}
NOISE_PREFIXES = {"however", "therefore", "because", "although"}


@dataclass(frozen=True)
class EnglishFactualFrame:
    """Source-grounded factual structure extracted from one English sentence."""

    sentence: str
    relation_type: str
    subject: str
    predicate: str
    object: str = ""
    complement: str = ""
    purpose: str = ""
    domain: str = ""
    compared_to: str = ""
    dimension: str = ""
    effect: str = ""
    mechanism: str = ""
    evidence_id: str | None = None
    confidence: float = 0.0
    unsupported_claims: list[str] = field(default_factory=list)
    false_confident: int = 0

    def __post_init__(self) -> None:
        if self.confidence < 0.0 or self.confidence > 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EnglishQualityScores:
    """Deterministic quality scores for extracted English factual frames."""

    specific_predicate_score: float
    argument_completeness_score: float
    relation_type_score: float
    generic_predicate_penalty: float
    unsupported_claim_penalty: float

    @property
    def total(self) -> float:
        value = (
            self.specific_predicate_score
            + self.argument_completeness_score
            + self.relation_type_score
            - self.generic_predicate_penalty
            - self.unsupported_claim_penalty
        ) / 3.0
        return round(max(0.0, min(1.0, value)), 4)

    def to_dict(self) -> dict[str, float]:
        payload = asdict(self)
        payload["total"] = self.total
        return payload


@dataclass(frozen=True)
class EnglishDecompositionResult:
    frame: EnglishFactualFrame | None
    quality: EnglishQualityScores
    abstained: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame.to_dict() if self.frame else None,
            "quality": self.quality.to_dict(),
            "abstained": self.abstained,
            "reason": self.reason,
        }


def _clean_text(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:-1].strip() if text.endswith(".") else text


def _clean_phrase(value: str) -> str:
    text = _clean_text(value)
    text = re.sub(r"^(an|a|the)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ,;:")
    return text


def _subject(value: str) -> str:
    text = _clean_phrase(value)
    parts = text.split()
    while parts and parts[0].casefold().strip(",") in NOISE_PREFIXES:
        parts.pop(0)
    return " ".join(parts).strip(" ,;:")


def _bounded(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _confidence(*parts: str, base: float) -> float:
    filled = sum(1 for part in parts if part)
    return _bounded(base + min(0.1, filled * 0.015))


def _definition(sentence: str, evidence_id: str | None) -> EnglishFactualFrame | None:
    match = re.match(
        r"^(?P<subject>.+?)\s+is\s+(?:an|a|the)?\s*(?P<complement>.+?)(?:\s+for\s+(?P<purpose>.+))?$",
        sentence,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    subject = _subject(match.group("subject"))
    complement = _clean_phrase(match.group("complement"))
    purpose = _clean_phrase(match.group("purpose") or "")
    domain = ""
    if purpose:
        domain_match = re.search(r"\bof\s+(.+)$", purpose, flags=re.IGNORECASE)
        if domain_match:
            domain = _clean_phrase(domain_match.group(1))
    if not subject or not complement:
        return None
    return EnglishFactualFrame(
        sentence=sentence,
        relation_type="definition",
        subject=subject,
        predicate="is",
        complement=complement,
        object=complement,
        purpose=purpose,
        domain=domain,
        evidence_id=evidence_id,
        confidence=_confidence(subject, complement, purpose, base=0.86),
    )


def _comparison(sentence: str, evidence_id: str | None) -> EnglishFactualFrame | None:
    match = re.match(
        r"^(?P<subject>.+?)\s+(?P<verb>provides|offers|has)\s+(?P<direction>more|less)\s+(?P<dimension>.+?)\s+than\s+(?P<target>.+)$",
        sentence,
        flags=re.IGNORECASE,
    )
    if match:
        subject = _subject(match.group("subject"))
        direction = match.group("direction").casefold()
        dimension = _clean_phrase(match.group("dimension"))
        target = _clean_phrase(match.group("target"))
        return EnglishFactualFrame(
            sentence=sentence,
            relation_type="comparison",
            subject=subject,
            predicate=f"{match.group('verb').casefold()}_{direction}_than",
            object=dimension,
            compared_to=target,
            dimension=dimension,
            evidence_id=evidence_id,
            confidence=_confidence(subject, dimension, target, base=0.88),
        )
    match = re.match(
        r"^(?P<subject>.+?)\s+is\s+(?P<dimension>faster|slower|larger|smaller|safer|riskier)\s+than\s+(?P<target>.+)$",
        sentence,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    subject = _subject(match.group("subject"))
    dimension = _clean_phrase(match.group("dimension"))
    target = _clean_phrase(match.group("target"))
    return EnglishFactualFrame(
        sentence=sentence,
        relation_type="comparison",
        subject=subject,
        predicate=f"is_{dimension}_than",
        object=dimension,
        compared_to=target,
        dimension=dimension,
        evidence_id=evidence_id,
        confidence=_confidence(subject, dimension, target, base=0.86),
    )


def _cause_effect(sentence: str, evidence_id: str | None) -> EnglishFactualFrame | None:
    match = re.match(
        r"^(?P<cause>.+?)\s+(?P<verb>reduces|increases|enables|prevents)\s+(?P<effect>.+?)\s+by\s+(?P<mechanism>.+)$",
        sentence,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.match(
            r"^(?P<cause>.+?)\s+(?P<verb>reduces|increases|enables|prevents)\s+(?P<effect>.+?)\s+(?:because|due to)\s+(?P<mechanism>.+)$",
            sentence,
            flags=re.IGNORECASE,
        )
    if not match:
        return None
    cause = _subject(match.group("cause"))
    effect = _clean_phrase(match.group("effect"))
    mechanism = _clean_phrase(match.group("mechanism"))
    predicate = SPECIFIC_VERBS.get(match.group("verb").casefold(), match.group("verb").casefold())
    return EnglishFactualFrame(
        sentence=sentence,
        relation_type="cause_effect",
        subject=cause,
        predicate=predicate,
        object=effect,
        effect=effect,
        mechanism=mechanism,
        evidence_id=evidence_id,
        confidence=_confidence(cause, effect, mechanism, base=0.87),
    )


def _temporal(sentence: str, evidence_id: str | None) -> EnglishFactualFrame | None:
    match = re.match(
        r"^(?P<subject>.+?)\s+(?P<verb>introduced|added|released)\s+(?P<object>.+)$",
        sentence,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    subject = _subject(match.group("subject"))
    obj = _clean_phrase(match.group("object"))
    predicate = SPECIFIC_VERBS.get(match.group("verb").casefold(), match.group("verb").casefold())
    return EnglishFactualFrame(
        sentence=sentence,
        relation_type="temporal_fact",
        subject=subject,
        predicate=predicate,
        object=obj,
        evidence_id=evidence_id,
        confidence=_confidence(subject, obj, base=0.86),
    )


def _svo(sentence: str, evidence_id: str | None) -> EnglishFactualFrame | None:
    match = re.match(
        r"^(?P<subject>.+?)\s+(?P<verb>packages|supports|manages|contains|includes|stores|records|tracks|validates|verifies|connects)\s+(?P<object>.+?)(?:\s+into\s+(?P<destination>.+))?$",
        sentence,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    subject = _subject(match.group("subject"))
    obj = _clean_phrase(match.group("object"))
    destination = _clean_phrase(match.group("destination") or "")
    predicate = SPECIFIC_VERBS.get(match.group("verb").casefold(), match.group("verb").casefold())
    return EnglishFactualFrame(
        sentence=sentence,
        relation_type="svo_fact",
        subject=subject,
        predicate=predicate,
        object=obj,
        domain=destination,
        evidence_id=evidence_id,
        confidence=_confidence(subject, obj, destination, base=0.84),
    )


PARSERS = (_comparison, _cause_effect, _temporal, _svo, _definition)


def score_frame(frame: EnglishFactualFrame | None) -> EnglishQualityScores:
    if frame is None:
        return EnglishQualityScores(0.0, 0.0, 0.0, 0.0, 0.0)
    predicate_generic = frame.predicate.casefold() in GENERIC_PREDICATES
    generic_is_supported_definition = frame.relation_type == "definition" and bool(frame.complement)
    specific_predicate_score = 0.7 if predicate_generic and generic_is_supported_definition else (0.0 if predicate_generic else 1.0)
    required_arguments = [frame.subject, frame.object or frame.complement]
    if frame.relation_type == "comparison":
        required_arguments.extend([frame.compared_to, frame.dimension])
    if frame.relation_type == "cause_effect":
        required_arguments.extend([frame.effect, frame.mechanism])
    argument_completeness_score = sum(1 for item in required_arguments if item) / max(1, len(required_arguments))
    relation_type_score = 1.0 if frame.relation_type in {"definition", "svo_fact", "comparison", "cause_effect", "temporal_fact"} else 0.0
    generic_predicate_penalty = 0.1 if predicate_generic and generic_is_supported_definition else (0.5 if predicate_generic else 0.0)
    unsupported_claim_penalty = 1.0 if frame.unsupported_claims else 0.0
    return EnglishQualityScores(
        specific_predicate_score=_bounded(specific_predicate_score),
        argument_completeness_score=_bounded(argument_completeness_score),
        relation_type_score=_bounded(relation_type_score),
        generic_predicate_penalty=_bounded(generic_predicate_penalty),
        unsupported_claim_penalty=_bounded(unsupported_claim_penalty),
    )


def decompose_english_fact(sentence: str, *, evidence_id: str | None = None) -> EnglishDecompositionResult:
    """Extract one narrow, source-grounded English factual frame.

    The parser uses explicit patterns only. If no supported pattern matches, it
    abstains instead of inventing unsupported relations.
    """

    cleaned = _clean_text(sentence)
    if not cleaned:
        return EnglishDecompositionResult(None, score_frame(None), True, "empty_sentence")
    if "?" in cleaned:
        return EnglishDecompositionResult(None, score_frame(None), True, "not_fact_statement_shape")
    for parser in PARSERS:
        frame = parser(cleaned, evidence_id)
        if frame is not None:
            return EnglishDecompositionResult(frame, score_frame(frame), False)
    return EnglishDecompositionResult(None, score_frame(None), True, "not_fact_statement_shape")


def evaluate_fixture_set(sentences: Iterable[str]) -> dict[str, Any]:
    results = [decompose_english_fact(sentence) for sentence in sentences]
    frames = [result.frame for result in results if result.frame is not None]
    generic_count = sum(1 for frame in frames if frame and frame.predicate.casefold() in GENERIC_PREDICATES)
    return {
        "fixture_count": len(results),
        "parsed_count": len(frames),
        "generic_predicate_ratio": round(generic_count / max(1, len(frames)), 4),
        "specific_predicate_count": sum(1 for frame in frames if frame and frame.predicate.casefold() not in GENERIC_PREDICATES),
        "comparison_extraction_count": sum(1 for frame in frames if frame and frame.relation_type == "comparison"),
        "cause_effect_extraction_count": sum(1 for frame in frames if frame and frame.relation_type == "cause_effect"),
        "unsupported_claims": sum(len(frame.unsupported_claims) for frame in frames if frame),
        "false_confident": sum(frame.false_confident for frame in frames if frame),
        "abstained_count": sum(1 for result in results if result.abstained),
    }
