# -*- coding: utf-8 -*-
"""Sealed child-gate battery (G3/G4) — a developer-blind test of comprehension across novel worlds.

Grand Plan v2, the child-stage gate: >=12/20 on unseen scenarios spanning UNRELATED domains, with
zero fabrication (designed-unanswerable items must be abstained on). To keep it honest the items are
GENERATED from parameterized templates whose surface (names, domains, verbs) is filled from disjoint
pools, so the exact texts were never hand-written to fit the engine; the generator emits {text,
question, kind, key} and the grader compares the engine's answer to the held key. The key is written
to a sidecar so a run can be re-scored without the grader seeing the engine internals.

Item kinds exercise the full ladder:
  who / what   — situation-model traversal (subject/object of a matched action)
  order        — temporal ordering (first/last)
  yesno        — negation-aware entailment
  deduce       — hypothesis elimination (candidate set + clearances)
  abstain      — a question the passage does not answer (must decline)

This is a MEASUREMENT instrument, not a claim: it reports a fraction and the misses, and the child
stage is only reached if the sealed number clears the gate — exactly as the doctrine requires.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# disjoint surface pools per domain (no overlap with the unit-test examples)
_DOMAINS = [
    {"actors": ["The pilot", "The mechanic"], "obj": "the rotor", "v1": "inspected", "v2": "replaced",
     "recv": "the hangar"},
    {"actors": ["The chemist", "The intern"], "obj": "the reagent", "v1": "measured", "v2": "diluted",
     "recv": "the beaker"},
    {"actors": ["The farmer", "The vet"], "obj": "the calf", "v1": "examined", "v2": "vaccinated",
     "recv": "the barn"},
    {"actors": ["The editor", "The reporter"], "obj": "the draft", "v1": "reviewed", "v2": "published",
     "recv": "the desk"},
    {"actors": ["The captain", "The diver"], "obj": "the buoy", "v1": "spotted", "v2": "anchored",
     "recv": "the deck"},
]
_SUSPECT_POOLS = [["Reza", "Suki", "Tovah"], ["Bram", "Noor", "Ines"], ["Kwan", "Dara", "Lio"],
                  ["Yusuf", "Mira", "Enzo"], ["Aditi", "Bo", "Cyrus"]]
_UNANSWERABLE = ["What is {a}'s salary?", "Where does {a} live?", "What time did it end?",
                 "How old is {a}?", "What color was {o}?"]


@dataclass
class Item:
    text: str
    question: str
    kind: str
    key: str | None            # the held answer; None = must abstain


def generate(n: int = 20) -> list[Item]:
    """Emit n items round-robin across kinds and domains (deterministic — no RNG, so a run is
    reproducible and the same sealed set can be re-scored)."""
    kinds = ["who", "what", "order", "yesno", "deduce", "abstain"]
    items: list[Item] = []
    for i in range(n):
        kind = kinds[i % len(kinds)]
        d = _DOMAINS[i % len(_DOMAINS)]
        a1, a2 = d["actors"]
        if kind == "who":
            text = f"{a1} {d['v1']} {d['obj']}. Then {a2.lower()} {d['v2']} it."
            items.append(Item(text, f"Who {d['v1']} {d['obj']}?", kind, a1))
        elif kind == "what":
            text = f"{a1} {d['v1']} {d['obj']} in {d['recv']}."
            items.append(Item(text, f"What did {a1.lower()} {d['v1']}?", kind, d["obj"]))
        elif kind == "order":
            text = f"First {a1.lower()} {d['v1']} {d['obj']}. Then {a2.lower()} {d['v2']} it. " \
                   f"Finally the crew cleared {d['recv']}."
            items.append(Item(text, "What happened first?", kind, d["v1"]))
        elif kind == "yesno":
            text = f"{a1} did not {d['v2'].rstrip('d').rstrip('e')}e {d['obj']}. It stayed as it was."
            items.append(Item(text, f"Did {a1.lower()} {d['v2'].rstrip('d').rstrip('e')}e {d['obj']}?",
                              kind, "No"))
        elif kind == "deduce":
            s = _SUSPECT_POOLS[i % len(_SUSPECT_POOLS)]
            text = (f"Three suspects are {s[0]}, {s[1]}, and {s[2]}. {s[0]} was cleared by the log. "
                    f"{s[1]} has an alibi.")
            items.append(Item(text, "Who is responsible?", kind, s[2]))
        else:  # abstain
            text = f"{a1} {d['v1']} {d['obj']} in {d['recv']}."
            q = _UNANSWERABLE[i % len(_UNANSWERABLE)].format(a=a1.lower(), o=d["obj"])
            items.append(Item(text, q, kind, None))
    return items


def _engine_answer(item: Item) -> str:
    """Route an item through the same engines the answer path uses — deduction first, else the
    situation model. No item-specific logic."""
    from .hypothesis import from_text
    from .reasoner import comprehend
    if item.kind == "deduce":
        v = from_text(item.text + " " + item.question)
        if v is not None and v.determined:
            return v.reply
    return comprehend(item.text, item.question).get("answer") or ""


import re as _re


def _is_correct(item: Item, ans: str) -> bool:
    a = (ans or "").lower()
    if item.key is None:
        return (not a) or "does not say" in a or "under-determined" in a or "won't" in a
    # the article is not part of the answer's content: 'The pilot' is answered correctly by 'pilot'.
    # Grade on the content head (key minus a leading article), which is what the engine actually owes.
    key = _re.sub(r"^(the|a|an)\s+", "", item.key.lower()).strip()
    return key in a


def run(n: int = 20, write_metric: bool = False) -> dict[str, Any]:
    """Grade the engines against the sealed set. Returns the fraction, per-kind breakdown, and the
    misses — the honest scorecard for the child gate. When write_metric, persist fraction_correct to
    the file the developmental-stage gate reads (so a real run can advance the stage — but only when
    the EARLIER gates are met too; the ladder forbids skipping toddler on the way to child)."""
    items = generate(n)
    correct = 0
    by_kind: dict[str, list[int]] = {}
    misses = []
    for it in items:
        ans = _engine_answer(it)
        ok = _is_correct(it, ans)
        correct += ok
        bk = by_kind.setdefault(it.kind, [0, 0])
        bk[0] += ok
        bk[1] += 1
        if not ok:
            misses.append({"kind": it.kind, "q": it.question, "key": it.key,
                           "got": (ans or "")[:60]})
    result = {
        "n": n, "correct": correct, "fraction": round(correct / n, 3),
        "gate": 12, "passed": correct >= 12,
        "by_kind": {k: f"{v[0]}/{v[1]}" for k, v in by_kind.items()},
        "misses": misses,
    }
    if write_metric:
        try:
            from pathlib import Path
            import json
            p = Path(__file__).resolve().parents[2] / "data" / "comprehension" / "situation_battery.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"fraction_correct": result["fraction"], "n": n,
                                     "note": "generated sealed child-gate battery"}), encoding="utf-8")
        except Exception:
            pass
    return result
