# -*- coding: utf-8 -*-
"""Derive what ATANOR's organs ARE and HAVE, so its architecture can be reasoned over like anything else.

SL-1's projection put the organs on the world surface as `has_a` edges. That alone cannot yield an
architecture hole, because the structural-hole detector works by PEER COMPARISON — "members of this
type carry relation R, this member does not" — and needs both a type and properties to compare.

Every fact here is READ off the repository, never listed:

  * the organ roster is the package directory itself, so an organ that exists is counted and one
    that is missing simply is not there to be counted (a hand roster could assert neither);
  * `is_a atanor_organ` gives every organ the same peer group. No taxonomy is invented — inventing
    one would be a hand table with extra steps, and the detector only needs peers, not a hierarchy;
  * possessions are checked on disk: a test suite, a doc, persisted data, an entry point.

That is enough for the ordinary detector to say "119 of 130 organs carry tests; these 11 do not"
without any code that knows what a test is. The claim is deliberately weak and checkable: this
module reports what is on disk. Whether a gap MATTERS is the detector's judgment, not this file's.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ORGAN_TYPE = "atanor_organ"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def organ_roster(root: Path | None = None) -> list[str]:
    """Every package directory. The roster IS the filesystem, so it cannot drift from reality."""
    pkgs = (root or _repo_root()) / "packages"
    if not pkgs.is_dir():
        return []
    return sorted(p.name for p in pkgs.iterdir()
                  if p.is_dir() and not p.name.startswith(("_", ".")))


def _importers(root: Path) -> dict[str, set[str]]:
    """organ -> the other organs that import it. Cached per root; one pass over the tree."""
    cached = _IMPORTERS.get(root)
    if cached is not None:
        return cached
    import re
    names = set(organ_roster(root))
    out: dict[str, set[str]] = {n: set() for n in names}
    pat = re.compile(r"packages\.([A-Za-z_][A-Za-z0-9_]*)")
    for organ in names:
        for py in (root / "packages" / organ).rglob("*.py"):
            if "__pycache__" in py.parts or "test" in py.name:
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for other in set(pat.findall(text)):
                if other in out and other != organ:
                    out[other].add(organ)
    _IMPORTERS[root] = out
    return out


_IMPORTERS: dict[Path, dict[str, set[str]]] = {}
_EMITTERS: dict[Path, set[str]] = {}

# A receipt is a DURABLE, addressable trace of what an organ did. Three shapes count, and the test
# is what the code does rather than what it is called -- `sealed_evidence` already showed how far a
# name match gets you (5/130, an artifact of filename spelling, not a signal).
_APPENDS = re.compile(r"""open\(\s*["']a["']|\.open\(\s*["']a["']|mode\s*=\s*["']a["']""")
_DURABLE = re.compile(r"\.jsonl\b")
_CONTRACT = re.compile(r"\b\w*Receipt\s*\(")
_RECORDS = re.compile(r"\b(record|log|append|emit)_\w*\(")

# NOT a receipt: `import logging`. A stdlib logger is ephemeral, unstructured and unaddressable --
# nothing can replay it and nothing can be held to it. Measured why this distinction is not
# pedantic: `conformal_gate`, which decides whether ATANOR answers or abstains, contains exactly
# one logging-shaped line (`import logging`) and no durable record of a single decision it made.


def _emitters(root: Path) -> set[str]:
    """Organs that themselves write a durable record. Cached; one pass, reused by the call test."""
    cached = _EMITTERS.get(root)
    if cached is not None:
        return cached
    out: set[str] = set()
    for organ in organ_roster(root):
        for py in (root / "packages" / organ).rglob("*.py"):
            if "__pycache__" in py.parts or "test" in py.name:
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if _CONTRACT.search(text) or (_DURABLE.search(text)
                                          and (_APPENDS.search(text) or _RECORDS.search(text))):
                out.add(organ)
                break
    _EMITTERS[root] = out
    return out


def organ_possessions(organ: str, root: Path | None = None) -> list[str]:
    """What this organ demonstrably has, checked on disk. Absence is reported as absence."""
    r = root or _repo_root()
    pkg = r / "packages" / organ
    have: list[str] = []
    if (pkg / "tests").is_dir() or any(pkg.glob("test_*.py")):
        have.append("tests")
    if any((r / "docs").glob(f"*{organ}*")) or (pkg / "README.md").exists():
        have.append("documentation")
    if (r / "data" / organ).exists():
        have.append("persisted_state")
    if (pkg / "__init__.py").exists() and (pkg / "__init__.py").stat().st_size > 0:
        have.append("public_interface")
    # Whether anything else in the system actually uses this organ. An organ nothing imports is the
    # built-but-unwired shape that keeps surfacing in review -- read here as an absence, so peer
    # coverage decides whether it is a hole rather than any rule written in this file.
    if _importers(r).get(organ):
        have.append("integration")
    # Evidence that this organ was ever measured, not merely written.
    if any((r / "reports").rglob(f"*{organ}*")) or any((r / "data" / "eval").glob(f"*{organ}*")):
        have.append("sealed_evidence")
    if _emits_receipt(organ, r):
        have.append("emits_receipt")
    return have


_TIER_DECL = re.compile(r"^ATANOR_TIER\s*=\s*[\"']([a-z_]+)[\"']", re.M)

# The four tiers of plan v5 §2. Held here only to reject a typo in a declaration -- which tier an
# organ belongs to is never decided in this file.
TIERS = ("reflex", "perception", "deliberative", "metabolic")


def organ_tier(organ: str, root: Path | None = None) -> str | None:
    """The tier this organ DECLARES for itself, or None when it has not said.

    Deliberately a reading, not a judgment. "May the orchestrator override this?" is a normative
    decision about the architecture, and a census that answered it would be dressing a policy up as
    a measurement -- the same move that made `sealed_evidence` look like a signal. So each organ
    states its own tier in its `__init__.py` and this reads the statement.

    That also keeps the declarations out of one central table, where they would be exactly the hand
    list this whole line of work exists to remove: an organ that is deleted takes its tier with it,
    and an organ that is added arrives undeclared and shows up as an absence.

    Read textually rather than by import: importing 132 packages to ask one question is expensive
    and runs their side effects."""
    init = (root or _repo_root()) / "packages" / organ / "__init__.py"
    try:
        m = _TIER_DECL.search(init.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    if not m:
        return None
    return m.group(1) if m.group(1) in TIERS else None


def unreceipted_by_tier(root: Path | None = None) -> dict[str, list[str]]:
    """Declared organs that emit no receipt, worst tier first.

    This is B2's work list and the reason B1 exists. An un-observed measuring organ is the worst
    case in the system: it governs, and it cannot be checked. Undeclared organs are reported
    separately rather than assumed harmless -- not having said what you are is not evidence."""
    r = root or _repo_root()
    out: dict[str, list[str]] = {t: [] for t in TIERS}
    out["undeclared"] = []
    for organ in organ_roster(r):
        if "emits_receipt" in organ_possessions(organ, r):
            continue
        tier = organ_tier(organ, r)
        out[tier or "undeclared"].append(organ)
    return out


def _emits_receipt(organ: str, root: Path) -> bool:
    """Does this organ leave a durable, addressable trace of what it did?

    Two ways to have one, because delegating is not the same as being silent: an organ may write
    its own record, or hand it to another organ's ledger. Both are checkable afterwards, which is
    the entire property. The second case is why this is not simply `organ in _emitters()` -- an
    organ that calls `flywheel.log_unread(...)` has a receipt and holds no `.jsonl` string of its
    own, and grading it silent would send the audit to fix organs that are already fine.

    The claim is deliberately narrow: this reports that a durable-write shape EXISTS in the organ,
    not that every decision it makes goes through one. An organ can pass here and still fail to
    receipt its main path. `emits_receipt` is a floor, and B2 is what reads it."""
    if organ in _emitters(root):
        return True
    emitters = _emitters(root)
    for py in (root / "packages" / organ).rglob("*.py"):
        if "__pycache__" in py.parts or "test" in py.name:
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _delegates_a_record(text, emitters):
            return True
    return False


def _delegates_a_record(text: str, emitters: set[str]) -> bool:
    """Is a recording function of an EMITTING organ actually called here?

    The call has to be BOUND to the import, and the first version of this did not bind them: it
    asked whether the file contained a record-shaped call anywhere and mentioned an emitter
    anywhere. `base_brain` was credited on that basis for calling its own
    `answer_experience.record_decision` in a file that separately imports `packages.conformal_gate`
    -- true of both halves, and evidence of neither. That is the same defect as reading
    `sealed_evidence` off a filename, so it is fixed rather than left as a convenient number.

    Two real shapes: a name imported FROM an emitter and then called, or a dotted call through the
    emitter's module path."""
    for other in emitters:
        if re.search(rf"\bpackages\.{re.escape(other)}[\w.]*\.(record|log|append|emit)_\w*\s*\(",
                     text):
            return True
        for m in re.finditer(rf"from\s+packages\.{re.escape(other)}[\w.]*\s+import\s+"
                             r"\(?([^)\n]+)\)?", text):
            for raw in m.group(1).split(","):
                name = raw.strip().split(" as ")[-1].strip()
                if _RECORDS.match(name + "(") and re.search(rf"\b{re.escape(name)}\s*\(", text):
                    return True
    return False


def census_triples(root: Path | None = None, *, allowed: frozenset[str] | None = None
                   ) -> list[tuple[str, str, str]]:
    """(organ, is_a, atanor_organ) + (organ, has_a, possession), filtered to real graph predicates."""
    from packages.continuous_self.self_projection import _live_predicates, _triple
    allowed = _live_predicates() if allowed is None else allowed
    out: list[tuple[str, str, str]] = []
    for organ in organ_roster(root):
        t = _triple(organ, "is_a", ORGAN_TYPE, allowed)
        if t:
            out.append(t)
        for owned in organ_possessions(organ, root):
            t = _triple(organ, "has_a", owned, allowed)
            if t:
                out.append(t)
    return out


def architecture_coverage(root: Path | None = None) -> dict[str, Any]:
    """Peer coverage per possession — the shape a structural hole is read from.

    An organ lacking something 90% of its peers carry is exactly what the knowledge-side detector
    calls a hole. Reported here as data, with the organs named, so the judgment stays external."""
    roster = organ_roster(root)
    if not roster:
        return {"organs": 0}
    owned: dict[str, list[str]] = {}
    for organ in roster:
        for item in organ_possessions(organ, root):
            owned.setdefault(item, []).append(organ)
    report: dict[str, Any] = {"organs": len(roster), "possessions": {}}
    for item, holders in sorted(owned.items()):
        lacking = [o for o in roster if o not in set(holders)]
        report["possessions"][item] = {
            "held_by": len(holders),
            "coverage": round(len(holders) / len(roster), 4),
            "lacking_count": len(lacking),
            "lacking": lacking[:12],
        }
    return report
