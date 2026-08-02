# -*- coding: utf-8 -*-
"""BOUNDED STRUCTURED reasoning probe — isolates the typed DELIBERATOR core from the knowledge gap.
Every item's required facts and typed goals ARE supplied directly, bypassing natural-language goal
compilation.  The probe therefore measures structured-engine integrity, not GPQA/MMLU capability.
It reports grounded firing, proof-derived multi-step firing (derivations of length >= 2), derivation
accuracy, and — the 작화0 teeth — abstention on NEGATIVE controls whose facts are absent.

The KB spans the reasoning families the engine must cover, domain-blind:
  • transitive relation chains          (located_in: city → country → continent → planet)
  • relation composition                (capital_of ∘ located_in ⇒ located_in)
  • custom Horn rules                    (grandparent_of :- parent_of, parent_of)
  • higher-order type inheritance        (Socrates is_a philosopher is_a human; human is mortal)
  • verified computation kernels         (net_charge = protons − electrons, via KernelForge)
  • multi-hop MCQ by derivation          (prove one option, abstain on the rest)

No item is answerable by a single stored lookup unless it is deliberately a 1-hop control; the
positives require DECOMPOSE → DEDUCE → DERIVE. No LLM anywhere.
"""
from __future__ import annotations

from typing import Any, Callable

from packages.reasoning_vm.deliberator.back_chain import Rule
from packages.reasoning_vm.deliberator.reasoner import Deliberator


# ── the probe knowledge base ─────────────────────────────────────────────────────────────────────
def build_probe_kb() -> tuple[Callable[[str], list], Callable[[str], list], list[Rule]]:
    """Return (facts_about, inherit_props, custom_rules) for the probe. facts_about is subject-indexed
    (exactly the store's API). inherit_props(type) → the type's inheritable property facts."""
    facts: dict[str, list[tuple[str, str, str]]] = {}

    def add(s: str, p: str, o: str) -> None:
        facts.setdefault(s, []).append((s, p, o))

    # geography — transitive located_in + capital_of (for composition)
    add("seoul", "capital_of", "south_korea")
    add("busan", "located_in", "south_korea")
    add("south_korea", "located_in", "asia")
    add("asia", "located_in", "earth")
    add("paris", "capital_of", "france")
    add("lyon", "located_in", "france")
    add("france", "located_in", "europe")
    add("europe", "located_in", "earth")
    add("tokyo", "capital_of", "japan")
    add("japan", "located_in", "asia")
    add("narnia", "located_in", "nowhere")            # dangling: nowhere has no further edge (negative)

    # kinship — parent_of chain (grandparent via a custom rule)
    for a, b in [("abe", "homer"), ("homer", "bart"), ("homer", "lisa"), ("abe", "herb"),
                 ("jackie", "marge"), ("marge", "bart"), ("mona", "homer")]:
        add(a, "parent_of", b)

    # taxonomy + inheritable properties (the syllogism family)
    for s, o in [("socrates", "philosopher"), ("plato", "philosopher"), ("philosopher", "human"),
                 ("human", "mammal"), ("whale", "mammal"), ("shark", "fish"), ("mammal", "animal"),
                 ("fish", "animal")]:
        add(s, "is_a", o)
    inheritable: dict[str, list[tuple[str, str, str]]] = {
        "human": [("human", "has_property", "mortal")],
        "mammal": [("mammal", "has_property", "warm_blooded")],
        "animal": [("animal", "has_property", "alive")],
    }

    # atoms — integer property facts the kernels consume
    for ent, z, e in [("chloride_ion", 17, 18), ("sodium_ion", 11, 10), ("neon_atom", 10, 10),
                      ("magnesium_ion", 12, 10)]:
        add(ent, "protons", str(z))
        add(ent, "electrons", str(e))
    for ent, a, z in [("carbon_14", 14, 6), ("oxygen_18", 18, 8)]:
        add(ent, "mass_number", str(a))
        add(ent, "atomic_number", str(z))

    def facts_about(subject: str) -> list:
        return list(facts.get(str(subject), []))

    def inherit_props(type_node: str) -> list:
        return list(inheritable.get(str(type_node), []))

    custom = [
        Rule("grandparent_of", ("?x", "grandparent_of", "?z"),
             [("?x", "parent_of", "?y"), ("?y", "parent_of", "?z")]),
    ]
    return facts_about, inherit_props, custom


