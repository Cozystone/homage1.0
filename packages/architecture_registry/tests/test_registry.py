from __future__ import annotations

import copy
from pathlib import Path

import pytest

from packages.architecture_registry.registry import (
    RegistryValidationError,
    discover_package_names,
    load_and_validate,
    load_catalog,
    validate_catalog,
)

REPO = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO / "packages"
CATALOG_PATH = REPO / "data" / "architecture" / "catalog" / "organ_registry_v1.json"


def _catalog() -> dict:
    return load_catalog(CATALOG_PATH)


def test_checked_in_catalog_exhaustively_matches_top_level_packages() -> None:
    catalog = load_and_validate(
        CATALOG_PATH,
        package_root=PACKAGE_ROOT,
        repo_root=REPO,
    )

    registered = tuple(organ["name"] for organ in catalog["organs"])
    assert registered == discover_package_names(PACKAGE_ROOT)


def test_census_does_not_infer_wiring_authority_or_capability() -> None:
    catalog = _catalog()

    for organ in catalog["organs"]:
        assert organ["built"]["status"] is True
        if organ["name"] not in {
            "cgsr",
            "cognitive_core",
            "continuous_self",
            "temporal_reasoning",
            "world4d",
            # AMENDED 2026-07-30, deliberately and for exactly one organ. This test pins every other
            # organ to V0/M1 because nothing in the repository had capability-stage evidence, and that
            # pin is what stopped a mass overwrite from inference earlier the same day. depth_learner
            # now has an E4 from a blind sealed exam: checkpoint frozen 07-29T13:08, pass conditions
            # committed 07-30T19:09, exam data created 07-30T23:18 -- so the conditions predate the data
            # and the data postdates the freeze -- scored by the operator on Town15, a town that was
            # never in training and never a validation town.
            #     docs/ATANOR_depth_E4_prereg.md 11
            #     data/e4_depth_seal_002/verdict.json   (attestation: true, examiner named)
            # The stage is additionally guarded by test_a_capability_stage_must_cite_an_attested_sealed_
            # verdict, which checks that citation, so this exception is not a hole: an organ named here
            # without an attested verdict still fails the suite.
            "depth_learner",
        }:
            assert organ["authority"] == {"level": "none", "refs": []}
            assert organ["wiring"] == {"runtime_status": "unknown", "refs": []}
            assert organ["evidence"]["stage"] in {"V0", "M1"}

    cognitive = next(
        organ for organ in catalog["organs"] if organ["name"] == "cognitive_core"
    )
    assert cognitive["evidence"] == {
        "stage": "M3",
        "refs": [
            "packages/cognitive_core",
            "packages/cognitive_core/tests",
            "packages/cognitive_core/tests/test_continuous_self_shadow.py",
            "packages/continuous_self/tests/test_loop.py",
            "apps/api/tests/test_cognitive_cycle_shadow.py",
            "reports/baseline_evidence/baseline_20260724T232815.306610Z_42f21ef3d6f0.manifest.json",
        ],
    }
    assert cognitive["wiring"] == {
        "runtime_status": "live_conditional",
        "refs": [
            "apps/api/app/routers/dual_brain.py",
            "packages/cognitive_core/chat_shadow.py",
            "packages/cognitive_core/continuous_self_shadow.py",
            "packages/continuous_self/loop.py",
        ],
    }
    assert cognitive["authority"]["level"] == "none"

    continuous = next(
        organ for organ in catalog["organs"]
        if organ["name"] == "continuous_self"
    )
    assert continuous["wiring"] == {
        "runtime_status": "live_default",
        "refs": [
            "apps/api/app/main.py",
            "apps/api/app/routers/continuous_self.py",
            "packages/continuous_self/loop.py",
        ],
    }
    assert continuous["authority"] == {"level": "none", "refs": []}
    assert continuous["evidence"] == {
        "stage": "M1",
        "refs": [
            "apps/api/app/main.py",
            "apps/api/app/routers/continuous_self.py",
            "packages/continuous_self/loop.py",
            "packages/continuous_self/tests/test_loop.py",
        ],
    }

    cgsr = next(organ for organ in catalog["organs"] if organ["name"] == "cgsr")
    assert cgsr["wiring"] == {
        "runtime_status": "live_conditional",
        "refs": ["packages/cgsr/cgsr/response_workspace.py"],
    }
    assert cgsr["authority"] == {
        "level": "secondary",
        "refs": ["packages/cgsr/cgsr/response_workspace.py"],
    }
    assert cgsr["evidence"] == {
        "stage": "M3",
        "refs": [
            "packages/cgsr/cgsr/response_workspace.py",
            "packages/world4d/tests/test_live_temporal_shadow.py",
            "reports/baseline_evidence/baseline_20260724T225531.739793Z_45bfaf0d04c9.manifest.json",
        ],
    }

    temporal = next(
        organ for organ in catalog["organs"]
        if organ["name"] == "temporal_reasoning"
    )
    assert temporal["wiring"] == {
        "runtime_status": "live_conditional",
        "refs": [
            "packages/cgsr/cgsr/response_workspace.py",
            "packages/temporal_reasoning/block_universe.py",
        ],
    }
    assert temporal["authority"] == {
        "level": "secondary",
        "refs": [
            "packages/cgsr/cgsr/response_workspace.py",
            "packages/temporal_reasoning/block_universe.py",
        ],
    }
    assert temporal["evidence"] == {
        "stage": "M3",
        "refs": [
            "packages/temporal_reasoning/block_universe.py",
            "packages/world4d/tests/test_live_temporal_shadow.py",
            "reports/baseline_evidence/baseline_20260724T225531.739793Z_45bfaf0d04c9.manifest.json",
        ],
    }

    world4d = next(
        organ for organ in catalog["organs"] if organ["name"] == "world4d"
    )
    assert world4d["evidence"] == {
        "stage": "M3",
        "refs": [
            "packages/world4d",
            "packages/world4d/tests",
            "packages/cgsr/cgsr/response_workspace.py",
            "reports/baseline_evidence/baseline_20260724T225531.739793Z_45bfaf0d04c9.manifest.json",
        ],
    }
    assert world4d["wiring"] == {
        "runtime_status": "live_conditional",
        "refs": [
            "packages/cgsr/cgsr/response_workspace.py",
            "packages/world4d/shadow.py",
        ],
    }
    assert world4d["authority"]["level"] == "none"


