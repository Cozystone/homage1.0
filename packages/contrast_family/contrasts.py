# -*- coding: utf-8 -*-
"""G0 — are the discrimination contrasts SUBSTITUTABLE, or is each site stuck with what its author reached for?

Plan v6 §7. The four instances all compute `contrast(feature, target, background) -> score` and then
threshold it, differing only in the contrast itself. If those contrasts can be swapped, every site
is currently limited by an arbitrary choice and consolidation's payoff is that each site gains
access to all of them. If none beats its incumbent anywhere, there is nothing to transfer and the
consolidation thesis dies here -- cheaply, before a second domain is frozen.

ONE SIGN CONVENTION, or the comparison is meaningless: every contrast returns HIGHER = this feature
singles out the target MORE.

AND THE FAMILY TURNED OUT TO HAVE TWO MEMBERS, NOT FOUR. Two of the four instances plan v6 counted
do not implement this interface at all, and neither was let in by widening it: `read_schema` decides
by agreement between two aligned SEQUENCES, and `_bridging` normalises by the POPULATION SIZE, which
a background of other features' values cannot supply. The second was caught by the sign-convention
test rather than by inspection -- the re-expression normalised by the wrong quantity and inverted
the very ordering it was meant to preserve. See NON_MEMBERS.

THE CONTROLS ARE PART OF THE FAMILY, not an afterthought. A contrast may substitute at a site
because the contrasts are equivalent, or because THAT SITE'S METRIC CANNOT TELL THEM APART. Those
look identical in a results table and only one is evidence. So two deliberately bad contrasts run
first at every site, and a site whose metric does not degrade under them is not measuring anything
and is refused admission. Same discipline as the transfer gate's INVALID: an instrument that cannot
fail is not an instrument.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

Contrast = Callable[[float, Sequence[float]], float]

_EPS = 1e-9


def ratio_to_mean(target: float, background: Sequence[float]) -> float:
    """From `type_affinity.discriminative`: how far above the candidates' average this sits.

    Sensitive to a background with one huge member, which is exactly the property that made the
    hybrid-grape profile swallow two shipyards before the absolute gate was added."""
    if not background:
        return 1.0
    mean = sum(background) / len(background)
    return target / mean if mean > _EPS else (1.0 if target <= _EPS else 1.0 / _EPS)


def inverse_share(target: float, background: Sequence[float]) -> float:
    """NOT A FAMILY MEMBER. Kept only so the reason it does not fit stays readable.

    `edge_attribution._bridging` asks what fraction of the DOCUMENTS a word occupies, and discards
    the widespread. Its denominator is the population size. This interface supplies the values of
    OTHER FEATURES, from which the population size is not derivable -- so the re-expression below
    normalises by the wrong quantity and inverts the ordering it was supposed to preserve, which is
    how the sign-convention test caught it.

    The interface could be widened to `(target, background, n)` to admit it. That would be inventing
    a shape to make a member fit, which is exactly what was refused for `read_schema`, and the same
    standard has to apply when the cost of applying it is losing a member."""
    total = sum(background) + target
    return 1.0 - (target / total) if total > _EPS else 0.0


def rank_gap(target: float, background: Sequence[float]) -> float:
    """From the architecture census's peer comparison: where the target sits among its peers.

    Non-parametric -- it reads only the ORDER, so a background with a wild outlier cannot move it.
    That is the property the other two lack, and the reason it is worth having in the family."""
    if not background:
        return 0.5
    below = sum(1 for b in background if b < target)
    ties = sum(1 for b in background if abs(b - target) <= _EPS)
    return (below + 0.5 * ties) / len(background)


# --- controls -----------------------------------------------------------------------------------

def constant(target: float, background: Sequence[float]) -> float:
    """Says nothing about anything. A site that still performs under this is not discriminating."""
    return 1.0


def inverted(target: float, background: Sequence[float]) -> float:
    """Deliberately backwards: scores the LEAST distinguishing feature highest. Deterministic, so
    the control is reproducible -- a shuffle would need a seed and this needs none."""
    return -ratio_to_mean(target, background)


REAL: dict[str, Contrast] = {
    "ratio_to_mean": ratio_to_mean,
    "rank_gap": rank_gap,
}
CONTROLS: dict[str, Contrast] = {"constant": constant, "inverted": inverted}
ALL: dict[str, Contrast] = {**REAL, **CONTROLS}

# The instances that are NOT in the family, and why. Forcing either in would mean inventing a shape
# to make a member fit -- the hand-authored taxonomy this whole line of work exists to avoid -- and
# the same standard has to hold when applying it costs a member. Recorded as measured non-members:
# plan v6 §1 counted four instances of a PRINCIPLE, and exactly two of them share an INTERFACE.
NON_MEMBERS = {
    "loop_schema.read_schema": "decides by agreement between two aligned sequences, not by "
                               "contrasting one value against a background",
    "edge_attribution._bridging": "normalises by the POPULATION SIZE (how many documents), which "
                                  "this interface does not supply and which cannot be derived from "
                                  "the other features' values",
}


@dataclass(frozen=True)
class SiteResult:
    site: str
    contrast: str
    score: float
    incumbent: bool = False

    def as_dict(self) -> dict:
        return {"site": self.site, "contrast": self.contrast, "score": round(self.score, 6),
                "incumbent": self.incumbent}


@dataclass(frozen=True)
class Admission:
    """Whether a site's own metric can tell a good contrast from a deliberately bad one."""
    site: str
    best_real: float
    worst_control: float
    admitted: bool
    reason: str

    def as_dict(self) -> dict:
        return {"site": self.site, "best_real": round(self.best_real, 6),
                "worst_control": round(self.worst_control, 6),
                "admitted": self.admitted, "reason": self.reason}


