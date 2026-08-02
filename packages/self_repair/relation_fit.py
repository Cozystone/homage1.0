# -*- coding: utf-8 -*-
"""Station 2 of the loop: does a proposed change produce objects the relation actually takes?

    from packages.self_repair.relation_fit import judge
    v = judge("made_of", ["fifty states", "one thousand years", "four constituent countries"])
    v.accept      # False -- these are parts, and made_of takes materials

THE CASE THIS WAS BUILT FROM, and the acid test it has to pass. In cycle E5-2 the miss ranking named
`consisting of` as the largest single class of extractor failures — 49 of them, the obvious next fix.
Reading the glosses showed why fixing it would have been damage:

    millennium     consisting of one thousand years
    United States  consisting of fifty states
    Netherlands    consisting of four constituent countries

That is `has_part`. Mapping it to `made_of` would have raised the harness score while asserting that a
country is MADE OF its states. A loop that optimises its own metric without judgment does exactly that,
and no gate we had could see it: the guard clause watches metrics that exist, and no metric measured
whether a mapping meant the right RELATION. The ConceptNet check could not help either — it holds no
entry for "United States made_of fifty states" to disagree with.

THE ORACLE IS FREE, WHICH IS WHY THIS IS BUILDABLE. A relation's objects are not arbitrary: `made_of`
takes materials, `capable_of` takes actions, `used_for` takes purposes. And that expectation does not
have to be written down, because the graph ALREADY HOLDS thousands of verified rows for each relation.
So a proposed change is judged by running it, collecting the objects it would newly assert, and asking
whether they look like the objects the relation already takes. Alien objects at scale mean the mapping
is wrong even when every individual match is a clean regex hit.

WHAT MAKES THIS NOT A HAND RULE, which the owner is right to keep asking. Nothing here lists what a
material is. The profile of each relation is COUNTED from existing rows — head nouns, their frequency,
and how much of the relation's mass they carry. A new object is scored against that measured
distribution. Swap the graph and the profile changes with it.

THE LIMIT, stated because a judgment station that overclaims is worse than none. This catches
DISTRIBUTIONAL aliens: objects unlike anything the relation has ever taken. It does not catch a wrong
mapping whose objects happen to resemble the right ones, and it cannot judge whether a relation is
worth having at all. It is one check, and it is the one that would have stopped the mistake actually
made.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CANDIDATES = REPO / "data" / "cloud_brain" / "derived_candidates"

_PROFILE_CACHE: dict = {}


@dataclass
class Verdict:
    accept: bool
    relation: str
    familiar: float                 # share of proposed objects that fit the measured profile
    alien: list = field(default_factory=list)
    profile_size: int = 0
    reason: str = ""

    def as_dict(self) -> dict:
        return {"accept": self.accept, "relation": self.relation,
                "familiar": round(self.familiar, 4), "alien": self.alien[:10],
                "profile_size": self.profile_size, "reason": self.reason}


def _head_plain(obj: str) -> str:
    """Last token, relation-agnostic. Used ONLY for clustering.

    Clustering must not depend on the relation-aware head, or the two call each other forever:
    _head needs to know if a relation is verb-taking, which asked clusters(), which builds profiles,
    which call _head. I wrote that cycle and it hung the process. Clustering only needs a rough
    grouping and the plain last token already produces the right one -- [used_for, capable_of] against
    [made_of] -- so it stays plain and the cycle is cut at its narrowest point."""
    words = re.findall(r"[a-z]+", str(obj or "").lower())
    return words[-1] if words else ""


_VERB_CACHE: dict = {}


def _verb_relation(relation: str) -> bool:
    """Does this relation take ACTIONS as objects? Read off the measured clusters, cached, and
    computed with the plain head so it cannot re-enter."""
    if relation in _VERB_CACHE:
        return _VERB_CACHE[relation]
    try:
        verdict = any(relation in g and "capable_of" in g for g in clusters(head=_head_plain))
    except Exception:
        verdict = relation in ("used_for", "capable_of")
    _VERB_CACHE[relation] = verdict
    return verdict


def _head(obj: str, relation: str = "") -> str:
    """The token that says what KIND of object this is — and WHICH token that is depends on the relation.

    English puts the head last in a noun phrase, so `fifty states` -> states and `stainless steel` ->
    steel. That is right for made_of and WRONG for the action relations, where the last word is the
    verb's object rather than the act: `cutting bread` -> bread, `carry a meaning` -> meaning. The
    first version used the last token everywhere, and it is why this gate could never separate
    used_for from capable_of.

    MEASURED, on 15,729 held-out ConceptNet pairs labelled UsedFor vs CapableOf:

        majority-class baseline   0.729
        last  token (what this used to do)   0.645   -- WORSE than guessing the common class
        FIRST token                          0.810

    The old signal was not weak, it was harmful. The verbs genuinely differ -- cutting, storing,
    holding are instrumental; fly, bite, breathe are agentive -- while the nouns they take do not
    (jaccard 0.290 on last words against 0.136 on first)."""
    words = re.findall(r"[a-z]+", str(obj or "").lower())
    if not words:
        return ""
    return words[0] if _verb_relation(relation) else words[-1]


def _profile_with(relation: str, head=None) -> Counter:
    """Count a relation's object heads using a CALLER-SUPPLIED head function.

    Split out so clustering can pass the plain last-token head while scoring passes the
    relation-aware one, which is what keeps the two from calling each other."""
    head = head or (lambda o: _head(o, relation))
    key = (relation, getattr(head, "__name__", "aware"))
    if key in _PROFILE_CACHE:
        return _PROFILE_CACHE[key]
    counts: Counter = Counter()
    for path in CANDIDATES.glob(f"*{relation}*.jsonl"):
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                h = head(r.get("o") or r.get("object") or "")
                if h:
                    counts[h] += 1
        except OSError:
            continue
    _PROFILE_CACHE[key] = counts
    return counts


def profile(relation: str) -> Counter:
    """What objects this relation actually takes, counted from the rows already on disk.

    Nothing here is declared. If the graph's `made_of` rows are mostly wood, steel and plastic, that
    is what made_of means for the purpose of this check — and if the graph changes, so does the
    profile."""
    return _profile_with(relation)


def _mass_score(objs: list, prof: Counter, relation: str = "") -> float:
    """How much of a relation's own object mass these heads sit on, per object.

    Membership alone was tried FIRST and it failed at scale: `air` and `anther` appear somewhere in
    made_of's 6,738 rows, so a wholesale-wrong proposal scored 'familiar' on the strength of a few
    incidental hits. Weighting by how much of the relation each head actually carries separates a
    head the relation LIVES on (wood, steel, flour) from one it merely touched once."""
    import math
    total = max(1, sum(prof.values()))
    if not objs:
        return 0.0
    return sum(math.log1p(prof.get(_head(o, relation), 0) / total * 1000)
               for o in objs) / len(objs)


def discriminate(proposed_objects, relations=None) -> dict:
    """Which relation do these objects fit BEST, and is that win decisive?

    This is the question the first version got wrong by not asking it. Judging one relation in
    isolation asks "could these be made_of objects?", and the answer is often yes-ish for any
    relation, which is how `consisting of` passed the very gate built to stop it. The useful question
    is comparative: if a set of objects fits three relations equally, the cue carries no relational
    information and adding it asserts something the evidence does not support."""
    rels = tuple(relations) if relations else ("used_for", "made_of", "capable_of")
    objs = [str(o) for o in proposed_objects if str(o).strip()]
    scores = {r: _mass_score(objs, profile(r), r) for r in rels}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best, best_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = (best_score - runner_up) / best_score if best_score > 0 else 0.0
    return {"scores": {k: round(v, 4) for k, v in scores.items()},
            "best": best, "margin": round(margin, 4)}


def clusters(relations=None, overlap: float = 0.15, head=None) -> list:
    """Relations grouped by how much their object vocabularies actually overlap.

    MEASURED, not declared, and it changes the coherence test from wrong to right. The instance vote
    was splitting `used to` across used_for and capable_of and calling the cue ambiguous -- but those
    two relations SHARE 7,384 head nouns (jaccard 0.272), five times any other pair here, because
    both take actions. Their disagreement is a fact about the relations, not about the cue.

    made_of overlaps neither (0.055, 0.045), so it stands alone, and a cue whose instances split
    ACROSS clusters is genuinely ambiguous in the way `consisting of` is."""
    rels = list(relations) if relations else ["used_for", "made_of", "capable_of"]
    sets = {r: set(_profile_with(r, head)) for r in rels}
    groups: list = []
    for r in rels:
        placed = False
        for g in groups:
            if any(sets[r] and sets[o] and
                   len(sets[r] & sets[o]) / len(sets[r] | sets[o]) >= overlap for o in g):
                g.append(r)
                placed = True
                break
        if not placed:
            groups.append([r])
    return groups


def coherence(proposed_objects, relations=None) -> dict:
    """Do the INSTANCES agree with each other about which relation this is?

    The check that the first two versions of this gate were missing, and the one the motivating case
    actually needed. `consisting of` was refused by hand as "has_part, not made_of" -- and that hand
    judgement was itself too coarse. It is BOTH:

        a mixture consisting of flour and water   -> made_of
        a country consisting of fifty states      -> has_part

    The relation is fixed by the OBJECT, not by the cue. So a cue->relation rule is the wrong
    granularity for it, and no amount of aggregate distributional fit can say so, because the
    aggregate is a blend of two populations that each fit something.

    Asking each instance separately exposes exactly that: if the instances disagree about which
    relation they belong to, the cue carries no relation and must not become a rule."""
    rels = tuple(relations) if relations else ("used_for", "made_of", "capable_of")
    objs = [str(o) for o in proposed_objects if str(o).strip()]
    if not objs:
        return {"coherence": 1.0, "modal": None, "n": 0}
    profs = {r: profile(r) for r in rels}
    votes: Counter = Counter()
    for o in objs:
        scored = sorted(((_mass_score([o], profs[r], r), r) for r in rels), reverse=True)
        if scored and scored[0][0] > 0:
            votes[scored[0][1]] += 1
    if not votes:
        return {"coherence": 0.0, "modal": None, "n": len(objs)}
    # agreement is measured over CLUSTERS: relations whose object vocabularies overlap are the same
    # kind of thing, so a vote split between them is not disagreement about what the cue means
    by_cluster: Counter = Counter()
    for group in clusters(rels):
        key = "|".join(sorted(group))
        by_cluster[key] = sum(votes.get(r, 0) for r in group)
    modal_cluster, top = by_cluster.most_common(1)[0]
    modal, _ = votes.most_common(1)[0]
    return {"coherence": top / sum(by_cluster.values()), "modal": modal,
            "modal_cluster": modal_cluster, "n": sum(votes.values()), "votes": dict(votes)}


def _judge_without_history(relation: str, proposed_objects) -> "Verdict":
    """Judge a relation that has no rows yet, using the vocabulary that named it.

    Needs SUBJECTS to check against the oracle, and `judge` is handed only objects, so a caller that
    can supply pairs gets a real verdict and one that cannot gets a REFUSAL rather than a pass. That
    asymmetry is deliberate: the failure mode being closed is a new relation accepting everything, and
    the safe default when evidence is unavailable is no."""
    external = {"used_for": "UsedFor", "capable_of": "CapableOf", "made_of": "MadeOf",
                "has_a": "HasA", "part_of": "PartOf", "is_a": "IsA", "at_location": "AtLocation",
                "causes": "Causes", "has_property": "HasProperty", "desires": "Desires",
                "created_by": "CreatedBy", "receives_action": "ReceivesAction"}.get(relation)
    n = len([o for o in proposed_objects if str(o).strip()])
    if not external:
        return Verdict(accept=False, relation=relation, familiar=0.0, profile_size=0,
                       reason=(f"{relation!r} has no rows of its own AND no entry in the external "
                               f"vocabulary, so nothing can corroborate it. Refused rather than "
                               f"waved through"))
    return Verdict(accept=False, relation=relation, familiar=0.0, profile_size=0,
                   reason=(f"{relation!r} has no history yet ({n} objects proposed). A relation with "
                           f"no rows cannot be judged against itself, and this path used to ACCEPT on "
                           f"that basis -- turning a new relation into a sink. Corroboration against "
                           f"{external} needs subjects as well as objects; call "
                           f"relation_discovery.discover(cue, pairs) for a real verdict"))



def judge(relation: str, proposed_objects, *, min_familiar: float = 0.35,
          min_profile: int = 200, min_margin: float = 0.15) -> Verdict:
    """Would these objects be at home under this relation, and under this one MORE than the others?

    Three conditions, and the third was added after the second version of this gate was defeated in
    the field by the exact case it was written for:

      familiarity   the objects' heads are ones the relation has taken
      mass          weighted by how much of the relation those heads carry, not mere membership
      margin        this relation must beat the runner-up. A cue whose objects fit every relation
                    equally well distinguishes nothing, and asserting it would be inventing a
                    relation the evidence does not pick out."""
    prof = profile(relation)
    if sum(prof.values()) < min_profile:
        # A RELATION WITH NO HISTORY IS NOT A LICENCE, and the first version made it one. When the
        # loop added `has_a` it had zero rows, so this branch abstained-and-accepted -- and the very
        # next run produced six proposals mapping cues like `intended to` onto it, including
        # deliberate garbage in a direct test. A new relation became a sink that swallowed everything
        # until it accumulated enough history to start refusing, by which point the history would be
        # made of whatever had been let through.
        #
        # So the fallback is the EXTERNAL oracle -- the same base-rate-controlled check that named the
        # relation in the first place. No internal history is required for it, and a relation nobody
        # can corroborate stays refused rather than open.
        return _judge_without_history(relation, proposed_objects)
    objs = [str(o) for o in proposed_objects if str(o).strip()]
    if not objs:
        return Verdict(accept=True, relation=relation, familiar=1.0, profile_size=sum(prof.values()),
                       reason="nothing proposed")
    heads = [_head(o, relation) for o in objs]
    familiar = sum(1 for h in heads if prof.get(h, 0) > 0) / len(heads)
    alien = sorted({o for o, h in zip(objs, heads) if prof.get(h, 0) == 0})

    disc = discriminate(objs)
    wins = disc["best"] == relation
    decisive = disc["margin"] >= min_margin
    coh = coherence(objs)
    # the instances must agree AND agree on THIS relation's kind. `consisting of` reaches 68%
    # agreement, but that agreement is for the ACTION cluster while the proposal was made_of --
    # which is precisely the mismatch that makes the cue ambiguous. Coherence alone said yes.
    in_modal = relation in (coh.get("modal_cluster") or "").split("|")
    consistent = coh["coherence"] >= 0.6 and in_modal
    accept = familiar >= min_familiar and wins and decisive and consistent

    reason = (f"{familiar:.0%} familiar heads; best fit {disc['best']!r} by {disc['margin']:.0%}; "
              f"instance agreement {coh['coherence']:.0%} (votes {coh.get('votes')})")
    if familiar < min_familiar:
        reason += f" — REFUSED: below {min_familiar:.0%} familiarity"
    elif not wins:
        reason += f" — REFUSED: these objects fit {disc['best']!r} better than {relation!r}"
    elif not decisive:
        reason += (f" — REFUSED: margin under {min_margin:.0%}; the objects fit several relations "
                   f"about equally, so the cue picks out no particular one")
    elif not in_modal:
        reason += (f" — REFUSED: the instances agree on {coh.get('modal_cluster')!r}, not on "
                   f"{relation!r}. The cue's own examples point somewhere else")
    elif not consistent:
        reason += (" — REFUSED: the instances disagree about which relation they are. The cue is "
                   "AMBIGUOUS, not wrong: its relation is fixed by the object, so a cue->relation "
                   "rule is the wrong granularity for it")
    return Verdict(accept=accept, relation=relation, familiar=familiar, alien=alien,
                   profile_size=sum(prof.values()), reason=reason)


def judge_extraction(relation: str, sentences, extractor) -> Verdict:
    """Run a proposed extractor over real sentences and judge what it would actually assert.

    Judging the RESULT rather than the regex is the point: a pattern is easy to argue about and its
    output is not. This is what a self-repair loop should call before applying its own patch."""
    produced = []
    for subject, sentence in sentences:
        try:
            for pred, obj in extractor(subject, sentence) or []:
                if pred == relation:
                    produced.append(obj)
        except Exception:
            continue
    return judge(relation, produced)
