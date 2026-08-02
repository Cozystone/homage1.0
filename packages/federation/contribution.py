# -*- coding: utf-8 -*-
"""A federation CONTRIBUTION — the unit a self-evolved node offers to the collective.

DOCTRINE (BINDING — constitution 1 + 4): a node federates STRUCTURE, never DATA.
  * ALLOWED payload: a verified SCHEMA (slots/predicates/rules — like an L3-induced state-transition
    schema), a ROUTER-diff (feature-signature -> lane rules), or ORGAN-PARAMs (a small weight vector /
    threshold set). These are the *shape* of an ability — domain-blind, entity-free.
  * FORBIDDEN payload: a corpus, a lived record, a personal/episodic graph, felt-state, ground facts,
    free prose. Shipping those is the exact failure we reject — weight-swallowing (a node's memories
    silently becoming everyone's) AND a privacy leak (another node's life bleeding into yours).

``sanitize()`` is the gate that enforces "structure not data". It REUSES wild_web's PII / harm /
identity gates verbatim (constitution 4), then adds the structure-shape checks the federation needs:
a data-carrying KEY (corpus/lived_record/...), an entity-leaking STRING (a proper noun / place / URL
survives), or an over-long prose STRING all mark the payload as DATA and reject it. Numeric params
(the legitimate content of an organ-param capability) are STRUCTURE and pass — the gate inspects
string content for identity/prose, never a weight array.

Fail-closed: a good contribution wrongly rejected costs one round-trip; a lived record wrongly
promoted is a doctrine breach that cannot be un-shipped.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any

# REUSE wild_web's safety floors verbatim (constitution 4). is_pii/is_harmful are word-boundaried;
# anonymize_wild derives identity from surface cues and substitutes names->SPEAKER_x, places->PLACE,
# urls->URL, digits->N. We treat any surviving SPEAKER_/PLACE/URL marker as an entity leak.
from packages.wild_web.transforms import anonymize_wild, is_harmful, is_pii

# capability kinds the federation understands. A contribution's payload must be one of these SHAPES.
CAPABILITY_KINDS = ("schema", "router", "organ-param")

# ── the "structure not data" shape gate ──────────────────────────────────────────────────────────
# Keys that mark a payload as a CORPUS / LIVED-RECORD / PERSONAL graph rather than a capability shape.
# Their presence is a hard reject: this is precisely the data a node must NEVER federate.
_DATA_CARRYING_KEYS = frozenset({
    "corpus", "facts", "fact", "records", "record", "triples", "triple", "rows",
    "memories", "memory", "episodes", "episode", "episodic", "lived_record", "lived",
    "personal_graph", "personal", "local_graph", "grounding", "groundings",
    "felt_state", "feelings", "hormones", "hormone", "diary", "journal_entries",
    "transcript", "conversation", "dialogue", "history", "documents", "document",
    "raw_text", "raw", "text", "passages", "passage", "examples_text", "samples_text",
    "user", "users", "owner", "profile", "identity", "biography",
})

# Entity markers that anonymize_wild leaves behind when a proper noun / place / URL was present.
# (Deliberately NOT "N": a digit->N substitution is a legitimate numeric param, not an entity.)
_ENTITY_MARKERS = ("SPEAKER_", "PLACE", "URL")

# A structure token (predicate/slot/id/lane name, a compact rule) is SHORT. A long string is prose —
# i.e. smuggled data — even if it happens to carry no proper noun.
_MAX_STRUCT_STR = 200


@dataclass
class SanitizeResult:
    """The verdict of the structure-only gate. ``ok`` is the promote-eligibility precondition."""
    ok: bool
    reasons: list[str] = field(default_factory=list)     # empty iff ok
    inspected_strings: int = 0
    detail: dict[str, Any] = field(default_factory=dict)


def _iter_strings(obj: Any):
    """Yield every string that appears anywhere in ``obj`` — as a dict KEY or as a value. Numbers,
    bools and None are ignored: numeric params are structure, not identity, and are allowed."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                yield k
            yield from _iter_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_strings(v)


