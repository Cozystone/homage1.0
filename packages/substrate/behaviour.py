# -*- coding: utf-8 -*-
"""V7-0 — a thing's vector read off HOW IT BEHAVES, and the test of whether that carries any signal.

Axis v7 §3, rung one. The claim under test is the whole axis in miniature: if a vector is derived
from behaviour rather than from a name, things that behave alike land near each other, and only then
can a transformation fitted in one region mean anything in another. `fhrr_core` assigns every atom a
hash of its spelling, so today the geometry carries nothing and nothing can travel through it.

WHAT "BEHAVIOUR" IS HERE, and why it is not a choice made for convenience. An entity's behaviour is
WHICH PREDICATES IT TAKES -- the same quantity `type_affinity` already reads off the shipped graph to
decide that 78% of paintings have a creator. So this is not a new representation invented for the
probe; it is the existing one, per entity instead of per kind.

THE CONFOUND, NAMED BEFORE THE RUN because it has already bitten this project once. Raw predicate
COUNTS measure how well-documented a thing is, not what kind of thing it is: a 223-member grape
class profiled at `is_a` 11.69 and swallowed two shipyards until prevalence replaced rate. The same
error at entity level would make every densely-documented entity look alike. So a behaviour vector
is a DISTRIBUTION over predicates -- shares that sum to one -- and an entity with thirty edges and
one with three are compared on shape, not size.

THE BASIS IS BUILT ON TRAINING KINDS AND THE GATE IS READ ON HELD-OUT KINDS. A basis fitted on the
same kinds it is scored against would be measuring its own fit.

THE CONTROL IS PART OF THE INSTRUMENT. Shuffling each entity's predicate labels destroys the
behaviour while preserving the magnitude; if the effect survives that, the effect was magnitude and
not behaviour. Same discipline as `contrast_family.admit` and the transfer gate's INVALID: an
instrument that cannot fail is not measuring.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

Edge = tuple[str, str, str]


@dataclass(frozen=True)
class Behaviour:
    """One entity as what it does: a distribution over the predicates it takes."""
    entity: str
    shares: dict[str, float]
    edges: int

    def vector(self, basis: Sequence[str]) -> list[float]:
        return [self.shares.get(p, 0.0) for p in basis]


def behaviour_of(entity: str, facts: Iterable[Edge], *, declaring: str = "is_a") -> Behaviour:
    """Distinct objects per predicate, normalised to a distribution.

    `is_a` is excluded: it is the KIND DECLARATION, and leaving it in would let the vector answer
    the question the gate asks -- an entity would be near its kind-mates because both say they are
    that kind, which is the label, not behaviour. The same reason `type_affinity` refuses to
    attribute the declaring predicate."""
    per: dict[str, set[str]] = {}
    for _s, p, o in facts:
        if str(p) == declaring:
            continue
        per.setdefault(str(p), set()).add(str(o))
    counts = {p: float(len(v)) for p, v in per.items()}
    total = sum(counts.values())
    shares = {p: c / total for p, c in counts.items()} if total > 0 else {}
    return Behaviour(entity, shares, int(total))


def shared_basis(behaviours: Sequence[Behaviour], *, min_holders: int = 2) -> list[str]:
    """The predicate dimensions, taken from the TRAINING behaviours only.

    A predicate held by a single entity is that entity's fingerprint, not a dimension anything can
    be compared along, so it is dropped.

    Counting HOLDERS, not share mass. The first version wrote `held.update(b.shares)`, and
    `Counter.update` on a mapping ADDS THE VALUES -- so dimensions were selected by total share mass
    and the filter silently became "common AND dominant" instead of "held by more than one". The
    V7-0 numbers first reported were computed on that basis and had to be taken again."""
    held: Counter = Counter()
    for b in behaviours:
        held.update(b.shares.keys())
    return sorted(p for p, n in held.items() if n >= min_holders)


def distance(a: Behaviour, b: Behaviour, basis: Sequence[str]) -> float:
    """Total-variation distance between two distributions: half the L1, bounded in [0, 1].

    Bounded on purpose. A cosine on sparse share-vectors reports 1.0 for any two entities with no
    predicate in common, which is most pairs, and would flatten exactly the differences being
    measured."""
    va, vb = a.vector(basis), b.vector(basis)
    return 0.5 * sum(abs(x - y) for x, y in zip(va, vb))


def shuffled(b: Behaviour, basis: Sequence[str]) -> Behaviour:
    """The control: same share MAGNITUDES, reassigned to DIFFERENT predicates PER ENTITY.

    The per-entity part is the whole control, and the first version got it wrong in a way worth
    keeping on the record: it rotated every entity's predicates by the SAME offset. A global
    relabelling is an ISOMETRY -- every pairwise distance is preserved exactly -- so the control
    reproduced the real separation to six decimal places and the gate read FAIL on an instrument
    that was structurally incapable of reading anything else.

    Rotating each entity by its OWN offset breaks the alignment between entities, which is precisely
    the thing the signal is supposed to live in. The offset comes from a stable digest of the name
    rather than `hash()` (which varies per process) or a seed (one more thing that could be chosen
    after seeing the result)."""
    if not basis:
        return b
    import hashlib
    off = int(hashlib.sha256(b.entity.encode("utf-8")).hexdigest()[:8], 16) % len(basis)
    if off == 0:
        off = 1                                    # a zero rotation would be the identity again
    rotated: dict[str, float] = {}
    for k, v in b.shares.items():
        if k in basis:
            rotated[basis[(basis.index(k) + off) % len(basis)]] = v
        else:
            rotated[k] = v
    return Behaviour(b.entity, rotated, b.edges)


@dataclass(frozen=True)
class SignalReading:
    """Does behaviour-derived geometry put same-kind things closer than arbitrary things?"""
    kinds: int
    entities: int
    same_kind_mean: float
    cross_kind_mean: float
    control_same_mean: float
    control_cross_mean: float
    basis_size: int
    held_out: tuple[str, ...] = field(default_factory=tuple)

    @property
    def separation(self) -> float:
        """How much closer same-kind pairs are. Positive means the geometry knows something."""
        return round(self.cross_kind_mean - self.same_kind_mean, 6)

    @property
    def control_separation(self) -> float:
        return round(self.control_cross_mean - self.control_same_mean, 6)

    @property
    def passed(self) -> bool:
        """Same-kind strictly nearer AND the control failing to reproduce it.

        Both halves are required. Without the second, an effect driven by how much an entity is
        documented would read exactly like an effect driven by what it is."""
        return self.separation > 0 and self.separation > self.control_separation * 2

    def as_dict(self) -> dict[str, Any]:
        return {"kinds": self.kinds, "entities": self.entities, "basis": self.basis_size,
                "same_kind_mean": round(self.same_kind_mean, 6),
                "cross_kind_mean": round(self.cross_kind_mean, 6),
                "separation": self.separation,
                "control_separation": self.control_separation,
                "passed": self.passed, "held_out_kinds": list(self.held_out)}


def _pair_means(groups: dict[str, list[Behaviour]], basis: Sequence[str]) -> tuple[float, float]:
    same, cross = [], []
    names = sorted(groups)
    for k in names:
        members = groups[k]
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                same.append(distance(members[i], members[j], basis))
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            for x in groups[names[a]]:
                for y in groups[names[b]]:
                    cross.append(distance(x, y, basis))
    return (sum(same) / len(same) if same else 0.0,
            sum(cross) / len(cross) if cross else 0.0)


def read_signal(train: Sequence[Behaviour], groups: dict[str, list[Behaviour]]) -> SignalReading:
    """The V7-0 gate. `train` builds the basis; `groups` are the HELD-OUT kinds it is read on."""
    basis = shared_basis(train)
    same, cross = _pair_means(groups, basis)
    ctrl_groups = {k: [shuffled(b, basis) for b in v] for k, v in groups.items()}
    c_same, c_cross = _pair_means(ctrl_groups, basis)
    return SignalReading(
        kinds=len(groups), entities=sum(len(v) for v in groups.values()),
        same_kind_mean=same, cross_kind_mean=cross,
        control_same_mean=c_same, control_cross_mean=c_cross,
        basis_size=len(basis), held_out=tuple(sorted(groups)))


# --- kind matching: where a DISTRIBUTION is the wrong comparison ---------------------------------

def kind_match(entity: Behaviour, prevalence: Mapping[str, float]) -> float:
    """How well an entity's predicates match what a MAJORITY of a kind's members hold.

    Not a distance between distributions, and the difference is the whole fix. The first wiring of
    this substrate renormalised each kind's prevalences into a distribution before comparing, which
    destroyed exactly the information A1c's absolute gate runs on: `painting` holding `creator` at
    0.785 is an ABSOLUTE claim about most paintings, and dividing it by the row total turns it into
    a relative share. Under that transform a small densely-documented class whose prevalences are
    all moderate -- `hybrid grape`: creator 0.386, manufacturer 0.179, author 0.143, country 0.48 --
    flattens into the same shape as a MIXTURE of kinds, which is what a merged node's residue is.
    So the shadow's first live reading picked the grape, the very answer the absolute gate exists to
    reject.

    Prevalence is bounded in [0,1] already and must not be renormalised. The score is two-sided,
    because either half alone is gameable:

      support   of the predicates the entity has, how prevalent are they in this kind -- an entity
                holding only things rare for the kind should not match it;
      coverage  of the predicates a MAJORITY of the kind holds, how many does the entity have -- an
                entity missing what defines the kind should not match it either.

    Their product, so a kind cannot win on one while failing the other. Returns 0.0 when there is
    nothing to compare, which is an absence and not a match."""
    if not entity.shares or not prevalence:
        return 0.0
    held = [p for p in entity.shares if entity.shares[p] > 0.0]
    if not held:
        return 0.0
    support = sum(float(prevalence.get(p, 0.0)) for p in held) / len(held)

    defining = [p for p, v in prevalence.items() if float(v) >= 0.5]
    coverage = (sum(1.0 for p in defining if p in entity.shares) / len(defining)
                if defining else 0.0)
    return round(support * coverage, 6)


def _lifts(profiles: Mapping[str, Mapping[str, float]]) -> dict[str, dict[str, float]]:
    """predicate -> kind -> how much more this predicate says THIS kind than the candidates average.

    The same move `type_affinity.discriminative` makes, which the substrate was not making. Raw
    prevalence lets a predicate every kind holds -- `located_in`, `country` -- contribute equally to
    every kind's support and dilute the signal, so entities matched several kinds comparably and the
    decisiveness gate abstained on 62 of 84."""
    preds = {p for pv in profiles.values() for p in pv}
    out: dict[str, dict[str, float]] = {k: {} for k in profiles}
    for p in preds:
        vals = {k: max(float(pv.get(p, 0.0)), 1e-6) for k, pv in profiles.items()}
        mean = sum(vals.values()) / len(vals)
        for k, v in vals.items():
            out[k][p] = v / mean if mean > 0 else 1.0
    return out


def rank_kinds(entity: Behaviour,
               profiles: Mapping[str, Mapping[str, float]], *,
               use_lift: bool = True) -> list[tuple[str, float]]:
    """Kinds this entity matches, best first. Scores are comparable because none is renormalised.

    `use_lift` weights each predicate's contribution by how much it DISTINGUISHES the kind, rather
    than by its raw prevalence. This is a change to the representation and not to any threshold:
    the decisiveness margin is untouched, so a coverage rise here has to come from the geometry
    separating better, which is the frozen gate's stated signature of transfer."""
    if not use_lift:
        return sorted(((k, kind_match(entity, pv)) for k, pv in profiles.items()),
                      key=lambda kv: -kv[1])

    lifts = _lifts(profiles)
    held = {p: v for p, v in entity.shares.items() if v > 0.0}
    out = []
    for k, pv in profiles.items():
        if not held:
            out.append((k, 0.0))
            continue

        # SUPPORT weighted by the ENTITY'S OWN SHARE, not by mere presence. The behaviour vector is
        # a distribution and the first version used only its support set, so an entity whose edges
        # are 90% `creator` scored identically to one that mentions `creator` once. That threw away
        # the quantity this whole substrate is built on.
        # SUPPORT WEIGHTED BY THE ENTITY'S OWN SHARE. Re-applied by operator decision on
        # 2026-07-29, with the frozen domain's verdict standing and recorded below rather than
        # revised. The behaviour vector is a distribution and a presence mean discards it: an entity
        # whose edges are 90% `creator` scored identically to one that mentions `creator` once.
        support = sum(v * float(pv.get(p, 0.0)) * lifts[k].get(p, 1.0) for p, v in held.items())

        # COVERAGE as a continuous share of the kind's characteristic MASS, not a count over a hard
        # `prevalence >= 0.5` cut. That cut was a number I chose, and it made any kind whose most
        # characteristic predicate sat at 0.48 structurally unmatchable -- score 0 against every
        # entity forever, which is what `hybrid grape` was doing. Mass has no cliff and no constant.
        # COVERAGE AS CHARACTERISTIC MASS, not a count over a hard `prevalence >= 0.5` cut. That
        # cut made any kind whose most characteristic predicate sat at 0.48 structurally unmatchable
        # -- score 0 against every entity forever. Mass has no cliff and no chosen constant.
        #
        # THE FROZEN DOMAIN SAYS BOTH OF THESE COST, and that verdict stands unrevised. The full 2x2,
        # measured after the two edits were read as one bundle and I twice named a cause before
        # separating them:
        #
        #   support          coverage     frozen domain B
        #   share-weighted   mass         25 / 4 / 0.345 / 0.862   REGRESSED   <- current state
        #   share-weighted   hard cut     25 / 4 / 0.345 / 0.862   REGRESSED
        #   presence-mean    mass         27 / 4 / 0.369 / 0.871   REGRESSED
        #   presence-mean    hard cut     28 / 3 / 0.369 / 0.903   baseline
        #
        # Each regresses B alone and they interact -- coverage reads neutral only while the support
        # change is present, because that one dominates. Both are in force because the operator chose
        # them knowing this table, which is what the gate is for: it measures, it does not decide.
        # The reading is not re-cut to match the decision, and `wrong` rising 3 -> 4 crosses a metric
        # registered as a HARD GUARD.
        total_mass = sum(float(v) for v in pv.values())
        cov = (sum(float(pv.get(p, 0.0)) for p in held if p in pv) / total_mass
               if total_mass > 0 else 0.0)

        out.append((k, round(support * cov, 6)))
    return sorted(out, key=lambda kv: -kv[1])


