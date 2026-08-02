# -*- coding: utf-8 -*-
"""Fetch and cache OWLv2 so F1 can benchmark it. Owner-authorised, 2026-07-30.

    python scripts/fetch_owlv2.py

F1 exists because "압도적 성능과 효율" needs a baseline and OWLv2 has never been measured here, despite
being imported on a live vision path in `packages/perception/open_vocab.py`. This downloads
google/owlv2-base-patch16-ensemble (~600 MB) from the Hugging Face hub into the local cache. Nothing is
sent anywhere; the fetch is one-way and the weights stay on disk.
"""
from __future__ import annotations

import sys
import time

MODEL = "google/owlv2-base-patch16-ensemble"


def main() -> None:
    t0 = time.time()
    print(f"fetching {MODEL} (~600 MB) into the local hub cache...", flush=True)
    try:
        from transformers import Owlv2ForObjectDetection, Owlv2Processor
    except Exception as e:                                   # pragma: no cover
        sys.exit(f"transformers is not importable: {e}")
    proc = Owlv2Processor.from_pretrained(MODEL)
    print(f"  processor ready ({time.time() - t0:.0f}s)", flush=True)
    model = Owlv2ForObjectDetection.from_pretrained(MODEL)
    n = sum(p.numel() for p in model.parameters())
    print(f"  weights ready ({time.time() - t0:.0f}s): {n / 1e6:.1f}M parameters", flush=True)
    print("cached. F1 can run offline from here.", flush=True)


if __name__ == "__main__":
    main()
