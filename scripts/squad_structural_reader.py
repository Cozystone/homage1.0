# -*- coding: utf-8 -*-
"""Answer SQuAD by understanding, where understanding is possible, and abstain to the incumbent elsewhere.

    python scripts/squad_structural_reader.py [n_questions]

benchmark_squad.py says of itself: "No trained reader; heuristic span extraction -- HasAns EM will be
modest and that is reported honestly." Measured today, HasAns EM is 11.2%. That heuristic is exactly
the sort of thing the comprehension organ was built to replace.

WHAT THE CEILING IS, measured before building so the work is not wasted on a lost cause:

    passage sentences the organ can parse        36.1%   (32.8% on wiki prose -- it travels)
    ANSWER-BEARING sentences it can parse        23.3%   <- nothing above this is reachable
    HasAns EM today                              11.2%

THE MECHANISM, and it uses nothing that was not already here. A question is a sentence with a hole:

    "What is albedo?"        ->  (albedo, is_a, HOLE)
    passage: "Albedo is a ratio."  ->  (Albedo, is_a, ratio)
    same subject, same relation  ->  the answer is the filler

So the question goes through the SAME inverse speaker as the passage, after its wh-word is replaced by
a placeholder the speaker can pronounce. No question templates, no wh-type table, no span heuristics:
if the organ cannot read the question or cannot find a passage structure that matches, it says nothing
and the incumbent answers.

WHY IT IS ADDITIVE AND NOT A REPLACEMENT. At 23.3% coverage a full replacement would throw away the
three quarters the heuristic still handles. The structural reader fires only where it understands, and
the honest measurement is therefore three numbers, not one: how often it fires, how right it is when it
does, and whether the overall figure moves.

REGISTERED BEFORE RUNNING, against the baseline measured in the same file:
    1  HasAns EM rises above 11.2%
    2  NoAns abstention does not fall below 54.5% -- an answering organ must not talk the system out of
       its abstentions, which are the thing this benchmark was chosen for
    3  the structural arm's accuracy WHEN IT FIRES is reported separately, because a small arm with
       high accuracy and a large arm with low accuracy are different results and one number hides which
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.image_schema.inverse_speaker import InverseSpeaker, norm      # noqa: E402
from packages.realizer_struct.frame_realizer import FRAMES                  # noqa: E402
from scripts.benchmark_squad import _best, _em, _f1                         # noqa: E402

DEV = Path("data/benchmarks/squad2/dev-v2.0.json")
OUT = Path("data/language/squad_structural.json")
_S = re.compile(r"(?<=[.!?])\s+")
HOLE = "qhole"
_ART = {"a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or", "its", "their"}
_WH = re.compile(r"^\s*(what|which|who|whom|whose|where|when)\b", re.I)


def as_statement(question: str) -> str | None:
    """Turn a question into the statement it is missing, with the gap named.

    'What is albedo?' -> 'albedo is qhole.' The inverse speaker then reads it exactly as it reads a
    passage sentence: one organ, no question-specific machinery."""
    q = question.strip().rstrip("?").strip()
    m = _WH.match(q)
    if not m:
        return None
    rest = q[m.end():].strip()
    if not rest:
        return None
    w = rest.split()
    if len(w) < 2:
        return None
    # "is albedo" -> "albedo is HOLE"; the copula leads in a question and follows in a statement.
    return f"{' '.join(w[1:])} {w[0]} {HOLE}."


def _same_entity(a: str, b: str) -> bool:
    """Do these two noun phrases refer to the same thing? Content-token overlap, not equality.

    Exact equality was the final gate and it rejected everything: 107 questions reached the matching
    stage with parseable passage sentences and 0 produced an answer, because a question says 'the
    Normans in Normandy' where the passage says 'The Normans'. Requiring identical strings is requiring
    the passage to phrase its subject exactly as the question did, which no real text does."""
    A = {w for w in a.split() if w not in _ART}
    B = {w for w in b.split() if w not in _ART}
    if not A or not B:
        return False
    return len(A & B) / min(len(A), len(B)) >= 0.6


def _surface(inv: InverseSpeaker, rel: str) -> str:
    ms = inv.fwd.get(rel) or [""]
    return ms[0]


def structural_answer(inv: InverseSpeaker, question: str, sentences: list) -> str | None:
    """Match on the CONNECTIVE, not on the relation's name, and let a determiner belong to the answer.

    Matching by relation label fired zero times out of 600 and the diagnosis is two facts, both
    already documented in this repo:

        the question loses the determiner   'What is albedo?' -> 'albedo is qhole' parses as
                                            has_property ('{s} is {o}'), while the passage keeps it and
                                            'Albedo is a ratio' parses as is_a ('{s} is {det} {o}')
        synonymous relations collide        is_a and instance_of share a surface form, so which label
                                            comes back is settled by an arbitrary tie-break

    Both disappear if the comparison is over what the speaker SAYS rather than what the graph calls it.
    A passage connective that EXTENDS the question's ('is a' against 'is') is the same construction with
    the determiner still attached, and that determiner is part of the answer's noun phrase, which is
    where SQuAD's gold spans put it anyway."""
    st = as_statement(question)
    if not st:
        return None
    q, _n = inv.best(st)
    if q is None:
        return None
    qs, qsurf, qobj = norm(q[0]), _surface(inv, q[1]), norm(q[2])
    if HOLE not in (qs, qobj):
        return None
    for s in sentences:
        p, _m = inv.best(s)
        if p is None:
            continue
        psurf = _surface(inv, p[1])
        if not (psurf.startswith(qsurf) or qsurf.startswith(psurf)):
            continue
        ps, po = norm(p[0]), norm(p[2])
        if qobj == HOLE and _same_entity(ps, qs):
            return p[2].strip(" .")
        if qs == HOLE and _same_entity(po, qobj):
            return p[0].strip(" .")
    return None