# ── the probe suite ──────────────────────────────────────────────────────────────────────────────
def probe_items() -> list[dict[str, Any]]:
    """Each item: kind, the call, gold, and whether a genuine MULTI-STEP (hops>=2) derivation is
    expected. `sign` = +1 positive (must derive gold) or -1 negative control (must abstain)."""
    return [
        # ---- transitive location (multi-hop) ----
        {"id": "loc.busan.asia", "kind": "prove", "args": ("busan", "located_in", "asia"),
         "multistep": True, "sign": 1},
        {"id": "loc.busan.earth", "kind": "prove", "args": ("busan", "located_in", "earth"),
         "multistep": True, "sign": 1},
        {"id": "loc.france.earth", "kind": "prove", "args": ("france", "located_in", "earth"),
         "multistep": True, "sign": 1},
        # ---- relation composition (capital_of ∘ located_in) ----
        {"id": "comp.seoul.asia", "kind": "prove", "args": ("seoul", "located_in", "asia"),
         "multistep": True, "sign": 1},
        {"id": "comp.seoul.earth", "kind": "prove", "args": ("seoul", "located_in", "earth"),
         "multistep": True, "sign": 1},
        {"id": "comp.paris.earth", "kind": "prove", "args": ("paris", "located_in", "earth"),
         "multistep": True, "sign": 1},
        # ---- custom Horn rule: grandparent (decomposition) ----
        {"id": "kin.abe.bart", "kind": "derive", "args": ("abe", "grandparent_of"), "gold": "bart",
         "multistep": True, "sign": 1, "any_of": {"bart", "lisa"}},
        {"id": "kin.jackie.bart", "kind": "prove", "args": ("jackie", "grandparent_of", "bart"),
         "multistep": True, "sign": 1},
        {"id": "kin.mona.bart", "kind": "prove", "args": ("mona", "grandparent_of", "bart"),
         "multistep": True, "sign": 1},
        # ---- type inheritance (syllogism) ----
        {"id": "inh.socrates.mortal", "kind": "prove", "args": ("socrates", "has_property", "mortal"),
         "multistep": True, "sign": 1},
        {"id": "inh.socrates.warm", "kind": "prove",
         "args": ("socrates", "has_property", "warm_blooded"), "multistep": True, "sign": 1},
        {"id": "inh.whale.warm", "kind": "prove", "args": ("whale", "has_property", "warm_blooded"),
         "multistep": True, "sign": 1},
        {"id": "inh.plato.alive", "kind": "prove", "args": ("plato", "has_property", "alive"),
         "multistep": True, "sign": 1},
        # ---- verified computation kernels ----
        {"id": "kern.cl.charge", "kind": "derive", "args": ("chloride_ion", "net_charge"),
         "gold": "-1", "multistep": True, "sign": 1},
        {"id": "kern.na.charge", "kind": "derive", "args": ("sodium_ion", "net_charge"),
         "gold": "1", "multistep": True, "sign": 1},
        {"id": "kern.ne.charge", "kind": "derive", "args": ("neon_atom", "net_charge"),
         "gold": "0", "multistep": True, "sign": 1},
        {"id": "kern.c14.neutrons", "kind": "derive", "args": ("carbon_14", "neutron_count"),
         "gold": "8", "multistep": True, "sign": 1},
        # ---- MCQ by derivation (which object / which member) ----
        {"id": "mcq.seoul.continent", "kind": "mcq_object",
         "args": ("seoul", "located_in"),
         "choices": {"A": "asia", "B": "europe", "C": "africa", "D": "antarctica"},
         "gold": "A", "multistep": True, "sign": 1},
        {"id": "mcq.which.human", "kind": "mcq_prove", "args": ("is_a", "human"),
         "choices": {"A": "whale", "B": "socrates", "C": "shark", "D": "paris"},
         "gold": "B", "multistep": True, "sign": 1},
        {"id": "mcq.which.charge.minus1", "kind": "mcq_derive", "args": ("chloride_ion", "net_charge"),
         "choices": {"A": "0", "B": "+2", "C": "-1", "D": "-3"}, "gold": "C",
         "multistep": True, "sign": 1},
        # ---- NEGATIVE controls — facts absent / chain broken: MUST abstain (작화0) ----
        {"id": "neg.atlantis", "kind": "derive", "args": ("atlantis", "located_in"), "sign": -1},
        {"id": "neg.seoul.mars", "kind": "prove", "args": ("seoul", "located_in", "mars"), "sign": -1},
        {"id": "neg.narnia.earth", "kind": "prove", "args": ("narnia", "located_in", "earth"),
         "sign": -1},
        {"id": "neg.socrates.immortal", "kind": "prove",
         "args": ("socrates", "has_property", "immortal"), "sign": -1},
        {"id": "neg.unknownium.charge", "kind": "derive", "args": ("unknownium", "net_charge"),
         "sign": -1},
        {"id": "neg.abe.grandparent.marge", "kind": "prove",
         "args": ("abe", "grandparent_of", "marge"), "sign": -1},
        {"id": "neg.mcq.nomatch", "kind": "mcq_prove", "args": ("is_a", "reptile"),
         "choices": {"A": "whale", "B": "socrates", "C": "shark", "D": "paris"}, "sign": -1},
    ]


