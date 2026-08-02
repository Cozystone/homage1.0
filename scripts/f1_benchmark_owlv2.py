# -*- coding: utf-8 -*-
"""F1: measure OWLv2 honestly -- cost, memory, and accuracy -- against our own path.

    python scripts/f1_benchmark_owlv2.py

"압도적 성능과 효율" needs a baseline, and OWLv2 has never been measured here despite being imported on a
live vision path in `packages/perception/open_vocab.py`. Owner-authorised download, cached locally at
593 MB / 155.0M parameters.

TWO HONESTY CONSTRAINTS STATED BEFORE ANY NUMBER.

    ATARI IS OUT OF DISTRIBUTION FOR OWLv2. It was trained on natural images; 8-pixel sprites on a black
    maze are not that. An accuracy win for us here is NOT evidence of general superiority, and no such
    claim is made. There are no large natural-image captures on disk to test the fair case, so the fair
    accuracy comparison is simply unavailable and is reported as unavailable.
    COST IS DOMAIN-INDEPENDENT and is what F1 actually needs.

AND ONE PREDICTION THAT COULD EMBARRASS THE STRATEGY, which is why it is tested first. OWLv2 resizes its
input to a fixed resolution, so ITS COST SHOULD BE CONSTANT in frame size while ours grows with pixels.
If so, then at large frames the comparison moves in ITS favour, not ours -- and the efficiency document's
plan to move efficiency claims to the large-frame domain is exactly backwards unless foveation carries it.
Measured on a small frame and a 16x-area upscale.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.atari_babble import blobs, sprite_mask                      # noqa: E402
from scripts.wire_learned_mask import frames_of                          # noqa: E402

OUT = Path("data/atari/f1_owlv2_benchmark.json")
OURS_ON_BODY = 0.680        # the chain's measured on-body with the hand mask


def upscale(f, k: int):
    return np.repeat(np.repeat(f, k, axis=0), k, axis=1)


def main() -> None:
    from packages.perception import open_vocab as ov
    print(f"open_vocab.available(): {ov.available()}")
    frames, bg, acts, truth, agree = frames_of(60, seed=3)
    H, W = frames[0].shape[:2]
    print(f"oracle verified r_x {agree['r_x']:.3f}; {len(frames)} frames of {W}x{H}\n")

    from PIL import Image
    vocab = ["a yellow character", "a ghost", "a small dot"]

    # warm the model so the first call's load does not land in the timing
    ov.detect(Image.fromarray(frames[0]), vocabulary=vocab)

    rows = {}
    for k, label in ((1, f"{W}x{H} (native)"), (4, f"{W*4}x{H*4} (16x area)")):
        imgs = [Image.fromarray(upscale(f, k)) for f in frames[:12]]
        t0 = time.perf_counter()
        dets = [ov.detect(im, vocabulary=vocab) for im in imgs]
        ms_owl = 1000 * (time.perf_counter() - t0) / len(imgs)

        big = [upscale(f, k) for f in frames[:12]]
        bgk = upscale(bg.astype(np.int16), k) if k > 1 else bg
        t0 = time.perf_counter()
        for f in big:
            blobs(sprite_mask(f, bgk))
        ms_ours = 1000 * (time.perf_counter() - t0) / len(big)

        n_det = float(np.mean([len(d) for d in dets]))
        rows[label] = {"owlv2_ms": ms_owl, "ours_ms": ms_ours,
                       "ratio_owl_over_ours": ms_owl / max(ms_ours, 1e-9),
                       "owlv2_detections_per_frame": n_det, "px": int(W * k * H * k)}
        print(f"  {label:<22} OWLv2 {ms_owl:>8.1f} ms   ours {ms_ours:>7.2f} ms   "
              f"OWLv2 is {ms_owl / max(ms_ours, 1e-9):>7.0f}x   ({n_det:.1f} detections/frame)",
              flush=True)

    a, b = rows[f"{W}x{H} (native)"], rows[f"{W*4}x{H*4} (16x area)"]
    owl_growth = b["owlv2_ms"] / max(a["owlv2_ms"], 1e-9)
    our_growth = b["ours_ms"] / max(a["ours_ms"], 1e-9)
    print(f"\n  cost growth for 16x the pixels:  OWLv2 {owl_growth:.2f}x   ours {our_growth:.2f}x")

    # accuracy, on Atari, which is OOD for OWLv2 -- reported and caveated, not claimed
    hits = 0
    n = 0
    for i, f in enumerate(frames[:30]):
        d = ov.detect(Image.fromarray(f), vocabulary=vocab)
        if not d:
            n += 1
            continue
        n += 1
        best = None
        for det in d:
            box = det.get("box") or det.get("bbox")
            if not box:
                continue
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            dist = float(np.hypot(cx - truth[i][0], cy - truth[i][1]))
            best = dist if best is None else min(best, dist)
        if best is not None and best < 8.0:
            hits += 1
    owl_acc = hits / max(n, 1)
    print(f"\n  OWLv2 finding the body on Atari: {owl_acc:.1%} of frames within 8 px")
    print(f"  our chain, measured earlier:     {OURS_ON_BODY:.1%}")
    print("  -> ATARI IS OUT OF DISTRIBUTION FOR OWLv2. This is not evidence of general superiority")
    print("     and no such claim is made; the fair-domain comparison needs natural images with ground")
    print("     truth, and there are none on disk.")

    print(f"\n-> the prediction that could embarrass the strategy: OWLv2's cost is "
          f"{'CONSTANT in frame size' if owl_growth < 1.5 else 'NOT constant'} "
          f"({owl_growth:.2f}x for 16x the pixels)")
    if owl_growth < 1.5 < our_growth:
        print("   CONFIRMED, and it matters: at large frames the comparison moves in OWLv2's favour,")
        print("   because its cost is fixed by architecture while ours grows with pixels. The plan to")
        print("   move efficiency claims to the large-frame domain only works if FOVEATION carries it --")
        print("   without foveation, going bigger helps them and not us.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"scales": rows, "owlv2_growth_16x": owl_growth,
                               "ours_growth_16x": our_growth,
                               "owlv2_body_acc_OOD": owl_acc, "ours_body_acc": OURS_ON_BODY,
                               "owlv2_params_M": 155.0, "owlv2_cache_MB": 593},
                              indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
