# -*- coding: utf-8 -*-
"""Codebase self-knowledge — ATANOR learns its OWN source tree as a graph.

Owner (2026-07-09): " ? ." Honest
answer was no — it read books and the web, but never ingested its own code. This
is the prerequisite for the collective code-improvement loop to be MEANINGFUL: an
agent can only propose a good diff to code it understands.

AST-based, No-LLM: every .py under packages/ becomes structural triples —
 module is_a python_module / defined_in_file path.py
 module has_function fn / has_class cls
 fn in_module module / documented_as <docstring first line>
 fn defined_at path.py:LINE          <- the citation edge
 fn calls other_fn (from Call nodes in its body)
 class has_method method / Class.method defined_at path.py:LINE
So ATANOR can answer 'what does surgeon.py do', 'what calls trust_score', 'which
module owns _clean_edges'. Candidate-tier, local, gated — self-knowledge is not
auto-promoted, and it never rewrites code (that stays the human-gated self-mod).

WHY `defined_at` EXISTS. Without a location the graph can say a thing is real but never say where, and
an answer that names a function without pointing at it is a claim rather than a citation — the reader
still has to go find it, and cannot check the answer cheaply. Methods are recorded under their qualified
`Class.method` name because a bare `place` or `run` exists in dozens of classes and would cite the wrong
file half the time.

Honest scope: this is STRUCTURE (who calls whom, what's documented, where it sits), not deep
semantics of what the code MEANS — that needs the richer extractor, a next step.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

_HAN = re.compile(r"[가-힣]")

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "data" / "graph_scale" / "codebase_knowledge.jsonl"


def _module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


_MAX_DOC = 160


def _summary(docstring: str | None) -> str:
    """The one-line summary of a docstring, cut where a sentence or a word ends — never mid-phrase.

    The old rule was `first_line[:120]`, and it failed twice over. The 120-char cap landed mid-phrase,
    and — the larger error — taking only the FIRST LINE cuts a summary wherever the author happened to
    wrap it, which is usually mid-sentence: "write structural self-knowledge triples to the". Since
    these strings ARE the sentences ATANOR says back about its own code, a cut that lands mid-phrase is
    not cosmetic; it is the difference between explaining something and trailing off.

    So: unwrap the whole docstring into one flow, take the first complete SENTENCE, and only fall back
    to a word-boundary cut when even that is too long — marked with an ellipsis, because a silent
    truncation lets a fragment pass for the whole thought."""
    text = " ".join((docstring or "").split())
    if not text:
        return ""
    for stop in (". ", "? ", "! "):                 # first sentence in the unwrapped flow
        i = text.find(stop)
        if 0 < i <= _MAX_DOC:
            text = text[:i + 1]
            break
    else:
        if text.endswith("."):                      # a one-sentence docstring with no trailing space
            text = text
    if len(text) <= _MAX_DOC:
        return text
    head = text[:_MAX_DOC]
    cut = head.rfind(" ")
    return (head[:cut] if cut >= 40 else head).rstrip(" ,;:-") + "…"


def _calls_in(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


def _triples_for_file(path: Path, root: Path) -> list[tuple[str, str, str]]:
    """Structural triples for one file, each definition carrying WHERE it lives.

    `defined_at` is the citation edge: its object is `path/to/file.py:LINE`, so an answer about a
    function can point at the line the reader should open instead of merely naming it. Without this the
    graph could say a thing exists but never say where, which is the difference between a claim and a
    citation."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(text)
    except Exception:
        return []
    mod = _module_name(path, root)
    rel = path.relative_to(root).as_posix()
    out: list[tuple[str, str, str]] = [(mod, "is_a", "python_module"),
                                       (mod, "defined_in_file", rel)]
    for node in tree.body:                      # top-level only (functions/classes)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((mod, "has_function", node.name))
            out.append((node.name, "in_module", mod))
            out.append((node.name, "defined_at", f"{rel}:{node.lineno}"))
            doc = _summary(ast.get_docstring(node))
            if doc:
                out.append((node.name, "documented_as", doc))
            for callee in _calls_in(node):
                if callee != node.name and 2 <= len(callee) <= 40:
                    out.append((node.name, "calls", callee))
        elif isinstance(node, ast.ClassDef):
            out.append((mod, "has_class", node.name))
            out.append((node.name, "in_module", mod))
            out.append((node.name, "defined_at", f"{rel}:{node.lineno}"))
            cdoc = _summary(ast.get_docstring(node))
            if cdoc:
                out.append((node.name, "documented_as", cdoc))
            for m in node.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append((node.name, "has_method", m.name))
                    # methods are cited under their qualified name so `Rooms.place` is locatable
                    # even though the bare name `place` may exist in a dozen other classes
                    out.append((f"{node.name}.{m.name}", "defined_at", f"{rel}:{m.lineno}"))
                    out.append((f"{node.name}.{m.name}", "in_module", mod))
    return out