def admit(site: str, run: Callable[[Contrast], float], *, margin: float = 1e-6) -> Admission:
    """Run the controls first. A site that scores as well under `constant` as under a real contrast
    is not measuring discrimination, and its swap results would be noise wearing a number."""
    real = max(run(fn) for fn in REAL.values())
    ctrl = max(run(fn) for fn in CONTROLS.values())
    ok = real > ctrl + margin
    return Admission(
        site, real, ctrl, ok,
        "the metric separates real contrasts from deliberately bad ones" if ok else
        "the metric scores a constant contrast as well as a real one; this site cannot discriminate")


def cross_swap(site: str, run: Callable[[Contrast], float], incumbent: str) -> list[SiteResult]:
    """Every real contrast at this site, including the one it was written with."""
    return sorted((SiteResult(site, name, run(fn), name == incumbent)
                   for name, fn in REAL.items()), key=lambda r: -r.score)


def probe(sites: dict[str, tuple[Callable[[Contrast], float], str]]) -> dict:
    """The whole G0 reading: admission, then swaps, then the one claim that matters."""
    admissions = {name: admit(name, run) for name, (run, _inc) in sites.items()}
    swaps = {name: cross_swap(name, run, inc)
             for name, (run, inc) in sites.items() if admissions[name].admitted}

    beaten: list[dict] = []
    for name, rows in swaps.items():
        inc = next((r for r in rows if r.incumbent), None)
        if inc is None:
            continue
        for r in rows:
            if not r.incumbent and r.score > inc.score + 1e-9:
                beaten.append({"site": name, "incumbent": inc.contrast,
                               "beaten_by": r.contrast,
                               "gain": round(r.score - inc.score, 6)})
    return {
        "family": sorted(REAL),
        "non_members": NON_MEMBERS,
        "sites_offered": len(sites),
        "sites_admitted": sum(1 for a in admissions.values() if a.admitted),
        "admissions": [a.as_dict() for a in admissions.values()],
        "swaps": {k: [r.as_dict() for r in v] for k, v in swaps.items()},
        "incumbent_beaten_somewhere": bool(beaten),
        "beats": beaten,
    }
