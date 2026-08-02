# -*- coding: utf-8 -*-
"""Small honest probes on the other SWE-bench variants. These do NOT fabricate scores — they report
whether a dataset even LOADS here, and for Multilingual attempt file-localization on 2 instances
(noting our organs are Python-AST-only, so non-Python instances are out of organ scope)."""
from __future__ import annotations

from typing import Any

# Candidate HF dataset ids, tried in order (the org prefix has moved over time).
VARIANTS = {
    "multilingual": ["swe-bench/SWE-bench_Multilingual", "princeton-nlp/SWE-bench_Multilingual"],
    "pro": ["ScaleAI/SWE-bench_Pro", "swe-bench/SWE-bench_Pro", "SWE-bench-Pro/SWE-bench_Pro"],
    "multimodal": ["princeton-nlp/SWE-bench_Multimodal", "swe-bench/SWE-bench_Multimodal"],
}


def _try_load(ids: list[str], split: str = "test") -> tuple[Any, str, str]:
    """Return (dataset_or_None, id_used, error). Tries each candidate id."""
    from datasets import load_dataset
    last = ""
    for ds_id in ids:
        for sp in (split, "train", "dev"):
            try:
                ds = load_dataset(ds_id, split=sp)
                return ds, f"{ds_id}[{sp}]", ""
            except Exception as e:
                last = f"{type(e).__name__}: {str(e)[:150]}"
    return None, "", last


def probe_multilingual(n: int = 2) -> dict[str, Any]:
    from packages.swe_eval import localizer as loc
    from packages.swe_eval import repo_reader as rr
    ds, used, err = _try_load(VARIANTS["multilingual"])
    if ds is None:
        return {"loads": False, "id": None, "error": err}
    out: dict[str, Any] = {"loads": True, "id": used, "n_total": len(ds), "instances": []}
    langs: dict[str, int] = {}
    for i in range(min(n, len(ds))):
        inst = ds[i]
        gold = loc.gold_files(inst["patch"])
        # infer language from the gold patch's file extensions (the dataset field varies by version)
        exts = {g.rsplit(".", 1)[-1].lower() for g in gold if "." in g}
        code_exts = exts - {"md", "txt", "rst", "json", "yaml", "yml", "cfg", "toml"}
        lang = inst.get("language") or inst.get("lang") or (
            "/".join(sorted(code_exts)) if code_exts else "/".join(sorted(exts)) or "?")
        langs[lang] = langs.get(lang, 0) + 1
        is_py = "py" in code_exts
        rec: dict[str, Any] = {"instance_id": inst.get("instance_id"), "repo": inst.get("repo"),
                               "gold_ext": sorted(exts), "language": lang}
        try:
            clone = rr.ensure_clone(inst["repo"], timeout_s=180)
            if clone.ok:
                py = rr.list_py_files(clone.path, inst["base_commit"])
                rec["n_py_files"] = len(py)
                rec["gold_files"] = gold
                if py:
                    lz = loc.localize(inst["problem_statement"], py)
                    rec["top1"] = lz.top1
                    rec["top5_hit"] = bool(set(lz.topk(5)) & set(gold))
                rec["organ_scope"] = "python-ast (in scope)" if is_py else \
                    f"OUT-OF-SCOPE (organs are Python-AST-only; gold edits are .{'/.'.join(sorted(code_exts)) or '?'})"
            else:
                rec["clone"] = clone.detail
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        out["instances"].append(rec)
    out["languages"] = langs
    return out


def probe_loadable(name: str) -> dict[str, Any]:
    """Just: does it load, how big, what fields. For Pro / Multimodal — no fabricated eval."""
    ds, used, err = _try_load(VARIANTS[name])
    if ds is None:
        return {"loads": False, "id": None, "error": err}
    return {"loads": True, "id": used, "n_total": len(ds), "fields": list(ds[0].keys())}