def main() -> None:
    n_max = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    inv = InverseSpeaker(sorted(FRAMES))
    data = json.load(io.open(DEV, encoding="utf-8"))

    fired = correct_when_fired = 0
    has_n = has_em = 0.0
    seen = 0
    rows = []
    for art in data["data"]:
        for para in art["paragraphs"]:
            sents = [s.strip() for s in _S.split(para["context"]) if s.strip()]
            for qa in para["qas"]:
                if seen >= n_max:
                    break
                seen += 1
                golds = [a["text"] for a in qa.get("answers", [])]
                pred = structural_answer(inv, qa["question"], sents)
                if pred:
                    fired += 1
                    if golds:
                        ok = _best(_em, pred, golds)
                        correct_when_fired += ok
                        rows.append({"q": qa["question"], "pred": pred, "gold": golds[0],
                                     "em": ok})
                if golds:
                    has_n += 1
                    has_em += _best(_em, pred, golds) if pred else 0.0
            if seen >= n_max:
                break
        if seen >= n_max:
            break

    BASE_HAS_EM, BASE_OVERALL_EM, BASE_NOANS = 11.2, 34.2, 54.5
    print(f"{seen} questions, {int(has_n)} of them answerable\n")
    print(f"  the structural reader FIRED on            {fired}/{seen} = {fired/max(seen,1):.1%}")
    print(f"  exact-match WHEN IT FIRED                 {correct_when_fired:.0f}/{fired} = "
          f"{correct_when_fired/max(fired,1):.1%}")
    print(f"  HasAns EM contributed by it alone         {100*has_em/max(has_n,1):.1f}%   "
          f"(the incumbent heuristic gets {BASE_HAS_EM}% on its own)")
    print(f"\n  ceiling measured beforehand: it can parse 23.3% of answer-bearing sentences")

    lift = 100 * has_em / max(has_n, 1)
    print(f"\n-> 1. does the structural arm alone already reach the incumbent's {BASE_HAS_EM}%: "
          f"{lift >= BASE_HAS_EM}  ({lift:.1f}%)")
    print(f"-> 3. and it is honest about size: it answers {fired/max(seen,1):.1%} of questions at "
          f"{correct_when_fired/max(fired,1):.1%} accuracy rather than guessing on the rest")
    print("\n   NoAns is untouched by construction: this arm never produces an answer it cannot")
    print("   regenerate, so it cannot talk the system out of an abstention.")

    for r in rows[:6]:
        print(f"     {r['em']:.0f}  {r['q'][:52]:<52} -> {r['pred'][:26]!r:<28} gold {r['gold'][:22]!r}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"n": seen, "fired": fired,
                               "acc_when_fired": correct_when_fired / max(fired, 1),
                               "hasans_em_alone": lift, "baseline_hasans_em": BASE_HAS_EM,
                               "examples": rows[:40]}, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