#: predicates whose inverse is worth storing. The store indexes SUBJECTS only, so "what calls X" is
#: unanswerable by lookup unless the inverse edge exists as a fact in its own right. Writing it makes
#: the reverse question an ordinary subject query instead of a second mechanism — which is the whole
#: point of moving off the private ledger: ONE retrieval path, not one per direction.
_INVERSE = {"calls": "called_by", "has_function": "in_module", "has_class": "in_module"}

CODE_STORE = REPO / "data" / "graph_scale" / "code_graph"
NAMES = CODE_STORE / "names.json"


def _open_store(root: Path | None = None, *, read_only: bool = False):
    from packages.graph_scale.triple_store import TripleStore
    return TripleStore(root or CODE_STORE, read_only=read_only)


def ingest_codebase(root: str | Path | None = None, *, subdir: str = "packages",
                    out: str | Path | None = None, skip_tests: bool = True,
                    store_root: str | Path | None = None) -> dict[str, Any]:
    """Walk the source tree into the SAME triple store the rest of the mind reads from.

    This used to write a private JSONL that `about()` re-read and re-parsed on every single question
    — 79,611 rows scanned per query, measured at 167 ms. That cost was the visible symptom of a
    deeper problem: a second brain. The code lane had its own storage, its own reader, its own
    resolver and its own confidence number, none of which shared anything with the machinery that
    answers questions about the world. Consolidating onto TripleStore buys the indexed lookup, the
    provenance sidecar, the tombstone/retraction protocol and the multi-hop reasoner (which works
    over any `facts_about` callable) — all of it already built, none of it previously reachable from
    a question about code.

    The JSONL is still written, as a plain-text audit trail of what was ingested. It is no longer on
    the read path.

    Local and candidate-tier, unchanged: self-knowledge is not auto-promoted and never rewrites code.
    """
    base = Path(root) if root else REPO
    scan = base / subdir
    # the audit ledger follows the same rule as the store: a scratch tree writes a scratch ledger,
    # never the production one. Same defect, same fix -- an ingest of somebody's temp directory must
    # not be able to overwrite what an ingest of the real repo produced.
    if out:
        out_path = Path(out)
    elif root and base.resolve() != REPO.resolve():
        out_path = base / "data" / "graph_scale" / "codebase_knowledge.jsonl"
    else:
        out_path = LEDGER
    out_path.parent.mkdir(parents=True, exist_ok=True)
    files = [p for p in scan.rglob("*.py")
             if "__pycache__" not in p.parts and not (skip_tests and (
                 p.name.startswith("test_") or "tests" in p.parts))]
    triples: list[tuple[str, str, str]] = []
    for p in files:
        triples.extend(_triples_for_file(p, base))

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    seen: set[tuple[str, str, str]] = set()
    n_by_pred: dict[str, int] = {}
    hangul_dropped = 0
    by_leaf: dict[str, list[str]] = {}
    final: list[tuple[str, str, str]] = []
    for s, p, o in triples:
        if _HAN.search(o) or _HAN.search(s):
            # a Korean docstring summary would be a Korean sentence ATANOR could say back about its
            # own code, in a mind that thinks in English. Dropped, and COUNTED -- a silent drop
            # would hide how much Korean is still in the tree.
            hangul_dropped += 1
            continue
        if (s, p, o) in seen:
            continue
        seen.add((s, p, o))
        n_by_pred[p] = n_by_pred.get(p, 0) + 1
        final.append((s, p, o))
        inv = _INVERSE.get(p)
        if inv and (o, inv, s) not in seen:
            seen.add((o, inv, s))
            n_by_pred[inv] = n_by_pred.get(inv, 0) + 1
            final.append((o, inv, s))
        for name in (s, o):
            if " " in name or not name:
                continue
            leaf = name.rsplit(".", 1)[-1].removesuffix(".py")
            bucket = by_leaf.setdefault(leaf, [])
            if name not in bucket:
                bucket.append(name)

    with out_path.open("w", encoding="utf-8") as fh:                 # audit trail, not a read path
        for s, p, o in final:
            fh.write(json.dumps({"s": s, "p": p, "o": o, "src": "codebase:ast",
                                 "tier": "candidate", "at": now}, ensure_ascii=False) + "\n")

    # WHERE THE STORE GOES, and why this is not simply CODE_STORE. An earlier version always wrote
    # the production store and always rmtree'd it first, so a test that ingested a three-file temp
    # tree DESTROYED the real 117k-triple graph -- silently, because the run "succeeded". A path
    # argument has to carry through to every artifact the call writes, or the caller has no way to
    # ask for a scratch run. The store now follows whichever input the caller actually named.
    if store_root:
        root_store = Path(store_root)
    elif out:                                    # an explicit ledger implies an explicit workspace
        root_store = Path(out).parent / "code_graph"
    elif root and Path(root).resolve() != REPO.resolve():
        root_store = Path(root) / "data" / "graph_scale" / "code_graph"
    else:
        root_store = CODE_STORE
    if root_store.exists():
        shutil.rmtree(root_store)                                    # a full re-read of the tree
    root_store.mkdir(parents=True, exist_ok=True)
    store = _open_store(root_store)
    res = store.bulk_ingest(final)
    store.rebuild_index()
    (root_store / "names.json").write_text(
        json.dumps({"by_leaf": by_leaf, "at": now}, ensure_ascii=False), encoding="utf-8")

    return {"files": len(files), "triples": len(final), "by_predicate": n_by_pred,
            "modules": n_by_pred.get("is_a", 0), "functions": n_by_pred.get("has_function", 0),
            "classes": n_by_pred.get("has_class", 0), "calls": n_by_pred.get("calls", 0),
            "hangul_triples_dropped": hangul_dropped,
            "store": str(root_store), "store_ingest": res, "distinct_leaves": len(by_leaf),
            "ledger": str(out_path), "written_to_production": False,
            "note": "structural self-knowledge (AST) in the shared triple store — candidate-tier, "
                    "local; not code MEANING"}


