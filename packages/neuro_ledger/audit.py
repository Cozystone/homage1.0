# -*- coding: utf-8 -*-
"""The neuro budget audit — enforce the architectural line so the No-LLM brain cannot grow into an LLM.

Enforced gates (a violation fails the audit / is not green):
  N1  no ledger entry may declare fact_source=True (a learned organ routes/scores/encodes — it is
      never a fact provider). Plus a BEST-EFFORT reference scan: answer-composition modules should
      not read a learned weight artifact and surface its output as an asserted fact. The reference
      scan is honest about its coverage (it is a heuristic, reported, not a hard gate).
  N3  every ENFORCED organ's parameter count <= SINGLE_ORGAN_MAX and the enforced total <= TOTAL_MAX.
  N-unreg  no model-like artifact under data/ + packages/ is left UNREGISTERED (a learned weight file
      that no ledger organ accounts for is a stowaway and a violation).

Advisory (surfaced, not a hard failure): heavy EXPERIMENTAL torch organs above the soft cap — the
structure-over-memorization retire targets (ACE2, the neural realizer). They are the owner's fear made
concrete; the audit reports them loudly while keeping the enforced No-LLM gate honest.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

from .ledger import (
    EXPERIMENTAL_SOFT_MAX,
    SINGLE_ORGAN_MAX,
    TOTAL_MAX,
    Organ,
    load_ledger,
    measure_all,
    repo_root,
)

# model-like weight extensions the unregistered detector scans (.bin excluded: too many corpora)
_MODEL_EXTS = (".npy", ".npz", ".pt", ".pth", ".pkl", ".joblib", ".safetensors")

# path substrings that mark a NON-learned artifact (indexes, triple stores, corpora, dumps, backups).
# Confirmed by the 2026-07-22 packages/+data/ sweep; kept tight so a real learned file is not hidden.
_DENY_SUBSTR = (
    "/atanor_index/", "/roam_index/", "world_pack", "kg_triples", "wiki_kg",
    ".perm.", ".sorted.", "postings", "doc_offset", "doc_len", "term_hash", "post_offset",
    "ace2_pack", "tokens_u16", "/traces/", "/rif_probe/", ".bak",
    "__pycache__", "node_modules", "/.git/",
)

# answer-composition modules the N1 reference scan inspects (best-effort coverage)
_ANSWER_COMPOSITION_GLOBS = (
    "apps/api/app/routers/realcity_agent.py",
    "apps/api/app/routers/base_brain.py",
    "packages/base_brain/grounded_generation.py",
    "packages/base_brain/zero_user_answer.py",
    "packages/base_brain/relational_lookup.py",
    "packages/grounded_composer/*.py",
)
# learned-artifact tokens that, if READ by an answer module as a fact, would break the doctrine
_LEARNED_ARTIFACT_TOKENS = (
    "learned_discriminator", "rif_enwiki_emb", "lexical_field", "phase_space",
    "vecs.npy", "realizer.pt", "ace2_", "mcq_judge.pt", "math_parser",
)


def audit_fact_source(measured: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """N1 (hard part): every organ must carry fact_source=False."""
    out = []
    for m in measured:
        if m.get("fact_source"):
            out.append({"gate": "N1", "organ": m["id"],
                        "detail": "ledger entry declares fact_source=True (a learned organ is not a fact source)"})
    return out


def audit_budget(measured: list[dict[str, Any]]) -> dict[str, Any]:
    """N3: enforced organs under the per-organ and total caps; experimental organs over the soft cap
    become advisories (not hard failures)."""
    violations: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []
    enforced_total = 0
    for m in measured:
        params = int(m.get("params", 0))
        if m.get("enforced", True):
            enforced_total += params
            if params > SINGLE_ORGAN_MAX:
                violations.append({"gate": "N3", "organ": m["id"], "params": params,
                                   "cap": SINGLE_ORGAN_MAX,
                                   "detail": f"enforced organ {m['id']} = {params:,} params exceeds "
                                             f"SINGLE_ORGAN_MAX {SINGLE_ORGAN_MAX:,}"})
        else:
            if params > EXPERIMENTAL_SOFT_MAX:
                advisories.append({"organ": m["id"], "params": params, "soft_cap": EXPERIMENTAL_SOFT_MAX,
                                   "status": m.get("status"),
                                   "detail": f"experimental organ {m['id']} = {params:,} params exceeds the "
                                             f"soft cap {EXPERIMENTAL_SOFT_MAX:,} — retire target "
                                             f"(structure-over-memorization doctrine)"})
    if enforced_total > TOTAL_MAX:
        violations.append({"gate": "N3", "organ": "<enforced-total>", "params": enforced_total,
                           "cap": TOTAL_MAX,
                           "detail": f"enforced total {enforced_total:,} exceeds TOTAL_MAX {TOTAL_MAX:,}"})
    return {"enforced_total": enforced_total, "violations": violations, "advisories": advisories}


def _covered_paths(ledger: list[Organ], root: Path) -> set[str]:
    covered: set[str] = set()
    for organ in ledger:
        for art in organ.artifacts:
            for p in glob.glob(str(root / art.glob), recursive=True):
                covered.add(str(Path(p).resolve()))
    return covered


def detect_unregistered_artifacts(roots: list[Path] | None = None,
                                  ledger: list[Organ] | None = None) -> list[dict[str, Any]]:
    """N-unreg: scan for model-like weight files not covered by any ledger organ and not on the
    non-learned denylist. Best-effort — honest about coverage (see run_audit's coverage note)."""
    root = repo_root()
    ledger = ledger if ledger is not None else load_ledger()
    scan_roots = roots if roots is not None else [root / "data", root / "packages"]
    covered = _covered_paths(ledger, root)
    out: list[dict[str, Any]] = []
    for scan_root in scan_roots:
        scan_root = Path(scan_root)
        if not scan_root.exists():
            continue
        for ext in _MODEL_EXTS:
            for p in scan_root.rglob(f"*{ext}"):
                if not p.is_file():
                    continue
                rp = str(p.resolve())
                norm = rp.replace("\\", "/").lower()
                if any(sub in norm for sub in _DENY_SUBSTR):
                    continue
                if rp in covered:
                    continue
                out.append({"gate": "N-unreg", "path": str(p),
                            "detail": "model-like artifact not registered in the neuro ledger "
                                      "(and not on the non-learned denylist) — register it or remove it"})
    return out


def scan_answer_composition_refs() -> dict[str, Any]:
    """N1 (best-effort): report which answer-composition modules reference a learned-artifact path.
    A reference is not itself a violation (embeddings for similarity are fine) — it is surfaced so an
    operator can confirm none is used as a FACT provider. Honest about limited coverage."""
    root = repo_root()
    refs: list[dict[str, Any]] = []
    scanned: list[str] = []
    for g in _ANSWER_COMPOSITION_GLOBS:
        for fp in glob.glob(str(root / g)):
            p = Path(fp)
            if not p.is_file():
                continue
            scanned.append(str(p.relative_to(root)).replace("\\", "/"))
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for tok in _LEARNED_ARTIFACT_TOKENS:
                if tok in text:
                    refs.append({"module": str(p.relative_to(root)).replace("\\", "/"), "token": tok})
    return {"scanned_modules": scanned, "references": refs,
            "coverage": "heuristic: greps a curated set of answer-composition modules for learned-"
                        "artifact path tokens; cannot statically prove a reference is similarity-use "
                        "vs fact-use — an operator confirms. Does not cover dynamically-built paths."}


def run_audit(write: bool = True, scan_roots: list[Path] | None = None,
              extra_measured: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Run every gate, assemble the scorecard, and (by default) write it to data/neuro_ledger/audit.json."""
    ledger = load_ledger()
    measured = measure_all(ledger)
    if extra_measured:
        measured = measured + list(extra_measured)

    n1 = audit_fact_source(measured)
    budget = audit_budget(measured)
    unreg = detect_unregistered_artifacts(scan_roots, ledger)
    refscan = scan_answer_composition_refs()

    violations = n1 + budget["violations"] + unreg
    enforced = [m for m in measured if m.get("enforced", True)]
    experimental = [m for m in measured if not m.get("enforced", True)]

    scorecard = {
        "generated_by": "packages/neuro_ledger/audit.run_audit",
        "budget": {"single_organ_max": SINGLE_ORGAN_MAX, "total_max": TOTAL_MAX,
                   "experimental_soft_max": EXPERIMENTAL_SOFT_MAX},
        "organs": measured,
        "enforced_count": len(enforced),
        "experimental_count": len(experimental),
        "total_params": budget["enforced_total"],          # enforced total governs the TOTAL_MAX gate
        "enforced_total": budget["enforced_total"],
        "experimental_total_estimate": sum(int(m.get("params", 0)) for m in experimental),
        "green": len(violations) == 0,
        "violations": violations,
        "advisories": budget["advisories"],
        "n1_fact_source_all_false": len(n1) == 0,
        "n1_reference_scan": refscan,
        "coverage_notes": [
            "N-unreg scans " + ", ".join(_MODEL_EXTS) + " (excludes .bin: too many corpora/token dumps).",
            "Non-learned artifacts (indexes, triple stores, tokenized corpora, feature dumps, backups) "
            "are excluded by a path denylist confirmed from the 2026-07-22 sweep.",
            "Params are MEASURED for .npy/.npz/weights.json and SIZE-ESTIMATED for torch .pt/.pkl "
            "(state_dict ~= bytes/4). Each organ carries a 'measured' flag.",
        ],
    }
    if write:
        out_dir = repo_root() / "data" / "neuro_ledger"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "audit.json").write_text(
            json.dumps(scorecard, ensure_ascii=False, indent=2), encoding="utf-8")
    return scorecard


if __name__ == "__main__":
    import sys
    card = run_audit(write=True)
    summary = {
        "green": card["green"],
        "enforced_count": card["enforced_count"],
        "enforced_total": card["enforced_total"],
        "total_max": card["budget"]["total_max"],
        "violations": card["violations"],
        "advisories": [a["organ"] for a in card["advisories"]],
        "experimental_total_estimate": card["experimental_total_estimate"],
    }
    sys.stdout.write(json.dumps(summary, indent=2) + "\n")
