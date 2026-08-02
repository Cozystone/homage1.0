# -*- coding: utf-8 -*-
"""Repo reader for SWE-bench — the (a) COMPREHENSION stage, honestly scoped.

Our existing code organ ``code_reason.code_situation`` reads exactly ONE function via the AST. There
is no whole-repo model in ATANOR. So this reader does the minimum a repo-scale task needs and no
more, and it is explicit about the gap:

  * ``ensure_clone`` makes a BLOBLESS partial clone (``--filter=blob:none``) of the GitHub repo once,
    so we get every commit+tree cheaply but download a file's bytes only when actually read. That
    lets us check out any ``base_commit`` and read a handful of candidate files without pulling the
    whole working tree — honest about disk, and time-boxed.
  * ``list_py_files`` / ``read_file`` expose the tree and file bytes at a commit.
  * ``read_functions`` lifts ``code_situation.build`` over a file: a list of per-function
    CodeSituation summaries. This is the ONLY structural understanding we have, and it is
    single-function granularity — the reader cannot model cross-file call graphs or module state.

Nothing here fabricates. A clone timeout or a missing file is reported as such; it never guesses.
"""
from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path

from packages.code_reason import code_situation as cs

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "data" / "swe_eval" / "repo_cache"


@dataclass
class CloneResult:
    repo: str
    ok: bool
    path: str
    detail: str


def _run(args: list[str], cwd: Path | None = None, timeout_s: int = 240) -> tuple[int, str, str]:
    p = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                       timeout=timeout_s, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout or "", p.stderr or ""


def ensure_clone(repo: str, timeout_s: int = 300) -> CloneResult:
    """Blobless partial clone of github.com/<repo>, reused if already present. Time-boxed."""
    dest = CACHE / repo.replace("/", "__")
    if (dest / ".git").is_dir():
        return CloneResult(repo, True, str(dest), "cached")
    CACHE.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{repo}.git"
    try:
        rc, _, err = _run(["git", "clone", "--filter=blob:none", "--no-checkout", url, str(dest)],
                          timeout_s=timeout_s)
    except subprocess.TimeoutExpired:
        return CloneResult(repo, False, str(dest), f"clone-timeout>{timeout_s}s")
    if rc != 0:
        return CloneResult(repo, False, str(dest), f"clone-failed: {err.strip()[:200]}")
    return CloneResult(repo, True, str(dest), "cloned")


def list_py_files(repo_dir: str, base_commit: str, timeout_s: int = 120) -> list[str]:
    """Every .py path in the tree at base_commit (no blob download — trees only)."""
    try:
        rc, out, _ = _run(["git", "ls-tree", "-r", "--name-only", base_commit],
                          cwd=Path(repo_dir), timeout_s=timeout_s)
    except subprocess.TimeoutExpired:
        return []
    if rc != 0:
        return []
    return [ln for ln in out.splitlines() if ln.endswith(".py")]


def read_file(repo_dir: str, base_commit: str, path: str, timeout_s: int = 60) -> str | None:
    """Bytes of one file at base_commit (lazily fetches just this blob). None if unavailable."""
    try:
        rc, out, _ = _run(["git", "show", f"{base_commit}:{path}"],
                          cwd=Path(repo_dir), timeout_s=timeout_s)
    except subprocess.TimeoutExpired:
        return None
    return out if rc == 0 else None


def read_functions(source: str) -> list[cs.CodeSituation]:
    """Lift code_situation.build over every top-level+nested function in a file. This is the only
    structural comprehension organ we have, and it is per-function — no cross-file model."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out: list[cs.CodeSituation] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                sit = cs.build(ast.unparse(node))
            except Exception:
                sit = None
            if sit is not None:
                out.append(sit)
    return out