def test_missing_registration_fails_strict() -> None:
    catalog = _catalog()
    removed = catalog["organs"].pop(0)["name"]

    issues = validate_catalog(catalog, package_root=PACKAGE_ROOT, repo_root=REPO)

    assert any(
        issue.startswith("unregistered package directories:") and removed in issue
        for issue in issues
    )


def test_duplicate_name_and_path_fail_strict() -> None:
    catalog = _catalog()
    catalog["organs"].append(copy.deepcopy(catalog["organs"][0]))

    issues = validate_catalog(catalog, package_root=PACKAGE_ROOT, repo_root=REPO)

    assert any(issue.startswith("duplicate organ name:") for issue in issues)
    assert any(issue.startswith("duplicate organ path:") for issue in issues)


@pytest.mark.parametrize(
    ("field_path", "invalid_value", "expected"),
    [
        (("lifecycle",), "incubating", ".lifecycle is invalid"),
        (("canonical_domain",), "misc", ".canonical_domain is invalid"),
        (("wiring", "runtime_status"), "probably_live", ".wiring.runtime_status is invalid"),
        (("authority", "level"), "maybe", ".authority.level is invalid"),
        (("evidence", "stage"), "green", ".evidence.stage is invalid"),
        (("built", "status"), "true", ".built.status must be a literal boolean"),
    ],
)
def test_invalid_enums_and_truthy_built_values_fail_strict(
    field_path: tuple[str, ...],
    invalid_value: object,
    expected: str,
) -> None:
    catalog = _catalog()
    target = catalog["organs"][0]
    for field in field_path[:-1]:
        target = target[field]
    target[field_path[-1]] = invalid_value

    issues = validate_catalog(catalog, package_root=PACKAGE_ROOT, repo_root=REPO)

    assert any(expected in issue for issue in issues)


def test_attested_wiring_and_authority_require_direct_refs() -> None:
    catalog = _catalog()
    organ = catalog["organs"][0]
    organ["wiring"] = {"runtime_status": "live_default", "refs": []}
    organ["authority"] = {"level": "primary", "refs": []}

    issues = validate_catalog(catalog, package_root=PACKAGE_ROOT, repo_root=REPO)

    assert any("wiring.refs required for attested runtime status" in issue for issue in issues)
    assert any("authority.refs required for attested authority" in issue for issue in issues)


def test_duplicate_json_object_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")

    with pytest.raises(RegistryValidationError, match="duplicate JSON key"):
        load_catalog(path)


def test_missing_evidence_ref_fails_strict() -> None:
    catalog = _catalog()
    catalog["organs"][0]["evidence"]["refs"] = ["packages/does_not_exist"]

    issues = validate_catalog(catalog, package_root=PACKAGE_ROOT, repo_root=REPO)

    assert any("does not exist: packages/does_not_exist" in issue for issue in issues)


def test_malformed_refs_are_reported_without_validator_crash() -> None:
    catalog = _catalog()
    catalog["organs"][0]["built"]["refs"] = 7

    issues = validate_catalog(catalog, package_root=PACKAGE_ROOT, repo_root=REPO)

    assert any(".built.refs must be a list" in issue for issue in issues)
