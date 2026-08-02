# -*- coding: utf-8 -*-
"""depth_learner must remain a library that can leave this repository as a directory move.

    pytest packages/depth_learner/tests/test_stays_splittable.py

WHY THIS EXISTS. This organ is the only one carrying capability-stage evidence -- E4, replicated across two
independent blind seals -- which makes it the first plausible candidate to become something separate
(`AlphaFramer-depth` was the owner's name for it). Measured 2026-07-31, the boundary is already clean: it
imports nothing from `packages.*`, only stdlib plus numpy, torch and cv2. Splitting it out today would be a
directory move rather than a refactor.

Clean boundaries do not stay clean by themselves. One convenient `from packages.graph_scale import ...`
turns a movable library into a tangled one, and nobody notices until the day someone tries to move it. This
test makes that day arrive immediately.

IT DOES NOT SAY THE SPLIT SHOULD HAPPEN. On measured numbers it should not: delta<1.25 near 0.5 against
published monocular work at 0.85+ on real photographs means shipping this would be shipping something
weaker than what is already free. What the test protects is the OPTION -- so the decision stays about
capability, and is never quietly foreclosed by an import.
"""
from __future__ import annotations

import ast
import io
import os
from pathlib import Path

PKG = Path("packages/depth_learner")

# Everything the library may reach for. Anything else is either a new dependency a split repo would have to
# declare, or a coupling that would prevent the split -- both are decisions, not accidents.
ALLOWED_THIRD_PARTY = {"numpy", "torch", "cv2"}
STDLIB_OK = {"__future__", "argparse", "collections", "dataclasses", "functools", "hashlib", "io",
             "itertools", "json", "math", "os", "pathlib", "random", "re", "shutil", "statistics",
             "subprocess", "sys", "time", "typing", "warnings", "datetime", "contextlib", "glob"}


def _modules(path: Path):
    try:
        tree = ast.parse(io.open(path, encoding="utf-8", errors="replace").read())
    except (OSError, SyntaxError):
        return set()
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            out.add(n.module.split(".")[0])
    return out


def _sources():
    for base, ds, fs in os.walk(PKG):
        ds[:] = [d for d in ds if d != "__pycache__"]
        for f in fs:
            if f.endswith(".py"):
                yield Path(base) / f


def test_imports_nothing_from_this_repository():
    """The load-bearing one. A single ATANOR import ends the option to move this directory."""
    coupled = {}
    for p in _sources():
        if "tests" in p.parts:
            continue
        bad = {m for m in _modules(p) if m == "packages"}
        if bad:
            coupled[str(p)] = sorted(bad)
    assert not coupled, (
        f"depth_learner now imports ATANOR packages: {coupled}. It was a standalone library on "
        f"2026-07-31 and that is what makes AlphaFramer-depth a directory move instead of a rewrite. "
        f"If the coupling is genuinely needed, delete this test on purpose and say why -- do not let the "
        f"option close by accident."
    )


def test_third_party_dependencies_stay_declared():
    """A split repo needs a requirements list. This is that list, enforced."""
    extra = {}
    for p in _sources():
        if "tests" in p.parts:
            continue
        unknown = {m for m in _modules(p)
                   if m not in ALLOWED_THIRD_PARTY and m not in STDLIB_OK and m != "packages"}
        if unknown:
            extra[str(p)] = sorted(unknown)
    assert not extra, (
        f"new third-party imports: {extra}. Add them to ALLOWED_THIRD_PARTY here and to whatever "
        f"requirements a split would ship, or drop them. An undeclared dependency is a split that fails "
        f"on someone else's machine."
    )


def test_the_organ_still_exists_where_the_evidence_says_it_does():
    """Cheap, and it catches the case where a move happens without the citations following it."""
    assert (PKG / "model.py").exists() and (PKG / "data.py").exists(), (
        "depth_learner's modules moved. data/e4_depth_seal_002/verdict.json and the registry entry cite "
        "this path; if the organ moved, the evidence citations have to move with it or the E4 row starts "
        "pointing at nothing.")
