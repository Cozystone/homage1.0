# -*- coding: utf-8 -*-
"""The schema basis on a REALLY RENDERED page: pixels in, DOM as oracle, parent-child edges scored.

    python scripts/schema_on_real_render.py [--site URL]

The synthetic test showed the mechanism works -- F1 0.500 against a flat baseline's 0.222 -- on flat
colour blocks drawn by me. Its own caveat was that a real render is far harder: real text antialiasing,
font glyphs, borders, gradients and images. This is that test.

    input   a PNG rendered by Chromium. Nothing reads a tag.
    oracle  getBoundingClientRect() for every laid-out element, plus its nearest ancestor that is also
            laid out -- the true parent-child edges
    method  colour-uniform regions -> Gestalt grouping by PROXIMITY and size -> PART_WHOLE hierarchy

WHY REAL TEXT IS THE HARD PART AND THE POINT. Glyphs are high-contrast and tiny, so colour-uniform
segmentation shatters a paragraph into hundreds of fragments. A person does not see hundreds of things;
they see a block of text, because proximity binds glyphs into lines and lines into paragraphs before any
reading happens. So this measures whether the Gestalt step can do what a person does before it can be
said to see a page at all.

REGISTERED, the same three as the synthetic run so the comparison is like for like:
    1  beats a random-parent control
    2  beats the flat "everything is a child of the page" guess, which is the control that flatters
    3  PART_WHOLE is doing the work -- removing the hierarchy step must be worse
And one more, because a real render can fail in a way a synthetic one cannot:
    4  the region count must not explode into glyph fragments -- reported either way
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.image_schema import PartWhole, Proximity, RegionScene     # noqa: E402

OUT = Path("data/language/schema_on_real_render.json")
SHOT = Path("data/language/render.png")
PAGE = Path("data/language/page.html")
VIEW = (1000, 800)

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
 body{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,Arial;color:#222;background:#fafafa}
 header{background:#26355c;color:#fff;padding:14px 24px;display:flex;gap:22px;align-items:center}
 header .brand{font-weight:700;font-size:19px}
 nav a{color:#d8e0f5;text-decoration:none;padding:6px 10px;border-radius:6px;background:#33437099}
 .wrap{display:flex;gap:20px;padding:20px}
 aside{width:210px;background:#eceef3;border:1px solid #dcdfe8;border-radius:8px;padding:12px}
 aside .item{background:#fff;border:1px solid #e3e6ee;border-radius:6px;padding:8px 10px;margin:8px 0}
 main{flex:1;display:flex;flex-direction:column;gap:16px}
 .card{background:#fff;border:1px solid #e2e5ee;border-radius:10px;padding:14px 16px}
 .card h2{margin:0 0 8px;font-size:17px;color:#26355c}
 .card p{margin:0;color:#4a4f5e}
 footer{background:#2b2b31;color:#c9c9d2;padding:18px 24px;margin-top:20px}
</style></head><body>
 <header><span class="brand">Atanor</span><nav>
   <a href="#">Overview</a><a href="#">Perception</a><a href="#">Language</a><a href="#">Logs</a>
 </nav></header>
 <div class="wrap">
  <aside>
    <div class="item">Body finding</div><div class="item">Segmentation</div>
    <div class="item">Constancy</div><div class="item">Schemas</div><div class="item">Executor</div>
  </aside>
  <main>
   <div class="card"><h2>Object constancy</h2>
     <p>The same thing seen twice must be closer than two different things. Tracking supplies the
     supervision and no labels are read from anywhere.</p></div>
   <div class="card"><h2>Motion segmentation</h2>
     <p>Background subtraction sees only change, so a stationary sprite is removed by construction.
     A model that sees appearance can find one that is not moving.</p></div>
   <div class="card"><h2>Image schemas</h2>
     <p>Verbs are not primitive. A closed basis of about twenty relations underlies the action
     vocabulary of every language, and wiring cost stops growing with vocabulary.</p></div>
  </main>
 </div>
 <footer>Measured, not asserted.</footer>
</body></html>"""