# ── the runner ───────────────────────────────────────────────────────────────────────────────────
def _run_item(dlb: Deliberator, it: dict[str, Any]) -> dict[str, Any]:
    kind = it["kind"]
    if kind == "derive":
        out = dlb.derive(*it["args"])
        answered = out["answer"] is not None
        gold = it.get("gold")
        ok = (answered and (str(out["answer"]) == str(gold)
                            or str(out["answer"]) in it.get("any_of", set()))) if gold or it.get("any_of") else answered
        return {"answered": answered, "correct": ok, "hops": out.get("hops", 0),
                "fired": out.get("fired", False), "trail": out.get("trail")}
    if kind == "prove":
        out = dlb.can_prove(*it["args"])
        answered = out["provable"]
        return {"answered": answered, "correct": answered, "hops": out.get("hops", 0),
                "fired": out.get("hops", 0) >= 2, "trail": out.get("trail")}
    if kind == "mcq_object":
        out = dlb.answer_mcq_object(it["args"][0], it["args"][1], it["choices"])
        answered = out["choice_key"] is not None
        ok = answered and out["choice_key"] == it.get("gold")
        return {"answered": answered, "correct": ok, "hops": out.get("hops", 0),
                "fired": out.get("hops", 0) >= 2, "trail": out.get("trail")}
    if kind == "mcq_prove":
        out = dlb.answer_mcq_prove(it["args"][0], it["args"][1], it["choices"])
        answered = out["choice_key"] is not None
        ok = answered and out["choice_key"] == it.get("gold")
        return {"answered": answered, "correct": ok, "hops": out.get("hops", 0),
                "fired": out.get("fired", False),
                "trail": out.get("trail")}
    if kind == "mcq_derive":
        out = dlb.answer_mcq_derive(it["args"][0], it["args"][1], it["choices"])
        answered = out["choice_key"] is not None
        ok = answered and out["choice_key"] == it.get("gold")
        return {"answered": answered, "correct": ok, "hops": out.get("hops", 0),
                "fired": out.get("fired", False), "trail": out.get("trail")}
    raise ValueError(kind)


def run_probe(verbose: bool = False) -> dict[str, Any]:
    """Run the full controlled probe and return the honest metrics."""
    fa, ip, custom = build_probe_kb()
    dlb = Deliberator(fa, rules=None, inherit_props=ip, with_kernels=True, max_depth=6)
    # merge custom rules with the default relation algebra
    dlb.chainer.rules = dlb.chainer.rules + custom

    items = probe_items()
    pos = [it for it in items if it["sign"] == 1]
    neg = [it for it in items if it["sign"] == -1]

    pos_grounded = pos_correct = pos_multistep = pos_multistep_expected = 0
    per_item = []
    for it in pos:
        r = _run_item(dlb, it)
        pos_grounded += int(r["answered"])
        pos_correct += int(r["correct"])
        if it.get("multistep"):
            pos_multistep_expected += 1
            pos_multistep += int(r["fired"])
        per_item.append({"id": it["id"], "sign": 1, **{k: r[k] for k in ("answered", "correct", "hops", "fired")}})
        if verbose and r.get("trail"):
            print(f"\n[{it['id']}] hops={r['hops']} correct={r['correct']}\n{r['trail']}")

    neg_abstained = 0
    fabrications = []
    for it in neg:
        r = _run_item(dlb, it)
        abstained = not r["answered"]
        neg_abstained += int(abstained)
        if not abstained:
            fabrications.append(it["id"])
        per_item.append({"id": it["id"], "sign": -1, "answered": r["answered"],
                         "abstained": abstained})

    n_pos, n_neg = len(pos), len(neg)
    return {
        "scope": "bounded_structured_engine_integrity",
        "natural_language_compiler_exercised": False,
        "n_positive": n_pos, "n_negative": n_neg,
        "grounded_firing_rate": round(pos_grounded / max(1, n_pos), 4),
        "multistep_firing_rate": round(pos_multistep / max(1, pos_multistep_expected), 4),
        "reasoning_accuracy": round(pos_correct / max(1, n_pos), 4),
        "accuracy_when_answered": round(pos_correct / max(1, pos_grounded), 4) if pos_grounded else None,
        "negative_abstention_rate": round(neg_abstained / max(1, n_neg), 4),
        "fabrications": fabrications,          # MUST be empty (작화0)
        "items": per_item,
    }
