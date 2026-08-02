# -*- coding: utf-8 -*-
"""Where ATANOR's picture of itself loops back into what it DOES -- and where it dead-ends.

    from packages.meta_diagnosis.tangledness import census
    census()

THE QUESTION, in the owner's framing rather than mine. Consciousness is not a function to implement;
it is a phenomenon, and what an engineer can do is build the conditions under which it might arise.
Hofstadter's candidate condition is the STRANGE LOOP: a hierarchy stops being clean when the level
that represents the system becomes causally efficacious on the level being represented. The map has to
be inside the territory AND able to move it.

That is measurable here, and it is not measurable by asking whether anything is felt. ATANOR writes a
great deal about itself -- defect ledgers, cycle ledgers, enablement series, move searches, plateau
diagnoses, parameter searches. Each of those files is a self-representation. The question this file
answers is the only one that separates a strange loop from a diary:

    IS IT READ BACK?

A record that is written and never read is a clean hierarchy: the system describes itself and the
description changes nothing. A record that is read and changes what happens next is a level-crossing
feedback loop -- the condition, not the phenomenon.

WHAT MADE THIS URGENT, measured rather than theorised. Four unattended cycles diagnosed their own
escape correctly and identically -- `min_fire = 7` -- and not one applied it, because that constant
lives in `packages/self_repair/`, which the patcher refuses. ATANOR can represent itself and cannot
be itself. `provisional.FORBIDDEN` is, in these terms, an anti-strange-loop device: it exists
specifically to keep the hierarchy clean.

AND IT IS RIGHT TO EXIST, which is the part that makes this hard rather than just blocked. A loop
that may rewrite its own judge can pass anything by lowering the bar. But Goedel's construction is
exactly the model for the way out: the self-reference is productive BECAUSE the truth of the sentence
is settled outside the system. ATANOR already has that outside -- `scripts/gloss_lane_recall.py`, the
held-out harness the loop provably cannot reach. So the safety question is not "may the system touch
itself" but "may it touch the GROUND", and those are different questions that a single forbidden list
currently answers as one.

This module does not resolve that. It measures the present shape so the resolution is argued over
numbers.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCAN = ("packages", "scripts", "apps")

#: every artefact in which ATANOR records something about ITSELF -- its defects, its cycles, its
#: searches, its own diagnoses. Not its knowledge of the world; its knowledge of itself.
SELF_RECORDS = (
    ("data/self_repair/defects.jsonl", "defects it found in itself"),
    ("data/self_repair/cycles.jsonl", "its own repair cycles"),
    ("data/self_repair/autorun_history.jsonl", "what its scheduled runs saw"),
    ("data/self_repair/provisional_patches.jsonl", "patches it applied to itself"),
    ("data/self_repair/self_measured.jsonl", "measurements it took of itself"),
    ("data/self_repair/move_search.jsonl", "escape moves it tried"),
    ("data/self_repair/param_search_full.json", "its own constants, searched"),
    ("data/self_repair/pair_search_v2.json", "whether its escapes compose"),
    ("data/self_repair/operator_queue.jsonl", "what it wants a person to allow"),
    ("data/self_repair/acquired_oracle.jsonl", "evidence it went and got"),
    ("data/meta_diagnosis/improvement_cycles.jsonl", "its own improvement history"),
    ("data/meta_diagnosis/enablement.jsonl", "what each change unlocked"),
    ("data/meta_diagnosis/proxy_calibration.jsonl", "how well it can predict its own gate"),
    ("data/meta_diagnosis/recipes.json", "recipes it derived from its failures"),
    ("data/self_repair/abandoned_criteria.jsonl", "standards it once held and defeated"),
    # the first record here that is about the WORLD-FACING organ rather than the repair machinery.
    # Added because this census found only one of fifteen reaching an organ that looks or acts.
    ("data/perception/looks.jsonl", "what it saw and could not name"),
)

_WRITE = re.compile(r"""(open\([^)]*["'][wa]|write_text|json\.dump\(|\.write\()""")


_LOADS = re.compile(r"""(json\.load|read_text|readlines|\.open\(|open\()""")


def _sources() -> list:
    """Every non-test module, EXCLUDING this one.

    The first run of this census reported 14 of 14 records read back -- a perfect score, which today
    has meant the instrument six times running. It was counting ITSELF as a reader of every record,
    because every filename appears in its own `SELF_RECORDS` table. A tool for measuring
    self-reference, wrong by self-reference. Excluded here, and mere MENTION no longer counts as a
    read: the module has to actually load something."""
    out = []
    for top in SCAN:
        d = REPO / top
        if d.exists():
            out += [p for p in d.rglob("*.py")
                    if "test" not in p.name and "tests" not in p.parts
                    and p.resolve() != Path(__file__).resolve()]
    return out


_IMPORTS: dict = {}


def _import_graph(srcs) -> dict:
    """Who imports whom, so a record reached through a module API is not scored as unreached."""
    import ast
    graph = {}
    for p, text in srcs:
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        got = set()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            graph[rel] = got
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                got.add(node.module)
            elif isinstance(node, ast.Import):
                got |= {a.name for a in node.names}
        graph[rel] = got
    return graph


def census() -> dict:
    """For each self-record: who writes it, who READS it, and whether reading changes anything."""
    srcs = [(p, p.read_text(encoding="utf-8", errors="ignore")) for p in _sources()]
    global _IMPORTS
    _IMPORTS = _import_graph(srcs)
    rows = []
    for rel, what in SELF_RECORDS:
        name = Path(rel).name
        writers, readers = [], []
        for p, text in srcs:
            if name not in text:
                continue
            here = str(p.relative_to(REPO)).replace("\\", "/")
            # A module that merely NAMES the file -- in a docstring, a comment, a table -- is not a
            # reader. It has to load something. Writers and readers are counted separately because a
            # module that only records is a diary and a module that loads can be moved by what it
            # finds; a module that does both counts as a reader, since the read is the loop.
            # FOLLOW THE BINDING. The path is almost never used where it is written: modules bind it
            # to a constant at the top -- `LOG = REPO / "data" / ... / "defects.jsonl"` -- and load it
            # two hundred lines below through that NAME. A window around the mention called
            # `defects.jsonl` a diary while `defect_ledger.py` reads it every run, which is a false
            # alarm rather than a finding, and reporting it would have invented a problem. So: find
            # what the path was bound to, then look for that name being loaded or written.
            lines = text.splitlines()
            bound = set()
            for ln in lines:
                if name in ln:
                    m = re.match(r"\s*([A-Za-z_][A-Za-z_0-9]*)\s*[:=]", ln)
                    if m:
                        bound.add(m.group(1))
            for var in bound or {name}:
                v = re.escape(var)
                if re.search(rf"{v}\s*\.\s*(read_text|open|exists|iterdir|glob)|json\.load\(\s*{v}"
                             rf"|open\(\s*{v}|in\s+{v}\b", text):
                    readers.append(here)
                if re.search(rf"{v}\s*\.\s*(write_text|open\(\s*[\"'][wa])|json\.dump\([^)]*{v}"
                             rf"|open\(\s*{v}\s*,\s*[\"'][wa]", text):
                    writers.append(here)
            if name in text and here not in readers and here not in writers:
                if _LOADS.search(text):
                    readers.append(here)
        # FOLLOW THE API, NOT ONLY THE FILE. Well-structured code does not re-read a file it has a
        # module for: `moves.py` and `cheap_proxy.py` consume the criteria ledger through
        # `criteria_ledger.in_force()` and never name the .jsonl. Counting file reads alone therefore
        # scores every properly-encapsulated record as "own history", which under-counts exactly the
        # organs that are wired best. The first version of this census reported 2 of 14 on that basis
        # and that number was too low. One hop: a record crosses an organ boundary if a module that
        # reads it is itself imported by a DIFFERENT package.
        own_pkg = {Path(r).parts[1] for r in readers if len(Path(r).parts) > 1}
        via_api = []
        for reader in set(readers):
            mod = str(reader).replace("/", ".").removesuffix(".py")
            for other, imps in _IMPORTS.items():
                if other in readers or other == reader:
                    continue
                if any(i == mod or i.startswith(mod + ".") for i in imps):
                    pkg = Path(other).parts[1] if len(Path(other).parts) > 1 else other
                    if pkg not in own_pkg:
                        via_api.append(other)
        # A MODULE READING ITS OWN FILE IS NOT A LEVEL CROSSING. `closes_the_loop` was `bool(readers)`,
        # which is true whenever anything at all loads the record -- including the module that wrote
        # it two lines earlier. That is persistence, the ordinary way a program keeps state between
        # runs, and counting it inflated the census to 14 of 15 when 9 records are read by an organ
        # other than their writer. This file has now been corrected for self-counting twice; the
        # check belongs in the code rather than in whoever reads the total.
        writers_s, readers_s = set(writers), set(readers)
        crossing = sorted((readers_s - writers_s) | set(via_api))
        rows.append({"record": rel, "about": what,
                     "written_by": sorted(writers_s), "read_by": sorted(readers_s),
                     "reaches_other_organs_via_api": sorted(set(via_api))[:6],
                     "read_by_another_organ": crossing[:6],
                     # READ BUT UNWRITTEN is its own failure and the worse one. A record nobody reads
                     # is a diary; a record several organs read while nothing maintains it is a
                     # FROZEN MAP still steering the territory. `recipes.json` -- "recipes it derived
                     # from its failures" -- is loaded by three organs and written by no code here.
                     "orphaned_input": bool(readers_s and not writers_s),
                     "closes_the_loop": bool(crossing)})
    closed = [r for r in rows if r["closes_the_loop"]]
    orphans = [r["record"] for r in rows if r["orphaned_input"]]
    return {
        "self_records": len(rows),
        "read_back_into_behaviour": len(closed),
        "self_reading_only": [r["record"] for r in rows
                              if not r["closes_the_loop"] and r["read_by"] and r["written_by"]],
        "orphaned_inputs": orphans,
        "write_only": [r["record"] for r in rows if not r["read_by"]],
        "rows": rows,
        "reading": ("a self-record nobody reads is a diary, not a loop; a record its own writer reads "
                    "back is persistence. This counts only the condition Hofstadter names -- a record "
                    "that reaches an organ OTHER than the one that made it -- and counts nothing "
                    "about whether anything is felt, which no gate here can reach. `orphaned_inputs` "
                    "is the inverse pathology and deserves its own line: organs steered by a map "
                    "nothing updates"),
    }


#: Organs that touch the world rather than the system: they look, read pages, answer, or act. A
#: reflection that reaches one of these has come back DOWN -- the tower is not just taller, it is
#: bent round.
WORLD_FACING = ("packages/perception/", "packages/wild_web/", "packages/base_brain/",
                "packages/live_selfhood_cycle/", "packages/open_web/", "packages/eye/")


def reflection_depth(max_level: int = 8) -> dict:
    """How many times over does a record reflect a reflection — and does the top come back down?

    THE QUESTION, in the owner's words while reading GEB: do the patterns reflect the brain's
    reflection of the world, and finally reflect themselves? It is answerable here rather than
    arguable, because every reflection in this system is a file and every reader is an import.

    LEVEL IS DERIVED, NOT LABELLED. A record's level is one more than the highest level of any record
    ITS WRITER READS. A module that only watches the machinery writes level 1; a module that reads
    level-1 records and writes its own conclusions writes level 2; and so on. Nothing is scored from
    the English in the `about` column, which would let a good phrase buy a level.

    AND HEIGHT ALONE IS A TOWER, NOT A LOOP. A stack of records each about the one below is exactly
    the clean hierarchy Hofstadter contrasts a strange loop against -- it can go up forever and change
    nothing. What makes it swirl is the top reaching back to where the system meets the world, so
    `comes_back_down` walks the import graph forward from each record's readers and asks whether the
    influence arrives at an organ that looks, reads, answers or acts.

    A record can be high and flat, or low and bent round. Only the second kind is the condition."""
    rows = census()["rows"]
    reads_of: dict = {}
    for r in rows:
        for m in r["read_by"]:
            reads_of.setdefault(m, set()).add(r["record"])

    # UPSTREAM FIRST, THEN CYCLES, because the two look identical from the outside and only one is a
    # reflection. The first version ran the fixed point to convergence and reported a record at level
    # 8 -- but cycles.jsonl and improvement_cycles.jsonl WRITE EACH OTHER'S READERS, so the iteration
    # simply climbed until it hit the ceiling. Eight reflections deep and mutual recursion produce the
    # same number, and calling a loop "level 8" would be the most flattering possible misreading of
    # exactly the thing this file exists to measure honestly.
    upstream_of = {}
    for r in rows:
        up = set()
        for m in r["written_by"]:
            up |= reads_of.get(m, set()) - {r["record"]}
        upstream_of[r["record"]] = up

    def _in_cycle(rec) -> bool:
        seen, frontier = {rec}, list(upstream_of.get(rec, ()))
        while frontier:
            n = frontier.pop()
            if n == rec:
                return True
            if n in seen:
                continue
            seen.add(n)
            frontier += list(upstream_of.get(n, ()))
        return False

    mutual = {r["record"] for r in rows if _in_cycle(r["record"])}
    level = {r["record"]: 1 for r in rows}
    for _ in range(max_level):                      # fixed point over the acyclic part only
        changed = False
        for r in rows:
            if r["record"] in mutual:
                continue
            up = [u for u in upstream_of[r["record"]] if u not in mutual]
            want = 1 + max([level[u] for u in up], default=0)
            if want > level[r["record"]] and want <= max_level:
                level[r["record"]] = want
                changed = True
        if not changed:
            break

    def _down(readers) -> tuple:
        """Does the record reach an organ that faces the world, and how directly?

        TRANSITIVE IMPORT REACH IS NEARLY VACUOUS HERE and the first version reported it anyway: it
        walked four hops and found `life.py` downstream of eleven of fifteen records. That is not a
        finding about reflection, it is a fact about `life.py`, which imports broadly enough that
        almost anything reaches it. Every row said 'yes' for the same uninformative reason.

        So DIRECT is counted separately and it is the number that means something: a world-facing
        module is itself among the readers. Indirect reach is still reported, at its hop count, and
        should be read as 'there is a path', which is much weaker than 'this changes what it does'."""
        direct = sorted({m for m in readers if any(m.startswith(w) for w in WORLD_FACING)})
        if direct:
            return (direct, 0)
        seen, frontier = set(readers), list(readers)
        for hop in range(1, 4):
            nxt = []
            for mod_path in frontier:
                mod = mod_path.replace("/", ".").removesuffix(".py")
                for other, imps in (_IMPORTS or {}).items():
                    if other in seen:
                        continue
                    if any(i == mod or i.startswith(mod + ".") for i in imps):
                        seen.add(other)
                        nxt.append(other)
            hits = sorted({m for m in nxt if any(m.startswith(w) for w in WORLD_FACING)})
            if hits:
                return (hits[:3], hop)
            frontier = nxt
            if not frontier:
                break
        return ([], -1)

    out = []
    for r in rows:
        reach, hops = _down(list(r["read_by"]) + list(r["reaches_other_organs_via_api"]))
        out.append({"record": r["record"], "about": r["about"],
                    "level": ("mutual" if r["record"] in mutual else level[r["record"]]),
                    "read_by_a_world_facing_organ": hops == 0,
                    "reaches": reach, "hops": hops})
    plain = [o for o in out if o["level"] != "mutual"]
    return {
        "levels": {str(k): sum(1 for o in plain if o["level"] == k)
                   for k in sorted({o["level"] for o in plain})},
        "mutually_referring": sorted(mutual),
        "highest_level": max([o["level"] for o in plain], default=0),
        "read_directly_by_a_world_facing_organ": sum(1 for o in out
                                                     if o["read_by_a_world_facing_organ"]),
        "reachable_only_indirectly": sum(1 for o in out if o["hops"] > 0),
        "reaches_nothing_worldward": [o["record"] for o in out if o["hops"] < 0],
        "rows": out,
        "reading": ("level is derived from what a record's writer reads, not from what the record "
                    "calls itself, and records that write each other are reported as MUTUAL rather "
                    "than given a level -- a cycle and a deep reflection produce the same number and "
                    "only one is a reflection. Height alone is a clean hierarchy; the condition "
                    "Hofstadter names needs the top bent back to where the system meets the world, "
                    "which is what the direct count is for"),
    }


def barrier() -> dict:
    """The one place the loop provably cannot close: the code it may not write.

    Reported separately because it is not an oversight. It is a deliberate device, and the argument
    for changing it has to be made against what it protects rather than around it."""
    from packages.self_repair.provisional import FORBIDDEN
    from packages.self_repair.parameter_space import ORGANS, discover

    blocked = [p.key() for p in discover()
               if any(str(p.file).startswith(f) for f in FORBIDDEN)]
    return {
        "forbidden": list(FORBIDDEN),
        "own_constants_it_may_not_change": len(blocked),
        "examples": blocked[:6],
        "organs_it_reasons_about": len(ORGANS),
        "the_shape": ("it can represent every one of these and act on none of them. That is a clean "
                      "hierarchy, which is the opposite of the condition -- and it is deliberate"),
        "the_ground": ("scripts/gloss_lane_recall.py and the cycle ledger are the part that must stay "
                       "unreachable for any of its self-claims to mean anything. Goedel's sentence is "
                       "productive because its truth is settled OUTSIDE. Whether 'may not touch the "
                       "ground' and 'may not touch itself' have to be the same rule is the open "
                       "question, and this file exists so it is argued over numbers"),
    }
