# -*- coding: utf-8 -*-
"""SL-1: an architecture hole must be READ, never listed."""
from __future__ import annotations

from packages.continuous_self.architecture_census import (
    ORGAN_TYPE, architecture_coverage, census_triples, organ_possessions, organ_roster)


def _repo(tmp_path, organs):
    """A miniature repo: {organ: [what it has on disk]}."""
    (tmp_path / "docs").mkdir()
    for organ, owns in organs.items():
        pkg = tmp_path / "packages" / organ
        pkg.mkdir(parents=True)
        if "tests" in owns:
            (pkg / "tests").mkdir()
        if "public_interface" in owns:
            (pkg / "__init__.py").write_text("x = 1", encoding="utf-8")
        if "persisted_state" in owns:
            (tmp_path / "data" / organ).mkdir(parents=True)
    return tmp_path


def test_the_roster_is_the_filesystem_not_a_list(tmp_path):
    """An organ that exists is counted; one that does not simply is not there. No roster to drift."""
    root = _repo(tmp_path, {"alpha": [], "beta": []})
    assert organ_roster(root) == ["alpha", "beta"]
    (root / "packages" / "gamma").mkdir()
    assert organ_roster(root) == ["alpha", "beta", "gamma"]   # noticed without editing anything


def test_possessions_are_checked_on_disk_and_absence_is_reported(tmp_path):
    root = _repo(tmp_path, {"has_all": ["tests", "public_interface"], "bare": []})
    assert set(organ_possessions("has_all", root)) >= {"tests", "public_interface"}
    assert organ_possessions("bare", root) == []


def test_a_minority_lacking_what_peers_carry_surfaces_as_a_hole(tmp_path):
    """The whole point: no rule here says an organ SHOULD have tests. Peer coverage says it."""
    organs = {f"o{i}": ["tests"] for i in range(9)}
    organs["lonely"] = []
    root = _repo(tmp_path, organs)
    cov = architecture_coverage(root)
    tests = cov["possessions"]["tests"]
    assert tests["held_by"] == 9 and cov["organs"] == 10
    assert tests["coverage"] == 0.9
    assert tests["lacking"] == ["lonely"]


def test_when_every_peer_lacks_it_there_is_no_hole(tmp_path):
    """Coverage, not a checklist: a thing nobody has is not an expectation anyone is failing."""
    root = _repo(tmp_path, {f"o{i}": [] for i in range(5)})
    assert "tests" not in architecture_coverage(root)["possessions"]


def test_triples_use_only_predicates_the_graph_really_has(tmp_path):
    root = _repo(tmp_path, {"alpha": ["tests"]})
    assert census_triples(root, allowed=frozenset()) == []          # invents nothing
    triples = census_triples(root, allowed=frozenset({"is_a", "has_a"}))
    assert ("alpha", "is_a", ORGAN_TYPE) in triples
    assert ("alpha", "has_a", "tests") in triples


# --- B1: the receipt audit ------------------------------------------------------------------

def _organ(root, name, *, body: str = "", init: str = "") -> None:
    pkg = root / "packages" / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text(init or "x = 1", encoding="utf-8")
    if body:
        (pkg / "core.py").write_text(body, encoding="utf-8")


def test_a_stdlib_logger_is_not_a_receipt(tmp_path):
    """The distinction is not pedantic. `conformal_gate` -- which decides whether ATANOR answers
    or abstains -- contains exactly one logging-shaped line and no durable record of any decision
    it ever made. An ephemeral, unaddressable line cannot be replayed or held to."""
    from packages.continuous_self.architecture_census import organ_possessions
    root = _repo(tmp_path, {})
    _organ(root, "noisy", body="import logging\nlogging.getLogger(__name__).info('decided')\n")
    _organ(root, "durable",
           body="from pathlib import Path\n"
                "def record(x):\n"
                "    with Path('data/x.jsonl').open('a') as fh: fh.write(x)\n")
    assert "emits_receipt" not in organ_possessions("noisy", root)
    assert "emits_receipt" in organ_possessions("durable", root)


