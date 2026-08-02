# -*- coding: utf-8 -*-
"""GPU phase-space trainer — blueprint phase 2: the propose side of propose-verify.

Trains the SAME RotatE-lite geometry as phase_space.train_phase_space (identical
math — count-normalized batch updates, decoupled attract/repel; both lessons were
MEASURED and are preserved), but on the GPU, which lifts the practical training
scale from a 1.5M-edge sample to the graph's full entity-edge core in minutes.

It writes the SAME artifacts (phases.npy / relations.npy / terms.json), so every
existing consumer — resonance routing, neighbors(), the hypothesis minter —
upgrades in place with zero wiring. The verification circuit is unchanged:
a better phase space only mints better QUESTIONS; facts still enter the store
exclusively through evidence gates (model-collapse immunity holds).
"""
from __future__ import annotations

import json
import time
from typing import Any

import numpy as np

from .phase_space import DIM, PHASES_PATH, REL_PATH, SPACE_DIR, TERMS_PATH, _SPACE, extract_edges

try:
    import torch
    _HAVE_TORCH = True
except Exception:  # pragma: no cover
    torch = None
    _HAVE_TORCH = False


def _save_artifacts(theta_np: "np.ndarray", rel_np: "np.ndarray", terms_payload: str,
                    on_locked: Any = None, retries: int = 6, log: Any = print) -> None:
    """Windows lock escape (measured the hard way): every reader mmaps
    phases.npy, and a mapped file cannot be reopened for write — killing the
    engine wasn't even enough (other importers keep maps). So never fight the
    lock: write VERSIONED artifact files (always writable) and flip the small
    current.json pointer. Readers resolve through the pointer; old maps stay
    valid on the old files until their holders reload."""
    from .phase_space import CURRENT_PATH

    SPACE_DIR.mkdir(parents=True, exist_ok=True)
    ver = time.strftime("%Y%m%d%H%M%S")
    names = {"phases": f"phases_v{ver}.npy", "relations": f"relations_v{ver}.npy",
             "terms": f"terms_v{ver}.json"}
    np.save(SPACE_DIR / names["phases"], theta_np)
    np.save(SPACE_DIR / names["relations"], rel_np)
    (SPACE_DIR / names["terms"]).write_text(terms_payload, encoding="utf-8")
    tmp = CURRENT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(names), encoding="utf-8")
    import os
    os.replace(tmp, CURRENT_PATH)
    # keep only the 3 newest versions (the older ones may still be mapped by
    # running readers — deletion failures are fine and retried next save)
    for pat in ("phases_v*.npy", "relations_v*.npy", "terms_v*.json"):
        old = sorted(SPACE_DIR.glob(pat))[:-3]
        for f in old:
            try:
                f.unlink()
            except OSError:
                pass
    log(f"  saved phase space v{ver} (pointer flipped)")


