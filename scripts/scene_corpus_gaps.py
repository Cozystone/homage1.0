# -*- coding: utf-8 -*-
"""S5b — the prior a per-scene test cannot have: many scenes, and what a boundary looks like across them.

    python scripts/scene_corpus_gaps.py --pages 200

WHAT THIS IS FOR. The grouping organ decides where one thing ends by asking, inside a single scene, whether
the widest gap beats a null. That test was repaired twice and still failed at the sample sizes senses
actually deliver: ten tracks in a frame, fifteen line gaps on a page. It is not a calibration problem. At
n = 10 the null's own variance exceeds the effect, so NO test of that shape can reach a decision, and a
person looking at the same frame needs no null draws at all -- five things move and five do not, and it is
obvious, because the prior over which gap structures are real was learned over a lifetime instead of being
recomputed from the ten things currently in view.

So the fix is not a better test inside one scene. It is a PRIOR ACROSS SCENES, and a prior needs scenes.

WHY THE CORPUS IS GENERATED RATHER THAN DOWNLOADED, and why that is not a shortcut. Chromium performs the
layout, so every gap here is a real rendering artefact and not a simulation of one; what is randomised is
the CSS -- font size, line height, margins, nesting, column count, block count, text length. And the labels
are exact rather than annotated: `Range.getClientRects()` returns the actual rendered line boxes, and each
line's nearest block-level ancestor says which block it belongs to, so two adjacent lines cross a real
boundary exactly when their blocks differ. No human labelling, no scraping, no network, and unlimited scale.

The corpus premise it replaces was wrong and the correction is recorded: S5a assumed depth_learner was
starving. Its own proofs say otherwise -- CARLA to City Sample transfer holds at rho 0.283 against a
random control of -0.006, 54 of 61 pairs, p = 2.16e-10, with the instrument validated on ground truth
first. That organ has data and lacks a CONSUMER. The cross-scene prior is the thing that is actually
starving.

REGISTERED BEFORE RUNNING:
    1  the corpus is not degenerate -- both classes present, base rate reported, and pages actually differ
    2  train and test share no page, so nothing is scored on a layout it was fitted to
    3  the learned prior beats the per-scene test AT SMALL n, which is the only place the claim matters
    4  and beats a shuffled-label control, because a classifier on 8 features will fit something
    5  the four checks in packages/self_check gate the verdict -- I no longer write my own pass condition
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.perception.gestalt import evidence                           # noqa: E402
from packages.self_check import preflight                                  # noqa: E402

OUT = Path("data/perception/scene_corpus_gaps.json")
VIEW = (1000, 800)

LINE_BOXES_JS = """() => {
  const out = [];
  const blockOf = (node) => {
    let p = node.parentElement;
    while (p) {
      const d = getComputedStyle(p).display;
      if (d === 'block' || d === 'list-item' || d === 'flex' || d === 'grid') return p;
      p = p.parentElement;
    }
    return document.body;
  };
  const ids = new Map();
  const idOf = (el) => { if (!ids.has(el)) ids.set(el, 'b' + ids.size); return ids.get(el); };
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walk.nextNode())) {
    if (!n.nodeValue || !n.nodeValue.trim()) continue;
    const r = document.createRange();
    r.selectNodeContents(n);
    const block = idOf(blockOf(n));
    for (const rect of r.getClientRects()) {
      if (rect.width < 2 || rect.height < 2) continue;
      out.push({top: rect.top, bottom: rect.bottom, left: rect.left,
                right: rect.right, block: block});
    }
  }
  return out;
}"""


def page_html(rng) -> str:
    """One randomised layout. Chromium lays it out; nothing about the geometry is chosen here."""
    fs = rng.integers(11, 22)
    lh = round(float(rng.uniform(1.15, 2.0)), 2)
    mb = rng.integers(2, 40)
    pad = rng.integers(0, 28)
    cols = 1 if rng.random() < 0.7 else int(rng.integers(2, 4))
    nblocks = int(rng.integers(3, 8))
    fam = rng.choice(["system-ui", "Georgia, serif", "Consolas, monospace", "Arial, sans-serif"])
    words = ("layout render glyph baseline ascender descender kerning leading tracking column "
             "gutter margin padding raster hinting subpixel gamma metric").split()
    # BLOCKS MUST BE LONG ENOUGH TO CONTAIN A WINDOW. The first version drew 4-60 words per block, so a
    # paragraph was two or three lines and EVERY window of six gaps crossed a margin -- a boundary was
    # present in 97.8% of sets and the registered non-degeneracy check refused the corpus before any AUC
    # was read. Long paragraphs are what make the negative class exist at all: a run of line gaps inside
    # one paragraph is a gap set with no boundary in it, which is precisely the case the organ has to
    # abstain on. The layout is still Chromium's; only the text length changed.
    parts = []
    for _i in range(nblocks):
        kind = rng.random()
        nw = int(rng.integers(90, 320))
        text = " ".join(rng.choice(words) for _ in range(nw))
        if kind < 0.12:
            parts.append(f"<h{int(rng.integers(1, 4))}>{text[:70]}</h2>")
        elif kind < 0.3:
            items = "".join(
                f"<li>{' '.join(rng.choice(words) for _ in range(int(rng.integers(14, 40))))}</li>"
                for _ in range(int(rng.integers(3, 8))))
            parts.append(f"<ul>{items}</ul>")
        elif kind < 0.45:
            inner = "".join(
                f"<p>{' '.join(rng.choice(words) for _ in range(int(rng.integers(80, 260))))}</p>"
                for _ in range(int(rng.integers(2, 4))))
            parts.append(f"<div style='padding:{pad}px;border:1px solid #ccc'>{inner}</div>")
        else:
            parts.append(f"<p>{text}</p>")
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>"
            f"body{{font-family:{fam};font-size:{fs}px;line-height:{lh};margin:{rng.integers(4, 40)}px;"
            f"column-count:{cols};column-gap:{rng.integers(10, 40)}px}}"
            f"p,ul,h1,h2,h3{{margin:0 0 {mb}px 0}}</style></head><body>"
            + "".join(parts) + "</body></html>")


def scenes(n_pages: int, seed: int = 0):
    """(gaps, crosses_a_real_boundary) per page, from real layout with exact labels."""
    from playwright.sync_api import sync_playwright
    rng = np.random.default_rng(seed)
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": VIEW[0], "height": VIEW[1]})
        for i in range(n_pages):
            pg.set_content(page_html(rng), wait_until="load")
            rects = pg.evaluate(LINE_BOXES_JS)
            if len(rects) < 6:
                continue
            rects.sort(key=lambda r: (round(r["left"] / 80), r["top"]))
            gaps, cross = [], []
            for a, z in zip(rects, rects[1:]):
                if abs(a["left"] - z["left"]) > 80:          # a column break, not a vertical gap
                    continue
                g = z["top"] - a["bottom"]
                if g < -2:
                    continue
                gaps.append(max(0.0, float(g)))
                cross.append(a["block"] != z["block"])
            if len(gaps) >= 6:
                out.append((np.array(gaps, float), np.array(cross, bool), i))
        b.close()
    return out


def features(g: np.ndarray) -> np.ndarray:
    """Scale-free description of a gap set, so what is learned is not the units of one domain.

    Everything is a ratio or a shape statistic. A prior expressed in pixels could not transfer to
    seconds, and transfer is the only thing that would make this a prior rather than a page rule."""
    v = np.sort(np.asarray(g, float))
    n = len(v)
    e = evidence(v, draws=60)
    rng_ = float(v[-1] - v[0]) or 1e-9
    d = np.diff(v)
    med = float(np.median(d[d > 0])) if np.any(d > 0) else 1e-9
    sd = float(v.std()) or 1e-9
    return np.array([
        np.log(n),
        e["eta2"],
        float(d.max()) / rng_ if len(d) else 0.0,
        float(d.max()) / med if len(d) else 0.0,
        float(d.max()) / sd if len(d) else 0.0,
        float((v.mean() - np.median(v)) / sd),
        float(np.mean((v - v.mean()) ** 3) / sd ** 3),
        float(v[-1] / max(np.median(v), 1e-9)),
    ], float), e["p"]


SIZES = (6, 8, 10, 12, 16, 24)


def windows(scenes_, per: int = 5, seed: int = 0):
    """Sub-windows at FIXED sizes, because window size was leaking the answer.

    The first version drew n uniformly from a range and evaluated in bands, and the shuffled-label
    control scored 0.849 at small n -- which is impossible unless something other than the labels was
    predicting them. It was n itself: a twelve-gap window is likelier to contain a boundary than a
    six-gap one, so any weight at all on log(n) buys AUC inside a band where n still varies. The gain
    measured that, not what a boundary looks like.

    Fixing n per evaluation removes the confound entirely: within one size there is nothing for window
    length to say. It is also the honest form of the question, which was never "can you decide on a
    window of five to twelve" but "can you decide on ten"."""
    rng = np.random.default_rng(seed)
    X, y, N, P, pg = [], [], [], [], []
    for g, c, idx in scenes_:
        for n in SIZES:
            if n > len(g):
                continue
            for _ in range(per):
                s = int(rng.integers(0, len(g) - n + 1))
                f, p = features(g[s:s + n])
                X.append(f)
                y.append(bool(c[s:s + n].any()))
                N.append(n)
                P.append(p)
                pg.append(idx)
    return np.array(X), np.array(y), np.array(N), np.array(P), np.array(pg)