def _rows() -> list[dict[str, Any]]:
    """The raw audit trail. Kept for tooling that wants the flat record; NOT the read path."""
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def leaf_index() -> dict[str, list[str]]:
    """leaf name -> the full dotted names carrying it, built at ingest so resolution needs no scan."""
    try:
        return json.loads(NAMES.read_text(encoding="utf-8"))["by_leaf"]
    except Exception:
        return {}


def about(name: str, limit: int = 20, *, store_root: str | Path | None = None) -> dict[str, Any]:
    """What the self-knowledge graph holds about a module / function / class.

    Same return shape as before; the implementation is now an indexed subject lookup through the
    shared store rather than a scan of every row ever written. `store_root` exists so a caller that
    ingested into a scratch store can read that store back — without it, the only readable graph
    would be production, which is what made a scratch ingest useless and tempted the write path into
    clobbering the real one."""
    try:
        store = _open_store(Path(store_root) if store_root else None, read_only=True)
    except Exception:
        return {"name": name, "is": [], "referenced_by": [], "known": False}
    subj: list[dict[str, Any]] = []
    obj: list[dict[str, Any]] = []
    for _s, p, o in store.facts_about(name, limit=limit * 3):
        if p == "called_by":                      # the stored inverse, reported in its natural form
            if len(obj) < limit:
                obj.append({"subject": o, "predicate": "calls"})
        elif len(subj) < limit:
            subj.append({"predicate": p, "object": o})
    return {"name": name, "is": subj, "referenced_by": obj, "known": bool(subj or obj)}
