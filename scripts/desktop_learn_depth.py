# -*- coding: utf-8 -*-
"""Learn which window is in front by nudging real windows and watching what moves.

    python scripts/desktop_learn_depth.py --harvest        # collect, restore, report label quality
    python scripts/desktop_learn_depth.py --harvest --train

Owner asked for this on the real desktop rather than a synthetic one, so this moves the operator's
actual windows. Three rules follow from that and none of them is optional.

  EVERY WINDOW GOES BACK. Original rectangles are read before anything moves and restored in a
  `finally`, so a crash, a Ctrl-C or an exception still puts the desktop back. A window left
  somewhere new is a change to somebody's workspace that they did not ask for.

  THE Z-ORDER IS NEVER TOUCHED. `SWP_NOZORDER | SWP_NOACTIVATE` — the stacking order is the ground
  truth this experiment is scored against, and a probe that disturbs its own answer key measures
  itself. It also means no window is raised, no focus is stolen, and nothing the operator is typing
  into changes.

  NUDGE, NOT REARRANGE. A few pixels, held for a moment, put back. Enough for a tracker to see and
  not enough to disrupt anything.

WHY THIS IS THE SAME MECHANISM AS THE CITY, NOT AN ANALOGY OF IT. Slide a window and its contents
displace while whatever it covers stays exactly where it was. That is the identical measurement a
body makes walking past a lamppost — near surface sweeps, far surface does not — so `rank_pairs`
reads it unchanged, with no screen-specific branch anywhere. And the desktop gives what no street
ever will: an exact answer, from the window manager, for free.

WHAT WOULD MAKE THIS FAIL, so the result can be read. Newly uncovered content is not flow, it is
appearance, and a tracker asked about it will return nonsense; window borders and shadows move with
the window and are the strongest corners on it. Both push the labels the SAME way as the true answer,
which is why label accuracy alone would be a weak claim and why the trained net is evaluated on
window pairs it never saw being moved.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.depth_learner.model import DepthNet                                # noqa: E402
from packages.depth_learner.ordinal import (rank_accuracy, rank_pairs,           # noqa: E402
                                            ranking_loss)
from packages.eye import ScreenSource                                            # noqa: E402

OUT = Path(r"D:\desktop_depth")
H, W = 240, 320
SWP_NOZORDER, SWP_NOACTIVATE, SWP_NOSIZE, SWP_NOMOVE = 0x0004, 0x0010, 0x0001, 0x0002

# Windows that must not be nudged: the shell owns the desktop and the taskbar, and moving the
# terminal this is running in would move the thing reading the results.
SKIP = ("Program Manager", "Windows 입력 환경", "NVIDIA GeForce Overlay", "Claude", "Cursor",
        "MINGW", "cmd.exe", "Windows PowerShell", "Terminal")


def list_windows() -> list[dict]:
    """Visible top-level windows, FRONT FIRST — EnumWindows enumerates in Z-order, and that order
    is the ground truth."""
    import win32gui
    out: list[dict] = []

    def cb(h, _):
        if not win32gui.IsWindowVisible(h) or win32gui.IsIconic(h):
            return
        t = win32gui.GetWindowText(h) or ""
        if not t.strip() or any(s.lower() in t.lower() for s in SKIP):
            return
        try:
            l, tp, r, b = win32gui.GetWindowRect(h)
        except Exception:
            return
        if r - l < 240 or b - tp < 180:
            return
        out.append({"h": h, "title": t[:44], "rect": (l, tp, r, b), "z": len(out)})

    win32gui.EnumWindows(cb, None)
    return out


def move_to(h: int, x: int, y: int) -> bool:
    """Move without raising, resizing, activating, or changing the stacking order."""
    return bool(ctypes.windll.user32.SetWindowPos(h, 0, int(x), int(y), 0, 0,
                                                  SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOSIZE))


def _rs(a: np.ndarray) -> np.ndarray:
    ys = (np.arange(H) * (a.shape[0] / H)).astype(np.int32)
    xs = (np.arange(W) * (a.shape[1] / W)).astype(np.int32)
    return np.ascontiguousarray(a[ys][:, xs])


def _covers(a: dict, b: dict) -> bool:
    al, at, ar, ab = a["rect"]
    bl, bt, br, bb = b["rect"]
    return min(ar, br) > max(al, bl) and min(ab, bb) > max(at, bt)


HWND_TOP, HWND_BOTTOM = 0, 1


def raise_window(h: int) -> bool:
    """Put this window on top WITHOUT activating it.

    THIS IS WHAT MAKES THE EXPERIMENT AN EXPERIMENT. The first version held the Z-order fixed so as
    not to disturb the answer key, and by doing so made the answer key constant: the same window was
    in front in all fourteen layouts, so a net could score 0.867 by learning "the window with this
    content is the front one" and never look at an occlusion boundary at all. Positions varied and
    the thing being predicted never did.

    `SWP_NOACTIVATE` reorders without stealing focus, so nothing the operator is typing into
    changes. The original order is restored by re-raising the windows back-to-front at the end."""
    return bool(ctypes.windll.user32.SetWindowPos(h, HWND_TOP, 0, 0, 0, 0,
                                                  SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE))


def restore_zorder(back_to_front: list[int]) -> None:
    """Re-raise in order, so the last one raised ends up on top — which reproduces the order found."""
    for h in back_to_front:
        try:
            raise_window(h)
        except Exception:
            pass
        time.sleep(0.05)


def scatter(wins: list[dict], rng, sw: int, sh: int) -> list[dict]:
    """Put the windows somewhere new, still overlapping, still on screen.

    THE EXPERIMENT NEEDS THIS. Three windows in one arrangement give two comparable pairs, and an
    accuracy over two pairs is two coin flips wearing a decimal point — the first training run
    reported 1.0 and then 0.5 and neither meant anything. Rearranging generates many distinct
    LAYOUTS from the same few windows, so a net can be trained on some and tested on others it has
    never seen. It is still only three window identities, which is the limit of what is open, and
    that limit is stated rather than hidden."""
    out = []
    for k, w in enumerate(wins):
        l, t_, r, b = w["rect"]
        ww, hh = r - l, b - t_
        # cluster them so they overlap: a spread-out desktop has no ordering to judge
        nx = int(rng.integers(40, max(60, sw - ww - 40)) * 0.55 + sw * 0.08)
        ny = int(rng.integers(40, max(60, sh - hh - 40)) * 0.55 + sh * 0.05)
        nx, ny = min(nx, sw - ww - 10), min(ny, sh - hh - 10)
        if move_to(w["h"], nx, ny):
            out.append({**w, "rect": (nx, ny, nx + ww, ny + hh)})
        else:
            out.append(w)
    time.sleep(0.35)
    return out


def harvest(src, offsets=(-18, 18, -12, 12), settle: float = 0.28, wins=None) -> dict:
    """Nudge each window in turn; keep what the motion said; put everything back.

    Returns the collected samples and, separately, how often the motion agreed with the Z-order."""
    wins = wins or list_windows()
    if len(wins) < 2:
        return {"error": f"need at least two movable windows; found {len(wins)}"}
    home = {w["h"]: w["rect"] for w in wins}                 # where they are RIGHT NOW
    samples, agree, total, skipped = [], 0, 0, 0

    try:
        for i, w in enumerate(wins):
            # Only windows that overlap something are informative — a window over bare desktop has
            # nothing to be in front OF.
            others = [o for o in wins if o["h"] != w["h"] and _covers(w, o)]
            if not others:
                skipped += 1
                continue
            l, t, r, b = home[w["h"]]
            for dx in offsets:
                before = src.grab().rgb
                if not move_to(w["h"], l + dx, t):
                    continue
                time.sleep(settle)
                after = src.grab().rgb
                move_to(w["h"], l, t)
                time.sleep(0.08)

                a_s, b_s = _rs(before), _rs(after)
                rp = rank_pairs(a_s, b_s, neighbourhood=0.30, min_ratio=1.5)
                if len(rp["pairs"]) < 24:
                    continue

                # Score against Z-order: a point inside the window that MOVED, compared against a
                # point inside a window BEHIND it, should have been called nearer.
                sy, sx = H / before.shape[0], W / before.shape[1]
                xy = rp["xy"]
                inside = lambda win: ((xy[:, 0] >= win["rect"][0] * sx) & (xy[:, 0] < win["rect"][2] * sx) &
                                      (xy[:, 1] >= win["rect"][1] * sy) & (xy[:, 1] < win["rect"][3] * sy))
                in_moved = inside(w)
                behind = np.zeros(len(xy), bool)
                for o in others:
                    if o["z"] > w["z"]:                       # strictly behind
                        behind |= inside(o)
                behind &= ~in_moved
                if behind.sum() < 8 or in_moved.sum() < 8:
                    continue
                pr = rp["pairs"]
                cross = (in_moved[pr[:, 0]] & behind[pr[:, 1]]) | (behind[pr[:, 0]] & in_moved[pr[:, 1]])
                if cross.sum() < 8:
                    continue
                right = in_moved[pr[cross, 0]].sum()          # "nearer" slot holds the moved window
                agree += int(right)
                total += int(cross.sum())

                samples.append({"rgb": a_s, "xy": xy, "pairs": pr, "conf": rp["conf"],
                                "moved_z": w["z"], "title": w["title"],
                                "layout": [dict(o, h=int(o["h"])) for o in wins]})
    finally:
        # UNCONDITIONAL. Whatever happened above, the desktop goes back to how it was found.
        for h, (l, t, r, b) in home.items():
            try:
                move_to(h, l, t)
            except Exception:
                pass

    return {"samples": samples, "windows": len(wins), "no_overlap": skipped,
            "label_agreement": round(agree / total, 4) if total else None,
            "comparisons": total,
            "restored": True}


def evaluate(net, dev, wins: list[dict], rgb: np.ndarray) -> dict:
    """Ask the net to order every overlapping window pair on a static screenshot."""
    with torch.no_grad():
        net.eval()
        x = torch.from_numpy(rgb.astype(np.float32) / 255.0)[None].permute(0, 3, 1, 2).to(dev)
        d = net(x).exp().squeeze().cpu().numpy()
        net.train()
    hits, n = 0, 0
    for i, a in enumerate(wins):
        for b in wins[i + 1:]:
            if not _covers(a, b):
                continue
            ma = _mask(a, wins[:i], rgb.shape[:2])
            mb = _mask(b, wins[:wins.index(b)], rgb.shape[:2])
            # COMPARE ACROSS THE SHARED BOUNDARY, not whole regions.
            #
            # An UNTRAINED net scored 0.794 on the whole-region version, which is impossible if the
            # comparison were fair — and it was not. The occluded window's visible pixels are thin
            # strips at the screen edge while the front window's are a large central block, so any
            # convolutional net scores above chance on the border artefacts its own zero-padding
            # creates, with no knowledge of anything. That shortcut invalidated every desktop
            # accuracy reported before this line existed.
            #
            # Restricting both sides to a band around the boundary they share removes it: the two
            # samples are then adjacent, similarly placed, and differ in nothing except which
            # surface they lie on — which is the only thing the question is about, and is also where
            # an occlusion cue physically is.
            band = _boundary_band(a, b, wins[:i], wins[:wins.index(b)], rgb.shape[:2])
            ma, mb = ma & band, mb & band
            if ma.sum() < 60 or mb.sum() < 60:
                continue
            hits += int(float(np.median(d[ma])) < float(np.median(d[mb])))
            n += 1
    return {"pairs": n, "accuracy": round(hits / n, 4) if n else None}


def _boundary_band(a: dict, b: dict, front_of_a, front_of_b, shape, width: int = 26) -> np.ndarray:
    """A strip hugging the edge where `a` overlaps `b` — where the occlusion actually happens."""
    import win32api
    sw = win32api.GetSystemMetrics(78) or 1920
    sh = win32api.GetSystemMetrics(79) or 1080
    Hs, Ws = shape
    sx, sy = Ws / sw, Hs / sh
    al, at, ar, ab = a["rect"]
    bl, bt, br, bb = b["rect"]
    ox0, oy0 = max(al, bl), max(at, bt)
    ox1, oy1 = min(ar, br), min(ab, bb)
    m = np.zeros((Hs, Ws), bool)
    x0 = max(0, int(ox0 * sx) - width); x1 = min(Ws, int(ox1 * sx) + width)
    y0 = max(0, int(oy0 * sy) - width); y1 = min(Hs, int(oy1 * sy) + width)
    m[y0:y1, x0:x1] = True
    return m


def _mask(win: dict, in_front: list[dict], shape) -> np.ndarray:
    import win32api
    sw = win32api.GetSystemMetrics(78) or 1920
    sh = win32api.GetSystemMetrics(79) or 1080
    Hs, Ws = shape
    sx, sy = Ws / sw, Hs / sh
    m = np.zeros((Hs, Ws), bool)
    l, t, r, b = win["rect"]
    m[max(0, int(t * sy)):int(b * sy), max(0, int(l * sx)):int(r * sx)] = True
    for o in in_front:
        ol, ot, orr, ob = o["rect"]
        m[max(0, int(ot * sy)):int(ob * sy), max(0, int(ol * sx)):int(orr * sx)] = False
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--layouts", type=int, default=14, help="distinct window arrangements to visit")
    ap.add_argument("--epochs", type=int, default=40)
    args = ap.parse_args()

    src = ScreenSource()
    ok, why = src.available()
    if not ok:
        sys.exit(f"screen unavailable: {why}")

    import win32api
    sw = win32api.GetSystemMetrics(78) or 1920
    sh = win32api.GetSystemMetrics(79) or 1080
    base = list_windows()
    if len(base) < 2:
        sys.exit(f"need at least two movable windows; found {len(base)}")
    HOME = {w["h"]: w["rect"] for w in base}          # the operator's actual desktop, recorded once
    HOME_Z = [int(w["h"]) for w in reversed(base)]    # back-to-front, to put the stacking back
    rng = np.random.default_rng(0)

    layouts, agreements = [], []
    try:
        for li in range(args.layouts):
            if li:
                # Vary WHICH window is in front, not only where the windows are. Without this the
                # thing being predicted is constant and the test is unfalsifiable.
                raise_window(int(base[int(rng.integers(0, len(base)))]["h"]))
                time.sleep(0.2)
                wins = scatter(list_windows() or base, rng, sw, sh)
            else:
                wins = base
            h = harvest(src, wins=wins)
            if "error" in h or not h["samples"]:
                continue
            still = _rs(src.grab().rgb)
            layouts.append({"i": li, "wins": wins, "samples": h["samples"], "still": still,
                            "front": wins[0]["title"] if wins else None})
            if h["label_agreement"] is not None:
                agreements.append(h["label_agreement"])
            print(f"  layout {li}: {len(h['samples'])} nudges, motion agreed with Z-order "
                  f"{h['label_agreement']} of {h['comparisons']}", flush=True)
    finally:
        # UNCONDITIONAL, and it covers the scattering as well as the nudging.
        for hh, (l, t_, r, b) in HOME.items():
            try:
                move_to(hh, l, t_)
            except Exception:
                pass
        restore_zorder(HOME_Z)
        print("desktop restored: positions AND stacking order back as found", flush=True)

    if len(layouts) < 4:
        sys.exit(f"only {len(layouts)} usable layouts — not enough to hold any out")

    print()
    print(f"=== does the motion know which window is in front? ===")
    print(f"  agreement with Win32 Z-order: {np.mean(agreements):.4f} over {len(agreements)} "
          f"layouts   (chance 0.5)")
    fronts = {}
    for L in layouts:
        fronts[L["front"]] = fronts.get(L["front"], 0) + 1
    print(f"  which window was in front, across layouts: {fronts}")
    if len(fronts) < 2:
        print("  WARNING: the front window never changed — an identity shortcut would score well")

    # HELD OUT BY LAYOUT. The net trains on some arrangements and is tested on others it never saw,
    # on a STILL screenshot with nothing moving — so it has to answer from appearance rather than
    # from having watched, and cannot pass by memorising where the front window sits.
    cut = int(len(layouts) * 0.7)
    trn_l, val_l = layouts[:cut], layouts[cut:]
    trn = [s for L in trn_l for s in L["samples"]]
    print()
    print(f"training on {len(trn)} nudges from {len(trn_l)} layouts; "
          f"{len(val_l)} layouts held out (labels from motion only — Z-order never enters the loss)")

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = DepthNet().to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=3e-4)

    def score(ls):
        hits = pairs = 0
        for L in ls:
            e = evaluate(net, dev, L["wins"], L["still"])
            if e["pairs"]:
                hits += e["accuracy"] * e["pairs"]
                pairs += e["pairs"]
        return (round(hits / pairs, 4) if pairs else None), pairs

    a0, n0 = score(val_l)
    print(f"  before training: held-out {a0} over {n0} pairs")
    for ep in range(args.epochs):
        order = rng.permutation(len(trn))
        tot = 0.0
        for s in range(0, max(1, len(order) - 3), 4):
            batch = [trn[i] for i in order[s:s + 4]]
            if not batch:
                continue
            x = torch.from_numpy(np.stack([b["rgb"] for b in batch]).astype(np.float32) / 255.0)
            pred = net(x.permute(0, 3, 1, 2).to(dev))
            loss = sum(ranking_loss(pred[k], b["xy"], b["pairs"], b["conf"])
                       for k, b in enumerate(batch)) / len(batch)
            opt.zero_grad(); loss.backward(); opt.step()
            tot += float(loss.detach())
        if ep % 10 == 9 or ep == args.epochs - 1:
            av, nv = score(val_l)
            at, nt = score(trn_l)
            print(f"  ep{ep}  loss {tot:.3f}   trained-on {at} ({nt})   HELD-OUT {av} ({nv})",
                  flush=True)

    av, nv = score(val_l)
    at, nt = score(trn_l)
    from scipy.stats import binomtest
    pv = binomtest(int(round(av * nv)), nv, 0.5).pvalue if nv else None
    OUT.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": net.state_dict(), "size": (W, H), "kind": "desktop_ordinal"},
               OUT / "desktop_ordinal.pt")
    proof = {"label_agreement_from_motion": round(float(np.mean(agreements)), 4),
             "layouts": len(layouts), "nudges": len(trn),
             "trained_on_layouts": {"accuracy": at, "pairs": nt},
             "held_out_layouts": {"accuracy": av, "pairs": nv, "p_vs_chance": pv},
             "window_identities": len(base),
             "ground_truth_used_for": "evaluation only — Z-order never entered the loss",
             "caveat": ("only %d window identities were open, so held-out LAYOUTS are new but the "
                        "windows themselves are not" % len(base))}
    print()
    print(f"=== ordering a STILL screen, nothing moving (chance 0.5) ===")
    print(f"  layouts it trained on   {at}  over {nt} pairs")
    print(f"  layouts held out        {av}  over {nv} pairs   p={pv}")
    print(f"  (only {len(base)} window identities were open — new arrangements, same windows)")
    pp = Path("data/depth_learner/proofs/desktop_ordinal.json")
    pp.parent.mkdir(parents=True, exist_ok=True)
    pp.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print("wrote", pp)


if __name__ == "__main__":
    main()