def render(url: str | None):
    """Chromium renders; we take pixels and, separately, the true boxes. The DOM is the ORACLE only."""
    from playwright.sync_api import sync_playwright
    js = """() => {
      const out = [];
      const all = document.querySelectorAll('body *');
      all.forEach((el, i) => {
        const r = el.getBoundingClientRect();
        if (r.width < 8 || r.height < 8) return;
        if (r.bottom < 0 || r.top > window.innerHeight) return;
        el.setAttribute('data-k', 'e' + i);
        out.push({k: 'e' + i, box: [r.left, r.top, r.right, r.bottom], tag: el.tagName});
      });
      const keyed = {};
      out.forEach(o => keyed[o.k] = o);
      out.forEach(o => {
        let p = document.querySelector('[data-k="' + o.k + '"]').parentElement;
        while (p && !p.getAttribute('data-k')) p = p.parentElement;
        o.parent = p ? p.getAttribute('data-k') : 'PAGE';
      });
      return out;
    }"""
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": VIEW[0], "height": VIEW[1]})
        if url:
            pg.goto(url, wait_until="networkidle", timeout=30000)
        else:
            PAGE.parent.mkdir(parents=True, exist_ok=True)
            PAGE.write_text(HTML, encoding="utf-8")
            pg.goto(PAGE.resolve().as_uri(), wait_until="load")
        els = pg.evaluate(js)
        pg.screenshot(path=str(SHOT))
        b.close()
    import cv2
    img = cv2.cvtColor(cv2.imread(str(SHOT)), cv2.COLOR_BGR2RGB)
    truth = {e["k"]: tuple(e["box"]) for e in els}
    parent = {e["k"]: e["parent"] for e in els}
    return img, truth, parent