def fit(X, y, iters: int = 4000, lr: float = 0.25):
    """Logistic regression by hand: eight features do not need a library, and this keeps it inspectable."""
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = np.hstack([(X - mu) / sd, np.ones((len(X), 1))])
    w = np.zeros(Z.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-Z @ w))
        w -= lr * (Z.T @ (p - y)) / len(y)
    return (mu, sd, w)


def predict(m, X):
    mu, sd, w = m
    Z = np.hstack([(X - mu) / sd, np.ones((len(X), 1))])
    return 1.0 / (1.0 + np.exp(-Z @ w))


def auc(score, label) -> float:
    s, l = np.asarray(score, float), np.asarray(label, bool)
    if l.all() or not l.any():
        return float("nan")
    r = np.argsort(np.argsort(s)) + 1
    n1, n0 = int(l.sum()), int((~l).sum())
    return float((r[l].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=200)
    a = ap.parse_args()

    sc = scenes(a.pages)
    print(f"rendered {len(sc)} usable pages of {a.pages} in Chromium at {VIEW[0]}x{VIEW[1]}")
    per_page_gaps = [len(g) for g, _c, _i in sc]
    print(f"line gaps per page: median {np.median(per_page_gaps):.0f}, "
          f"range {min(per_page_gaps)}-{max(per_page_gaps)}")

    X, y, N, P, pg = windows(sc)
    pages = np.unique(pg)
    cut = pages[int(0.7 * len(pages))]
    tr, te = pg < cut, pg >= cut
    print(f"\ngap sets: {len(X)}   boundary present in {y.mean():.1%}   "
          f"train {tr.sum()} on {len(np.unique(pg[tr]))} pages / test {te.sum()} on "
          f"{len(np.unique(pg[te]))} pages")
    print(f"-> 1. corpus is not degenerate: {0.05 < y.mean() < 0.95 and len(sc) > 20}")
    print(f"-> 2. no page is in both splits: {not (set(pg[tr]) & set(pg[te]))}")

    m = fit(X[tr], y[tr])
    learned = predict(m, X[te])
    per_scene = 1.0 - P[te]                       # the per-scene test's own confidence that a cut exists
    rng = np.random.default_rng(7)
    m_ctl = fit(X[tr], rng.permutation(y[tr]))
    ctl = predict(m_ctl, X[te])

    # REPORTED AT EACH FIXED n, never in bands. Bands were what hid the confound: a "5-12" band still
    # lets window length vary inside it, and the shuffled control scored 0.849 there off log(n) alone.
    # The control's own spread is printed too, because a near-constant predictor's AUC is a ranking of
    # floating-point dust and would look like a baseline without being one.
    print(f"\n{'gap set size (FIXED)':<22}{'sets':>7}{'base':>8}{'per-scene AUC':>15}"
          f"{'LEARNED AUC':>13}{'shuffled':>10}{'ctl span':>10}")
    rows = {}
    for n_fixed in SIZES:
        s = te & (N == n_fixed)
        if s.sum() < 40:
            continue
        b = auc(1.0 - P[s], y[s])
        L = auc(predict(m, X[s]), y[s])
        pc = predict(m_ctl, X[s])
        c = auc(pc, y[s])
        span = float(pc.max() - pc.min())
        rows[f"n={n_fixed}"] = {"sets": int(s.sum()), "base_rate": float(y[s].mean()),
                                "per_scene_auc": b, "learned_auc": L, "shuffled_auc": c,
                                "ctl_span": span}
        print(f"{f'n = {n_fixed}':<22}{int(s.sum()):>7}{y[s].mean():>8.1%}{b:>15.3f}"
              f"{L:>13.3f}{c:>10.3f}{span:>10.3f}")

    small = rows.get("n=10")
    all_b, all_L = auc(per_scene, y[te]), auc(learned, y[te])
    print(f"\n{'ALL n':<22}{int(te.sum()):>7}{y[te].mean():>8.1%}{all_b:>15.3f}{all_L:>13.3f}"
          f"{auc(ctl, y[te]):>10.3f}")

    v = preflight.run("S5b: a cross-scene prior beats the per-scene test where the per-scene test cannot",
                      observed_source="chromium layout", intended_source="chromium layout",
                      base_rate=float(y[te].mean()), n=int(te.sum()),
                      real_score=(small or {}).get("learned_auc"),
                      control_score=(small or {}).get("per_scene_auc"),
                      target_size=abs((small or {}).get("learned_auc", 0.5) - 0.5),
                      unit_size=abs((small or {}).get("shuffled_auc", 0.5) - 0.5) or 0.02)
    print(f"\n-> PREFLIGHT  may_promote: {v.may_promote}")
    for c in v.checks:
        mark = "green" if c.green else ("FAILED" if c.ran else "COULD NOT RUN")
        print(f"     {c.name:<14}{mark:<15}{c.detail}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"pages": len(sc), "sets": int(len(X)),
                               "base_rate": float(y.mean()), "by_n": rows,
                               "all_per_scene_auc": all_b, "all_learned_auc": all_L,
                               "weights": [float(x) for x in m[2]],
                               "preflight": v.as_dict()}, indent=2), encoding="utf-8")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
