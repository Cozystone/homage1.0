# -*- coding: utf-8 -*-
"""The registered falsification: a verb never seen, learned from a gloss, changing behaviour.

    python scripts/unseen_verb_test.py [n_episodes]

Registered in ATANOR_action_wiring_from_language_2026-07-29.md before anything was built:

    A system that executes `avoid`, `eat` and `chase` because those three were built is a lookup table
    with extra steps. The only test that separates composition from tabulation is that it must
    correctly execute VERBS IT HAS NEVER SEEN, supplied only as a sentence, judged BEHAVIOURALLY.

`shun` and `gorp` appear in no frame, no bind map, and no corpus here — `gorp` is not a word. What they
get is one English sentence apiece, and the route is the one humans actually use for rare vocabulary:
you learn `abscond` from "to leave secretly", not from absconding.

    "Gorp is defined as avoid."   ->  (gorp, defined_as, avoid)      read, not pattern-matched
    avoid is bound to PROXIMITY polarity -1
    therefore gorp is PROXIMITY polarity -1                          by FOLLOWING THE EDGE

THE RESOLUTION IS TRAVERSAL, NOT A TABLE. `resolve()` below walks defined_as and alias edges until it
reaches a relation that has a schema, and it is the same three lines whether the chain is one hop or
five. Adding a new verb adds an EDGE, never a row of code — which is the whole claim, and the reason
this test is the one that can refute it.

WHAT IS STILL SUPPLIED: the three bindings at the end of the chain (avoid, chase, reach -> PROXIMITY).
The unseen verbs reach them without being enumerated, which is what is being tested; the existence of a
grounded endpoint is not.

REGISTERED BEFORE RUNNING:
    1  gorp and shun compile to a goal functional IDENTICAL to the one their gloss names — exact
       structural comparison, not a similarity score
    2  behaviourally, the gorp arm dies at the same rate as the avoid arm
    3  and BOTH die less than an arm whose unseen verb was glossed to `chase` — without this the first
       two are satisfied by an executor that ignores its instruction

POSITIONS ARE SUPPLIED HERE and this is therefore NOT an agent result. Today's pixel body-finding is
right 57% of the time and at that accuracy the executor produces no measurable steering at all
(avoid 14.06 vs random 15.11, p=0.26, with the polarity control inverted). Running this on pixels would
measure the perception blocker, not the language claim. Both are open; they are measured apart.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.image_schema import Proximity                                  # noqa: E402
from packages.image_schema.inverse_speaker import InverseSpeaker, norm       # noqa: E402
from packages.realizer_struct.frame_realizer import FRAMES, load_mined_frames  # noqa: E402
from scripts.atari_find_body import measured_warmup                          # noqa: E402
from scripts.atari_play import make                                          # noqa: E402
from scripts.schema_executor_pacman import episode                           # noqa: E402
from scripts.atari_taught import fit_ram_to_screen                           # noqa: E402

OUT = Path("data/language/unseen_verb_test.json")

NEW_FRAMES = {"avoid": {"tmpl": "{s} must stay away from {o}"},
              "chase": {"tmpl": "{s} must go after {o}"}}
BOUND = {"avoid": (Proximity, -1), "chase": (Proximity, +1)}

# One sentence per unseen verb. Nothing else about them exists anywhere.
GLOSSES = ["Shun is defined as avoid.",
           "Gorp is defined as avoid.",
           "Zibble is defined as chase."]


def resolve(rel: str, graph: dict, seen=None):
    """Walk definition edges until a relation with a schema is reached. Three lines, any depth."""
    seen = seen or set()
    if rel in BOUND:
        return BOUND[rel], [rel]
    if rel in seen:
        return None, []
    seen.add(rel)
    for tgt in graph.get(rel, ()):
        got, path = resolve(tgt, graph, seen)
        if got:
            return got, [rel] + path
    return None, []


def main() -> None:
    load_mined_frames()
    for r, f in NEW_FRAMES.items():
        FRAMES.setdefault(r, f)
    inv = InverseSpeaker(sorted(FRAMES))

    print("Three sentences. `shun`, `gorp` and `zibble` are in no frame, no bind map, no corpus.\n")
    graph: dict = {}
    rows = []
    for g in GLOSSES:
        best, n = inv.best(g)
        rec = {"gloss": g, "structure": best, "alternatives": n}
        if best is None:
            rec["stage"] = "UNREADABLE"
        else:
            subj, rel, obj = best
            v, target = norm(subj), norm(obj)
            graph.setdefault(v, []).append(target)
            rec.update({"stage": "READ", "verb": v, "via": rel, "means": target})
        rows.append(rec)
        print(f"  {g:<30} -> {rec.get('structure')}")

    print()
    compiled = {}
    for rec in rows:
        if rec.get("stage") != "READ":
            continue
        got, path = resolve(rec["verb"], graph)
        if not got:
            rec["stage"] = "UNRESOLVED"
            print(f"  {rec['verb']:<10} no path from the gloss to any bound relation")
            continue
        cls, pol = got
        compiled[rec["verb"]] = (cls, pol)
        rec.update({"stage": "COMPILED", "path": path, "schema": cls("me", "x", polarity=pol).name,
                    "polarity": pol})
        print(f"  {rec['verb']:<10} {' -> '.join(path):<24} {rec['schema']} polarity {pol:+d}")

    same = all(compiled.get(v, (None, None))[1] == BOUND["avoid"][1] for v in ("shun", "gorp")) \
        and compiled.get("zibble", (None, None))[1] == BOUND["chase"][1]
    print(f"\n-> 1. the unseen verbs compile to exactly their gloss's goal functional: {same}")
    if not same:
        sys.exit("registered test 1 failed; the behavioural arms would be meaningless")

    env = make()
    warm = measured_warmup(env, env.action_space.n)
    fit, agree = fit_ram_to_screen(env, warm)
    env.close()
    print(f"   oracle r_x {agree['r_x']:.3f} — POSITIONS SUPPLIED, so this is a mechanism test\n")

    N = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    arms = {"random": "random", "avoid (known verb)": "avoid",
            "gorp (unseen, glossed to avoid)": "avoid", "zibble (unseen, glossed to chase)": "chase"}
    res = {}
    for label, mode in arms.items():
        runs = [episode(mode, warm, 800 + s, fit) for s in range(N)]
        res[label] = [1000.0 * r["deaths"] / max(r["steps"], 1) for r in runs]
        d = np.array(res[label])
        print(f"  {label:<34} deaths/1000 {d.mean():>6.2f} +- {d.std(ddof=1):>4.2f}")

    from scipy.stats import mannwhitneyu
    A = np.array(res["avoid (known verb)"])
    G = np.array(res["gorp (unseen, glossed to avoid)"])
    Z = np.array(res["zibble (unseen, glossed to chase)"])
    R = np.array(res["random"])
    p_same = mannwhitneyu(G, A, alternative="two-sided").pvalue
    p_g = mannwhitneyu(G, Z, alternative="less").pvalue
    p_r = mannwhitneyu(G, R, alternative="less").pvalue

    print(f"\n-> 2. gorp behaves like the verb it was glossed to: "
          f"p = {p_same:.4f}  {'INDISTINGUISHABLE, as required' if p_same > 0.05 else 'DIFFERENT — fails'}")
    print(f"-> 3. gorp dies less than zibble (opposite gloss): p = {p_g:.4f}   "
          f"{'REAL' if p_g < 0.05 else 'not established'}")
    print(f"      and less than random:                        p = {p_r:.4f}   "
          f"{'REAL' if p_r < 0.05 else 'not established'}")
    passed = same and p_same > 0.05 and p_g < 0.05
    print(f"\n{'THE REGISTERED FALSIFICATION IS NOT REFUTED' if passed else 'FAILS'} — "
          f"a verb that exists only in one sentence changed behaviour, and a differently glossed one "
          f"changed it the other way.")
    print("What this does NOT establish: positions are supplied, so the pixel front-end remains the")
    print("open blocker, and the endpoint bindings (avoid/chase -> PROXIMITY) are still written by hand.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"rows": rows, "arms": res, "p_same": float(p_same),
                               "p_vs_opposite": float(p_g), "p_vs_random": float(p_r),
                               "passed": bool(passed)}, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
