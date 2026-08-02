# -*- coding: utf-8 -*-
"""Windows shim + entry to run the OFFICIAL swebench evaluation for a GOLD self-test.

swebench's harness imports the Unix-only ``resource`` module at import time; the actual work happens
inside Linux Docker containers, so on Windows we inject a no-op ``resource`` shim and then call the
real ``run_evaluation.main``. Feeding ``predictions_path='gold'`` runs the dataset's own gold patch —
this validates that the eval path on THIS machine correctly resolves a known-good patch (it does NOT
credit ATANOR with anything). Args come from the environment; kwargs are filtered to main's actual
signature so it survives version drift."""
import inspect
import os
import sys
import types


def _shim_resource() -> None:
    if "resource" in sys.modules:
        return
    m = types.ModuleType("resource")
    m.getrlimit = lambda *a: (0, 0)      # type: ignore[attr-defined]
    m.setrlimit = lambda *a: None        # type: ignore[attr-defined]
    for n in ("RLIMIT_NOFILE", "RLIMIT_AS", "RLIMIT_STACK", "RLIMIT_CPU", "RLIMIT_DATA"):
        setattr(m, n, 0)
    m.RLIM_INFINITY = -1                  # type: ignore[attr-defined]
    sys.modules["resource"] = m


def run() -> None:
    _shim_resource()
    from swebench.harness.run_evaluation import main
    kwargs = dict(
        dataset_name=os.environ.get("SWE_DATASET", "princeton-nlp/SWE-bench_Verified"),
        split="test",
        instance_ids=[os.environ["SWE_INSTANCE_ID"]],
        predictions_path="gold",
        max_workers=1,
        force_rebuild=False,
        cache_level="env",
        clean=False,
        open_file_limit=4096,
        run_id=os.environ.get("SWE_RUN_ID", "atanor_gold_selftest"),
        timeout=int(os.environ.get("SWE_TIMEOUT", "1800")),
        namespace=os.environ.get("SWE_NAMESPACE", "swebench"),
        rewrite_reports=False,
        modal=False,
        instance_image_tag="latest",
        env_image_tag="latest",
        report_dir=".",
    )
    sig = inspect.signature(main)
    kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
    main(**kwargs)


if __name__ == "__main__":
    run()
