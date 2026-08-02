"""Static wiring census separates source references from runtime claims."""
from __future__ import annotations

from pathlib import Path

import pytest

from packages.architecture_registry.registry import discover_package_names
from packages.architecture_registry.static_graph import (
    build_static_graph,
    summarize_static_graph,
)

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def repository_graph():
    names = discover_package_names(REPO / "packages")
    return build_static_graph(REPO, names)


def test_repository_graph_is_exhaustive_and_scoped(repository_graph):
    names = discover_package_names(REPO / "packages")

    assert tuple(organ["name"] for organ in repository_graph["organs"]) == names
    assert len(repository_graph["canonical_hash"]) == 64
    assert "does not establish runtime reachability" in repository_graph["claim_scope"]
    assert summarize_static_graph(repository_graph)["organ_count"] == len(names)


def test_every_reference_points_to_an_existing_source_file(repository_graph):
    for organ in repository_graph["organs"]:
        for reference in organ["production_inbound"] + organ["test_inbound"]:
            assert (REPO / reference["source"]).is_file()


def test_fixture_separates_production_tests_dynamic_literals_and_parse_failures(tmp_path):
    repo = tmp_path
    for name in ("alpha", "beta", "gamma"):
        (repo / "packages" / name).mkdir(parents=True)
        (repo / "packages" / name / "__init__.py").write_text("", encoding="utf-8")
    (repo / "packages" / "alpha" / "live.py").write_text(
        "from packages.beta import value\n"
        "import importlib\n"
        "importlib.import_module('packages.gamma.worker')\n",
        encoding="utf-8",
    )
    tests = repo / "packages" / "alpha" / "tests"
    tests.mkdir()
    (tests / "test_only.py").write_text("import packages.gamma\n", encoding="utf-8")
    (repo / "packages" / "beta" / "broken.py").write_text("def broken(:\n", encoding="utf-8")

    graph = build_static_graph(repo, ("alpha", "beta", "gamma"), scan_roots=("packages",))
    second = build_static_graph(repo, ("alpha", "beta", "gamma"), scan_roots=("packages",))
    by_name = {organ["name"]: organ for organ in graph["organs"]}

    assert graph == second
    assert by_name["beta"]["static_status"] == "production_static_reference"
    assert by_name["beta"]["production_inbound"][0]["owner"] == "packages.alpha"
    assert by_name["gamma"]["static_status"] == "production_static_reference"
    assert any(
        row["import_kind"] == "dynamic_literal"
        for row in by_name["gamma"]["production_inbound"]
    )
    assert by_name["gamma"]["test_inbound"]
    assert graph["parse_failures"] == [{
        "source": "packages/beta/broken.py",
        "error": "SyntaxError",
    }]


def test_self_import_does_not_count_as_external_wiring(tmp_path):
    package = tmp_path / "packages" / "alpha"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "from packages.alpha import local\n",
        encoding="utf-8",
    )
    graph = build_static_graph(tmp_path, ("alpha",), scan_roots=("packages",))
    assert graph["organs"][0]["static_status"] == "no_external_static_reference"
    assert graph["organs"][0]["production_inbound"] == []
