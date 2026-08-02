# -*- coding: utf-8 -*-
"""The SWE-engineering SELF-EVOLUTION loop — a SAFE, closed, crisp-oracle improvement loop.

This is the code-domain twin of ``packages/fluency/evolve.py``. Where fluency evolves a register CONFIG
against a PROXY tethered to a frozen human anchor, this loop evolves the repo-engineering CONFIG
(localization ranking + which edit-schema families the proposer may use) against a CRISP ORACLE: the
repo's own FAIL_TO_PASS + PASS_TO_PASS tests, run by ``regression_gate.verify_native``. "SWE resolved"
is a real pass/fail, so this domain is genuinely, autonomously evolvable — unlike naturalness there is
no human anchor to keep honest, the tests ARE the ground truth.

BRUTAL HONESTY (BINDING — honesty over hype):
  * The loop climbs a PROXY measured on a NATIVE FIXTURE SET (tiny self-contained git repos, no Docker):
    localization top-1 correctness + the count of edit candidates the native regression gate certifies
    GREEN. This proxy is a stand-in for the real benchmark, which needs prebuilt Docker images per
    instance. The proxy gain is REAL (every verified fixture is oracle-certified) but it is NOT the same
    as raising resolved on SWE-bench_Verified/Pro/Multilingual/Multimodal.
  * Real resolved on the full benchmark is ~0 today (one reachable single-token instance,
    astropy-12907, resolves under Docker; the rest is image-availability + single-token schema reach).
    The 90-avg north star is a FAR target the loop climbs TOWARD, recorded beside its honest current
    value, NEVER claimed as reached. See ``goal_scoreboard()`` and data/swe_eval/goal_scoreboard.json.

The loop's baseline CONFIG is deliberately a RESTRICTED starting capability (test-fusion off, only two
edit families enabled) so the climb is a genuine discovery of the levers — exactly the fluency pattern
(baseline register knobs the loop improves). Each accepted generation UNLOCKS a lever ONLY because the
crisp native oracle confirms more fixtures localize/resolve with NO regression and ZERO unverified diff.

A candidate is ACCEPTED iff ALL of, in safety order:
  (1) NO UNVERIFIED DIFF — every bug fixture the candidate CLAIMS resolved is re-checked by the REAL
      native oracle; a candidate that ships a diff the repo's own tests do not certify green (the
      fabrication / rubber-stamp-gate case) is REJECTED. This is the crisp-oracle analogue of fluency's
      faithfulness gate, and the isomorph of the anchor cross-check (a swapped gate is caught by the
      real tests, exactly as a swapped scorer is caught by the frozen anchor).
  (2) PROXY UP — the combined proxy (½ localization-top1 + ½ verified-diff) strictly increases.
  (3) NO REGRESSION — no fixture that the baseline localized top-1 or resolved becomes worse.

Rejections are the SAFETY PROOF, not failures: a loop that CANNOT be talked into shipping an
unverified diff or regressing a green fixture is the deliverable. Accepted configs are SIGNED,
ROLLBACKABLE generations (sha1 over the canonical config) under data/swe_eval/evolution/ — never by
overwriting any live surface. The loop holds ZERO learned weights: it is a SELECTOR over curated config
DATA (localization toggle + edit-schema family set), registered in the neuro ledger at 0 params.

Run: python -X utf8 -m packages.swe_eval.evolve
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from packages.swe_eval import edit_schemas as es
from packages.swe_eval import localizer as loc
from packages.swe_eval import regression_gate as rg

REPO = Path(__file__).resolve().parents[2]
_DEFAULT_EVOLVE_DIR = REPO / "data" / "swe_eval" / "evolution"
_SCOREBOARD_PATH = REPO / "data" / "swe_eval" / "goal_scoreboard.json"

# The bounded knob universe. l3_induced / guarded_early_return are deliberately OUT of the loop's
# universe (l3 is inert without an induced store; guarded double-fixes a fixture and muddies the
# demonstration) — the loop only ever selects among these curated, domain-blind families.
FAMILY_UNIVERSE: tuple[str, ...] = (
    "operand_substitution", "comparison_flip", "block_deletion",
    "none_guard_insertion", "boolop_flip",
)
_CONTENT_TOP_MIN, _CONTENT_TOP_MAX = 5, 40
BUG_VERIFY_BUDGET = 16                # max native gate calls per bug fixture (cheap-first, first-green)
_TOL = 1e-9

# ── the north-star, recorded honestly (target the loop climbs toward; current beside it) ───────────
NORTH_STAR_TARGET = 90.0             # owner goal: >= 90 avg across the four SWE-bench tracks
SWE_COMPONENTS = ("verified", "pro", "multilingual", "multimodal")

Gate = Callable[[dict[str, Any], str], "rg.RegressionVerdict"]
ShipOverride = Callable[[dict[str, Any]], str]


# ── config <-> data (a config is a small JSON-able dict of DATA knobs) ─────────────────────────────
def baseline_config() -> dict[str, Any]:
    """The loop's STARTING config — a deliberately RESTRICTED capability so the climb is a real
    discovery: failing-test fusion OFF (pure lexical localization) and only the two cheapest edit
    families enabled. The loop must EARN fusion + operand-substitution + the multi-line guard family by
    proving, through the crisp oracle, that each raises the proxy with no regression."""
    return {
        "use_test_fusion": False,
        "content_top": 25,
        "enabled_families": ["comparison_flip", "block_deletion"],
    }


def normalize_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Clamp knobs and gate the family set to FAMILY_UNIVERSE (a candidate cannot smuggle a family
    outside the curated universe — the same closed-vocabulary contract as fluency's register gate)."""
    fams = tuple(f for f in FAMILY_UNIVERSE if f in set(cfg.get("enabled_families", ())))
    ct = int(cfg.get("content_top", 25))
    ct = max(_CONTENT_TOP_MIN, min(_CONTENT_TOP_MAX, ct))
    return {
        "use_test_fusion": bool(cfg.get("use_test_fusion", False)),
        "content_top": ct,
        "enabled_families": list(fams),
    }