def test_delegating_the_record_still_counts_as_having_one(tmp_path):
    """An organ may write its own trace or hand it to another organ's ledger; both are checkable
    afterwards, which is the whole property. Grading a delegator silent would send the audit to
    fix organs that are already fine."""
    from packages.continuous_self.architecture_census import organ_possessions
    root = _repo(tmp_path, {})
    _organ(root, "ledger",
           body="from pathlib import Path\n"
                "def record_row(x):\n"
                "    with Path('data/l.jsonl').open('a') as fh: fh.write(x)\n")
    _organ(root, "caller",
           body="from packages.ledger.core import record_row\n"
                "def decide():\n    record_row('why')\n")
    assert "emits_receipt" in organ_possessions("caller", root)


def test_a_tier_is_read_from_the_organ_never_decided_here(tmp_path):
    """"May the orchestrator override this?" is a normative decision about the architecture. A
    census that answered it would be dressing a policy up as a measurement."""
    from packages.continuous_self.architecture_census import organ_tier
    root = _repo(tmp_path, {})
    _organ(root, "declared", init='x = 1\nATANOR_TIER = "reflex"\n')
    _organ(root, "silent")
    _organ(root, "typo", init='ATANOR_TIER = "reflexx"\n')
    assert organ_tier("declared", root) == "reflex"
    assert organ_tier("silent", root) is None
    assert organ_tier("typo", root) is None          # an unknown tier is not a tier


def test_the_work_list_separates_undeclared_from_compliant(tmp_path):
    """Not having said what you are is not evidence that you are harmless."""
    from packages.continuous_self.architecture_census import unreceipted_by_tier
    root = _repo(tmp_path, {})
    _organ(root, "gate", init='ATANOR_TIER = "reflex"\n')       # declared, no receipt
    _organ(root, "quiet")                                        # undeclared, no receipt
    _organ(root, "good", init='ATANOR_TIER = "reflex"\n',
           body="from pathlib import Path\n"
                "def record(x):\n"
                "    with Path('d.jsonl').open('a') as fh: fh.write(x)\n")
    got = unreceipted_by_tier(root)
    assert got["reflex"] == ["gate"]                              # `good` is compliant
    assert got["undeclared"] == ["quiet"]


def test_a_record_call_must_be_bound_to_the_emitter_it_is_credited_to(tmp_path):
    """The first version of the delegation test asked whether a file contained a record-shaped call
    ANYWHERE and mentioned an emitter ANYWHERE. `base_brain` was credited on that basis for calling
    its OWN `answer_experience.record_decision` in a file that separately imports
    `packages.conformal_gate` -- true of both halves and evidence of neither, which is the same
    defect as reading `sealed_evidence` off a filename."""
    from packages.continuous_self.architecture_census import organ_possessions
    root = _repo(tmp_path, {})
    _organ(root, "ledger",
           body="from pathlib import Path\n"
                "def record_row(x):\n"
                "    with Path('l.jsonl').open('a') as fh: fh.write(x)\n")
    # calls its OWN recorder, and merely mentions the emitter for an unrelated reason
    _organ(root, "coincidence",
           body="from packages.ledger.core import something_else\n"
                "def record_decision(x):\n    return x\n"
                "def go():\n    record_decision(1)\n")
    _organ(root, "genuine",
           body="from packages.ledger.core import record_row\n"
                "def go():\n    record_row('why')\n")
    assert "emits_receipt" not in organ_possessions("coincidence", root)
    assert "emits_receipt" in organ_possessions("genuine", root)


def test_a_dotted_call_through_the_emitters_path_also_counts(tmp_path):
    from packages.continuous_self.architecture_census import organ_possessions
    root = _repo(tmp_path, {})
    _organ(root, "ledger",
           body="from pathlib import Path\n"
                "def record_row(x):\n"
                "    with Path('l.jsonl').open('a') as fh: fh.write(x)\n")
    _organ(root, "dotted",
           body="import packages.ledger.core\n"
                "def go():\n    packages.ledger.core.record_row('why')\n")
    assert "emits_receipt" in organ_possessions("dotted", root)
