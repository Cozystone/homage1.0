# -*- coding: utf-8 -*-
"""The FUSED repo-engineering pipeline for ONE instance — localize, propose, VERIFY, ship-only-green.

This is the wave's payload: not a new standalone tool but a wiring in which proven organs co-operate.
Every stage CALLS an existing verified organ; the pipeline is the glue and the MEC-wrapped certificate.

  (1) LOCALIZE   -> packages.deliberator.repo_engineering.deliberate_localization
                    (a DELIBERATION: file_scan line-scorer -> import graph -> code_situation AST,
                     MEC-scheduled cheap-before-expensive, with a certificate or an honest abstain).
  (2) PROPOSE    -> two organs, both propose->verify, neither ships unverified:
                    (a) code_author / L3 predicate REFRAME: extract the target function signature via
                        code_situation and build the anchor from FAIL_TO_PASS; on a real repo function
                        this parses to 0 literal examples and code_author ABSTAINS (recorded honestly).
                    (b) edit-schema MUTATION (packages.swe_eval.edit_schemas): domain-blind structural
                        edits of the localized function(s) — the reachable path for a repo FIX.
  (3) VERIFY     -> packages.swe_eval.regression_gate (isomorphic to physics_truth): apply each
                    candidate at base_commit, run FAIL_TO_PASS + PASS_TO_PASS; ACCEPT only green.
                    fail-0: the FIRST green candidate is shipped; if none is green, ABSTAIN (patch=None).

MEC (packages.metacog.record_span) wraps the stages so the whole flow is watched like every other
deliberation. Nothing here fabricates a pass — the repo's own tests are the sole oracle.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from packages.swe_eval import edit_schemas as es
from packages.swe_eval import localizer as loc
from packages.swe_eval import regression_gate as rg
from packages.swe_eval import repo_reader as rr

try:
    from packages.metacog.probes import record_span
except Exception:                                     # pragma: no cover
    def record_span(*_a, **_k):                        # type: ignore
        return None


@dataclass
class PatchResult:
    instance_id: str
    repo: str
    base_commit: str
    reached: str = "loaded"
    stopped_at: str = ""
    # localization (measurement vs gold is reported, NEVER used to steer generation)
    localized_top_file: str | None = None
    localized_target_fn: str | None = None
    localization_top5_hit: bool = False
    localization_cert: dict[str, Any] = field(default_factory=dict)
    # propose
    from_scratch_applicable: bool = False
    from_scratch_note: str = ""
    n_candidates: int = 0
    n_verified: int = 0
    schemas_tried: dict[str, int] = field(default_factory=dict)
    # verify / ship
    verified_diff: str | None = None
    accepted_schema: str | None = None
    verdict: dict[str, Any] = field(default_factory=dict)
    backend: str = ""
    resolved: bool = False
    notes: list[str] = field(default_factory=list)


def _reframe_code_author(instance: dict[str, Any], file_src: str, fn_name: str) -> tuple[bool, str]:
    """PATCH-GEN organ (a): extract the localized function's signature (code_situation) and build the
    verification anchor from FAIL_TO_PASS, then ask code_author (via the deliberator predicate) whether
    it can FORM a from-scratch synthesis Task. On a real repo function the FAIL_TO_PASS pytest node-ids
    parse to 0 literal examples, so code_author abstains — recorded honestly (this is why the mutation
    path, not from-scratch synthesis, is the reachable one)."""
    from packages.code_reason import code_author as ca
    from packages.code_reason.authorship_harness import Task
    import ast
    sig = f"def {fn_name}():"
    try:
        tree = ast.parse(file_src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
                args = [a.arg for a in node.args.args]
                sig = f"def {fn_name}({', '.join(args)}):"
                break
    except SyntaxError:
        pass
    f2p = rg._as_list(instance.get("FAIL_TO_PASS"))
    test = "\n".join(f"# FAIL_TO_PASS: {t}" for t in f2p)
    task = Task(name=fn_name, signature=sig, docstring=instance.get("problem_statement", "")[:400],
                test=test)
    examples = ca._parse_examples(task)
    if examples:
        return True, f"code_author formed a Task with {len(examples)} literal examples"
    return False, ("code_author reframe inapplicable: FAIL_TO_PASS are pytest node-ids, not literal "
                   "asserts -> 0 examples; a repo fix is an EDIT to an existing body, not from-scratch "
                   "synthesis -> hand to the edit-schema mutation path")


# the reachable single-token/single-block fixes are cheapest and highest-yield -> tried first. This
# is a SCHEMA-major sweep: every operand-substitution across the localized files before any rarer
# family, so a repo that is a one-operand fix (astropy-12907) is reached long before the budget on the
# large top-ranked file is spent. Within a family: localization file rank, then issue-relevant funcs.
# single-token / single-block families first (cheapest, highest single-instance yield), then the
# W-A multi-token / multi-statement families — so a one-operand fix (12907) is reached long before the
# widened enumeration is paid for, and the verify budget is spent cheap-first.
_FAMILY_RANK = {"operand_substitution": 0, "block_deletion": 1, "comparison_flip": 2,
                "boolop_flip": 3, "return_toggle": 4, "unary_not_toggle": 5,
                "condition_refinement": 6, "none_guard_insertion": 7, "guarded_early_return": 8,
                "statement_wrap_guard": 9, "adjacent_stmt_swap": 10, "l3_induced": 11}


def _function_callgraph_distance(src: str, issue_toks: set[str]) -> dict[str, int]:
    """Cheap FUNCTION-level call graph: BFS distance of every function from the nearest issue-named
    function (0 = the issue names it, 1 = it is CALLED BY an issue-named function, ...). This is the
    'cheap call graph' localization signal at function scope — the real fix often lives in a helper
    (astropy-12907's `_cstack`) CALLED BY the issue-named entry point (`separability_matrix`), so
    call-graph proximity floats that helper up without any repo-specific knowledge."""
    import ast
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {}
    fns = {n.name: n for n in ast.walk(tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    callees: dict[str, set[str]] = {}
    for name, node in fns.items():
        cs: set[str] = set()
        for c in ast.walk(node):
            if isinstance(c, ast.Call):
                f = c.func
                nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
                if nm in fns:
                    cs.add(nm)
        callees[name] = cs
    dist = {name: (0 if name.lower() in issue_toks else 99) for name in fns}
    for _ in range(6):                                   # bounded BFS (shallow file, cheap)
        changed = False
        for name, cs in callees.items():
            for callee in cs:
                if dist[name] + 1 < dist.get(callee, 99):
                    dist[callee] = dist[name] + 1
                    changed = True
        if not changed:
            break
    return dist


def generate_and_verify(instance: dict[str, Any], clone_path: str, ranked_files: list[str],
                        *, container: str | None, budget: int = 1200, topk_files: int = 5,
                        max_functions_per_file: int = 200) -> PatchResult:
    """Enumerate domain-blind edit schemas over the localized functions and VERIFY each via the
    regression gate; ship the FIRST green candidate (fail-0). Uses localization's ranked files ONLY
    (no gold leakage). Reuses a single container across candidates when given one."""
    r = PatchResult(instance["instance_id"], instance["repo"], instance["base_commit"])
    base = instance["base_commit"]
    issue_toks = loc._tokens(instance.get("problem_statement", ""))

    def read(path: str) -> str | None:
        return rr.read_file(clone_path, base, path)

    # build the whole candidate list with a priority key, so MEC-style cheap-first ordering reaches a
    # single-token fix without exhausting the budget on the largest file. The key INTERLEAVES files
    # (position-within-(file,family) before file rank) so a lower-ranked gold file is not starved by a
    # huge top-ranked one, and orders functions by CALL-GRAPH proximity to the issue-named entry point.
    # Each candidate remembers its file+function for the certificate.
    scored: list[tuple[tuple[int, int, int], str, str, es.EditCandidate]] = []
    for frank, path in enumerate(ranked_files[:topk_files]):
        src = read(path)
        if not src:
            continue
        sits = rr.read_functions(src)
        if sits and not r.from_scratch_applicable:      # one honest from-scratch reframe probe per file
            named = next((s for s in sits if s.name.lower() in issue_toks), sits[0])
            app, note = _reframe_code_author(instance, src, named.name)
            r.from_scratch_applicable = r.from_scratch_applicable or app
            r.from_scratch_note = note
        cg_dist = _function_callgraph_distance(src, issue_toks)
        fns = [s.name for s in sits][:max_functions_per_file]
        # order functions by call-graph distance to an issue-named function, then source order
        _orig = {n: i for i, n in enumerate(fns)}
        fns.sort(key=lambda n: (cg_dist.get(n, 99), _orig.get(n, 0)))
        pos_in_family: dict[int, int] = {}
        for fn_name in fns:
            for c in es.propose_edits(src, fn_name):
                fam = _FAMILY_RANK.get(c.schema, 9)
                pos = pos_in_family.get(fam, 0)
                pos_in_family[fam] = pos + 1
                scored.append(((fam, pos, frank), path, fn_name, c))
    scored.sort(key=lambda x: x[0])
    r.n_candidates = len(scored)

    src_cache: dict[str, str] = {}
    verified = 0
    for _key, path, fn_name, c in scored:
        if verified >= budget:
            r.notes.append(f"verify budget {budget} exhausted before exhausting {len(scored)} candidates")
            break
        r.schemas_tried[c.schema] = r.schemas_tried.get(c.schema, 0) + 1
        osrc = src_cache.setdefault(path, read(path) or "")
        diff = es.unified_diff(osrc, c.new_source, path)
        if not diff.strip():
            continue
        t0 = time.perf_counter()
        v = rg.verify_docker(instance, diff, cid=container)
        verified += 1
        record_span("repo_pipeline.verify_candidate", (time.perf_counter() - t0) * 1000.0,
                    ok=(v.status == rg.ACCEPTED), meta={"schema": c.schema, "status": v.status})
        if v.status == rg.UNDECIDED and v.law == "insufficient-eval-environment":
            r.notes.append(f"regression gate UNDECIDED: {v.reason}")
            r.backend, r.verdict, r.n_verified = v.backend, v.__dict__, verified
            return r
        if v.resolved:
            r.verified_diff, r.accepted_schema, r.localized_target_fn = diff, c.schema, fn_name
            r.verdict, r.backend, r.resolved, r.n_verified = v.__dict__, v.backend, True, verified
            r.notes.append(f"ACCEPTED green diff via {c.schema} on {path}::{fn_name} ({c.description})")
            return r
    r.n_verified = verified
    r.notes.append("no candidate turned FAIL_TO_PASS green without regressing PASS_TO_PASS "
                   "within budget -> abstain (fail-0: no unverified diff shipped)")
    return r


# a hard cap so a 2-file pair sweep can never blow the verify budget: at most this many cheap
# single-token candidates per file -> at most MULTIFILE_PER_FILE**2 combined candidates gated.
MULTIFILE_PER_FILE = 6
_CHEAP_FAMILIES = {"operand_substitution", "comparison_flip", "boolop_flip", "return_toggle",
                   "unary_not_toggle", "block_deletion"}


def _cheap_candidates_for_file(src: str, issue_toks: set[str],
                               limit: int) -> list[tuple[str, es.EditCandidate]]:
    """The cheapest single-token/single-block candidates for a file, function-ranked by call-graph
    proximity to the issue — the bounded material for a 2-file coordinated edit."""
    sits = rr.read_functions(src)
    cg_dist = _function_callgraph_distance(src, issue_toks)
    fns = [s.name for s in sits]
    _orig = {n: i for i, n in enumerate(fns)}
    fns.sort(key=lambda n: (cg_dist.get(n, 99), _orig.get(n, 0)))
    out: list[tuple[str, es.EditCandidate]] = []
    for fn_name in fns:
        for c in es.propose_edits(src, fn_name):
            if c.schema in _CHEAP_FAMILIES:
                out.append((fn_name, c))
                if len(out) >= limit:
                    return out
    return out


def generate_multifile(instance: dict[str, Any], clone_path: str, ranked_files: list[str],
                       *, container: str | None, budget: int = 60,
                       per_file: int = MULTIFILE_PER_FILE) -> PatchResult:
    """BOUNDED 2-file coordinated edit: when no single-file candidate is green, try the cartesian
    product of the cheapest edits on the top-2 localized files, combined into ONE multi-file diff and
    gated as one. Hard-capped at ``per_file**2`` candidates; ships the first green pair, else abstains
    (fail-0). Uses localization's ranked files only (no gold leakage)."""
    r = PatchResult(instance["instance_id"], instance["repo"], instance["base_commit"])
    r.reached = "patch_generation"
    base = instance["base_commit"]
    issue_toks = loc._tokens(instance.get("problem_statement", ""))
    files = [p for p in ranked_files[:2]]
    if len(files) < 2:
        r.notes.append("multi-file: fewer than 2 localized files -> not attempted")
        return r
    srcs = {p: (rr.read_file(clone_path, base, p) or "") for p in files}
    cand_a = _cheap_candidates_for_file(srcs[files[0]], issue_toks, per_file)
    cand_b = _cheap_candidates_for_file(srcs[files[1]], issue_toks, per_file)
    r.notes.append(f"multi-file: {len(cand_a)}x{len(cand_b)} pairs over {files[0]} + {files[1]}")
    verified = 0
    for fa, ca in cand_a:
        for fb, cb in cand_b:
            if verified >= budget:
                r.notes.append(f"multi-file verify budget {budget} exhausted -> abstain")
                r.n_verified = verified
                return r
            diff = es.combine_diffs([es.unified_diff(srcs[files[0]], ca.new_source, files[0]),
                                     es.unified_diff(srcs[files[1]], cb.new_source, files[1])])
            if not diff.strip():
                continue
            t0 = time.perf_counter()
            v = rg.verify_docker(instance, diff, cid=container)
            verified += 1
            record_span("repo_pipeline.verify_multifile", (time.perf_counter() - t0) * 1000.0,
                        ok=(v.status == rg.ACCEPTED), meta={"status": v.status})
            if v.status == rg.UNDECIDED and v.law == "insufficient-eval-environment":
                r.notes.append(f"multi-file gate UNDECIDED: {v.reason}")
                r.backend, r.verdict, r.n_verified = v.backend, v.__dict__, verified
                return r
            if v.resolved:
                r.verified_diff, r.accepted_schema = diff, f"multifile[{ca.schema}+{cb.schema}]"
                r.verdict, r.backend, r.resolved, r.n_verified = v.__dict__, v.backend, True, verified
                r.notes.append(f"ACCEPTED 2-file diff: {files[0]}::{fa} ({ca.schema}) + "
                               f"{files[1]}::{fb} ({cb.schema})")
                return r
    r.n_verified = verified
    r.notes.append("multi-file: no green 2-file pair within budget -> abstain (fail-0)")
    return r


def run_instance_patch(instance: dict[str, Any], *, clone_timeout_s: int = 300,
                       budget: int = 120, topk_files: int = 5,
                       manage_container: bool = True, allow_multifile: bool = False) -> PatchResult:
    """The whole fused flow for one instance: localize (deliberation) -> propose -> verify -> ship green.
    ``allow_multifile`` opt-in adds a bounded 2-file fallback when no single-file candidate is green."""
    from packages.deliberator import repo_engineering as re_delib
    t_all = time.perf_counter()
    r = PatchResult(instance["instance_id"], instance["repo"], instance["base_commit"])

    clone = rr.ensure_clone(instance["repo"], timeout_s=clone_timeout_s)
    if not clone.ok:
        r.stopped_at = "comprehension"
        r.notes.append(f"clone: {clone.detail}")
        return r
    py_files = rr.list_py_files(clone.path, instance["base_commit"])
    if not py_files:
        r.stopped_at = "comprehension"
        r.notes.append("could not list files at base_commit")
        return r
    r.reached = "comprehension"

    # (1) LOCALIZE as a deliberation ------------------------------------------------------------
    # The failing test (FAIL_TO_PASS node-ids + test_patch) is the SPECIFICATION SWE-bench gives us —
    # it is NOT the gold solution patch. Passing it strengthens localization (top-1 lever) with no gold
    # leakage: generation below consumes only lz.ranked_files, never instance["patch"].
    issue_toks = loc._tokens(instance.get("problem_statement", ""))
    lz = re_delib.deliberate_localization(
        instance.get("problem_statement", ""), py_files,
        read_file=lambda p: rr.read_file(clone.path, instance["base_commit"], p),
        issue_tokens=issue_toks, f2p=rg._as_list(instance.get("FAIL_TO_PASS")),
        test_patch=instance.get("test_patch", ""))
    r.localized_top_file = lz.top_file
    r.localized_target_fn = lz.target_function
    r.localization_cert = lz.certificate
    gold = set(loc.gold_files(instance["patch"]))
    r.localization_top5_hit = bool(set(lz.ranked_files[:5]) & gold)   # measurement only
    if lz.abstained:
        r.stopped_at = "file_localization"
        r.notes.append(lz.reason or "localization abstained")
        return r
    r.reached = "file_localization"

    # (2)+(3) PROPOSE + VERIFY ------------------------------------------------------------------
    container = rg.start_container(instance["instance_id"]) if manage_container else None
    try:
        gv = generate_and_verify(instance, clone.path, lz.ranked_files or py_files,
                                 container=container, budget=budget, topk_files=topk_files)
        # opt-in bounded 2-file fallback: only when single-file abstained AND the gate could actually run
        if (allow_multifile and not gv.resolved
                and not (gv.verdict and gv.verdict.get("law") == "insufficient-eval-environment")):
            mf = generate_multifile(instance, clone.path, lz.ranked_files or py_files,
                                    container=container)
            if mf.resolved:
                gv.verified_diff, gv.accepted_schema = mf.verified_diff, mf.accepted_schema
                gv.verdict, gv.backend, gv.resolved = mf.verdict, mf.backend, True
                gv.n_verified += mf.n_verified
            gv.notes += mf.notes
    finally:
        if container and manage_container:
            rg.stop_container(container)

    # merge
    r.from_scratch_applicable = gv.from_scratch_applicable
    r.from_scratch_note = gv.from_scratch_note
    r.n_candidates = gv.n_candidates
    r.n_verified = gv.n_verified
    r.schemas_tried = gv.schemas_tried
    r.verified_diff = gv.verified_diff
    r.accepted_schema = gv.accepted_schema
    r.verdict = gv.verdict
    r.backend = gv.backend
    r.resolved = gv.resolved
    if gv.localized_target_fn:
        r.localized_target_fn = gv.localized_target_fn
    r.notes += gv.notes
    r.reached = "patch_generation"
    r.stopped_at = "" if r.resolved else "patch_generation"

    record_span("repo_pipeline.instance", (time.perf_counter() - t_all) * 1000.0, ok=r.resolved,
                meta={"instance": r.instance_id, "resolved": r.resolved, "n_verified": r.n_verified})
    return r