def regions_from_pixels(img, min_px: int = 150) -> dict:
    """Colour-uniform regions. Connectivity would merge a child into its parent, which is the structure."""
    import cv2
    q = (img.astype(np.int16) // 16)
    key = q[:, :, 0] * 4096 + q[:, :, 1] * 64 + q[:, :, 2]
    out, i = {}, 0
    H, W = img.shape[:2]
    for k in np.unique(key):
        m = (key == k).astype(np.uint8)
        n, _lab, st, _c = cv2.connectedComponentsWithStats(m, 8)
        for j in range(1, n):
            if st[j, cv2.CC_STAT_AREA] < min_px:
                continue
            x, y, w, h = (st[j, cv2.CC_STAT_LEFT], st[j, cv2.CC_STAT_TOP],
                          st[j, cv2.CC_STAT_WIDTH], st[j, cv2.CC_STAT_HEIGHT])
            if w * h >= H * W * 0.9:
                continue
            i += 1
            out[f"r{i}"] = (float(x), float(y), float(x + w), float(y + h))
    return out


def gestalt_groups(scene: RegionScene, names: list, max_groups: int = 400) -> list:
    seen, groups = set(), []
    for a in names:
        if a in seen or len(groups) >= max_groups:
            continue
        grp = [a]
        seen.add(a)
        for b in names:
            if b in seen:
                continue
            near = Proximity(a, b).signed(scene)
            if near is None or near < 0.5:
                continue
            sa, sb = scene._area(a), scene._area(b)
            if sa <= 0 or sb <= 0 or max(sa, sb) / min(sa, sb) > 4.0:
                continue
            grp.append(b)
            seen.add(b)
        if len(grp) > 1:
            groups.append(grp)
    return groups


def recover(img, use_hierarchy=True, random_parent=False, flat=False, seed=0):
    regs = regions_from_pixels(img)
    names = sorted(regs)
    if flat:
        return {n: "PAGE" for n in names}, regs
    rng = np.random.default_rng(seed)
    if random_parent:
        return ({n: (str(rng.choice([m for m in names if m != n])) if len(names) > 1 else "PAGE")
                 for n in names}, regs)
    scene0 = RegionScene(regs)
    boxes = dict(regs)
    for i, g in enumerate(gestalt_groups(scene0, names)):
        xs = [regs[n] for n in g]
        boxes[f"g{i}"] = (min(b[0] for b in xs), min(b[1] for b in xs),
                          max(b[2] for b in xs), max(b[3] for b in xs))
    scene = RegionScene(boxes)
    par = {}
    for n in names:
        best, area = None, 0.0
        if use_hierarchy:
            for w in boxes:
                if w == n:
                    continue
                d = PartWhole(n, w).signed(scene)
                if d is None or d < 0.9:
                    continue
                a = scene._area(w)
                if a > 0 and (best is None or a < area):
                    best, area = w, a
        par[n] = best or "PAGE"
    return par, regs


def score(pred, regs, truth, parent) -> dict:
    def match(box):
        best, iou = None, 0.0
        for t, tb in truth.items():
            w = max(0.0, min(box[2], tb[2]) - max(box[0], tb[0]))
            h = max(0.0, min(box[3], tb[3]) - max(box[1], tb[1]))
            inter = w * h
            u = ((box[2] - box[0]) * (box[3] - box[1])
                 + (tb[2] - tb[0]) * (tb[3] - tb[1]) - inter)
            if u > 0 and inter / u > iou:
                best, iou = t, inter / u
        return best if iou > 0.4 else None

    ident = {r: match(b) for r, b in regs.items()}
    tp = fp = 0
    for r, p in pred.items():
        t = ident.get(r)
        if t is None:
            continue
        true_par = parent.get(t, "PAGE")
        if p == "PAGE":
            pred_par = "PAGE"
        elif p in ident:
            pred_par = ident[p]
        else:
            members = [m for m, q in pred.items() if q == p and ident.get(m)]
            pred_par = ident[members[0]] if members else None
        if pred_par == true_par:
            tp += 1
        else:
            fp += 1
    n = tp + fp
    prec = tp / max(n, 1)
    # RECALL IS AGAINST ALL TRUE EDGES, not against the regions that happened to match.
    # The first version returned recall = precision, which reported 1.000 for getting every edge right
    # among the TEN of twenty-five elements that matched at all -- a precision on a filtered subset,
    # mislabelled as F1. The unmatched fifteen are the hard ones (text runs, nav links), and a metric
    # that silently drops them measures the filter rather than the method.
    rec = tp / max(len(truth), 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    return {"matched": n, "true_elements": len(truth), "precision": prec, "recall": rec, "f1": f1}


def main() -> None:
    url = None
    if "--site" in sys.argv:
        url = sys.argv[sys.argv.index("--site") + 1]
    img, truth, parent = render(url)
    print(f"rendered {'a live site: ' + url if url else 'a local page'} at {VIEW[0]}x{VIEW[1]}")
    print(f"oracle: {len(truth)} laid-out elements, "
          f"{sum(1 for v in parent.values() if v != 'PAGE')} nested edges (DOM is truth ONLY)\n")

    regs = regions_from_pixels(img)
    print(f"regions recovered from PIXELS: {len(regs)}   (synthetic gave 18 from 26)\n")

    arms = {"SCHEMA (Gestalt + PART_WHOLE)": {}, "no hierarchy step": {"use_hierarchy": False},
            "flat: everything is the page": {"flat": True},
            "random parent (control)": {"random_parent": True}}
    print(f"{'method':<34}{'matched':>9}{'precision':>11}{'recall':>9}{'F1':>8}")
    res = {}
    for name, kw in arms.items():
        pred, r = recover(img, **kw)
        sc = score(pred, r, truth, parent)
        res[name] = sc
        print(f"{name:<34}{sc['matched']:>9}{sc['precision']:>11.3f}"
              f"{sc['recall']:>9.3f}{sc['f1']:>8.3f}", flush=True)

    S = res["SCHEMA (Gestalt + PART_WHOLE)"]
    print(f"\n-> 1. beats random parent: {S['f1'] > res['random parent (control)']['f1'] + 0.05}  "
          f"({res['random parent (control)']['f1']:.3f})")
    print(f"-> 2. beats the flat page guess: "
          f"{S['f1'] > res['flat: everything is the page']['f1'] + 0.05}  "
          f"({res['flat: everything is the page']['f1']:.3f})")
    print(f"-> 3. PART_WHOLE does the work: {S['f1'] > res['no hierarchy step']['f1'] + 0.05}  "
          f"({res['no hierarchy step']['f1']:.3f})")
    print(f"-> 4. no glyph explosion: {len(regs) < 10 * len(truth)}  "
          f"({len(regs)} regions for {len(truth)} elements)")
    print(f"\n   recall is over ALL {len(truth)} true elements; only {S['matched']} matched a region")
    print("   at IoU>0.4 at all, and the unmatched ones are the hard cases -- text runs and links.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"url": url, "elements": len(truth), "regions": len(regs),
                               "arms": res}, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}; render at {SHOT}")


if __name__ == "__main__":
    main()
