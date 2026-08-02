# -*- coding: utf-8 -*-
"""Every mirror built toward selfhood, and whether it points at anything.

    from packages.meta_diagnosis.selfhood_census import census
    census()

THE OWNER'S FRAME: scattered sunlight only lights a fire if the mirrors are aimed at one point. Build
as many mirrors as possible -- but a mirror facing the ground adds nothing, and this project's measured
pathology all year has been exactly that: organs built, present, and unread. Six instances in one day.

So before proposing new organs for selfhood, this counts the ones that exist. Fifteen packages and
twenty-odd modules already carry the vocabulary -- global workspace, inner voice, felt judgment,
self-model, homeostasis, narrative corpus, continuous self, autopoiesis. The question is not whether
they were built. It is:

    IMPORTED   does any non-test module use it at all
    LIVE       is it reachable from something that actually runs -- the API app, a daemon, the loop
    FEEDS      does what it computes reach a DIFFERENT organ, or does it terminate in a report

The third column is the one that matters for the Axiom of Self. M2 requires that a judgment about a
norm be re-usable by later judgment; R requires that a past commitment exert force on a present
choice. Both are cross-organ by definition. An organ whose output nothing else consumes cannot
participate in either, however sophisticated it is inside.

WHAT THIS DELIBERATELY DOES NOT MEASURE: whether anything is felt. The project's standing rule is that
a qualia verdict is outside what any gate here reaches. This counts aim, not fire.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: the mirrors -- every package and module whose subject is the system itself rather than the world.
MIRRORS = (
    ("packages/cortex_g2/global_workspace.py", "global workspace: one stage all organs can reach"),
    ("packages/live_selfhood_cycle/workspace.py", "the live selfhood workspace"),
    ("packages/inner_voice", "inner speech -- the owner's own proposed tell"),
    ("packages/continuous_self/self_model.py", "the model it keeps of itself"),
    ("packages/continuous_self/homeostasis.py", "keeping its own state in range"),
    ("packages/self_model/self_in_world_probe.py", "itself as a causal node in the world"),
    ("packages/self_model/self_causal_reasoner.py", "reasoning about its own effects"),
    ("packages/subjective/felt_judgment.py", "judgment that carries a felt weight"),
    ("packages/base_brain/felt_speech.py", "speech that carries one"),
    ("packages/knowledge_repair/felt_limits.py", "feeling the edge of what it knows"),
    ("packages/autonomy_kernel/intrinsic_drive.py", "wanting something without being asked"),
    ("packages/autonomy_kernel/narrative_corpus.py", "its own story, as material"),
    ("packages/neural_emotion", "hormones as dynamics rather than labels"),
    ("packages/spark_chamber/homeostasis.py", "endogenous rhythm"),
    ("packages/consciousness_audit", "auditing its own consciousness claims"),
    ("packages/consciousness_blind", "the blind control for those claims"),
    ("packages/selfhood_runtime", "selfhood at runtime"),
    ("packages/selfhood_control", "the control arm"),
    ("packages/live_selfhood_monitor", "watching the selfhood cycle"),
    ("packages/self_acceleration", "changing its own rate"),
    ("packages/self_evolution", "changing its own structure"),
    ("packages/ego_network/seed_identity.py", "the identity it starts from"),
    ("packages/embodiment/identity.py", "identity through a body"),
)

#: things that actually run: if a mirror is reachable from one of these, it is aimed at something.
LIVE_ROOTS = ("apps/api/app/main.py", "packages/self_repair/autorun.py",
              "packages/live_selfhood_cycle", "packages/reasoning_vm/cls_daemon.py")


def _modname(rel: str) -> str:
    return rel.replace("/", ".").removesuffix(".py")


def _sources() -> list:
    out = []
    for top in ("packages", "apps", "scripts"):
        d = REPO / top
        if d.exists():
            out += [p for p in d.rglob("*.py")
                    if "tests" not in p.parts and not p.name.startswith("test_")]
    return out


def _imports(text: str) -> set:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    got = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            got.add(node.module)
        elif isinstance(node, ast.Import):
            got |= {a.name for a in node.names}
    return got


def census() -> dict:
    srcs = [(str(p.relative_to(REPO)).replace("\\", "/"),
             p.read_text(encoding="utf-8", errors="ignore")) for p in _sources()]
    graph = {rel: _imports(text) for rel, text in srcs}

    rows = []
    for target, what in MIRRORS:
        mod = _modname(target)
        importers = sorted({rel for rel, imps in graph.items()
                            if rel != target and any(i == mod or i.startswith(mod + ".")
                                                     for i in imps)})
        # LIVE: reachable, transitively, from something that actually runs
        live, seen, frontier = False, set(), [r for r in importers]
        while frontier and not live:
            cur = frontier.pop()
            if cur in seen:
                continue
            seen.add(cur)
            if any(cur.startswith(root) for root in LIVE_ROOTS):
                live = True
                break
            frontier += [rel for rel, imps in graph.items()
                         if rel not in seen and any(i == _modname(cur) or
                                                    i.startswith(_modname(cur) + ".")
                                                    for i in imps)]
        # FEEDS: consumed by an organ in a DIFFERENT package -- the cross-level condition
        own = target.split("/")[1] if "/" in target else target
        cross = [r for r in importers if len(r.split("/")) > 1 and r.split("/")[1] != own]
        rows.append({"mirror": target, "about": what, "importers": len(importers),
                     "live": live, "feeds_other_organs": len(cross),
                     "consumed_by": cross[:3],
                     "aimed": bool(live and cross)})

    aimed = [r for r in rows if r["aimed"]]
    dark = [r for r in rows if r["importers"] == 0]
    return {
        "mirrors": len(rows),
        "aimed_at_something": len(aimed),
        "nothing_imports_them": len(dark),
        "dark_list": [r["mirror"] for r in dark],
        "rows": rows,
        "reading": ("a mirror facing the ground adds no light. This counts AIM -- imported, live, and "
                    "consumed by a different organ -- because both conditions of the Axiom of Self "
                    "are cross-organ: a judgment that later judgment can reuse, and a past commitment "
                    "that pushes a present choice"),
        "not_measured": ("whether anything is felt. No gate here reaches it, and the owner has said "
                         "they will judge that by talking to it"),
    }
