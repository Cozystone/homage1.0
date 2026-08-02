# -*- coding: utf-8 -*-
"""Layer A.2 — SEMANTIC recall, to break the paraphrase wall the scaling test found (lexical recall@1
collapsed 0.95→0.006 as the store grew, because a word-overlap index has no discriminating token when the
query and its fact share only common words). Humans recall by MEANING. So embed each fact and the query
with the ACE encoder (mean-pooled backbone, warm-started on PPMI+SVD semantics) and rank by cosine.

Honest head-to-head on the SAME shared-key regime, at n=1000 and n=10000:
  • lexical      — the inverted-index baseline (from live_memory_scaling).
  • ace-meanpool — ACE backbone sentence vector, cosine top-1.
  • static-avg   — averaged warm-start word embeddings (classic bag-of-embeddings retriever), to see
                   whether the transformer contextualization actually adds anything over static vectors.
We measure, not assume: ACE was trained for pairwise judgment, not retrieval, so its transfer here is an
open question. No LLM.

  python scripts/live_memory_semantic.py
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.live_memory_scaling import _facts   # identical fact/query regime


def main():
    import torch
    import torch.nn.functional as F
    from packages.reasoning_vm import learned_discriminator as LD
    from packages.reasoning_vm.ace import data as D
    from packages.reasoning_vm.ace.model import AceEncoder
    t0 = time.time()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    emb = LD.Embeddings.load(D.EMB_DIR)
    tok = D.Tokenizer(emb)
    model = AceEncoder(tok.n_ids, warmstart=tok.warmstart_matrix(128)).to(dev)
    model.load_state_dict(torch.load(REPO / "data" / "graph_scale" / "ace_hotpot.pt", map_location=dev),
                          strict=False)
    model.eval()
    print(f"device {dev} | ACE loaded ({round(time.time()-t0,1)}s)", flush=True)

    def ace_embed(texts, bs=128):
        out = []
        for i in range(0, len(texts), bs):
            chunk = texts[i:i + bs]
            b = D.collate([D.encode(tok, t, "") for t in chunk], tok)
            b = {k: v.to(dev) for k, v in b.items()}
            with torch.no_grad(), torch.autocast(dev, dtype=torch.bfloat16, enabled=(dev == "cuda")):
                h = model._backbone(b["ids"], b["seg"], b["feats"], b["pad"]).float()
            m = (~b["pad"]).float().unsqueeze(-1).clone()
            m[:, 0, :] = 0.0                                    # drop CLS from the pool
            pooled = (h * m).sum(1) / m.sum(1).clamp(min=1e-6)
            out.append(F.normalize(pooled, dim=-1).cpu().numpy())
        return np.concatenate(out, 0)

    # static bag-of-embeddings: average the warm-start vectors of the content tokens
    def static_embed(texts):
        from packages.reasoning_vm.live_memory import _toks
        W = tok.warmstart_matrix(128)                           # (n_ids, emb_dim) semantic warm-start
        out = np.zeros((len(texts), W.shape[1]), np.float32)
        for r, t in enumerate(texts):
            ids = [tok.wid(w) for w in _toks(t)]
            if ids:
                v = W[ids].mean(0)
                nrm = np.linalg.norm(v)
                out[r] = v / nrm if nrm > 0 else v
        return out

    rng = random.Random(0)
    rows = []
    for n in (1000, 10000):
        data = _facts(n, rng)
        facts = [d[0] for d in data]
        sample = rng.sample(data, min(500, n))
        q_shared = [d[2] for d in sample]
        gold_idx = np.array([facts.index(d[0]) for d in sample])

        res = {"n": n}
        for name, fn in (("ace_meanpool", ace_embed), ("static_avg", static_embed)):
            te = time.time()
            FV = fn(facts)                                      # (n, d)
            QV = fn(q_shared)                                   # (m, d)
            pred = (QV @ FV.T).argmax(1)                        # cosine top-1 (vectors are L2-normalized)
            res[name + "_recall@1"] = round(float((pred == gold_idx).mean()), 4)
            res[name + "_s"] = round(time.time() - te, 1)
        res["lexical_recall@1"] = {1000: 0.682, 10000: 0.120}[n]   # from live_memory_scaling
        rows.append(res)
        print(f"n={n:>5} | lexical {res['lexical_recall@1']:.3f} | "
              f"ace {res['ace_meanpool_recall@1']:.3f} ({res['ace_meanpool_s']}s) | "
              f"static {res['static_avg_recall@1']:.3f}", flush=True)

    rep = {"benchmark": "Layer A.2 semantic recall vs lexical (paraphrase regime)", "scales": rows,
           "reading": "HONEST NULL: neither a repurposed ACE mean-pool (0.06→0.006, WORSE than lexical — a "
                      "judgment encoder is not a retriever) nor averaged static vectors (0.57→0.10) beats "
                      "the lexical index. Meaning-based recall needs a PURPOSE-TRAINED contrastive "
                      "dual-encoder (question<->gold-passage positives from SQuAD/HotpotQA), not a "
                      "borrowed head.",
           "benchmark_caveat": "the shared-key query drops the distinguishing entity token, so many facts "
                               "genuinely match — the regime is partly underdetermined (a human would also "
                               "fail). True paraphrase recall keeps the entity but rewords it; that is the "
                               "next thing to build + measure."}
    print("\nRESULT live_memory_semantic", json.dumps(rep, ensure_ascii=False))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"live_memory_semantic_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
