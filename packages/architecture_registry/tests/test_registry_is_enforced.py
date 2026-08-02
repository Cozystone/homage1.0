# -*- coding: utf-8 -*-
"""The registry is now enforced, because a validator nobody runs is not a structure.

    pytest packages/architecture_registry/tests/test_registry_is_enforced.py

WHY THIS EXISTS. data/architecture/catalog/organ_registry_v1.json is the declared architecture, and its
judgement columns were mostly `unknown` and `V0`, and on 2026-07-30 I read that as ROT and filled them from
a transitive import walk. That was wrong, and the file said so: registry.py defines wiring as "Attested
runtime reachability; unknown is retained until direct call-path evidence is cited", and
test_census_does_not_infer_wiring_authority_or_capability pins every organ but five hand-curated ones to
`{"runtime_status": "unknown", "refs": []}`. The five that ARE filled cite specific call-path files and
baseline evidence manifests. `unknown` was a POLICY, not a gap, and my inference has been reverted out of it.

What was genuinely missing: fourteen real packages had no entry at all, and nothing ran the validator on
every test run. Those two are fixed here. The inference itself lives in
data/architecture/wiring_measurement.json with its own claim_scope, which is where an inference belongs.

WHAT IS DELIBERATELY *NOT* ASSERTED. No test here requires an organ to be wired, or to be at any evidence
stage, or to be anything other than honestly described. `fusion_loop` sits off the serving path ON PURPOSE
-- its own docstring says "CONTROLLED closed-loop test posture, NOT live unsupervised operation" -- and a
test that demanded everything be live_default would have forced an unsupervised self-improvement cycle onto
live traffic. Enforcement means the file tells the truth, not that the truth is flattering.

AND THE CENSUSES DISAGREE, which is recorded rather than reconciled by guessing. `static_graph.py` reports
115 production_static_reference / 27 no_external_static_reference over 143 organs; the measurement written
on 2026-07-30 reports 69 live_default / 27 live_conditional / 48 unwired. They are different questions --
"does anything outside reference it" versus "is it reachable by imports from the entrypoint" -- and
static_graph carries the disclaimer that matters: literal import references do NOT establish runtime
reachability, default enablement, authority, or capability. An import inside a function that never runs is
a reference and not an execution. The newer number is the weaker claim of the two and must not be quoted as
if it proved organs RUN.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from packages.architecture_registry import registry as R
from packages.architecture_registry import static_graph as SG

CATALOG = Path("data/architecture/catalog/organ_registry_v1.json")
REPO = Path(".")


@pytest.fixture(scope="module")
def catalog():
    if not CATALOG.exists():
        pytest.skip(f"no catalog at {CATALOG}")
    return R.load_catalog(CATALOG)


def test_the_catalog_is_strictly_valid(catalog):
    """Schema, enums, refs, duplicate keys, and every ref resolving to a real path on disk.

    The roots are passed explicitly, matching test_registry.py. Calling this with defaults was my own
    first mistake here, and the finding it hid was real: my fill had written PROSE into evidence.refs
    ("packages/self_check reachable from apps/api/app/main.py"). A refs field holds repository paths, and
    a sentence in it is an attestation that cites nothing."""
    findings = R.validate_catalog(catalog, package_root=Path("packages"), repo_root=REPO)
    assert not findings, "the checked-in registry does not validate:\n  " + "\n  ".join(
        str(f) for f in findings[:20])


def test_every_real_package_is_declared(catalog):
    """Fourteen packages existed without an entry. An undeclared organ is an unowned one."""
    declared = {o["name"] for o in catalog["organs"]}
    real = set(R.discover_package_names(Path("packages")))
    missing = sorted(real - declared)
    assert not missing, (
        f"{len(missing)} packages exist with no registry entry: {missing[:12]}. "
        f"Run `python scripts/registry_wiring_fill.py --write` to declare them, then set "
        f"lifecycle and canonical_domain by hand -- the tool defaults them and defaults are how "
        f"this file rotted in the first place."
    )


def test_no_entry_points_at_a_package_that_does_not_exist(catalog):
    """The other direction: a stale entry for a deleted organ is a map of a place that is gone."""
    real = set(R.discover_package_names(Path("packages")))
    ghosts = sorted(o["name"] for o in catalog["organs"]
                    if o["name"] not in real and not os.path.isdir(o.get("path", "")))
    assert not ghosts, f"registry entries with no package on disk: {ghosts[:12]}"


# A TEST OF MINE STOOD HERE AND IT WAS WRONG. It asserted that the judgement columns must NOT be
# uniformly default, on the reading that "unknown x125" was rot. It was policy: registry.py states
# "unknown is retained until direct call-path evidence is cited", and
# test_census_does_not_infer_wiring_authority_or_capability pins every organ but five to unknown/[]. My
# test would have forced inference into an attestation-only column, permanently. Deleted rather than
# weakened, because the correct assertion is the existing one and duplicating it adds nothing.


def test_a_capability_stage_must_cite_an_attested_sealed_verdict(catalog):
    """E4 and above need an evaluator who is not the builder, and the citation has to prove it.

    AMENDED DELIBERATELY 2026-07-30, which is what the previous version of this test demanded of anyone
    who ever wanted to raise a stage past M3. It used to forbid E4+ outright, because nothing in the
    repository had one and a small p-value measured by the builder, on a harness the builder wrote, over
    data the builder chose, is M3. `depth_learner` now has one, and the amendment does not loosen the
    rule -- it states it: an E4+ organ must CITE a verdict file that carries `attestation: true`, a named
    examiner, and a pass.

    What made exam 002 an attestation rather than a good number, all of it checkable without trusting me:

        checkpoint frozen           2026-07-29T13:08:16
        pre-registration committed  2026-07-30T19:09:27   -- conditions fixed before the data existed
        exam data created           2026-07-30T23:18:18   -- so the model provably never trained on it
        town                        Town15, never in training and never a validation town
        scored by                   the operator, on a seal that had produced no prior verdict
        result                      net p10 0.4563 vs constant p90 0.2266 and shuffled p90 0.3866

    An organ that names a stage without such a file still fails, and that is the part worth keeping."""
    claims = [o for o in catalog["organs"] if o["evidence"]["stage"] in ("E4", "E5", "E6")]
    for o in claims:
        verdicts = [r for r in o["evidence"].get("refs", []) if r.endswith(".json") and "verdict" in r]
        assert verdicts, (
            f"{o['name']} claims {o['evidence']['stage']} and cites no verdict file. E4+ requires an "
            f"independent evaluator and a holdout nobody has seen; the citation is how that is checked."
        )
        for ref in verdicts:
            p = Path(ref)
            assert p.exists(), f"{o['name']} cites {ref}, which does not exist"
            v = json.loads(p.read_text(encoding="utf-8"))
            assert v.get("pass") is True, f"{o['name']} cites {ref}, which records a FAIL"
            assert v.get("attestation") is True, (
                f"{o['name']} cites {ref}, which is marked attestation: false -- it was read off a seal "
                f"that had already produced a verdict, so feedback had flowed and it cannot attest.")
            assert v.get("examiner"), f"{o['name']} cites {ref}, which names no examiner"
            assert "DIAGNOSTIC" not in str(v.get("examiner", "")).upper(), (
                f"{o['name']} cites a verdict its own examiner labelled DIAGNOSTIC")


def test_the_embodiment_line_is_filed_under_embodiment(catalog):
    """eye and hand were filed under `platform`, which hid the body from its own domain."""
    dom = {o["name"]: o["canonical_domain"] for o in catalog["organs"]}
    for organ in ("eye", "hand"):
        if organ in dom:
            assert dom[organ] == "embodiment", (
                f"{organ} is filed under {dom[organ]!r}. It is one of the body's two doors -- "
                f"`eye` is 'a retina, not a sensor', `hand` is 'one door for motor output' -- and "
                f"filing them under platform is why the embodiment domain showed a single organ.")


def test_the_static_import_census_still_parses_every_file():
    """static_graph is the older, more careful census. If it stops parsing, the map goes blind."""
    names = R.discover_package_names(Path("packages"))
    g = SG.build_static_graph(REPO, names)
    s = SG.summarize_static_graph(g)
    assert s["parse_failure_count"] == 0, f"{s['parse_failure_count']} files failed to parse"
    assert s["organ_count"] == len(names)
    assert "does not establish runtime reachability" in g["claim_scope"], (
        "static_graph's claim_scope disclaimer was weakened. It is the sentence that keeps an import "
        "reference from being quoted as proof that an organ RUNS.")


def test_the_wiring_measurement_records_that_it_is_the_weaker_claim():
    """The 2026-07-30 measurement is import-reachability, not execution. It must say so."""
    p = Path("data/architecture/wiring_measurement.json")
    if not p.exists():
        pytest.skip("no wiring measurement recorded")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "claim_scope" in d, (
        "wiring_measurement.json carries no claim_scope. It reports live_default/live_conditional/"
        "unwired from a transitive import walk, which does NOT establish that an organ executes -- an "
        "import inside a function that never runs is a reference, not an execution. Say so in the file."
    )
