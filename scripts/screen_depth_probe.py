# -*- coding: utf-8 -*-
"""Which window is in front? Asked of the depth sense, answered by the window manager.

    python scripts/screen_depth_probe.py

Owner, 2026-07-29: 컴퓨터 화면을 볼때도 한 브라우저가 다른 브라우저 뒤에 있다 이런식으로 응용도 되게.

A desktop is the sharpest possible test of an ordinal depth sense, for two reasons. It has no metres
at all — nothing on a screen is four metres away — so anything that works here works because depth
was represented as ORDER rather than distance. And it has perfect ground truth for free: Windows
knows exactly which window is on top, and never had to be annotated by anyone.

TWO QUESTIONS, and they are different.

  ZERO-SHOT. Does the net trained on driving footage order desktop windows correctly? A desktop has
  none of the cues a road has — no ground plane, no perspective convergence, no sky — so the honest
  expectation is near chance, and near chance would be a real finding rather than a failure: it
  would say the ORDINAL FORMULATION carries across while the learned features do not.

  FROM MOTION. Does the label-making mechanism itself work here? Slide one window over another and
  the physics is the same as a body walking past a lamppost: the moving surface's texture displaces,
  the surface behind it does not, and `rank_pairs` reads which is which. If this works, then the
  route to a desktop depth sense is the one the owner asked for — ATANOR works it out by watching,
  not by being told what a window is.

The second is measured on a SYNTHETIC desktop rather than by dragging the operator's real windows
around. Not squeamishness: a synthetic one lets the true order be set and varied deliberately, which
a screenshot of whatever happens to be open does not, and moving someone's windows while they are
working is not an act to take without asking.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.depth_learner.model import DepthNet                        # noqa: E402
from packages.depth_learner.ordinal import rank_pairs                    # noqa: E402
from packages.eye import ScreenSource                                    # noqa: E402

CKPTS = {"supervised (CARLA metres)": Path(r"D:\carla\depth_model\depthnet.pt"),
         "self-supervised (motion only)": Path(r"D:\carla\depth_model\ordinal_selfsup.pt")}
H, W = 240, 320


def _rs(a: np.ndarray) -> np.ndarray:
    ys = (np.arange(H) * (a.shape[0] / H)).astype(np.int32)
    xs = (np.arange(W) * (a.shape[1] / W)).astype(np.int32)
    return np.ascontiguousarray(a[ys][:, xs])


# --- the real desktop -------------------------------------------------------------------------------

def windows() -> list[dict]:
    """Visible top-level windows in Z-ORDER, front first. EnumWindows enumerates in exactly that
    order, which is the ground truth this probe is scored against."""
    import win32gui
    out: list[dict] = []

    def cb(h, _):
        if not win32gui.IsWindowVisible(h) or win32gui.IsIconic(h):
            return
        t = win32gui.GetWindowText(h) or ""
        if not t.strip():
            return
        try:
            l, tp, r, b = win32gui.GetWindowRect(h)
        except Exception:
            return
        if r - l < 200 or b - tp < 150:
            return
        out.append({"h": h, "title": t[:48], "rect": (l, tp, r, b), "z": len(out)})

    win32gui.EnumWindows(cb, None)
    return out


def _exclusive(win: dict, others: list[dict], shape: tuple[int, int],
               scale: tuple[float, float]) -> np.ndarray:
    """A mask of the part of `win` that nothing in front of it covers — the pixels actually visible.

    Sampling a window's whole rectangle would sample its occluder's pixels too, and the probe would
    be asking about a region that is partly the other window. This is what makes the comparison a
    comparison of two things rather than of one thing with itself."""
    Hs, Ws = shape
    sx, sy = scale
    m = np.zeros((Hs, Ws), bool)
    l, t, r, b = win["rect"]
    m[max(0, int(t * sy)):int(b * sy), max(0, int(l * sx)):int(r * sx)] = True
    for o in others:                       # only those IN FRONT
        ol, ot, orr, ob = o["rect"]
        m[max(0, int(ot * sy)):int(ob * sy), max(0, int(ol * sx)):int(orr * sx)] = False
    return m


def zero_shot(nets: dict) -> dict:
    """Does a net trained on the world order a desktop?"""
    src = ScreenSource()
    ok, why = src.available()
    if not ok:
        return {"error": f"screen unavailable: {why}"}
    frame = src.grab()
    rgb = _rs(frame.rgb)
    sy, sx = H / frame.rgb.shape[0], W / frame.rgb.shape[1]

    ws = windows()
    preds = {k: _predict(n, rgb) for k, n in nets.items()}
    rows, results = [], {k: [] for k in nets}
    for i, a in enumerate(ws):
        for b in ws[i + 1:]:
            al, at, ar, ab = a["rect"]
            bl, bt, br, bb = b["rect"]
            if min(ar, br) <= max(al, bl) or min(ab, bb) <= max(at, bt):
                continue                                   # they do not overlap; no order to judge
            ma = _exclusive(a, ws[:i], (H, W), (sx, sy))
            mb = _exclusive(b, ws[:ws.index(b)], (H, W), (sx, sy))
            if ma.sum() < 400 or mb.sum() < 400:
                continue
            row = {"front": a["title"], "behind": b["title"]}
            for k, d in preds.items():
                # a is IN FRONT (lower z), so its depth should read SMALLER
                got = float(np.median(d[ma])) < float(np.median(d[mb]))
                results[k].append(got)
                row[k] = bool(got)
            rows.append(row)

    # A binomial p against chance, because sixteen window pairs is not many and 5/16 looks like an
    # inversion while being entirely consistent with a coin. Saying "systematically backwards" from
    # that would be reading a pattern into a small sample.
    from scipy.stats import binomtest
    sig = {k: round(binomtest(int(np.sum(v)), len(v), 0.5).pvalue, 4) for k, v in results.items() if v}
    return {"window_pairs": len(rows), "p_vs_chance": sig,
            "accuracy": {k: (round(float(np.mean(v)), 3) if v else None) for k, v in results.items()},
            "windows": [w["title"] for w in ws[:10]], "detail": rows[:12]}


# --- a desktop whose true order we set ---------------------------------------------------------------

def synthetic(trials: int = 40, seed: int = 0) -> dict:
    """Overlapping textured panels, one of which slides. Does the motion say which is on top?

    This is the same physics as a body passing a lamppost, with the depth ordering reduced to two
    layers — which is all a desktop has. Nothing here knows what a window is."""
    rng = np.random.default_rng(seed)
    hit, n, abstained = 0, 0, 0
    for t in range(trials):
        Hs, Ws = 480, 640
        bg = _texture(Hs, Ws, rng)
        # the back panel, static
        b0 = (rng.integers(40, 140), rng.integers(40, 200), 260, 320)
        # the front panel, which will slide
        f0 = (rng.integers(90, 200), rng.integers(150, 300), 240, 280)
        shift = int(rng.choice([-14, -10, 10, 14]))
        front_on_top = bool(rng.integers(0, 2))

        def compose(dx: int) -> np.ndarray:
            img = bg.copy()
            panels = [(b0, _texture(b0[2], b0[3], np.random.default_rng(1000 + t), 0), 0),
                      (f0, _texture(f0[2], f0[3], np.random.default_rng(2000 + t), dx), dx)]
            if not front_on_top:
                panels = panels[::-1]
            for (y, x, ph, pw), tex, ddx in panels:
                xx = x + (ddx if ddx else 0)
                y1, x1 = min(y + ph, Hs), min(xx + pw, Ws)
                if y1 <= y or x1 <= max(xx, 0):
                    continue
                img[y:y1, max(xx, 0):x1] = tex[:y1 - y, :x1 - max(xx, 0)]
            return img

        a_img, b_img = compose(0), compose(shift)
        r = rank_pairs(a_img, b_img, neighbourhood=0.30, min_ratio=1.5)
        if len(r["pairs"]) < 20:
            abstained += 1
            continue
        # which panel did the tracker say moved? The one that moved is the one on top only if the
        # sliding panel IS on top; when it is behind, the visible sliding pixels are the ones NOT
        # covered, and the covering panel stays put. Either way: moving == in front of what it covers.
        xy, pairs = r["xy"], r["pairs"]
        fy, fx = f0[0], f0[1]
        in_front_panel = ((xy[:, 1] >= fy) & (xy[:, 1] < fy + f0[2]) &
                          (xy[:, 0] >= fx) & (xy[:, 0] < fx + f0[3]))
        nearer = np.zeros(len(xy), bool)
        nearer[pairs[:, 0]] = True
        farther = np.zeros(len(xy), bool)
        farther[pairs[:, 1]] = True
        moving_judged_nearer = (nearer & in_front_panel).sum() > (farther & in_front_panel).sum()
        hit += int(moving_judged_nearer == front_on_top)
        n += 1
    return {"trials": n, "abstained": abstained,
            "accuracy": round(hit / n, 3) if n else None,
            "note": "the sliding panel is judged in front iff it really is; chance is 0.5"}


def _texture(h: int, w: int, rng, phase: int = 0) -> np.ndarray:
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    a = (np.sin((x + phase) / rng.uniform(4, 9)) * np.cos(y / rng.uniform(5, 11)) +
         np.sin((x + y + phase) / rng.uniform(3, 7)))
    a = (a - a.min()) / (np.ptp(a) + 1e-6) * 220 + 20   # numpy 2 removed ndarray.ptp
    return np.repeat(a[:, :, None], 3, axis=2).astype(np.uint8)


@torch.no_grad()
def _predict(net, rgb: np.ndarray) -> np.ndarray:
    x = torch.from_numpy(rgb.astype(np.float32) / 255.0)[None].permute(0, 3, 1, 2)
    return net(x).exp().squeeze().cpu().numpy()


def main() -> None:
    nets = {}
    for name, p in CKPTS.items():
        if p.exists():
            n = DepthNet()
            n.load_state_dict(torch.load(p, map_location="cpu", weights_only=False)["state_dict"])
            n.eval()
            nets[name] = n
    if not nets:
        sys.exit("no checkpoints found")

    print("=== 1. zero-shot: do nets trained on the WORLD order a DESKTOP? ===")
    z = zero_shot(nets)
    if "error" in z:
        print(" ", z["error"])
    else:
        print(f"  {z['window_pairs']} overlapping window pairs, ground truth = Win32 Z-order")
        for k, v in z["accuracy"].items():
            pv = z.get("p_vs_chance", {}).get(k)
            call = ("indistinguishable from chance" if pv is None or pv > 0.05
                    else ("above chance" if v > 0.5 else "INVERTED — systematically backwards"))
            print(f"    {k:32s} {v}   p={pv}   <- {call}")

    print("\n=== 2. from motion: does the label-maker work on a screen at all? ===")
    s = synthetic()
    print(f"  {s['trials']} trials ({s['abstained']} abstained), accuracy {s['accuracy']}   (chance 0.5)")

    out = Path("data/depth_learner/proofs/screen_depth_probe.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"zero_shot": z, "from_motion": s}, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print("\nwrote", out)


if __name__ == "__main__":
    main()