def _canonical_json(cfg: dict[str, Any]) -> str:
    n = normalize_config(cfg)
    n["enabled_families"] = sorted(n["enabled_families"])
    return json.dumps(n, sort_keys=True, ensure_ascii=False)


def config_signature(cfg: dict[str, Any]) -> str:
    """A tamper-evident signature over the canonical config (so an accepted generation is 'signed')."""
    return hashlib.sha1(_canonical_json(cfg).encode("utf-8")).hexdigest()[:16]


def _copy_config(cfg: dict[str, Any]) -> dict[str, Any]:
    return normalize_config(cfg)


# ── the native fixture set (the crisp-oracle proxy; no Docker) ─────────────────────────────────────
#
# LOCALIZATION fixtures are pure in-memory rankings (issue text + repo tree + the failing test that
# SWE-bench GIVES us — never the gold patch). BUG fixtures are tiny self-contained git repos with a
# real bug + a real FAIL_TO_PASS/PASS_TO_PASS, gated by regression_gate.verify_native (real pytest).
# Each edit family fixes exactly one bug fixture, so the proxy responds cleanly to the config knobs.

_LOC_FIXTURES: list[dict[str, Any]] = [
    {
        # cross-package: the true edit site (the RST writer, named by the failing test) is lexically
        # DOMINATED by a central table.py in another package. Only the failing-test signal floats it to
        # top-1 — the real "2/10 -> higher" localization lever, measured natively.
        "id": "cross_pkg_test_named",
        "problem": "Table Column Row join vstack lose formatting when written by the writer",
        "gold": "astropy/io/ascii/rst.py",
        "f2p": ["astropy/io/ascii/tests/test_rst.py::test_rst_with_header_rows"],
        "test_patch": "",
        "files": {
            "astropy/io/ascii/rst.py": "class RST:\n    def write(self, lines):\n        return lines\n",
            "astropy/io/ascii/core.py": "x = 1\n",
            "astropy/table/table.py": ("class Table:\n    pass\nclass Column:\n    pass\n"
                                       "class Row:\n    pass\ndef join():\n    pass\ndef vstack():\n    pass\n"),
        },
    },
    {
        # same-package: the issue names a symbol the target file defines; plain lexical already nails it
        # and there is NO failing-test signal, so fusion is identity here. This is the "already correct,
        # must not regress" localization fixture — a candidate that breaks it is rejected.
        "id": "same_pkg_lexical",
        "problem": "separability_matrix returns a wrong separable result",
        "gold": "pkg/separable.py",
        "f2p": [],
        "test_patch": "",
        "files": {
            "pkg/core.py": "x = 1\n",
            "pkg/separable.py": ("def separability_matrix(model):\n    return _cstack(model)\n\n"
                                 "def _cstack(left):\n    a = 1\n    return a\n"),
            "pkg/util.py": "def helper():\n    return 0\n",
        },
    },
]

# Each bug fixture: a function with a real bug and tests. `family` documents which edit family fixes it
# (asserted separable by construction; the loop never READS this — the native oracle decides).
_BUG_FIXTURES: list[dict[str, Any]] = [
    {
        "id": "operand_choose", "family": "operand_substitution", "filename": "mod.py", "fn": "choose",
        "src": "def choose(a, b):\n    result = a\n    return result\n",
        "tests": ("from mod import choose\n"
                  "def test_choose():\n    assert choose(1, 2) == 2\n"
                  "def test_keep():\n    assert choose(5, 5) == 5\n"),
        "f2p": ["test_mod.py::test_choose"], "p2p": ["test_mod.py::test_keep"],
    },
    {
        "id": "none_guard_collect", "family": "none_guard_insertion", "filename": "mod.py", "fn": "collect",
        "src": "def collect(x):\n    out = []\n    for k in x:\n        out.append(k)\n    return out\n",
        "tests": ("from mod import collect\n"
                  "def test_none():\n    assert collect(None) == []\n"
                  "def test_list():\n    assert collect([1, 2, 3]) == [1, 2, 3]\n"),
        "f2p": ["test_mod.py::test_none"], "p2p": ["test_mod.py::test_list"],
    },
    {
        "id": "comparison_is_less", "family": "comparison_flip", "filename": "mod.py", "fn": "is_less",
        "src": "def is_less(a, b):\n    return a <= b\n",
        "tests": ("from mod import is_less\n"
                  "def test_strict():\n    assert is_less(2, 2) == False\n"
                  "def test_true():\n    assert is_less(1, 2) == True\n"),
        "f2p": ["test_mod.py::test_strict"], "p2p": ["test_mod.py::test_true"],
    },
]


