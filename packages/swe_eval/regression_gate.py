# -*- coding: utf-8 -*-
"""Regression gate — the VERIFY stage, isomorphic to ``situation_model.physics_truth``.

physics_truth screens a world observation against domain-blind physical invariants and returns
ACCEPTED / QUARANTINED / UNDECIDED — ATANOR may learn only from the accepted, quarantines the
twin-bugs, and abstains when it cannot judge. This gate is the SAME shape for a candidate patch: the
repo's own tests are the invariant. A candidate is

  * ACCEPTED   — it applies, every FAIL_TO_PASS goes green AND every PASS_TO_PASS stays green. Only
                 this may be SHIPPED (the fail-0 floor: nothing unverified is ever emitted).
  * QUARANTINED — it applies but a FAIL_TO_PASS is still red, or it broke a PASS_TO_PASS (a
                 regression). A twin-bug: never shipped.
  * UNDECIDED   — the gate could not be RUN here (no eval environment / the diff does not apply). We
                 abstain rather than guess green, exactly like physics_truth on missing conditions.

Two backends, and the verdict ALWAYS records which one ran (honest about the Windows/CRLF limit the
prior run found):
  * ``docker``  — drive pytest DIRECTLY inside the prebuilt swebench instance image (repo at
                  /testbed, conda env ``testbed``). We reset to base_commit, apply the dataset's
                  test_patch, apply the candidate, and run FAIL_TO_PASS + PASS_TO_PASS ourselves,
                  transferring every patch with LF newlines via ``docker cp``. This SIDESTEPS the
                  swebench harness's CRLF bug (which emits CRLF container scripts on a Windows host) by
                  never using that harness — we issue the container commands ourselves.
  * ``native``  — a local clone + pytest, for a self-contained pure-Python instance whose deps import
                  on the host (used to prove the gate end-to-end without Docker). Heavy compiled repos
                  (astropy C extensions) are out of native scope -> UNDECIDED with that reason.

The gate DECIDES nothing about correctness beyond the tests; the tests are the oracle. It never edits
a reused organ and never fabricates a pass.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ACCEPTED = "accepted"
QUARANTINED = "quarantined"
UNDECIDED = "undecided"

REPO = Path(__file__).resolve().parents[2]


@dataclass
class RegressionVerdict:
    status: str                       # ACCEPTED | QUARANTINED | UNDECIDED
    law: str                          # the invariant applied (regression-green / -red / -broke-p2p / ...)
    reason: str
    backend: str = ""                 # which eval path ran (docker | native | none)
    f2p_pass: int = 0
    f2p_total: int = 0
    p2p_pass: int = 0
    p2p_total: int = 0
    failed: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        """The mirror of physics_truth.Verdict.learnable: only an ACCEPTED patch may be shipped."""
        return self.status == ACCEPTED


def _as_list(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        try:
            j = json.loads(v)
            return [str(x) for x in j] if isinstance(j, list) else [v]
        except Exception:
            return [v]
    return []


def image_for(instance_id: str) -> str:
    """The prebuilt swebench instance image name (Verified namespace). ``a__b`` -> ``a_1776_b``."""
    norm = instance_id.replace("__", "_1776_").lower()
    return f"swebench/sweb.eval.x86_64.{norm}:latest"


# ── docker backend (drive pytest in the instance image ourselves, LF-controlled) ──────────────────

def _docker_available() -> bool:
    try:
        p = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                           capture_output=True, text=True, timeout=30)
        return p.returncode == 0
    except Exception:
        return False


def _image_present(image: str) -> bool:
    try:
        p = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True,
                           timeout=30)
        return p.returncode == 0
    except Exception:
        return False


def start_container(instance_id: str, timeout_s: int = 60) -> str | None:
    """Run the instance image detached (sleep infinity) and return its container id, or None."""
    image = image_for(instance_id)
    if not (_docker_available() and _image_present(image)):
        return None
    try:
        p = subprocess.run(["docker", "run", "-d", image, "sleep", "infinity"],
                           capture_output=True, text=True, timeout=timeout_s)
        return p.stdout.strip() if p.returncode == 0 else None
    except Exception:
        return None


def stop_container(cid: str) -> None:
    for args in (["docker", "rm", "-f", cid],):
        try:
            subprocess.run(args, capture_output=True, text=True, timeout=60)
        except Exception:
            pass


def _cp_text(cid: str, text: str, dest: str) -> None:
    """Copy text into the container with LF newlines (the whole point: no CRLF ever reaches bash)."""
    h = Path(tempfile.gettempdir()) / f"atanor_swe_{os.getpid()}_{abs(hash(dest)) % 10**8}"
    h.write_text(text, encoding="utf-8", newline="\n")
    try:
        subprocess.run(["docker", "cp", str(h), f"{cid}:{dest}"], capture_output=True, text=True,
                       timeout=60)
    finally:
        try:
            h.unlink()
        except OSError:
            pass


def _dexec(cid: str, cmd: str, timeout_s: int = 900) -> tuple[int, str, str]:
    try:
        p = subprocess.run(["docker", "exec", cid, "bash", "-lc", cmd], capture_output=True,
                           text=True, timeout=timeout_s, encoding="utf-8", errors="replace")
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


_RESULT_RE = re.compile(r"^(PASSED|FAILED|ERROR)\s+(\S+)", re.M)


def _run_tests(cid: str, nodes: list[str], repo_dir: str = "/testbed",
               timeout_s: int = 900) -> dict[str, str]:
    """Run the given pytest node-ids and return {nodeid: PASSED|FAILED|ERROR}. Chunked so a large
    PASS_TO_PASS list never overflows the command line."""
    results: dict[str, str] = {}
    CHUNK = 80
    for i in range(0, len(nodes), CHUNK):
        chunk = nodes[i:i + CHUNK]
        listfile = f"/tmp/atanor_nodes_{i}.txt"
        _cp_text(cid, "\n".join(chunk) + "\n", listfile)
        cmd = (f"cd {repo_dir} && python -m pytest $(cat {listfile}) -rA --tb=no -q "
               f"--no-header -p no:cacheprovider 2>&1")
        _, out, _ = _dexec(cid, cmd, timeout_s=timeout_s)
        for m in _RESULT_RE.finditer(out):
            status, nid = m.group(1), m.group(2)
            # keep the WORST status seen for a node (ERROR/FAILED beat PASSED)
            prev = results.get(nid)
            if prev in ("FAILED", "ERROR"):
                continue
            results[nid] = status
        # any requested node with no line at all -> treat as ERROR (collection failure)
        for nid in chunk:
            results.setdefault(nid, "ERROR")
    return results


def _match(nodes: list[str], results: dict[str, str]) -> tuple[int, list[str]]:
    """Count how many requested nodes PASSED; return (n_pass, failed_nodes). Matches by exact id or
    by suffix (pytest sometimes prints a normalized id)."""
    npass = 0
    failed: list[str] = []
    keys = list(results.keys())
    for n in nodes:
        st = results.get(n)
        if st is None:
            st = next((results[k] for k in keys if k.endswith(n) or n.endswith(k)), "ERROR")
        if st == "PASSED":
            npass += 1
        else:
            failed.append(n)
    return npass, failed


def verify_docker(instance: dict[str, Any], diff: str, cid: str | None = None,
                  timeout_s: int = 900) -> RegressionVerdict:
    """Verify one candidate diff by driving pytest inside the instance image. Reuses ``cid`` if given
    (amortizes startup across a candidate sweep); otherwise starts and stops its own container."""
    iid = instance["instance_id"]
    base = instance["base_commit"]
    test_patch = instance.get("test_patch", "")
    f2p = _as_list(instance.get("FAIL_TO_PASS"))
    p2p = _as_list(instance.get("PASS_TO_PASS"))

    own = cid is None
    if own:
        cid = start_container(iid)
    if not cid:
        return RegressionVerdict(UNDECIDED, "insufficient-eval-environment",
                                 f"no runnable swebench image for {iid} (docker down or image absent)",
                                 backend="none")
    try:
        # reset to a clean base, apply the dataset test_patch (exposes the FAIL_TO_PASS tests)
        _dexec(cid, f"cd /testbed && git reset --hard {base} -q && git clean -fdq")
        if test_patch.strip():
            _cp_text(cid, test_patch, "/tmp/atanor_test.patch")
            rc, out, err = _dexec(cid, "cd /testbed && git apply -v /tmp/atanor_test.patch 2>&1")
            if rc != 0 and "cleanly" not in out:
                return RegressionVerdict(UNDECIDED, "insufficient-eval-environment",
                                         f"test_patch did not apply: {out.strip()[-160:]}",
                                         backend="docker")
        # apply the CANDIDATE
        _cp_text(cid, diff, "/tmp/atanor_cand.patch")
        rc, out, err = _dexec(cid, "cd /testbed && git apply /tmp/atanor_cand.patch 2>&1")
        if rc != 0:
            return RegressionVerdict(UNDECIDED, "diff-does-not-apply",
                                     f"candidate diff did not apply at {base[:8]}: {out.strip()[-160:]}",
                                     backend="docker", detail={"apply_error": out.strip()[-300:]})
        # FAIL_TO_PASS FIRST as a cheap filter: the vast majority of candidates never fix the target
        # bug, so gate on the (small) F2P set before paying for the (large) PASS_TO_PASS regression run.
        res = _run_tests(cid, f2p, timeout_s=timeout_s)
        f2p_pass, f2p_failed = _match(f2p, res)
        if f2p_pass < len(f2p):
            return RegressionVerdict(QUARANTINED, "fail-to-pass-still-red",
                                     f"{f2p_pass}/{len(f2p)} FAIL_TO_PASS green — the target bug is not fixed",
                                     backend="docker", f2p_pass=f2p_pass, f2p_total=len(f2p),
                                     p2p_total=len(p2p), failed=f2p_failed)
        # F2P is green -> now run the full PASS_TO_PASS regression set
        p2p_res = _run_tests(cid, p2p, timeout_s=timeout_s)
        p2p_pass, p2p_failed = _match(p2p, p2p_res)
        v = RegressionVerdict("", "", "", backend="docker", f2p_pass=f2p_pass, f2p_total=len(f2p),
                              p2p_pass=p2p_pass, p2p_total=len(p2p), failed=f2p_failed + p2p_failed)
        if f2p_pass == len(f2p) and p2p_pass == len(p2p):
            v.status, v.law = ACCEPTED, "regression-green"
            v.reason = (f"all {len(f2p)} FAIL_TO_PASS now pass and all {len(p2p)} PASS_TO_PASS hold "
                        f"— the repo's own tests certify the fix")
        elif f2p_pass < len(f2p):
            v.status, v.law = QUARANTINED, "fail-to-pass-still-red"
            v.reason = f"{f2p_pass}/{len(f2p)} FAIL_TO_PASS green — the target bug is not fixed"
        else:
            v.status, v.law = QUARANTINED, "regression-broke-pass-to-pass"
            v.reason = f"FAIL_TO_PASS fixed but {len(p2p) - p2p_pass} PASS_TO_PASS regressed"
        return v
    finally:
        if own:
            stop_container(cid)


# ── native backend (pure-python local clone + pytest; for the self-contained fixture proof) ───────

def verify_native(repo_dir: str, test_patch: str, diff: str, f2p: list[str], p2p: list[str],
                  base_commit: str | None = None, timeout_s: int = 300) -> RegressionVerdict:
    """Run FAIL_TO_PASS + PASS_TO_PASS in a local git working tree (deps must import on the host).
    Used to prove the propose->verify->accept loop natively; SAYS backend='native'."""
    rd = Path(repo_dir)
    if not (rd / ".git").exists():
        return RegressionVerdict(UNDECIDED, "insufficient-eval-environment",
                                 f"{repo_dir} is not a git working tree", backend="native")

    def _git(args: list[str]) -> tuple[int, str]:
        p = subprocess.run(["git", "-C", str(rd)] + args, capture_output=True, text=True,
                           timeout=120, encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    def _apply(patch: str) -> tuple[int, str]:
        h = rd / ".atanor_patch"
        h.write_text(patch, encoding="utf-8", newline="\n")
        rc, out = _git(["apply", str(h)])
        try:
            h.unlink()
        except OSError:
            pass
        return rc, out

    if base_commit:
        _git(["reset", "--hard", base_commit])
        _git(["clean", "-fdq"])
    if test_patch.strip():
        rc, out = _apply(test_patch)
        if rc != 0:
            return RegressionVerdict(UNDECIDED, "insufficient-eval-environment",
                                     f"test_patch did not apply: {out[-160:]}", backend="native")
    rc, out = _apply(diff)
    if rc != 0:
        return RegressionVerdict(UNDECIDED, "diff-does-not-apply",
                                 f"candidate did not apply: {out[-160:]}", backend="native")
    try:
        proc = subprocess.run(["python", "-m", "pytest", *f2p, *p2p, "-rA", "--tb=no", "-q",
                               "--no-header", "-p", "no:cacheprovider"],
                              cwd=str(rd), capture_output=True, text=True, timeout=timeout_s,
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return RegressionVerdict(UNDECIDED, "insufficient-eval-environment", "pytest timed out",
                                 backend="native")
    finally:
        if base_commit:
            _git(["reset", "--hard", base_commit])
            _git(["clean", "-fdq"])
    res = {m.group(2): m.group(1) for m in _RESULT_RE.finditer(proc.stdout or "")}
    f2p_pass, f2p_failed = _match(f2p, res)
    p2p_pass, p2p_failed = _match(p2p, res)
    v = RegressionVerdict("", "", "", backend="native", f2p_pass=f2p_pass, f2p_total=len(f2p),
                          p2p_pass=p2p_pass, p2p_total=len(p2p), failed=f2p_failed + p2p_failed)
    if f2p_pass == len(f2p) and p2p_pass == len(p2p):
        v.status, v.law = ACCEPTED, "regression-green"
        v.reason = f"all {len(f2p)} FAIL_TO_PASS pass and all {len(p2p)} PASS_TO_PASS hold (native)"
    elif f2p_pass < len(f2p):
        v.status, v.law = QUARANTINED, "fail-to-pass-still-red"
        v.reason = f"{f2p_pass}/{len(f2p)} FAIL_TO_PASS green"
    else:
        v.status, v.law = QUARANTINED, "regression-broke-pass-to-pass"
        v.reason = f"{len(p2p) - p2p_pass} PASS_TO_PASS regressed"
    return v
