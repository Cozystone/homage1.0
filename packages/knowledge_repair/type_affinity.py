# -*- coding: utf-8 -*-
"""A1c — separate a merged name by KIND, using property-to-kind affinity the graph already holds.

Written from the residue A1b left, not from a guess. After one full round on the real `Athens`
node, 36 edges remained and `foreign_vocabulary` returned EMPTY over them. Looking at them says
why immediately:

    is_a painting / made_of oil paint / made_of canvas / creator Kenneth Hall / creator Eve Kirk
    manufacturer Shin Kurushima Dockyard / manufacturer Huanghai Shipbuilding
    is_a literary work / author Reinhard Stupperich / author Helladius of Antinoopolis
    country Zimbabwe / located_in Midlands Province
    is_a hybrid grape / is_a weather station / is_a hill / is_a mint

A1b measures COHESION OF OBJECT TEXT, and it was right for what it was built on: long `defined_as`
sentences, where "floor / stairs / storey / level" cluster and betray a second lexeme. Here the
objects are one or two words. There is no text to cohere. A1b is not broken -- its work finished in
round one, and this residue is a different problem wearing the same shape.

The residue is not one word's leftovers. It is DIFFERENT KINDS OF THING sharing a name: a painting,
a ship, an encyclopedia article, a town in Zimbabwe, a grape. A person separates these instantly,
and not by reading the words -- by knowing that PAINTINGS HAVE CREATORS AND ARE MADE OF PAINT WHILE
SHIPS HAVE MANUFACTURERS. That knowledge is not a table someone has to write here. It is already in
the graph, in every other painting and every other ship. Measured on the shipped store:

    painting          n=491561   made_of 1.54  is_a 1.48  located_in 1.31  creator 1.03  genre 0.54
    literary work     n=229786   is_a 2.01  author 0.98  genre 0.84  country 0.58  located_in 0.40
    weather station   n=28839    located_in 2.15  is_a 2.01  country 1.22  ...  creator 0.06
    hill              n=221043   located_in 1.67  is_a 1.40  country 1.11  ...  creator 0.01

`creator` is 1.03 per painting and 0.01 per hill; `author` belongs to the written kinds and to no
place. The separation is there to be read.

WHY IT IS A LIFT AND NOT A RATE. `is_a`, `located_in` and `country` are high for EVERY kind above.
Ranking on the raw rate would hand every edge to whichever candidate is largest, which is the same
failure the composer hit when coverage-maximisation always chose `is_a` because everything has one.
So a predicate speaks for a kind only in PROPORTION to how much it speaks for the other candidates
in play -- the identical discriminative move `_bridging` makes for words in A1b. One principle, two
substrates, and neither one carries a list.

NOTHING IS WRITTEN, and nothing is invented: candidate kinds come only from `is_a` edges the node
itself asserts. If the node never says it is a painting, no painting referent exists here.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from packages.knowledge_repair.attribution import Referent
from packages.knowledge_repair.edge_attribution import EdgeVerdict

Edge = tuple[str, str, str]

# The rate of a predicate that appears for no member at all. Kept above zero so a lift stays finite
# and a kind with a genuinely absent property is merely unlikely rather than impossible -- the
# graph's silence about one kind is not proof.
_FLOOR = 0.01


@dataclass(frozen=True)
class TypeProfile:
    """What the graph says entities of one kind typically have. Read, never authored.

    `rates` is PREVALENCE -- the fraction of this kind's members that hold the predicate at all --
    and not edges-per-member, which is what the first version measured and what made the first real
    run wrong. `hybrid grape` (223 members) profiled at `is_a` 11.69, `located_in` 7.33, `creator`
    1.74: every rate enormous, not because grapes are unusual but because a small well-documented
    population carries many edges per member. Ranking on that ranks DOCUMENTATION DENSITY, and the
    grape duly swallowed eleven edges of the real residue including two shipyards.

    Prevalence cannot exceed 1.0, so density cannot inflate it, and one entity carrying two hundred
    `creator` edges counts once."""
    type_label: str
    members: int
    rates: Mapping[str, float]                     # predicate -> fraction of members holding it

    def rate(self, predicate: str) -> float:
        return float(self.rates.get(predicate, 0.0))


def types_declared(subject: str, facts: Iterable[Edge], *,
                   declaring: str = "is_a") -> list[str]:
    """The kinds THIS node claims to be. The only source of candidate referents here.

    A merged node states its own ambiguity: `Athens` asserts `is_a painting`, `is_a literary work`,
    `is_a hill`. Reading candidates off the node keeps the search bounded by what is actually
    claimed, and makes inventing a kind impossible."""
    seen: dict[str, None] = {}
    low = str(subject).strip().lower()
    for s, p, o in facts:
        if str(p) != declaring:
            continue
        label = str(o).strip()
        if label and label.lower() != low:
            seen.setdefault(label, None)
    return list(seen)


def type_profiles(store: Any, types: Sequence[str], *,
                  min_members: int = 20) -> dict[str, TypeProfile]:
    """Predicate PREVALENCE per kind, computed from the graph's own population of that kind.

    A kind with too few members is dropped rather than profiled: a prevalence over three entities is
    noise, and a noisy profile would attract edges with false confidence. Returns {} if the store
    cannot supply columns, so every caller degrades to "no verdict" instead of to a guess."""
    try:
        import numpy as np
        from packages.scene_model.evaluate import extension
        cols = store.open_columns()
        s, p = cols["s"], cols["p"]
        stride = int(p.max()) + 1
    except Exception:
        return {}

    out: dict[str, TypeProfile] = {}
    for label in types:
        try:
            ext = extension(store, label)
            if len(ext) < min_members:
                continue
            rows = np.isin(s, ext)
            # DISTINCT (entity, predicate) pairs, so one entity with two hundred `creator` edges
            # counts once. Packed into a single int64 key because np.unique over an axis of several
            # million columns is far slower than over a flat array.
            pairs = np.unique(s[rows].astype(np.int64) * stride + p[rows].astype(np.int64))
            pids, holders = np.unique((pairs % stride).astype(np.int64), return_counts=True)
            rates: dict[str, float] = {}
            for pid, n in zip(pids.tolist(), holders.tolist()):
                try:
                    name = store.terms.term(pid)
                except Exception:
                    continue
                if name:
                    rates[str(name)] = n / len(ext)
            out[label] = TypeProfile(label, int(len(ext)), rates)
        except Exception:
            continue                               # one unreadable kind must not kill the pass
    return out


def discriminative(profiles: Mapping[str, TypeProfile]) -> dict[str, dict[str, float]]:
    """kind -> predicate -> how much more this predicate says THIS kind than the others in play.

    Lift against the mean over the candidates, not against the whole graph: the question is never
    "is `located_in` rare?" but "does `located_in` tell a hill from a painting?", and among these
    candidates it does not. A predicate every candidate shares lands near 1.0 and is therefore
    silent, which is the correct outcome and needs no list of stop-predicates."""
    if not profiles:
        return {}
    preds = {p for prof in profiles.values() for p in prof.rates}
    out: dict[str, dict[str, float]] = {k: {} for k in profiles}
    for pred in preds:
        rates = {k: max(prof.rate(pred), _FLOOR) for k, prof in profiles.items()}
        mean = sum(rates.values()) / len(rates)
        for k, r in rates.items():
            out[k][pred] = r / mean if mean > 0 else 1.0
    return out


def attribute_by_kind(subject: str, residue: Sequence[Edge],
                      profiles: Mapping[str, TypeProfile], *,
                      declaring: str = "is_a", margin: float = 1.6,
                      min_lift: float = 1.5, min_prevalence: float = 0.5) -> list[EdgeVerdict]:
    """Verdict per residue edge, by which kind its predicate speaks for.

    Three gates, all of which must clear, and all three there because a wrong placement is worse
    than an unplaced edge -- it looks resolved:

      `min_prevalence`  MOST members of the kind must hold the property. Absolute, and the gate the
                        first version lacked. Without it a predicate no candidate really holds is
                        decided by the floor: `manufacturer` at 0.05 against 0.01 for the rest lifts
                        to ~3.8 and wins, so the real run handed two shipyards to a grape. Being
                        less rare than the alternatives is not the same as being typical, and only
                        the second one is evidence.

                        The line is a majority rather than a tuned dial, and it is the same claim
                        the module rests on stated as a number: a property speaks for a kind when
                        having it is what members of that kind DO. Measured -- 78% of paintings
                        have a creator, 83% of literary works an author; 18% of hybrid grapes have
                        a manufacturer. The first two are what those kinds are like, the third is
                        incidental, and only a majority line separates them.

                        This gate is also the only thing that can say NONE OF THE ABOVE. Athens
                        declares thirteen kinds and a ship is not among them, so the shipyard edges
                        have no right owner here; without an absolute floor the ranking would still
                        hand them to whichever candidate was least unlike a ship.
      `min_lift`        it has to speak for this kind more than the candidates average, or it is a
                        bridging predicate and says nothing.
      `margin`          it has to speak for this kind clearly more than for the runner-up, or two
                        kinds both plausibly own it and the honest verdict is that the evidence
                        does not separate them.

    The declaring predicate is never attributed. That is not an exclusion list, it is the same fact
    stated once: `is_a` is what PRODUCED these candidates, so letting it also choose among them
    would be reading the answer off the question."""
    lifts = discriminative(profiles)
    if not lifts:
        return [EdgeVerdict(e, None, "unknown", "no kind profile available") for e in residue]

    out: list[EdgeVerdict] = []
    for edge in residue:
        _s, pred, _o = edge
        pred = str(pred)
        if pred == declaring:
            out.append(EdgeVerdict(edge, None, "unknown",
                                   "declares a kind; it is what the candidates were read from"))
            continue

        ranked = sorted(((lifts[k].get(pred, 0.0), k) for k in lifts), reverse=True)
        top, top_kind = ranked[0]
        runner = ranked[1][0] if len(ranked) > 1 else 0.0
        prevalence = profiles[top_kind].rate(pred)

        if prevalence < min_prevalence:
            out.append(EdgeVerdict(
                edge, None, "unknown",
                f"'{pred}' is held by only {prevalence:.0%} of {top_kind}; "
                f"no candidate kind here really has this property"))
        elif top < min_lift:
            out.append(EdgeVerdict(
                edge, None, "unknown",
                f"'{pred}' is held by every candidate kind here; it separates nothing"))
        elif runner > 0 and top < runner * margin:
            out.append(EdgeVerdict(
                edge, None, "unknown",
                f"'{pred}' fits {top_kind} and {ranked[1][1]} about equally"))
        else:
            out.append(EdgeVerdict(
                edge, f"{subject} ({top_kind})", "assigned",
                f"{prevalence:.0%} of {top_kind} have '{pred}', {top:.1f}x the alternatives"))
    return out


def substrate_opinion(subject: str, residue: Sequence[Edge],
                      profiles: Mapping[str, TypeProfile]) -> dict[str, Any]:
    """The v7 behaviour-substrate's SECOND OPINION on this node. Shadow only: nothing here reaches
    `attribute_by_kind`'s verdict.

    Why it exists at all, and why it is not authoritative. `packages/substrate` was built with three
    measured rungs on top of it (V7-0, V7-1, V7-2) and imported by NOTHING -- the eighth instance in
    this repository of the built-but-unwired pathology, and the first one I produced myself. An
    organ nothing calls cannot be evaluated by any domain's numbers, which also blocks V7-3: the
    frozen-domain gate needs a domain whose eval path provably traverses the substrate, and no such
    domain existed.

    So the channel is opened here, at the M3 tier of the evidence ladder: live, observed, and
    non-authoritative. A1c currently places 10 of the real Athens residue and gets 10 right; making
    a freshly-measured embedding authoritative over a verified result would risk that for a rung's
    convenience. When the shadow has a record, it can be compared against the verdict it shadows --
    and only then is there anything to promote.

    Returns {} on any failure: an opinion that cannot be formed is an absence, not a verdict."""
    try:
        from packages.substrate import behaviour_of, decisive_kind, rank_kinds
        prev = {k: dict(p.rates) for k, p in profiles.items()}
        me = behaviour_of(subject, residue)
        kind, score, why = decisive_kind(me, prev)
        ranked = [k for k, s in rank_kinds(me, prev) if s > 0.0][:3]
        if kind is None and not ranked:
            return {}
        return {"nearest_kind": kind, "score": round(score, 6), "basis": why,
                "ranked": ranked, "authoritative": False, "tier": "M3 live shadow"}
    except Exception:
        return {}


def kind_referents(subject: str, profiles: Mapping[str, TypeProfile]) -> list[Referent]:
    """The kinds that survived profiling, as referents the rest of the loop already understands."""
    return [Referent(f"{subject} ({k})", frozenset({k.lower()})) for k in sorted(profiles)]


def summarise_kinds(verdicts: Sequence[EdgeVerdict]) -> dict[str, Any]:
    """Which kinds actually attracted edges, and how many stayed unplaced."""
    by_kind = Counter(v.referent for v in verdicts if v.placed)
    return {"assigned": sum(by_kind.values()), "unknown": sum(1 for v in verdicts if not v.placed),
            "kinds": dict(by_kind.most_common())}
