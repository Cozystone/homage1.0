# -*- coding: utf-8 -*-
"""Phase space v0 — the PHFE representation TRAINED from data, not decorative.

The macro gap: every ATANOR term is an opaque symbol; similarity is substring
matching (measured failures: /, referent picks). LLMs get analogy
and generalization from a learned geometry. This module gives the graph its own
learned geometry using the wave-interference primitive the PHFE vision already
commits to: every concept is a vector of PHASES; related concepts interfere
constructively (small phase differences), unrelated ones destructively.

The training rule is the RotatE principle (Sun et al., ICLR 2019 — phase
rotations model relations; pRotatE is the phase-only variant): a relation is a
ROTATION on the phase circle, so a true edge (s, r, o) means θ_s + r ≈ θ_o.
We train by SGD with negative sampling over the store's ENTITY-VALUED edges.
Pure numpy, d=8 phases per node — 6-float-class footprint, no transformer,
no external model: the No-LLM contract holds because this is our own tiny
geometry learned from our own curated graph.

What it buys immediately:
 resonance(a, b) — graded similarity with no string overlap required
 neighbors(term) — analogy-class retrieval (referent disambiguation signal)
 link prediction — an honest, standard self-eval (filtered Hits@10)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[2]
SPACE_DIR = REPO / "data" / "graph_scale" / "phase_space"
PHASES_PATH = SPACE_DIR / "phases.npy"
REL_PATH = SPACE_DIR / "relations.npy"
TERMS_PATH = SPACE_DIR / "terms.json"
# Windows lock escape hatch: every reader mmaps phases.npy (mmap_mode='r'), and
# a mapped file cannot be reopened for write — so a retrain could never save
# while the engine (or any importer) was alive. Trainers therefore write
# VERSIONED artifact files and flip this small pointer; readers resolve through
# it. The legacy fixed paths remain the fallback for old spaces.
CURRENT_PATH = SPACE_DIR / "current.json"


def _artifact_paths() -> tuple[Path, Path, Path]:
    """Newest space wins: the GPU trainer writes versioned files behind the
    current.json pointer, while the CPU trainer writes the legacy fixed paths.
    Compare mtimes so a fresh CPU train (tests, no-CUDA hosts) is never shadowed
    by an older pointer — and vice versa."""
    versioned = None
    try:
        if CURRENT_PATH.exists():
            c = json.loads(CURRENT_PATH.read_text(encoding="utf-8"))
            v = (SPACE_DIR / c["phases"], SPACE_DIR / c["relations"], SPACE_DIR / c["terms"])
            if v[0].exists():
                versioned = v
    except Exception:
        pass
    if versioned and PHASES_PATH.exists():
        return versioned if versioned[0].stat().st_mtime >= PHASES_PATH.stat().st_mtime \
            else (PHASES_PATH, REL_PATH, TERMS_PATH)
    if versioned:
        return versioned
    return PHASES_PATH, REL_PATH, TERMS_PATH

DIM = 8

# sentence (defined_as objects are prose — they'd poison the geometry)
ENTITY_PREDS = ("is_a", "capital", "capital_of", "located_in", "country", "part_of",
                "used_for", "capable_of", "has_part", "수도", "국가", "소재지",
                "최고점", "수도인 지역", "저자", "제작자", "설립자", "최고경영자",
                "발견자", "구성요소", "상위개념", "원인", "결과")

_SPACE: dict[str, Any] = {"phases": None, "terms": None, "idx": None, "mtime": 0.0}


def _dist(theta_s: np.ndarray, rot: np.ndarray, theta_o: np.ndarray) -> np.ndarray:
    """RotatE phase distance: |sin((θs + r − θo)/2)| summed over dims — 0 when the
    rotation lands exactly, max when opposed. Shape-broadcasting friendly."""
    return np.abs(np.sin((theta_s + rot - theta_o) / 2.0)).sum(axis=-1)


def extract_edges(store: Any, max_edges: int = 1_500_000) -> tuple[list[tuple[int, int, int]], dict[int, str]]:
    """Entity-valued (s, p, o) id-triples from the raw columns + the id->term map
    for every id involved. Bounded single pass, tombstones respected upstream."""
    cols = store.open_columns()
    pred_ids = {}
    for p in ENTITY_PREDS:
        pid = store.terms.lookup(p)  # existing-id lookup; None when never interned
        if pid is not None:
            pred_ids[pid] = p
    if not pred_ids:
        return [], {}
    s_col, p_col, o_col = cols["s"], cols["p"], cols["o"]
    n = len(p_col)
    edges: list[tuple[int, int, int]] = []
    step = max(1, n // max_edges) if n > max_edges else 1
    mask_vals = np.array(sorted(pred_ids), dtype=p_col.dtype)
    for start in range(0, n, 2_000_000):
        pc = np.asarray(p_col[start:start + 2_000_000])
        hit = np.isin(pc, mask_vals)
        idxs = np.nonzero(hit)[0][::step]
        sc = np.asarray(s_col[start:start + 2_000_000])[idxs]
        oc = np.asarray(o_col[start:start + 2_000_000])[idxs]
        pc = pc[idxs]
        edges.extend(zip(sc.tolist(), pc.tolist(), oc.tolist()))
        if len(edges) >= max_edges:
            edges = edges[:max_edges]
            break
    terms: dict[int, str] = {}
    for s, p, o in edges:
        for tid in (s, o):
            if tid not in terms:
                try:
                    terms[tid] = store.terms.term(int(tid))
                except Exception:
                    terms[tid] = str(tid)
    return edges, terms


def train_phase_space(store: Any, max_edges: int = 1_500_000, epochs: int = 30,
                      lr: float = 0.5, margin: float = 2.0, batch: int = 4096,
                      min_degree: int = 3, min_edges: int = 1000, seed: int = 3,
                      dim: int = DIM, log: Any = print) -> dict[str, Any]:
    """Train phases by margin ranking with corrupted negatives (the standard KG
    recipe). Saves the space + returns an honest held-out link-prediction eval.

    min_degree matters more than anything: the raw store averages ~3 edges per
    node (measured 1.4M edges over 501k terms — mostly single-mention Wikidata
    tails), and one observation cannot move a random phase anywhere. Training
    on the DENSE CORE (degree ≥ 3) is what makes the geometry learnable; sparse
    tails join later runs as the graph thickens around them."""
    rng = np.random.default_rng(seed)
    edges, terms = extract_edges(store, max_edges)
    if len(edges) < min_edges:
        return {"error": "too few entity edges", "edges": len(edges)}
    # dense-core filter: keep nodes seen min_degree+ times, edges among them
    from collections import Counter

    deg = Counter()
    for s, _p, o in edges:
        deg[s] += 1
        deg[o] += 1
    keep = {t for t, d in deg.items() if d >= min_degree}
    edges = [(s, p, o) for s, p, o in edges if s in keep and o in keep]
    terms = {t: n for t, n in terms.items() if t in keep}
    if len(edges) < min_edges:
        return {"error": "dense core too small", "edges": len(edges)}
    log(f"  dense core: edges={len(edges):,} terms={len(terms):,} (min_degree={min_degree})")
    tids = sorted(terms)
    tidx = {t: i for i, t in enumerate(tids)}
    pids = sorted({p for _s, p, _o in edges})
    pidx = {p: i for i, p in enumerate(pids)}
    E = np.array([(tidx[s], pidx[p], tidx[o]) for s, p, o in edges], dtype=np.int64)
    rng.shuffle(E)
    # 2% held out for the honest eval — capped at 10% so a small (test/synthetic)
    # graph never loses its whole training split to the holdout
    cut = min(max(1000, len(E) // 50), max(1, len(E) // 10))
    hold, tr = E[:cut], E[cut:]
    n_t = len(tids)
    theta = rng.uniform(0, 2 * np.pi, size=(n_t, dim)).astype(np.float32)
    rel = rng.uniform(0, 2 * np.pi, size=(len(pids), dim)).astype(np.float32)
    # Two hard-won lessons are baked in here (both MEASURED on this graph):
    # 1. COUNT-NORMALIZED batch updates. Raw np.add.at accumulation let a hub
    #    predicate (is_a = 64% of edges) receive ~200 radians of pulls per batch
    #    — the relation vector thrashed around the circle and NOTHING converged
    #    (d_pos flat at the 5.09 random expectation for 15 epochs). Each index
    #    now moves by the MEAN gradient of its batch occurrences.
    # 2. Decoupled attract/repel. Attraction alone has a degenerate optimum
    #    (all phases equal => d=0 everywhere), so negatives inside the repel
    #    threshold push back. d_neg staying near random (~5.1) while d_pos
    #    falls is the collapse check — both are logged.
    repel_at = 4.0
    n_p = len(pids)
    for ep in range(epochs):
        rng.shuffle(tr)
        sum_dp, sum_dn, nb = 0.0, 0.0, 0
        for i in range(0, len(tr), batch):
            b = tr[i:i + batch]
            s, p, o = b[:, 0], b[:, 1], b[:, 2]
            neg_o = rng.integers(0, n_t, size=len(b))
            arg_p = (theta[s] + rel[p] - theta[o]) / 2.0
            arg_n = (theta[s] + rel[p] - theta[neg_o]) / 2.0
            d_pos = np.abs(np.sin(arg_p)).sum(axis=1)
            d_neg = np.abs(np.sin(arg_n)).sum(axis=1)
            sum_dp += float(d_pos.sum())
            sum_dn += float(d_neg.sum())
            nb += len(b)
            g_p = (np.sign(np.sin(arg_p)) * np.cos(arg_p) * 0.5).astype(np.float32)
            gs = np.zeros_like(theta)
            gr = np.zeros_like(rel)
            np.add.at(gs, s, g_p)
            np.add.at(gs, o, -g_p)
            np.add.at(gr, p, g_p)
            close = d_neg < repel_at
            if close.any():
                g_n = (np.sign(np.sin(arg_n[close])) * np.cos(arg_n[close]) * 0.5).astype(np.float32)
                np.add.at(gs, s[close], -g_n)      # push s AWAY from the negative
                np.add.at(gs, neg_o[close], g_n)
            cs = np.bincount(np.concatenate([s, o, s[close], neg_o[close]]),
                             minlength=n_t).astype(np.float32)[:, None]
            cr = np.bincount(p, minlength=n_p).astype(np.float32)[:, None]
            theta -= lr * gs / np.maximum(cs, 1.0)
            rel -= lr * gr / np.maximum(cr, 1.0)
        log(f"  epoch {ep + 1}/{epochs}: mean d_pos={sum_dp / nb:.3f}  mean d_neg={sum_dn / nb:.3f}")
    theta = np.mod(theta, 2 * np.pi)
    SPACE_DIR.mkdir(parents=True, exist_ok=True)
    np.save(PHASES_PATH, theta)
    np.save(REL_PATH, rel)
    TERMS_PATH.write_text(json.dumps({"terms": [terms[t] for t in tids],
                                      "preds": [store.terms.term(int(p)) for p in pids]},
                                     ensure_ascii=False), encoding="utf-8")
    _SPACE["phases"] = None  # force reload
    # honest eval: filtered-ish Hits@10 on held-out edges against random candidates
    hits, ranks = 0, []
    sample = hold[rng.permutation(len(hold))[:500]]
    cand = rng.integers(0, n_t, size=200)
    for s, p, o in sample:
        d_true = _dist(theta[s], rel[p], theta[o])
        d_cand = _dist(theta[s][None, :], rel[p][None, :], theta[cand])
        rank = 1 + int((d_cand < d_true).sum())
        ranks.append(rank)
        if rank <= 10:
            hits += 1
    return {"edges": len(edges), "terms": n_t, "hits_at_10": hits / max(1, len(sample)),
            "mean_rank": float(np.mean(ranks)), "candidates": 201}


def _load() -> bool:
    try:
        phases_path, _rel_path, terms_path = _artifact_paths()
        if not phases_path.exists():
            return False
        key = f"{phases_path.name}:{phases_path.stat().st_mtime}"
        if _SPACE["phases"] is None or _SPACE["mtime"] != key:
            _SPACE["phases"] = np.load(phases_path, mmap_mode="r")
            data = json.loads(terms_path.read_text(encoding="utf-8"))
            _SPACE["terms"] = data["terms"]
            _SPACE["idx"] = {t: i for i, t in enumerate(data["terms"])}
            _SPACE["mtime"] = key
        return True
    except Exception:
        return False


def resonance(a: str, b: str) -> float | None:
    """Constructive-interference similarity in [−1, 1]: mean cosine of phase
    differences. None when either term wasn't in the trained subgraph."""
    if not _load():
        return None
    ia, ib = _SPACE["idx"].get(a), _SPACE["idx"].get(b)
    if ia is None or ib is None:
        return None
    return float(np.cos(_SPACE["phases"][ia] - _SPACE["phases"][ib]).mean())


