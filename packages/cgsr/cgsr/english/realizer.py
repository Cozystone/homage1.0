"""English canonical realization with evidence and slot gates."""

from __future__ import annotations

import re
from typing import Any

from .canonical_frames import CanonicalAnswerPlan, EnglishConstructionFrame, RealizedAnswer
from .construction_patterns import frame_by_family


NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)*(?:%|GB|GiB|ms|s|개|건)?\b")


def _claim_for_family(plan: CanonicalAnswerPlan, family: str) -> dict[str, Any]:
    for claim in plan.claims:
        if str(claim.get("family") or "") == family:
            return claim
    for claim in plan.claims:
        if str(claim.get("intent") or "") == plan.intent:
            return claim
    return plan.claims[0] if plan.claims else {}


def fill_slots(frame: EnglishConstructionFrame, claim: dict[str, Any], plan: CanonicalAnswerPlan) -> dict[str, str]:
    """Fill construction slots from a graph-grounded claim."""

    slots: dict[str, str] = {}
    for slot in frame.slots:
        value = claim.get(slot)
        if value is None and slot == "evidence_ref" and plan.evidence_refs:
            value = plan.evidence_refs[0]
        if value is None and slot == "uncertainty":
            value = plan.uncertainty
        if value is not None:
            slots[slot] = str(value)
    return slots


def unsupported_slots(frame: EnglishConstructionFrame, slots: dict[str, str], plan: CanonicalAnswerPlan) -> list[str]:
    """Return unsupported or missing slot names."""

    missing = [slot for slot in frame.required_slots if not slots.get(slot)]
    unsupported = list(missing)
    if frame.evidence_required and not plan.evidence_refs:
        unsupported.append("evidence_ref")
    return sorted(set(unsupported))


def realize_frame(frame: EnglishConstructionFrame, slots: dict[str, str]) -> str:
    """Render a single English frame from already verified slots."""

    safe_slots = {slot: slots.get(slot, "") for slot in frame.slots}
    text = frame.surface_template.format(**safe_slots)
    return re.sub(r"\s+", " ", text).strip()


def realize_answer_plan(plan: CanonicalAnswerPlan) -> RealizedAnswer:
    """Realize a grounded answer plan without inventing new claims."""

    if plan.language != "en":
        raise ValueError("English realizer requires an English canonical plan")
    used_frames: list[str] = []
    filled: dict[str, str] = {}
    unsupported: list[str] = []
    parts: list[str] = []
    for family in plan.discourse_order:
        frame = frame_by_family(family)
        claim = _claim_for_family(plan, family)
        slots = fill_slots(frame, claim, plan)
        unsupported.extend(unsupported_slots(frame, slots, plan))
        if unsupported:
            continue
        text = realize_frame(frame, slots)
        parts.append(text)
        used_frames.append(frame.frame_id)
        filled.update(slots)
    if not parts:
        frame = frame_by_family("abstention")
        slots = {"x": plan.intent or "this question"}
        parts.append(realize_frame(frame, slots))
        used_frames.append(frame.frame_id)
        filled.update(slots)
    text = " ".join(parts)
    return RealizedAnswer(
        language="en",
        text=text,
        used_frames=used_frames,
        filled_slots=filled,
        evidence_refs=list(plan.evidence_refs),
        unsupported_claims=sorted(set(unsupported)),
        entity_locks=sorted(str(value) for value in plan.glossary_terms.values() if value),
        number_locks=NUMBER_RE.findall(text),
        trace_hidden=True,
    )
