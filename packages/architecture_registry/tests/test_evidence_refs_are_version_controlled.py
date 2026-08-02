# -*- coding: utf-8 -*-
"""Evidence a claim rests on must be in version control, or the claim rests on nothing.

    pytest packages/architecture_registry/tests/test_evidence_refs_are_version_controlled.py

FOUND WHILE TIDYING, 2026-07-30. `depth_learner` had just been raised to E4 citing
`data/e4_depth_seal_002/verdict.json` -- and `data/` is gitignored. The registry's only capability claim
pointed at a file that was not tracked, could be deleted by any cleanup, and existed on exactly one machine.
The claim would have survived; its evidence would not.

The verdict, the public manifest and the prediction metadata are 31 KB together. The raw arrays they refer
to are 217 MB and stay out of the repository -- what has to be durable is the RECORD, not the pixels: the
hashes in these files are what let someone re-derive the arrays and check that they match.

This test does not care which files are cited. It cares that every ref a registry entry uses to justify its
stage can be read back out of git.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from packages.architecture_registry import registry as R

CATALOG = Path("data/architecture/catalog/organ_registry_v1.json")


def _tracked(path: str) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", path],
                       capture_output=True, text=True)
    return r.returncode == 0


@pytest.fixture(scope="module")
def catalog():
    if not CATALOG.exists():
        pytest.skip(f"no catalog at {CATALOG}")
    return R.load_catalog(CATALOG)


def test_every_evidence_ref_of_a_capability_claim_is_tracked(catalog):
    """The load-bearing one: an E4+ stage may not cite a file git does not have.

    A directory-level ref (a package path) is fine -- git tracks its contents. A FILE ref must be tracked
    itself, because that is the artefact being appealed to."""
    untracked = []
    for organ in catalog["organs"]:
        if organ["evidence"]["stage"] not in ("E4", "E5", "E6"):
            continue
        for ref in organ["evidence"].get("refs", []):
            p = Path(ref)
            if p.is_dir():
                continue
            if not _tracked(ref):
                untracked.append((organ["name"], ref))
    assert not untracked, (
        f"capability claims cite files git does not track: {untracked}. `data/` is gitignored, so a "
        f"verdict left there is one cleanup away from vanishing while the claim it backs survives. "
        f"Add it with `git add -f`; the records are kilobytes, the raw arrays are not and belong outside."
    )


def test_every_evidence_ref_exists_on_disk(catalog):
    missing = [(o["name"], r) for o in catalog["organs"]
               for r in o["evidence"].get("refs", []) if not Path(r).exists()]
    assert not missing, f"evidence refs that do not exist: {missing}"


def test_the_membrane_calibration_artifact_is_tracked():
    """Not a registry ref, but the same failure: the live gate's threshold lived only in gitignored data.

    ATANOR_MEMBRANE_LIVE defaults to 1 in apps/api/app/main.py, so the answer path abstains against a
    q_hat read from data/conformal_gate/membrane_calibration.json. A calibration that exists on one disk
    and in no history is a live decision boundary nobody can reconstruct or audit."""
    p = "data/conformal_gate/membrane_calibration.json"
    if not Path(p).exists():
        pytest.skip("no membrane calibration on this machine")
    assert _tracked(p), (
        f"{p} is not tracked. The live membrane's accept/abstain threshold comes from this file; "
        f"untracked, the gate's behaviour cannot be reproduced or reviewed after the fact."
    )