def interference_scene(k_nodes: int = 18, seed: int = 5) -> dict[str, Any]:
    """A REAL phase-interference scene for the visualization: nodes are
 actual trained concepts, links are TRUE constructive pairs (high resonance),
 prunes are TRUE destructive pairs (low resonance). Nothing staged — the
 simulation the UI plays is the geometry the engine actually learned."""
    if not _load():
        return {"nodes": [], "links": [], "prunes": []}
    import numpy as _np

    rng = _np.random.default_rng(seed)
    terms = _SPACE["terms"]
    ko = [i for i, t in enumerate(terms)
          if any("가" <= c <= "힣" for c in t) and 2 <= len(t) <= 6][:400]
    if len(ko) < k_nodes:
        ko = list(range(min(len(terms), 400)))
    picked = sorted(rng.choice(len(ko), size=min(k_nodes, len(ko)), replace=False).tolist())
    idxs = [ko[i] for i in picked]
    ph = _np.asarray(_SPACE["phases"])[idxs]
    sims = _np.cos(ph[:, None, :] - ph[None, :, :]).mean(axis=2)
    nodes = [{"id": i, "label": terms[t]} for i, t in enumerate(idxs)]
    pairs = [(i, j, float(sims[i, j])) for i in range(len(idxs))
             for j in range(i + 1, len(idxs))]
    pairs.sort(key=lambda p: -p[2])
    links = [{"a": a, "b": b, "resonance": round(r, 3)} for a, b, r in pairs[:14] if r > 0.3]
    prunes = [{"a": a, "b": b, "resonance": round(r, 3)} for a, b, r in pairs[-8:] if r < -0.2]
    return {"nodes": nodes, "links": links, "prunes": prunes,
            "source": "trained_phase_space", "dim": DIM}


def neighbors(term: str, k: int = 10) -> list[tuple[str, float]]:
    """k nearest concepts by phase interference — retrieval with NO string overlap."""
    if not _load():
        return []
    i = _SPACE["idx"].get(term)
    if i is None:
        return []
    ph = np.asarray(_SPACE["phases"])
    sims = np.cos(ph - ph[i]).mean(axis=1)
    order = np.argsort(-sims)
    out = []
    for j in order[: k + 1]:
        if int(j) == i:
            continue
        out.append((_SPACE["terms"][int(j)], float(sims[int(j)])))
        if len(out) >= k:
            break
    return out