def _data_carrying_keys(obj: Any) -> list[str]:
    """Every denylisted corpus/lived-record key that appears anywhere in the payload."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.strip().lower() in _DATA_CARRYING_KEYS:
                hits.append(k)
            hits.extend(_data_carrying_keys(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            hits.extend(_data_carrying_keys(v))
    return hits


def _entity_leak(s: str) -> bool:
    """True iff a proper noun / place / URL survives in ``s`` (via wild_web's anonymizer). A pure
    structure string (lowercase predicate/slot names, operators, ids) is unchanged except digits->N,
    so no SPEAKER_/PLACE/URL marker appears; a leaked name/place/url leaves one behind."""
    anon = anonymize_wild(s)
    return any(m in anon for m in _ENTITY_MARKERS)


def sanitize(payload: Any, provenance: Any = None) -> SanitizeResult:
    """Enforce "structure not data" over a contribution's payload (+ provenance).

    Rejection reasons (a payload may trip several):
      * ``pii``               — a string carries an email or phone (wild_web.is_pii)
      * ``harmful``           — a string reads as harm/abuse (wild_web.is_harmful; moral 0th floor)
      * ``entity_leak``       — a proper noun / place / URL survives a string (wild_web anonymizer)
      * ``data_carrying_key`` — a corpus/lived-record/personal key is present (shape is DATA)
      * ``prose``             — an over-long string: prose, i.e. smuggled data, not a structure token
      * ``empty``             — nothing to federate
    """
    reasons: list[str] = []
    detail: dict[str, Any] = {}

    combined = {"payload": payload, "provenance": provenance}
    strings = list(_iter_strings(combined))
    if payload is None or payload == {} or payload == []:
        return SanitizeResult(ok=False, reasons=["empty"], inspected_strings=0,
                              detail={"note": "no structure to federate"})

    dk = _data_carrying_keys(combined)
    if dk:
        reasons.append("data_carrying_key")
        detail["data_carrying_keys"] = sorted(set(dk))

    pii_hits, harm_hits, ent_hits, prose_hits = [], [], [], []
    for s in strings:
        if is_pii(s):
            pii_hits.append(s[:60])
        if is_harmful(s):
            harm_hits.append(s[:60])
        if _entity_leak(s):
            ent_hits.append(s[:60])
        if len(s) > _MAX_STRUCT_STR:
            prose_hits.append(s[:60])
    if pii_hits:
        reasons.append("pii"); detail["pii"] = pii_hits
    if harm_hits:
        reasons.append("harmful"); detail["harmful"] = harm_hits
    if ent_hits:
        reasons.append("entity_leak"); detail["entity_leak"] = ent_hits
    if prose_hits:
        reasons.append("prose"); detail["prose"] = prose_hits

    return SanitizeResult(ok=not reasons, reasons=reasons,
                          inspected_strings=len(strings), detail=detail)


@dataclass
class Contribution:
    """What one node offers the collective. ``payload`` is STRUCTURE ONLY (see module doctrine).

    ``self_reported_score`` is the node's OWN claim about the capability — recorded for the audit, but
    the sealed judge NEVER uses it to decide promotion (constitution 2: a capability is promoted
    because it reproduces on a developer-blind holdout, not because a node felt it was good).
    """
    node_id: str
    capability_kind: str                                 # schema | router | organ-param
    capability_id: str                                   # stable id (a capability replaces its own id)
    payload: dict[str, Any]                              # STRUCTURE ONLY
    self_reported_score: float = 0.0                     # the node's claim (advisory; never decisive)
    target_suite: str = ""                               # which sealed holdout suite it claims to solve
    provenance: dict[str, Any] = field(default_factory=dict)  # how it evolved (structure/metadata)

    def sanitize(self) -> SanitizeResult:
        """Structure-only + privacy gate over payload + provenance. node_id is an identifier, so it is
        PII/harm-scanned but not entity-scanned (anonymizing an id would destroy identity)."""
        res = sanitize(self.payload, self.provenance)
        nid = str(self.node_id or "")
        if is_pii(nid) or is_harmful(nid):
            res = SanitizeResult(
                ok=False,
                reasons=sorted(set(res.reasons + ["pii_node_id"])),
                inspected_strings=res.inspected_strings,
                detail={**res.detail, "node_id": nid[:60]},
            )
        return res

    def kind_ok(self) -> bool:
        return self.capability_kind in CAPABILITY_KINDS

    def digest(self) -> str:
        """A content digest of the STRUCTURE (payload + kind + id) — the stable identity used in a
        signed generation. Excludes self_reported_score (a claim, not part of the capability)."""
        import hashlib
        canon = json.dumps(
            {"capability_kind": self.capability_kind, "capability_id": self.capability_id,
             "payload": self.payload, "target_suite": self.target_suite},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Contribution":
        return Contribution(
            node_id=d["node_id"],
            capability_kind=d["capability_kind"],
            capability_id=d["capability_id"],
            payload=d.get("payload", {}),
            self_reported_score=float(d.get("self_reported_score", 0.0)),
            target_suite=d.get("target_suite", ""),
            provenance=d.get("provenance", {}) or {},
        )