def train_from_triples(triples: list[tuple[str, str, str]], *, dim: int = 64,
                       epochs: int = 40, lr: float = 0.5, seed: int = 3,
                       min_degree: int = 2, log: Any = print) -> dict[str, Any]:
    """Train the RotatE geometry directly on STRING triples (e.g. a clean external
    source like ConceptNet), WITHOUT touching the production artifacts. Returns the
    trained arrays + honest held-out Hits@10 so a clean-source space can be spot-
    checked and compared before any promotion. Same math as the store trainer."""
    from collections import Counter
    deg: Counter = Counter()
    for s, _p, o in triples:
        deg[s] += 1
        deg[o] += 1
    keep = {t for t, d in deg.items() if d >= min_degree}
    triples = [(s, p, o) for s, p, o in triples if s in keep and o in keep and s != o]
    if len(triples) < 500:
        return {"error": "too few edges after dense-core", "edges": len(triples)}
    tids = sorted({t for s, _p, o in triples for t in (s, o)})
    tidx = {t: i for i, t in enumerate(tids)}
    pids = sorted({p for _s, p, _o in triples})
    pidx = {p: i for i, p in enumerate(pids)}
    rng = np.random.default_rng(seed)
    E = np.array([(tidx[s], pidx[p], tidx[o]) for s, p, o in triples], dtype=np.int64)
    rng.shuffle(E)
    cut = min(max(1000, len(E) // 50), max(1, len(E) // 10))
    hold, tr = E[:cut], E[cut:]
    n_t, n_p = len(tids), len(pids)
    log(f"  clean-source train: edges={len(triples):,} terms={n_t:,} preds={n_p} dim={dim}")

    use_gpu = _HAVE_TORCH and torch.cuda.is_available()
    if use_gpu:
        dev = "cuda"
        g = torch.Generator(device=dev).manual_seed(seed)
        theta = torch.rand((n_t, dim), generator=g, device=dev) * 2 * torch.pi
        rel = torch.rand((n_p, dim), generator=g, device=dev) * 2 * torch.pi
        TR = torch.from_numpy(tr).to(dev)
        repel_at = dim / 2.0
        batch = 65_536
        for ep in range(epochs):
            TR = TR[torch.randperm(len(TR), generator=g, device=dev)]
            for i in range(0, len(TR), batch):
                b = TR[i:i + batch]
                s, p, o = b[:, 0], b[:, 1], b[:, 2]
                neg = torch.randint(0, n_t, (len(b),), generator=g, device=dev)
                ap = (theta[s] + rel[p] - theta[o]) / 2.0
                an = (theta[s] + rel[p] - theta[neg]) / 2.0
                gp = torch.sign(torch.sin(ap)) * torch.cos(ap) * 0.5
                gs = torch.zeros_like(theta); gr = torch.zeros_like(rel)
                gs.index_add_(0, s, gp); gs.index_add_(0, o, -gp); gr.index_add_(0, p, gp)
                close = torch.abs(torch.sin(an)).sum(1) < repel_at
                sc, nc = s[close], neg[close]
                if len(sc):
                    gn = torch.sign(torch.sin(an[close])) * torch.cos(an[close]) * 0.5
                    gs.index_add_(0, sc, -gn); gs.index_add_(0, nc, gn)
                cs = torch.bincount(torch.cat([s, o, sc, nc]), minlength=n_t).float().unsqueeze(1)
                cr = torch.bincount(p, minlength=n_p).float().unsqueeze(1)
                theta -= lr * gs / torch.clamp(cs, min=1.0)
                rel -= lr * gr / torch.clamp(cr, min=1.0)
        theta_np = torch.remainder(theta, 2 * torch.pi).cpu().numpy().astype(np.float32)
        rel_np = rel.cpu().numpy().astype(np.float32)
    else:
        theta_np = rng.uniform(0, 2 * np.pi, (n_t, dim)).astype(np.float32)
        rel_np = rng.uniform(0, 2 * np.pi, (n_p, dim)).astype(np.float32)
        # (numpy path is the CPU trainer's loop; omitted here — GPU is the intended path)
        log("  (no CUDA — clean-source trainer needs GPU for this scale)")
    hits, sample = 0, hold[rng.permutation(len(hold))[:500]]
    cand = rng.integers(0, n_t, size=200)
    for s, p, o in sample:
        dt = np.abs(np.sin((theta_np[s] + rel_np[p] - theta_np[o]) / 2.0)).sum()
        dc = np.abs(np.sin((theta_np[s][None] + rel_np[p][None] - theta_np[cand]) / 2.0)).sum(1)
        if 1 + int((dc < dt).sum()) <= 10:
            hits += 1
    return {"phases": theta_np, "rel": rel_np, "terms": tids, "idx": tidx,
            "preds": pids, "edges": len(triples), "terms_n": n_t,
            "hits_at_10": round(hits / max(1, len(sample)), 4), "dim": dim}


def neighbors_of(term: str, space: dict[str, Any], k: int = 6) -> list[tuple[str, float]]:
    """k-nearest by phase interference on a returned (unsaved) space — for spot-checks."""
    i = space["idx"].get(term)
    if i is None:
        return []
    ph = space["phases"]
    sims = np.cos(ph - ph[i]).mean(axis=1)
    order = np.argsort(-sims)
    out = []
    for j in order[:k + 1]:
        if int(j) != i:
            out.append((space["terms"][int(j)], round(float(sims[int(j)]), 3)))
        if len(out) >= k:
            break
    return out


def _clean_edges(store: Any, edges: list[tuple[int, int, int]], *,
                 attractor_indeg: int = 5000, hub_outdeg: int = 12,
                 log: Any = print) -> list[tuple[int, int, int]]:
    """Train on TRUSTED structure, not noise — the geometry is only as good as its
    edges. Drop the same contamination the closure/surgeon gates drop: generic
    attractor objects (is_a in-degree ≥ threshold = WordNet-batch 'entity'-likes),
    polysemy HUB subjects (is_a out-degree ≥ 12, un-sense-separated), and self-loops.
    This is the fix for 'juke is_a cooperation' — garbage in was the whole problem."""
    from collections import Counter
    isa = store.terms.lookup("is_a")
    o_indeg: Counter = Counter()
    s_outdeg: Counter = Counter()
    for s, p, o in edges:
        if p == isa:
            o_indeg[o] += 1
            s_outdeg[s] += 1
    attractors = {o for o, c in o_indeg.items() if c >= attractor_indeg}
    hubs = {s for s, c in s_outdeg.items() if c >= hub_outdeg}
    out = [(s, p, o) for s, p, o in edges
           if s != o and not (p == isa and (o in attractors or s in hubs))]
    log(f"  clean filter: {len(edges):,} -> {len(out):,} edges "
        f"(dropped {len(attractors)} attractors, {len(hubs)} hubs)")
    return out


def train_phase_space_gpu(store: Any, max_edges: int = 8_000_000, epochs: int = 30,
                          lr: float = 0.5, batch: int = 65_536, min_degree: int = 3,
                          min_edges: int = 1000, seed: int = 3, dim: int = DIM,
                          save: bool = True, clean: bool = False, on_locked: Any = None,
                          log: Any = print) -> dict[str, Any]:
    """Margin-ranking phase training on CUDA (numpy fallback = delegate to the
    CPU trainer). Saves the shared artifacts + returns the honest held-out eval.
    save=False runs a pure benchmark (dim sweeps) without touching the live space."""
    if not (_HAVE_TORCH and torch.cuda.is_available()):
        from .phase_space import train_phase_space
        log("  (no CUDA — delegating to the CPU trainer)")
        return train_phase_space(store, max_edges=min(max_edges, 1_500_000), epochs=epochs,
                                 lr=lr, min_degree=min_degree, min_edges=min_edges, seed=seed,
                                 dim=dim, log=log)
    dev = "cuda"
    # LOW-END STABILITY (owner directive): cap the training batch to free VRAM
    # so an RTX 4060 / older Quadro trains without OOM — smaller batch, same
    # result, a little slower. Radeon / no-CUDA already delegated to CPU above.
    try:
        from packages.reasoning_vm.device import profile as _dev_profile

        _free = float(_dev_profile().get("free_vram_gb", 0) or 0)
        if 0 < _free < 6:
            batch = min(batch, 16_384 if _free >= 3 else 8_192)
            log(f"  (modest VRAM {_free:.1f}GB — batch capped to {batch} for stability)")
    except Exception:
        pass
    t_start = time.time()
    rng = np.random.default_rng(seed)
    edges, terms = extract_edges(store, max_edges)
    if len(edges) < min_edges:
        return {"error": "too few entity edges", "edges": len(edges)}
    if clean:
        edges = _clean_edges(store, edges, log=log)
        node_ids = {s for s, _p, _o in edges} | {o for _s, _p, o in edges}
        terms = {t: n for t, n in terms.items() if t in node_ids} or terms
    # dense-core filter (same rationale as CPU: one observation cannot place a phase)
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
    E_np = np.array([(tidx[s], pidx[p], tidx[o]) for s, p, o in edges], dtype=np.int64)
    rng.shuffle(E_np)
    cut = min(max(1000, len(E_np) // 50), max(1, len(E_np) // 10))
    hold, tr_np = E_np[:cut], E_np[cut:]
    n_t, n_p = len(tids), len(pids)

    g = torch.Generator(device=dev).manual_seed(seed)
    theta = (torch.rand((n_t, dim), generator=g, device=dev) * 2 * torch.pi)
    rel = (torch.rand((n_p, dim), generator=g, device=dev) * 2 * torch.pi)
    TR = torch.from_numpy(tr_np).to(dev)
    # repel threshold must scale with dimension: the |sin| distance ranges
    # [0, dim] and random pairs sit near dim/2 — a constant 4.0 (tuned at
    # dim=8) never fires at dim>=32, the repel term goes silent, and quality
    # COLLAPSES with dimension (measured in the dim sweep: 0.96 @8 -> 0.28
    # @64). dim/2 restores the same relative geometry at every width.
    repel_at = dim / 2.0
    for ep in range(epochs):
        perm = torch.randperm(len(TR), generator=g, device=dev)
        TR = TR[perm]
        sum_dp = torch.zeros((), device=dev)
        sum_dn = torch.zeros((), device=dev)
        nb = 0
        for i in range(0, len(TR), batch):
            b = TR[i:i + batch]
            s, p, o = b[:, 0], b[:, 1], b[:, 2]
            neg_o = torch.randint(0, n_t, (len(b),), generator=g, device=dev)
            arg_p = (theta[s] + rel[p] - theta[o]) / 2.0
            arg_n = (theta[s] + rel[p] - theta[neg_o]) / 2.0
            d_pos = torch.abs(torch.sin(arg_p)).sum(dim=1)
            d_neg = torch.abs(torch.sin(arg_n)).sum(dim=1)
            sum_dp += d_pos.sum()
            sum_dn += d_neg.sum()
            nb += len(b)
            # lesson 1 preserved: per-index MEAN gradient (count-normalized),
            # or hub predicates (is_a = most edges) thrash and nothing converges
            g_p = torch.sign(torch.sin(arg_p)) * torch.cos(arg_p) * 0.5
            gs = torch.zeros_like(theta)
            gr = torch.zeros_like(rel)
            gs.index_add_(0, s, g_p)
            gs.index_add_(0, o, -g_p)
            gr.index_add_(0, p, g_p)
            # lesson 2 preserved: decoupled repel (attraction alone collapses to d=0)
            close = d_neg < repel_at
            s_c, n_c = s[close], neg_o[close]
            if len(s_c):
                g_n = torch.sign(torch.sin(arg_n[close])) * torch.cos(arg_n[close]) * 0.5
                gs.index_add_(0, s_c, -g_n)
                gs.index_add_(0, n_c, g_n)
            cs = torch.bincount(torch.cat([s, o, s_c, n_c]), minlength=n_t).float().unsqueeze(1)
            cr = torch.bincount(p, minlength=n_p).float().unsqueeze(1)
            theta -= lr * gs / torch.clamp(cs, min=1.0)
            rel -= lr * gr / torch.clamp(cr, min=1.0)
        log(f"  epoch {ep + 1}/{epochs}: mean d_pos={float(sum_dp) / nb:.3f}  mean d_neg={float(sum_dn) / nb:.3f}")
    theta = torch.remainder(theta, 2 * torch.pi)
    theta_np = theta.detach().cpu().numpy().astype(np.float32)
    rel_np = rel.detach().cpu().numpy().astype(np.float32)
    if save:
        _save_artifacts(theta_np, rel_np,
                        json.dumps({"terms": [terms[t] for t in tids],
                                    "preds": [store.terms.term(int(p)) for p in pids]},
                                   ensure_ascii=False),
                        on_locked=on_locked, log=log)
        _SPACE["phases"] = None  # force consumers to reload the new space
    # honest eval, identical protocol to the CPU trainer (held-out, 200 candidates)
    hits, ranks = 0, []
    sample = hold[rng.permutation(len(hold))[:500]]
    cand = rng.integers(0, n_t, size=200)
    for s, p, o in sample:
        d_true = float(np.abs(np.sin((theta_np[s] + rel_np[p] - theta_np[o]) / 2.0)).sum())
        d_cand = np.abs(np.sin((theta_np[s][None, :] + rel_np[p][None, :] - theta_np[cand]) / 2.0)).sum(axis=1)
        rank = 1 + int((d_cand < d_true).sum())
        ranks.append(rank)
        if rank <= 10:
            hits += 1
    return {"edges": len(edges), "terms": n_t, "hits_at_10": hits / max(1, len(sample)),
            "mean_rank": float(np.mean(ranks)), "candidates": 201, "dim": dim,
            "saved": bool(save), "seconds": round(time.time() - t_start, 1), "device": dev}
