# -*- coding: utf-8 -*-
"""Wiring audit — systematic detector for the "built-but-unwired" failure class.

Why this exists (2026-07-18). One session surfaced FIVE instances of the same pathology:
  1. `gather_neighborhood(min_overlap)` — parameter declared, never used (dead knob)
  2. `_EN_WH` — regex built, unreachable behind `_EN_FUNC` (dead mapping)
  3. `PMISolver` — full class built, never called by the exam cascade (unwired lever)
  4. `wiki_passages_en_full` — 7.0M English passages on disk, loader defaulted to the
     retired Korean corpus (unwired asset + stale default after the English-only pivot)
  5. `wiki_kg_en` — 4.5M English triples on disk, benchmark unioned the 503k Korean lane
The root cause is structural, not personal: BUILDING an asset and WIRING it are separate
manual steps with no cross-check, so the second step silently goes missing — and a default
written before a doctrine pivot (English-only, 2026-07-17) keeps pointing at a retired lane
forever. This script makes the gap measurable instead of anecdotal.

Checks (all read-only; no store writes, no network):
  A. LANE MANIFEST vs CODE — data/graph_scale/LANES.json declares the canonical asset per
     role and the parked ones. Flag any code default that references a PARKED lane.
  B. UNWIRED DATA ASSETS — top-level dirs/files under data/graph_scale + data/atanor_index
     that no non-test code references at all (candidates for wiring or parking).
  C. ENV-FLAG REGISTRY — every os.environ.get("ATANOR_*"/"OPENBOOK_*"...) flag found in
     code, with whether any test exercises it (untested flags = untested branches).
  D. DEAD PARAMETERS — function params (AST scan) never read in the function body
     (the `min_overlap` class; heuristic, self/cls/_ and **kwargs excluded).
  E. SEED HYGIENE — sha256/md5 over a bare input variable with no component salt prefix
     (the GPQA guess↔harness coupling class; E3/E4 root cause).

Exit code 0 always (informational tool, not a gate) — wire into the seal battery only by
an explicit operator decision. Usage:  python scripts/audit_wiring.py [--json]
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

# Windows cp949 console mangles em-dashes and Korean in findings — the exact ops-trap class
# this audit documents (a Korean curl body was once mangled into a false "guard not firing").
# The tool immunises itself instead of asking every caller to remember PYTHONIOENCODING.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
CODE_DIRS = [REPO / "packages", REPO / "scripts", REPO / "apps" / "api"]
MANIFEST = REPO / "data" / "graph_scale" / "LANES.json"

# data roots whose first-level entries are considered "assets" for check B
ASSET_ROOTS = [REPO / "data" / "graph_scale", REPO / "data" / "atanor_index"]
# names that are legitimately unreferenced (backups are parked by convention, caches rebuilt)
_SKIP_ASSET = re.compile(r"\.bak\b|_bak\b|backup|legacy|^__|\.tmp$", re.IGNORECASE)


def _py_files() -> list[Path]:
    out = []
    for root in CODE_DIRS:
        if root.exists():
            out.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    return out


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def check_manifest(files: dict[Path, str]) -> list[str]:
    """A: code defaults pointing at lanes the manifest says are PARKED."""
    issues: list[str] = []
    if not MANIFEST.exists():
        return ["LANES.json missing — manifest check skipped (create it to enable)"]
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    parked = {p["name"]: p.get("reason", "") for p in man.get("parked", [])}
    canonical = {r: c["name"] for r, c in man.get("canonical", {}).items()}
    for path, src in files.items():
        if "test" in path.parts or path.name.startswith("test_"):
            continue
        for name, reason in parked.items():
            # a parked lane referenced outside a comment is a stale default candidate
            for m in re.finditer(re.escape(name), src):
                line_start = src.rfind("\n", 0, m.start()) + 1
                line = src[line_start:src.find("\n", m.start())]
                stripped = line.strip()
                if stripped.startswith("#") or name + "_" in line:   # comment / longer name
                    continue
                issues.append(f"PARKED lane '{name}' referenced by {path.relative_to(REPO)}: "
                              f"{stripped[:90]}  (parked: {reason})")
                break                                                # one report per file per lane
    if not canonical:
        issues.append("manifest has no canonical roles declared")
    return issues


def check_unwired_assets(files: dict[Path, str]) -> list[str]:
    """B: on-disk assets no non-test code mentions at all."""
    blob = "\n".join(src for p, src in files.items()
                     if "test" not in p.parts and not p.name.startswith("test_"))
    out = []
    for root in ASSET_ROOTS:
        if not root.exists():
            continue
        for child in sorted(root.iterdir()):
            name = child.name
            if _SKIP_ASSET.search(name) or name.startswith("."):
                continue
            if name not in blob:
                size_mb = 0.0
                try:
                    size_mb = sum(f.stat().st_size for f in child.rglob("*") if f.is_file()) / 1e6 \
                        if child.is_dir() else child.stat().st_size / 1e6
                except Exception:
                    pass
                out.append(f"UNWIRED asset {child.relative_to(REPO)}  (~{size_mb:.0f} MB, "
                           f"zero code references)")
    return out


_FLAG = re.compile(r"""environ(?:\.get)?\(\s*['"]([A-Z][A-Z0-9_]+)['"]""")


def check_flags(files: dict[Path, str]) -> list[str]:
    """C: env flags in code, and whether any test file exercises each."""
    in_code: dict[str, set[str]] = {}
    test_blob = "\n".join(src for p, src in files.items()
                          if "test" in p.parts or p.name.startswith("test_"))
    for p, src in files.items():
        if "test" in p.parts or p.name.startswith("test_"):
            continue
        for m in _FLAG.finditer(src):
            in_code.setdefault(m.group(1), set()).add(str(p.relative_to(REPO)))
    out = []
    for flag in sorted(in_code):
        if flag in ("PATH", "HOME", "USERPROFILE", "TEMP", "TMP"):
            continue
        tested = flag in test_blob
        if not tested:
            where = sorted(in_code[flag])[0]
            out.append(f"UNTESTED flag {flag}  (used in {where}"
                       + (f" +{len(in_code[flag]) - 1} more" if len(in_code[flag]) > 1 else "") + ")")
    return out


def check_dead_params(files: dict[Path, str]) -> list[str]:
    """D: declared parameters never read in the body (min_overlap class). Heuristic."""
    out = []
    for p, src in files.items():
        if "test" in p.parts or p.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # protocol/override methods legitimately ignore params (__exit__(exc_type, exc, tb),
            # HTMLParser.handle_starttag(attrs)…) — flagging them is pure noise
            if node.name.startswith("__") or node.name.startswith("handle_"):
                continue
            args = [a.arg for a in list(node.args.args) + list(node.args.kwonlyargs)
                    if a.arg not in ("self", "cls") and not a.arg.startswith("_")]
            if not args:
                continue
            used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            for a in args:
                if a not in used:
                    out.append(f"DEAD param '{a}' in {p.relative_to(REPO)}:"
                               f"{node.lineno} {node.name}()")
    return out


_HASH = re.compile(r"(?:sha256|sha1|md5)\(\s*(?:str\()?\s*([A-Za-z_][A-Za-z0-9_.]*)\s*[).]")


def check_seed_hygiene(files: dict[Path, str]) -> list[str]:
    """E: hashing a bare variable (no literal salt in the expression) — coupling risk."""
    out = []
    for p, src in files.items():
        if "test" in p.parts or p.name.startswith("test_"):
            continue
        for i, line in enumerate(src.splitlines(), 1):
            if "sha256(" not in line and "md5(" not in line and "sha1(" not in line:
                continue
            if '"' in line.split("sha256(")[-1][:40] or "'" in line.split("sha256(")[-1][:40]:
                continue                                   # a literal (salt) participates — fine
            m = _HASH.search(line)
            if m:
                out.append(f"UNSALTED hash of '{m.group(1)}' at {p.relative_to(REPO)}:{i} — "
                           f"if any harness seeds by the same value, pick and answer couple (E3 class)")
    return out


def main() -> int:
    files = {p: _read(p) for p in _py_files()}
    report = {
        "A_parked_lane_refs": check_manifest(files),
        "B_unwired_assets": check_unwired_assets(files),
        "C_untested_flags": check_flags(files),
        "D_dead_params": check_dead_params(files),
        "E_unsalted_hashes": check_seed_hygiene(files),
    }
    if "--json" in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    total = sum(len(v) for v in report.values())
    print(f"wiring audit — {len(files)} files scanned, {total} findings\n")
    for section, items in report.items():
        print(f"[{section}] {len(items)}")
        for it in items[:25]:
            print(f"  - {it}")
        if len(items) > 25:
            print(f"  ... +{len(items) - 25} more (use --json)")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
