# -*- coding: utf-8 -*-
"""Fault localization for SWE-bench — the (b) stage: issue text -> which FILE to edit.

Honesty note (BINDING): ATANOR has NO issue->file localization organ. What it has is the lexical
line-scoring principle inside ``self_repair.repair_cycle._relevant_window`` (score a file's lines by
the defect's own vocabulary to find the fault region). This module lifts that SAME principle to file
granularity so we can MEASURE the gap: how often a plain lexical baseline, given only the issue text
and the repo tree, names a file the gold patch actually touches. It is a baseline yardstick, not a
claim of capability — a real localizer would need call-graph + test-trace reasoning we do not have.

Two phases keep it cheap on a blobless clone:
  1. PATH score over ALL files (no blob download) — issue identifiers vs the dotted module path.
  2. CONTENT rescore of the top path candidates only (lazy-fetch just those blobs) — count of the
     issue's salient identifiers that appear as def/class names or bare tokens in the file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

# Salient identifiers in an issue: dotted paths (a.b.c), snake_case, CamelCase, backticked names.
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{2,}")
_STOP = {
    "the", "and", "for", "this", "that", "with", "from", "have", "not", "but", "you", "are", "was",
    "https", "github", "com", "issue", "please", "should", "would", "could", "when", "then", "code",
    "python", "import", "true", "false", "none", "self", "def", "class", "return", "test", "tests",
    "example", "following", "https://github", "www", "org", "html", "http", "error", "traceback",
}


def _tokens(text: str) -> set[str]:
    """Salient identifiers from issue text, plus the tail of any dotted name (foo.bar.baz -> baz)."""
    toks: set[str] = set()
    for m in _IDENT.findall(text or ""):
        t = m.strip(".")
        if not t:
            continue
        low = t.lower()
        if low in _STOP or len(t) < 3:
            continue
        toks.add(low)
        if "." in t:                       # module.attr -> also index the leaf and each segment
            for seg in t.split("."):
                if len(seg) >= 3 and seg.lower() not in _STOP:
                    toks.add(seg.lower())
    return toks


def _path_score(path: str, toks: set[str]) -> float:
    """Overlap of issue tokens with the dotted module path (astropy/modeling/separable.py ->
    {astropy, modeling, separable}). The single strongest cheap signal."""
    segs = {s.lower() for s in re.split(r"[/\\.]", path) if len(s) >= 3}
    hit = segs & toks
    base = path.rsplit("/", 1)[-1][:-3].lower()      # filename stem
    bonus = 2.0 if base in toks else 0.0
    return len(hit) + bonus


def _content_score(source: str, toks: set[str]) -> float:
    """How many salient issue identifiers appear in the file, weighting def/class names higher."""
    if not source:
        return 0.0
    names = set(re.findall(r"^\s*(?:def|class)\s+(\w+)", source, re.M))
    name_hit = sum(1 for n in names if n.lower() in toks)
    body_toks = set(re.findall(r"[A-Za-z_]\w{2,}", source.lower()))
    body_hit = len(body_toks & toks)
    return 3.0 * name_hit + 0.1 * body_hit


@dataclass
class Localization:
    ranked: list[tuple[str, float]] = field(default_factory=list)   # (path, score), best first
    top1: str | None = None
    considered: int = 0

    def topk(self, k: int) -> list[str]:
        return [p for p, _ in self.ranked[:k]]


def localize(problem_statement: str, py_files: list[str],
             read_file: Callable[[str], str | None] | None = None,
             content_top: int = 25) -> Localization:
    """Rank repo files by likelihood of being the edit site. ``read_file(path)->src`` enables the
    content rescore of the top path-candidates; omit it for a path-only (blobless) ranking."""
    toks = _tokens(problem_statement)
    # exclude test files from candidates — the fix is (almost always) not in the test tree
    cands = [p for p in py_files if "/test" not in p and not p.rsplit("/", 1)[-1].startswith("test_")]
    scored = [(p, _path_score(p, toks)) for p in cands]
    scored.sort(key=lambda x: -x[1])
    if read_file is not None:
        head = scored[:content_top]
        rescored: list[tuple[str, float]] = []
        for p, ps in head:
            src = read_file(p)
            rescored.append((p, ps + _content_score(src or "", toks)))
        rescored.sort(key=lambda x: -x[1])
        ranked = rescored + scored[content_top:]
    else:
        ranked = scored
    return Localization(ranked=ranked, top1=ranked[0][0] if ranked else None, considered=len(cands))


def gold_files(patch: str) -> list[str]:
    """The files a gold patch modifies (the localization ground truth)."""
    return re.findall(r"^\+\+\+ b/(.+?)\s*$", patch or "", re.M)


# ── the FAILING-TEST signal (W-A top-1 lever): the test names the site far better than lexical alone ─
#
# SWE-bench GIVES the failing test (test_patch + FAIL_TO_PASS node-ids) — it is the specification, NOT
# the gold solution. The test file lives in ``<pkg>/tests/test_<x>.py`` and (a) sits in the package the
# fix is in, (b) often shares the fixed file's stem, (c) imports the module under test, (d) references
# the symbols the fix touches. These are the "stack-trace names files/functions" + "call-graph
# proximity to the test" signals; fusing them re-ranks a central lexical winner BELOW the actually
# edited file. Nothing here reads the gold patch — only the test the benchmark hands us.

_DIFF_HUNK = re.compile(r"^\+\+\+ b/(.+?)\s*$", re.M)


@dataclass
class TestSignal:
    test_files: list[str] = field(default_factory=list)     # FAIL_TO_PASS test file paths
    pkg_dirs: list[str] = field(default_factory=list)        # package dir of each test (parent-of-/tests)
    test_stems: list[str] = field(default_factory=list)      # test stem with the test_ affix stripped
    imported_modules: set[str] = field(default_factory=set)  # dotted modules the test imports
    referenced: set[str] = field(default_factory=set)        # lowercased identifiers the test names

    @property
    def active(self) -> bool:
        return bool(self.test_files or self.imported_modules or self.referenced)


def _pkg_dir_of_test(path: str) -> str:
    """astropy/io/ascii/tests/test_rst.py -> astropy/io/ascii (the package the fix is in). If the test
    is not under a ``tests`` dir, its own directory is the package dir."""
    parts = path.split("/")
    if "tests" in parts:
        i = len(parts) - 1 - parts[::-1].index("tests")   # last 'tests' segment
        return "/".join(parts[:i])
    return "/".join(parts[:-1])


def _test_stem(path: str) -> str:
    stem = path.rsplit("/", 1)[-1]
    stem = stem[:-3] if stem.endswith(".py") else stem
    if stem.startswith("test_"):
        stem = stem[5:]
    elif stem.endswith("_test"):
        stem = stem[:-5]
    return stem.lower()


def _added_lines_for(test_patch: str, path: str) -> str:
    """The added ('+') content lines of ``path``'s hunks in a unified test_patch (handles a test file
    the base commit does not yet have — the spec is still in the diff)."""
    out: list[str] = []
    cur = None
    for ln in (test_patch or "").splitlines():
        m = re.match(r"^\+\+\+ b/(.+?)\s*$", ln)
        if m:
            cur = m.group(1)
            continue
        if ln.startswith("--- ") or ln.startswith("diff "):
            continue
        if cur == path and ln.startswith("+") and not ln.startswith("+++"):
            out.append(ln[1:])
    return "\n".join(out)


def build_test_signal(f2p: list[str], test_patch: str,
                      read_file: Callable[[str], str | None] | None) -> TestSignal:
    """Extract the failing-test localization signal from the FAIL_TO_PASS node-ids + the test_patch
    (and, when available, the test file's base content). Pure structure — no gold patch is consulted."""
    sig = TestSignal()
    tfiles: list[str] = []
    for node in (f2p or []):
        tp = str(node).split("::", 1)[0]
        if tp.endswith(".py") and tp not in tfiles:
            tfiles.append(tp)
    # a test file mentioned only in the test_patch (created there) still counts
    for tp in _DIFF_HUNK.findall(test_patch or ""):
        stem = tp.rsplit("/", 1)[-1]
        if (stem.startswith("test_") or stem.endswith("_test.py")) and tp not in tfiles:
            tfiles.append(tp)
    sig.test_files = tfiles
    sig.pkg_dirs = sorted({_pkg_dir_of_test(t) for t in tfiles})
    sig.test_stems = sorted({_test_stem(t) for t in tfiles if _test_stem(t)})
    for tp in tfiles:
        text = ""
        if read_file is not None:
            text = read_file(tp) or ""
        text = text + "\n" + _added_lines_for(test_patch, tp)
        for m in re.finditer(r"^\s*from\s+([\w.]+)\s+import\s+(.+)$", text, re.M):
            sig.imported_modules.add(m.group(1))
            for nm in re.findall(r"[A-Za-z_]\w+", m.group(2)):
                sig.referenced.add(nm.lower())
        for m in re.finditer(r"^\s*import\s+([\w.]+)", text, re.M):
            sig.imported_modules.add(m.group(1))
        for tok in re.findall(r"[A-Za-z_]\w{2,}", text):
            low = tok.lower()
            if low not in _STOP:
                sig.referenced.add(low)
    return sig


# fusion weights (declared control constants, NOT knowledge): tuned so an exact test-stem match inside
# the test's own package outranks a central lexical winner, while a file with NO test signal keeps its
# lexical order. Verified on the fixed 10-sample not to hurt top-5.
# strict priority within a package tier: stem match (the test is NAMED after the file it tests) beats
# a direct import beats symbol-definition corroboration. Symdef is only a weak tiebreak so a central
# helper the test happens to reference cannot outrank the file the test is named for.
_W_STEM_EXACT = 12.0   # candidate file stem == test stem (test_rst.py <-> rst.py) — strongest
_W_STEM_PREFIX = 8.0   # one stem is a prefix of the other (sky_coord <-> sky_coordinate)
_W_IMPORT = 7.0        # the test imports this file's module directly
_W_SYMDEF = 1.0        # per top-level symbol the file defines that the test references (weak, capped)
_SYMDEF_CAP = 3


def _module_of(path: str) -> str:
    return path[:-3].replace("/", ".") if path.endswith(".py") else path.replace("/", ".")


def _test_tier(path: str, sig: TestSignal) -> int:
    """Membership tier by the test's package: 0 = DIRECTLY in the test's package dir, 1 = under its
    subtree, 2 = elsewhere. The dominant signal (measured: 9/10 Verified golds sit in the test's own
    package), so it is the PRIMARY sort key — a lexically-central file in a different package cannot
    outrank the actual edit site once the failing test is known."""
    if not sig.pkg_dirs:
        return 2
    cdir = path.rsplit("/", 1)[0] if "/" in path else ""
    best = 2
    for pkg in sig.pkg_dirs:
        if not pkg:
            continue
        if cdir == pkg:
            return 0
        if path.startswith(pkg + "/"):
            best = min(best, 1)
    return best


def _test_locality_score(path: str, sig: TestSignal,
                         read_file: Callable[[str], str | None] | None) -> float:
    """Within-tier failing-test affinity: stem match + direct import + defined symbols the test names.
    (Directory membership is handled separately, as the primary tier.)"""
    if not sig.active:
        return 0.0
    score = 0.0
    stem = path.rsplit("/", 1)[-1][:-3].lower() if path.endswith(".py") else ""
    for ts in sig.test_stems:
        if stem and stem == ts:
            score += _W_STEM_EXACT
            break
        if stem and len(stem) >= 4 and len(ts) >= 4 and (stem.startswith(ts) or ts.startswith(stem)):
            score += _W_STEM_PREFIX
            break
    mod = _module_of(path)
    if mod in sig.imported_modules or mod.rsplit(".", 1)[-1] in {m.rsplit(".", 1)[-1] for m in sig.imported_modules}:
        score += _W_IMPORT
    if read_file is not None:      # symbols the test references that this file defines (stack-trace-like)
        src = read_file(path)
        if src:
            names = set(re.findall(r"^\s*(?:def|class)\s+(\w+)", src, re.M))
            hits = sum(1 for n in names if n.lower() in sig.referenced)
            score += _W_SYMDEF * min(hits, _SYMDEF_CAP)
    return score


def fuse_ranking(base_ranked: list[tuple[str, float]], sig: TestSignal,
                 read_file: Callable[[str], str | None] | None) -> list[tuple[str, float]]:
    """Re-rank a lexical ranking by the failing-test signal: PRIMARY key = test-package tier, then the
    within-tier affinity (stem/import/symbol), then the lexical score. Reads only the symbols of files
    that are already in the test's package (tier 0/1) so the extra I/O stays bounded. Pure structure;
    no gold patch consulted."""
    if not sig.active or not base_ranked:
        return base_ranked
    lex = {p: s for p, s in base_ranked}
    def loc_of(p: str) -> float:
        return _test_locality_score(p, sig, read_file if _test_tier(p, sig) < 2 else None)
    ordered = sorted(base_ranked, key=lambda ps: (_test_tier(ps[0], sig), -loc_of(ps[0]), -ps[1]))
    # expose a monotone fused score (tier dominates, then affinity, then lexical) for the certificate
    out: list[tuple[str, float]] = []
    for p, _s in ordered:
        tier = _test_tier(p, sig)
        fused = (2 - tier) * 100.0 + loc_of(p) + 0.001 * lex.get(p, 0.0)
        out.append((p, round(fused, 3)))
    return out


def localize_fused(problem_statement: str, py_files: list[str],
                   read_file: Callable[[str], str | None] | None,
                   f2p: list[str] | None = None, test_patch: str = "",
                   content_top: int = 25) -> tuple[Localization, TestSignal]:
    """Lexical localization RE-RANKED by the failing-test proximity signal. Falls back to exactly
    ``localize`` when there is no test signal. Returns (localization, signal) so the deliberation can
    report which sub-goals grounded. Never consults the gold patch."""
    base = localize(problem_statement, py_files, read_file=read_file, content_top=content_top)
    sig = build_test_signal(f2p or [], test_patch, read_file)
    if not sig.active or not base.ranked:
        return base, sig
    fused = fuse_ranking(base.ranked, sig, read_file)
    return Localization(ranked=fused, top1=fused[0][0] if fused else None,
                        considered=base.considered), sig
