# -*- coding: utf-8 -*-
"""Round-trip faithfulness — check what prose SAYS against what it was ALLOWED to say.

    from packages.graph_scale.roundtrip_faithfulness import check
    v = check(propositions, prose)
    v.faithful        # False if the prose asserts anything it was not given
    v.added           # the fabrications, named
    v.dropped         # what it was given and did not convey

THE PROBLEM THIS SOLVES. ATANOR's honesty floor is "say only what is verified, else abstain", and prose
has no verifier — so fluency looks like it must cost honesty. It does not, because fabrication lives in
the PROPOSITIONS, not in the prose. "PropertyTable is a class at property_table.py:124" is checkable;
whether it is said as "PropertyTable, defined at line 124, is a class" or "You'll find PropertyTable at
property_table.py:124" is not a truth question at all. So the two acts separate:

    SELECT   which verified propositions to say, and in what order
    REALIZE  turn that ordered set into sentences

and realization is fabrication-free *by construction* if it is closed over its input. This module is
what makes "closed over its input" a measured property instead of a promise: re-extract the claims from
the produced prose and require them to be a subset of what was handed in.

THE METHOD IS THE OWNER'S OWN, GENERALISED. The owner proposed (2026-07-31) reverse-deriving a clean
prompt from a good website, rebuilding the site from that prompt alone, and scoring similarity against
the reference — a round-trip consistency oracle, valuable because it is free, automatic and
unflatterable. The same shape works on sentences:

    propositions -> prose -> re-extract propositions -> compare

    additions  => FABRICATION. must be zero. this is the floor, checked mechanically.
    losses     => the prose dropped something it was asked to convey.
    fluency    => scored separately, and only on prose already known to be faithful.

WHAT THIS DELIBERATELY DOES NOT DO. It cannot judge whether the propositions SELECTED were the apt ones
— whether "it decides where a file goes" beats "it defines seven methods" as an answer to "what does
Rooms do". No round trip can: aptness is not recoverable from the output. That is the real wall, it is
the same wall as design taste in code review, and naming it here keeps a faithfulness score from being
read as a quality score.

THE BOTTLENECK RULE, which decides whether any round-trip design is honest. The intermediate must be a
real bottleneck. In the website version, an unconstrained "prompt" lets the winning strategy become
smuggling — the prompt degenerates into `#3A7BD5, 14px, margin 22px`, or in the limit the HTML itself —
and then similarity scores high while nothing was understood. That is the classic degenerate-autoencoder
pathology. Here the equivalent guard is that the extractor works on the PROSE ALONE and never sees the
proposition list, so it cannot be led to the answer it is supposed to find independently.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Proposition:
    """One checkable claim. `subject`/`predicate`/`object` mirror the graph's own triples so a
    proposition set is exactly what retrieval already returns — nothing is re-modelled."""

    subject: str
    predicate: str
    object: str

    def key(self) -> tuple:
        return (_norm(self.subject), self.predicate, _norm(self.object))

    def say(self) -> str:
        return f"{self.subject} {self.predicate} {self.object}"


@dataclass
class Verdict:
    faithful: bool
    added: list = field(default_factory=list)      # claims in the prose that were not given
    dropped: list = field(default_factory=list)    # claims given that the prose did not convey
    conveyed: list = field(default_factory=list)
    coverage: float = 0.0
    detail: str = ""

    def as_dict(self) -> dict:
        return {"faithful": self.faithful, "added": self.added, "dropped": self.dropped,
                "coverage": round(self.coverage, 4), "detail": self.detail}


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:[./][A-Za-z0-9_.]+)*(?::\d+)?")
_TICKED = re.compile(r"`([^`]+)`")


def _norm(s: str) -> str:
    return re.sub(r"[\s`]+", " ", str(s or "")).strip().lower()


def entities_in(prose: str) -> set[str]:
    """Every identifier-shaped or backticked token the prose commits to.

    Backticks are read first because they are how this system marks a name it is ASSERTING; a bare
    English word that happens to look like an identifier is not a commitment. Working on the prose
    alone is what keeps the check independent -- an extractor that could see the answer key would
    find exactly the claims it was told to find."""
    out = {_norm(m) for m in _TICKED.findall(prose)}
    for tok in _IDENT.findall(prose):
        if "_" in tok or "." in tok or "/" in tok or ":" in tok or re.search(r"[a-z][A-Z]", tok):
            out.add(_norm(tok))
    return {o for o in out if o}


def check(propositions, prose: str, *, require_all: bool = False) -> Verdict:
    """Compare what the prose commits to against what it was given.

    ADDITIONS are the hard failure: an entity asserted in the prose that appears in no supplied
    proposition is, by definition, something the realizer introduced. DROPS are reported but are not a
    failure by default -- a good answer is often shorter than everything it could have said, and
    treating brevity as infidelity would push the realizer toward reciting."""
    props = [p if isinstance(p, Proposition) else Proposition(*p) for p in propositions]
    allowed: set[str] = set()
    for p in props:
        allowed |= entities_in(p.say())
        allowed.add(_norm(p.subject))
        allowed.add(_norm(p.object))

    said = entities_in(prose)
    added = sorted(said - allowed)
    conveyed = [p.say() for p in props
                if _norm(p.object) in said or _norm(p.object) in _norm(prose)]
    dropped = [p.say() for p in props if p.say() not in conveyed]
    coverage = len(conveyed) / max(1, len(props))

    faithful = not added and (not require_all or not dropped)
    if added:
        detail = (f"{len(added)} claim(s) in the prose were never supplied: "
                  f"{', '.join(added[:6])}")
    elif dropped and require_all:
        detail = f"{len(dropped)} supplied claim(s) were not conveyed"
    else:
        detail = (f"faithful: every entity asserted was supplied; "
                  f"coverage {coverage:.0%} of {len(props)} propositions")
    return Verdict(faithful=faithful, added=added, dropped=dropped, conveyed=conveyed,
                   coverage=coverage, detail=detail)


def propositions_from_answer(answer: dict) -> list[Proposition]:
    """Lift the propositions a code answer was BUILT from, so its own prose can be checked.

    This is the honest wiring: the check must run against what retrieval actually returned, not
    against a list reconstructed from the sentence — which would compare the prose to itself.

    It reads the certificate's `propositions`, which is the complete record of facts used. The first
    version of this function guessed instead, lifting only cited locations and a sample of evidence
    concepts, and every real answer came back "unfaithful" — because the prose truthfully mentioned
    the module a class sits in and the functions it calls, and the guessed list did not contain them.
    The lesson generalises: a faithfulness check is only as honest as the record of what was given,
    so the fix belonged in the certificate, not in loosening the check."""
    cert = answer.get("reasoning_certificate") or {}
    subject = (cert.get("anchor_concept") or {}).get("id", "")
    recorded = cert.get("propositions")
    if recorded:
        return [Proposition(p.get("s", subject), p.get("p", ""), p.get("o", "")) for p in recorded]
    props: list[Proposition] = []                       # fallback for answers predating the field
    for loc in cert.get("cited_locations", []) or []:
        props.append(Proposition(subject, "defined_at", loc))
    for ev in cert.get("evidence_concepts", []) or []:
        props.append(Proposition(subject, "holds", str(ev)))
    return props