def decisive_kind(entity: Behaviour, profiles: Mapping[str, Mapping[str, float]], *,
                  margin: float = 1.6) -> tuple[str | None, float, str]:
    """The best-matching kind ONLY when it beats the runner-up decisively. Otherwise nothing.

    Measured cause, on the real 36-edge Athens residue: without this the shadow placed 15 edges to
    A1c's 10, and all five extras were `located_in` -- a predicate every place-kind holds, so it
    separates none of them. `weather station` won those only because it has few defining predicates,
    which makes covering one of them score high. Precision was 10/15 = 0.67 against A1c's 10/10.

    The argument is not new and is not fitted to those five cases: `type_affinity.attribute_by_kind`
    already refuses on `top < runner * margin`, for the same reason and with the same constant. What
    was missing was that the substrate had support and coverage but no test of DECISIVENESS, so a
    kind could win by being the least uninformative rather than by being right.

    Returns (kind, score, reason) with kind=None when nothing is decisive."""
    ranked = [(k, s) for k, s in rank_kinds(entity, profiles) if s > 0.0]
    if not ranked:
        return None, 0.0, "no kind holds what this entity has"
    top, top_score = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else 0.0
    if runner > 0.0 and top_score < runner * margin:
        return None, top_score, f"'{top}' and '{ranked[1][0]}' fit about equally"
    return top, top_score, f"decisive over the runner-up by >= {margin}x"