def _git(rd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(rd), *args], check=True, capture_output=True, text=True)


@dataclass
class Fixtures:
    """A run-scoped fixture set: pure-python localization fixtures + on-disk git bug repos, plus two
    caches so re-scoring a config never re-runs pytest it already ran (localization depends only on the
    fusion/content knobs; bug outcomes depend only on the enabled-family set)."""
    loc: list[dict[str, Any]]
    bug: list[dict[str, Any]]
    root: Path
    _loc_cache: dict[tuple, dict[str, bool]] = field(default_factory=dict)
    _bug_cache: dict[tuple, dict[str, tuple[bool, str]]] = field(default_factory=dict)

    @property
    def bug_by_id(self) -> dict[str, dict[str, Any]]:
        return {b["id"]: b for b in self.bug}

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def build_fixtures() -> Fixtures:
    """Materialize the bug fixtures as isolated git repos (system temp — no parent conftest). The
    localization fixtures need no disk. Deterministic and self-contained."""
    root = Path(tempfile.mkdtemp(prefix="atanor_swe_evolve_"))
    bugs: list[dict[str, Any]] = []
    for spec in _BUG_FIXTURES:
        rd = root / spec["id"]
        rd.mkdir(parents=True)
        (rd / spec["filename"]).write_text(spec["src"], encoding="utf-8")
        (rd / "test_mod.py").write_text(spec["tests"], encoding="utf-8")
        _git(rd, "init", "-q")
        _git(rd, "config", "user.email", "t@t")
        _git(rd, "config", "user.name", "t")
        _git(rd, "add", "-A")
        _git(rd, "commit", "-qm", "base")
        base = subprocess.run(["git", "-C", str(rd), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        bugs.append({**spec, "repo_dir": str(rd), "base": base})
    return Fixtures(loc=list(_LOC_FIXTURES), bug=bugs, root=root)


# ── scoring a config against the fixture set ───────────────────────────────────────────────────────
@dataclass
class ConfigScore:
    proxy: float                                 # ½ localization-top1 + ½ verified-diff, in [0, 1]
    loc_hits: int
    n_loc: int
    verified: int                                # bug fixtures the (given) gate certified resolved
    n_bug: int
    per_fixture: dict[str, bool]                 # "loc:<id>" / "bug:<id>" -> success (for regression)
    shipped_diffs: dict[str, str] = field(default_factory=dict)   # bug id -> the diff claimed resolved

    def as_dict(self) -> dict[str, Any]:
        return {"proxy": round(self.proxy, 6), "loc_top1": f"{self.loc_hits}/{self.n_loc}",
                "verified_diffs": f"{self.verified}/{self.n_bug}"}


def _oracle_gate(fix: dict[str, Any], diff: str) -> "rg.RegressionVerdict":
    """The CRISP oracle: the repo's own FAIL_TO_PASS + PASS_TO_PASS, run natively (real pytest)."""
    return rg.verify_native(fix["repo_dir"], "", diff, fix["f2p"], fix["p2p"], base_commit=fix["base"])


def _score_localization(cfg: dict[str, Any], fixtures: Fixtures) -> dict[str, bool]:
    key = (cfg["use_test_fusion"], cfg["content_top"])
    if key in fixtures._loc_cache:
        return fixtures._loc_cache[key]
    out: dict[str, bool] = {}
    for fx in fixtures.loc:
        files = list(fx["files"])
        read = fx["files"].get
        if cfg["use_test_fusion"]:
            lz, _sig = loc.localize_fused(fx["problem"], files, read, f2p=fx["f2p"],
                                          test_patch=fx.get("test_patch", ""),
                                          content_top=cfg["content_top"])
        else:
            lz = loc.localize(fx["problem"], files, read_file=read, content_top=cfg["content_top"])
        out[fx["id"]] = (lz.top1 == fx["gold"])
    fixtures._loc_cache[key] = out
    return out


def _score_bugs(cfg: dict[str, Any], fixtures: Fixtures, gate: Gate,
                ship_override: ShipOverride | None) -> dict[str, tuple[bool, str]]:
    """For each bug fixture, propose edits restricted to the enabled families and ship the FIRST diff
    the given ``gate`` certifies resolved (fail-0: nothing else is shipped). ``ship_override`` (used
    only by the fabrication probe) bypasses enumeration to ship a fixed diff — modelling a candidate
    that claims a fix without proposing a real one."""
    fams = set(cfg["enabled_families"])
    honest = gate is _oracle_gate and ship_override is None
    key = tuple(sorted(fams))
    if honest and key in fixtures._bug_cache:
        return fixtures._bug_cache[key]
    out: dict[str, tuple[bool, str]] = {}
    for fix in fixtures.bug:
        if ship_override is not None:
            diff = ship_override(fix)
            v = gate(fix, diff)
            out[fix["id"]] = (bool(v.resolved), diff)
            continue
        resolved, shipped = False, ""
        cands = [c for c in es.propose_edits(fix["src"], fix["fn"]) if c.schema in fams]
        for c in cands[:BUG_VERIFY_BUDGET]:
            diff = es.unified_diff(fix["src"], c.new_source, fix["filename"])
            if not diff.strip():
                continue
            v = gate(fix, diff)
            if v.resolved:
                resolved, shipped = True, diff
                break
        out[fix["id"]] = (resolved, shipped)
    if honest:
        fixtures._bug_cache[key] = out
    return out


def score_config(cfg: dict[str, Any], fixtures: Fixtures, gate: Gate | None = None,
                 ship_override: ShipOverride | None = None) -> ConfigScore:
    """Score a config on the fixture set. ``gate`` defaults to the crisp native oracle; a candidate may
    carry an ALTERNATIVE gate (used to demonstrate a rubber-stamp gate is caught by the real oracle)."""
    cfg = normalize_config(cfg)
    gate = gate or _oracle_gate
    loc_res = _score_localization(cfg, fixtures)
    bug_res = _score_bugs(cfg, fixtures, gate, ship_override)
    per: dict[str, bool] = {f"loc:{k}": v for k, v in loc_res.items()}
    shipped: dict[str, str] = {}
    for bid, (resolved, diff) in bug_res.items():
        per[f"bug:{bid}"] = resolved
        if resolved:
            shipped[bid] = diff
    loc_hits, n_loc = sum(loc_res.values()), len(loc_res)
    verified, n_bug = sum(1 for r, _ in bug_res.values() if r), len(bug_res)
    proxy = 0.5 * (loc_hits / n_loc if n_loc else 0.0) + 0.5 * (verified / n_bug if n_bug else 0.0)
    return ConfigScore(proxy=proxy, loc_hits=loc_hits, n_loc=n_loc, verified=verified, n_bug=n_bug,
                       per_fixture=per, shipped_diffs=shipped)


# ── candidates (DATA-level config knobs; the two adversarial kinds are guarded, never accepted) ────
@dataclass
class Candidate:
    cand_id: str
    kind: str                                    # "config" | "fabrication" | "regression"
    config: dict[str, Any]
    gate: Gate | None = None                     # None => crisp native oracle (no-unverified axis)
    ship_override: ShipOverride | None = None    # None => honest enumeration (no-unverified axis)
    rationale: str = ""


def _with(base: dict[str, Any], **changes: Any) -> dict[str, Any]:
    cfg = _copy_config(base)
    cfg.update(changes)
    return normalize_config(cfg)


def _add_family(base: dict[str, Any], fam: str) -> dict[str, Any]:
    return _with(base, enabled_families=list(base["enabled_families"]) + [fam])


def perturb(base: dict[str, Any]) -> list[Candidate]:
    """Enumerate BOUNDED neighbor configs — ONE knob changed at a time: turn on failing-test fusion,
    enable one more edit family, or nudge content_top. Deliberately includes knobs that yield NO proxy
    gain on the fixtures (a family with no matching fixture, a content_top nudge) so the search is
    bounded by the oracle, not by a hand rule."""
    base = normalize_config(base)
    out: list[Candidate] = []
    if not base["use_test_fusion"]:
        out.append(Candidate("cfg_test_fusion_on", "config", _with(base, use_test_fusion=True),
                             rationale="turn ON the failing-test localization signal (the top-1 lever)"))
    for fam in FAMILY_UNIVERSE:
        if fam not in set(base["enabled_families"]):
            out.append(Candidate(f"cfg_enable_{fam}", "config", _add_family(base, fam),
                                 rationale=f"admit the '{fam}' edit-schema family to the proposer"))
    for delta in (5, -5):
        ct = base["content_top"] + delta
        if _CONTENT_TOP_MIN <= ct <= _CONTENT_TOP_MAX:
            out.append(Candidate(f"cfg_content_top_{ct}", "config", _with(base, content_top=ct),
                                 rationale=f"content rescore depth -> {ct}"))
    return out


# ── the acceptance gate (every rejection carries an honest reason) ─────────────────────────────────
@dataclass
class Verdict:
    accepted: bool
    reason: str                                  # accepted | unverified_diff | no_proxy_gain | regression
    proxy_before: float
    proxy_after: float
    unverified_diffs: int
    regressed: list[str] = field(default_factory=list)
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"accepted": self.accepted, "reason": self.reason,
                "proxy_before": round(self.proxy_before, 6), "proxy_after": round(self.proxy_after, 6),
                "unverified_diffs": self.unverified_diffs, "regressed": self.regressed,
                "detail": self.detail}


def _count_unverified(cand: ConfigScore, fixtures: Fixtures) -> int:
    """Re-check every CLAIMED-resolved bug diff with the REAL native oracle. A claim the repo's own
    tests do not certify green is an unverified (fabricated) diff. This is the crisp-oracle isomorph of
    fluency's frozen-anchor cross-check: a swapped gate is caught by re-running the true tests."""
    unverified = 0
    for bid, diff in cand.shipped_diffs.items():
        truth = _oracle_gate(fixtures.bug_by_id[bid], diff)
        if not truth.resolved:
            unverified += 1
    return unverified


def evaluate(candidate: Candidate, baseline: ConfigScore, fixtures: Fixtures) -> Verdict:
    """Adjudicate one candidate against the current baseline. Gates in SAFETY order:

        no-unverified-diff (fabrication)  ->  proxy gain  ->  no regression

    The no-unverified gate is checked FIRST and is HARD: a candidate that ships a diff the repo's own
    tests do not certify green is rejected regardless of how good its proxy looks."""
    cand = score_config(candidate.config, fixtures, gate=candidate.gate,
                        ship_override=candidate.ship_override)
    # (1) NO UNVERIFIED DIFF — only re-verify when a non-oracle gate/override was used (honest configs
    #     are oracle-certified by construction, so this stays free on the climb path).
    unverified = 0
    if candidate.gate is not None or candidate.ship_override is not None:
        unverified = _count_unverified(cand, fixtures)

    def verdict(accepted: bool, reason: str, detail: str = "", regressed: list[str] | None = None) -> Verdict:
        return Verdict(accepted=accepted, reason=reason, proxy_before=baseline.proxy,
                       proxy_after=cand.proxy, unverified_diffs=unverified,
                       regressed=regressed or [], detail=detail)

    if unverified > 0:
        return verdict(False, "unverified_diff",
                       f"{unverified} claimed-resolved diff(s) the native oracle does NOT certify green "
                       f"— a rubber-stamped fix is refused (fail-0: nothing unverified is shipped)")

    # (2) PROXY UP
    if cand.proxy <= baseline.proxy + _TOL:
        return verdict(False, "no_proxy_gain",
                       f"proxy {cand.proxy:.4f} did not beat baseline {baseline.proxy:.4f}")

    # (3) NO REGRESSION — no fixture that the baseline got right becomes worse
    regressed = [k for k, ok in baseline.per_fixture.items() if ok and not cand.per_fixture.get(k, ok)]
    if regressed:
        return verdict(False, "regression",
                       f"{len(regressed)} fixture(s) regressed despite the higher mean: {regressed[:5]}",
                       regressed=regressed)

    return verdict(True, "accepted",
                   f"proxy {baseline.proxy:.4f} -> {cand.proxy:.4f}, no unverified diff, no regression")


# ── the adversarial candidates the loop MUST reject (the safety proof made concrete) ──────────────
def _stamp_gate(fix: dict[str, Any], diff: str) -> "rg.RegressionVerdict":
    """A rubber-stamp gate: returns ACCEPTED without ever running the repo's tests."""
    return rg.RegressionVerdict(rg.ACCEPTED, "regression-green",
                                "STAMPED accepted without running the tests", backend="none")


def _noop_diff(fix: dict[str, Any]) -> str:
    """A diff that does NOT fix the bug (appends a comment) — the thing a fabricator ships as 'green'."""
    return es.unified_diff(fix["src"], fix["src"].rstrip("\n") + "\n# stamped-not-fixed\n", fix["filename"])


def make_fabrication_candidate(base: dict[str, Any]) -> Candidate:
    """A fabrication attempt: a rubber-stamp gate that certifies a NO-OP diff 'green' without running
    the repo's tests. The no-unverified gate catches it — the real native oracle re-runs FAIL_TO_PASS
    and finds it still red, so every claimed fix is an unverified diff -> REJECTED."""
    return Candidate("adv_fabrication", "fabrication",
                     _with(base, enabled_families=list(FAMILY_UNIVERSE)),
                     gate=_stamp_gate, ship_override=_noop_diff,
                     rationale="rubber-stamp gate ships a no-op diff as 'green' without running tests")


def regression_probe_baseline() -> dict[str, Any]:
    """A baseline where the wrong-operand bug is already GREEN (operand_substitution enabled) and
    fusion is off — the setup the regression probe is measured against."""
    return {"use_test_fusion": False, "content_top": 25,
            "enabled_families": ["operand_substitution", "comparison_flip"]}


def make_regression_candidate(base: dict[str, Any]) -> Candidate:
    """A regression attempt: turn fusion ON (raises the localization proxy) but DROP
    operand_substitution (the only family that fixes the wrong-operand fixture). Measured against
    ``regression_probe_baseline`` the mean proxy RISES, yet a previously-green fixture goes red ->
    REJECTED as a regression (proxy up is not enough; nothing green may be lost)."""
    cfg = {"use_test_fusion": True, "content_top": 25, "enabled_families": ["comparison_flip"]}
    return Candidate("adv_regression", "regression", cfg,
                     rationale="fusion ON (proxy up) but drops operand_substitution (regresses a green fixture)")


# ── signed, rollbackable persistence (never overwrites any live surface) ──────────────────────────
def _evolve_dir(out_dir: Path | None) -> Path:
    d = Path(out_dir) if out_dir is not None else _DEFAULT_EVOLVE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _generations_path(out_dir: Path | None) -> Path:
    return _evolve_dir(out_dir) / "generations.jsonl"


def _active_path(out_dir: Path | None) -> Path:
    return _evolve_dir(out_dir) / "active.json"


def sign_generation(cfg: dict[str, Any], *, gen_index: int, parent: str | None, proxy: float,
                    verified: int, loc_hits: int, reason: str,
                    out_dir: Path | None = None) -> dict[str, Any]:
    """Append one SIGNED generation and move the active pointer to it. Append-only: any prior
    generation stays rollbackable."""
    sig = config_signature(cfg)
    gen_id = f"g{gen_index:03d}-{sig}"
    record = {
        "gen_id": gen_id, "gen_index": gen_index, "parent": parent, "signature": sig,
        "ts": round(time.time(), 3), "proxy": round(proxy, 6), "verified_diffs": verified,
        "loc_top1": loc_hits, "reason": reason, "config": normalize_config(cfg),
        "note": "signed repo-engineering CONFIG generation; no live surface is overwritten",
    }
    with _generations_path(out_dir).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    _active_path(out_dir).write_text(
        json.dumps({"active": gen_id, "signature": sig, "ts": record["ts"]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def list_generations(out_dir: Path | None = None) -> list[dict[str, Any]]:
    p = _generations_path(out_dir)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    return out


def active_generation(out_dir: Path | None = None) -> dict[str, Any] | None:
    p = _active_path(out_dir)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def config_of_generation(gen_id: str, out_dir: Path | None = None) -> dict[str, Any] | None:
    for rec in list_generations(out_dir):
        if rec["gen_id"] == gen_id:
            return normalize_config(rec["config"])
    return None


def rollback(gen_id: str, out_dir: Path | None = None) -> dict[str, Any]:
    """Roll the active pointer back to a prior signed generation, after re-checking its signature still
    matches its stored config (tamper-evidence)."""
    rec = next((r for r in list_generations(out_dir) if r["gen_id"] == gen_id), None)
    if rec is None:
        raise KeyError(f"no such generation: {gen_id}")
    if config_signature(rec["config"]) != rec["signature"]:
        raise ValueError(f"generation {gen_id} failed signature check (tampered)")
    payload = {"active": gen_id, "signature": rec["signature"], "ts": round(time.time(), 3),
               "rolled_back": True}
    _active_path(out_dir).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    return payload


# ── the closed loop ───────────────────────────────────────────────────────────────────────────────
def run(rounds: int = 6, persist: bool = True, out_dir: Path | None = None,
        include_safety_probes: bool = True, fixtures: Fixtures | None = None) -> dict[str, Any]:
    """Run the bounded, gated hill-climb over the config knob space. Each round proposes neighbors of
    the current best, accepts the best strictly-improving one that clears every gate (oracle-certified,
    no unverified diff, no regression), and persists it as a signed generation. Reports the honest
    trajectory and the safety rejections."""
    own_fixtures = fixtures is None
    fixtures = fixtures or build_fixtures()
    try:
        base = baseline_config()
        best = base
        best_score = score_config(best, fixtures)
        parent_sig: str | None = None
        gen_index = 0

        rejections: Counter = Counter()
        accepted_history: list[dict[str, Any]] = []
        proxy_trajectory: list[float] = [best_score.proxy]

        generations: list[dict[str, Any]] = []
        if persist:
            rec = sign_generation(best, gen_index=gen_index, parent=None, proxy=best_score.proxy,
                                  verified=best_score.verified, loc_hits=best_score.loc_hits,
                                  reason="baseline", out_dir=out_dir)
            generations.append(rec)
            parent_sig = rec["gen_id"]

        proxy_start = best_score.proxy
        rounds_run = 0
        for r in range(1, rounds + 1):
            winner: Candidate | None = None
            winner_score: ConfigScore | None = None
            for cand in perturb(best):
                v = evaluate(cand, best_score, fixtures)
                if not v.accepted:
                    rejections[v.reason] += 1
                    continue
                cs = score_config(cand.config, fixtures)
                if winner_score is None or cs.proxy > winner_score.proxy:
                    winner, winner_score = cand, cs
            if winner is None:
                accepted_history.append({"round": r, "accepted": None, "reason": "plateau",
                                         "proxy": round(best_score.proxy, 6)})
                break
            best, best_score = winner.config, winner_score
            gen_index += 1
            rounds_run = r
            proxy_trajectory.append(best_score.proxy)
            rec = None
            if persist:
                rec = sign_generation(best, gen_index=gen_index, parent=parent_sig,
                                      proxy=best_score.proxy, verified=best_score.verified,
                                      loc_hits=best_score.loc_hits,
                                      reason=f"accepted:{winner.cand_id}", out_dir=out_dir)
                generations.append(rec)
                parent_sig = rec["gen_id"]
            accepted_history.append({
                "round": r, "accepted": winner.cand_id, "rationale": winner.rationale,
                "proxy": round(best_score.proxy, 6),
                "loc_top1": f"{best_score.loc_hits}/{best_score.n_loc}",
                "verified_diffs": f"{best_score.verified}/{best_score.n_bug}",
                "gen_id": rec["gen_id"] if rec else None,
            })

        # ── safety probes: the loop MUST reject a fabrication candidate and a regression candidate ──
        safety: dict[str, Any] = {}
        if include_safety_probes:
            fab = evaluate(make_fabrication_candidate(best), best_score, fixtures)
            reg_base = score_config(regression_probe_baseline(), fixtures)
            reg = evaluate(make_regression_candidate(best), reg_base, fixtures)
            rejections[fab.reason] += 1
            rejections[reg.reason] += 1
            safety = {"fabrication": fab.as_dict(), "regression": reg.as_dict(),
                      "both_rejected": (not fab.accepted) and (not reg.accepted)}

        report = {
            "domain": "swe_engineering",
            "status": "crisp-oracle-evolvable",
            "proxy_kind": ("native-fixture PROXY (localization top-1 + oracle-certified verified-diff "
                           "count); a stand-in for Docker-gated real resolved, NOT the benchmark number"),
            "rounds_requested": rounds,
            "rounds_accepted": rounds_run,
            "proxy_before": round(proxy_start, 6),
            "proxy_after": round(best_score.proxy, 6),
            "proxy_gain": round(best_score.proxy - proxy_start, 6),
            "proxy_trajectory": [round(x, 6) for x in proxy_trajectory],
            "localization_top1": f"{best_score.loc_hits}/{best_score.n_loc}",
            "verified_diffs": f"{best_score.verified}/{best_score.n_bug}",
            "best_config": normalize_config(best),
            "history": accepted_history,
            "rejections_by_reason": dict(rejections),
            "safety_rejections": int(rejections.get("unverified_diff", 0))
                                 + int(rejections.get("regression", 0)),
            "safety_probes": safety,
            "active_generation": active_generation(out_dir) if persist else None,
            "n_generations": len(generations),
            "ceiling_note": ("the fixture proxy is a small, curated knob space: the loop plateaus once "
                             "it has unlocked fusion + the fixtures' families, by design. The gain is a "
                             "PROXY gain on native fixtures, NOT resolved on the real benchmark (that "
                             "needs Docker images + wider schema reach). The deliverable is the SAFE "
                             "closed loop (crisp oracle, no unverified diff, no regression), plus the "
                             "honest north star it climbs toward."),
            "is_autonomous_safe": True,          # crisp oracle: the repo's own tests, not a human anchor
            "north_star": {"benchmark": "swe_avg", "target": NORTH_STAR_TARGET},
        }
        return report
    finally:
        if own_fixtures:
            fixtures.cleanup()


# ── the honest goal scoreboard (target 90 vs the honest current ~0) ───────────────────────────────
def _read_json(p: Path) -> Any | None:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:
        return None


def goal_scoreboard(loop_report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compose the HONEST scoreboard. current_avg is the mean of the four tracks' honest current values
    (all ~0); it is recorded beside the target 90, never claimed as reached. reachable_subset_resolved
    is read from the real Docker patch_report (astropy-12907 resolves; the full benchmark is ~0)."""
    patch = _read_json(REPO / "data" / "swe_eval" / "patch_report.json") or {}
    agg = patch.get("aggregate", {})
    reachable_resolved = int(agg.get("resolved", 0))
    verified_diffs = int(agg.get("verified_diffs", 0))
    # SWE-bench_Verified has 500 instances; only the reachable single-token subset has been attempted +
    # resolved under Docker. resolved% over the FULL set is the honest track number.
    VERIFIED_N = 500
    verified_pct = round(100.0 * reachable_resolved / VERIFIED_N, 4)     # ~0.2 (1/500)

    per_benchmark = {
        "verified": {
            "status": "measurable-but-low", "resolved_pct": verified_pct,
            "reachable_resolved": reachable_resolved, "n_full": VERIFIED_N,
            "backend": "docker (native fixtures for the self-evolution proxy)",
            "blocker": "prebuilt per-instance images + single-token/single-function schema reach; only "
                       "the reachable subset resolves today",
        },
        "pro": {"status": "loads-not-run", "resolved_pct": 0.0,
                "blocker": "dataset loads (probe) but the harness has not been run end-to-end on Pro"},
        "multilingual": {"status": "out-of-scope-java", "resolved_pct": 0.0,
                         "blocker": "the edit-schema engine is a Python-AST mutator; Multilingual is "
                                    "Java-centric -> out of scope until a JVM/AST backend exists"},
        "multimodal": {"status": "out-of-scope-vision", "resolved_pct": 0.0,
                       "blocker": "needs vision + browser tool-use to read the visual issue; not wired"},
    }
    current_avg = round(sum(b["resolved_pct"] for b in per_benchmark.values()) / len(per_benchmark), 4)
    measured_ceiling = max(b["resolved_pct"] for b in per_benchmark.values())

    board = {
        "benchmark": "swe_avg",
        "target": NORTH_STAR_TARGET,
        "current_avg": current_avg,                    # honest, ~0 — NEVER > measured_ceiling
        "measured_ceiling": measured_ceiling,          # the single best track number actually observed
        "gap_to_target": round(NORTH_STAR_TARGET - current_avg, 4),
        "claimed_reached": False,
        "per_benchmark": per_benchmark,
        "reachable_subset_resolved": reachable_resolved,
        "top1_localization": ("native fixtures: fusion lifts 1/2 -> 2/2 top-1; on SWE-bench_Verified "
                              "the fused localizer measured 8/10 top-1 (report.json)"),
        "self_evolution_proxy": {
            "proxy_before": (loop_report or {}).get("proxy_before"),
            "proxy_after": (loop_report or {}).get("proxy_after"),
            "proxy_gain": (loop_report or {}).get("proxy_gain"),
            "note": "native-fixture proxy gain; a stand-in for resolved, not the benchmark number",
        },
        "next_two_levers": [
            "IMAGE AVAILABILITY: pull/build the prebuilt swebench instance images so the crisp Docker "
            "oracle can run over a real sample (turns the native-proxy climb into real resolved counts).",
            "SCHEMA REACH: widen the edit-schema families beyond single-token/single-block (multi-hunk "
            "coordinated edits, import/API-shape edits) so more of SWE-bench_Verified's fixes fall inside "
            "the enumerable-and-verified family.",
        ],
        "honest_framing": ("90 is a FAR north star. Current is ~0 (one reachable Docker-verified "
                           "instance; Pro not run; Multilingual is Java / out of scope; Multimodal needs "
                           "vision). The deliverable is a WORKING crisp-oracle climb-loop + this honest "
                           "scoreboard, not a large number."),
        "generated_at": _now(),
    }
    return board


def write_scoreboard(loop_report: dict[str, Any] | None = None, path: Path | None = None) -> Path:
    board = goal_scoreboard(loop_report)
    p = path or _SCOREBOARD_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(board, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def _now() -> str:
    import datetime
    return datetime.datetime.now().replace(microsecond=0).isoformat()


# ── neuro ledger: register the loop's footprint (ZERO learned params — a config selector) ─────────
def neuro_ledger_organ():
    """Declare the evolve loop to the neuro ledger as a 0-param CONTROL organ (mirrors fluency's
    evolve loop + swe_eval.neuro_registration — declares an Organ WITHOUT editing the ledger). The loop
    holds NO learned weights: it enumerates curated config knobs, scores them with the regression
    oracle, and selects a winner. Footprint is exactly 0; never a fact source."""
    from packages.neuro_ledger.ledger import Organ
    return Organ(
        id="swe_evolve_loop",
        path="packages/swe_eval/evolve.py",
        role="closed self-evolution loop: enumerates repo-engineering CONFIG knobs (localization "
             "test-fusion + content depth, edit-schema family set) and PROMOTES a config only on "
             "oracle-certified proxy-up + no-unverified-diff + no-regression; a SELECTOR over curated "
             "config DATA, ZERO learned weights",
        gate="swe_engineering self-evolution acceptance gate (crisp native regression oracle x "
             "no-unverified-diff x no-regression; signed rollbackable generations)",
        artifacts=[],
        fact_source=False,
        enforced=False,
        status="active",
        fallback_params=0,
    )


def budget_check() -> dict[str, Any]:
    """Measure the loop's real parameter footprint. INVARIANT: 0 learned params, not a fact source."""
    from packages.neuro_ledger.ledger import measure_params
    o = neuro_ledger_organ()
    m = measure_params(o)
    params = int(m.get("params", 0))
    return {"id": o.id, "params": params, "fact_source": o.fact_source,
            "ok": params == 0 and o.fact_source is False}


def main() -> None:
    import io
    import sys
    rep = run(persist=True)
    board = goal_scoreboard(rep)
    write_scoreboard(rep)
    buf = io.StringIO()
    buf.write("SWE-engineering SELF-EVOLUTION loop — SAFE, crisp-oracle (HONEST native-fixture proxy)\n\n")
    buf.write(f"  proxy {rep['proxy_before']} -> {rep['proxy_after']} "
              f"(gain {rep['proxy_gain']:+.4f}) over {rep['rounds_accepted']} accepted round(s); "
              f"trajectory {rep['proxy_trajectory']}\n")
    buf.write(f"  localization top-1 {rep['localization_top1']}, "
              f"verified diffs {rep['verified_diffs']} (native oracle)\n")
    sp = rep.get("safety_probes", {})
    if sp:
        buf.write(f"  safety proof (rejections): fabrication REJECTED ({sp['fabrication']['reason']}, "
                  f"{sp['fabrication']['unverified_diffs']} unverified diff(s)); "
                  f"regression REJECTED ({sp['regression']['reason']}, "
                  f"regressed {sp['regression']['regressed']})\n")
    buf.write(f"  rejections by reason: {rep['rejections_by_reason']}\n")
    buf.write(f"  NORTH STAR: swe_avg target {board['target']} vs current {board['current_avg']} "
              f"(gap {board['gap_to_target']}); reachable_subset_resolved={board['reachable_subset_resolved']}\n")
    buf.write(f"  per-benchmark: " + ", ".join(
        f"{k}={v['status']}({v['resolved_pct']})" for k, v in board["per_benchmark"].items()) + "\n")
    buf.write(f"  ceiling: {rep['ceiling_note']}\n")
    buf.write(f"  neuro budget: {budget_check()}\n")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.stdout.write(buf.getvalue())


if __name__ == "__main__":
    main()
