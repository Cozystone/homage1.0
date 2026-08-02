# -*- coding: utf-8 -*-
"""Layer A real-world recall — the synthetic 'shared-key' regime was partly underdetermined, so test on
REAL natural-language paraphrase: SQuAD questions are human rewordings of their gold passage. Store the
passages as live memory, query with the questions, and ask: is the gold passage retrieved? This is the
honest test of whether Layer A's lexical index is already good enough for real recall, or whether a
purpose-trained retriever is actually needed.

Compares, over the SAME passage store:
  • lexical      — LiveMemory IDF inverted index (what Layer A ships today).
  • static_avg   — averaged warm-start word vectors, cosine (classic bag-of-embeddings retriever).
Metrics: recall@1 and recall@5 (gold passage among top-k). No LLM.

  python scripts/live_memory_real_recall.py [n_passages]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main():
    from packages.reasoning_vm.ace import data as D
    from packages.reasoning_vm import learned_discriminator as LD
    from packages.reasoning_vm.live_memory import LiveMemory, _toks
    t0 = time.time()
    n_pass = int(sys.argv[1]) if len(sys.argv) > 1 else 2000

    rows = D.load_squad("dev")                                     # real questions + gold contexts
    # dedup passages, map each answerable question to its gold passage id
    pid = {}
    passages = []
    qa = []                                                        # (question, gold_pid)
    for r in rows:
        if not r["answerable"]:
            continue
        c = r["ctx"]
        if c not in pid:
            if len(passages) >= n_pass:
                continue                                          # cap the store; skip Qs for unseen paras
            pid[c] = len(passages)
            passages.append(c)
        qa.append((r["q"], pid[c]))
    qa = [(q, i) for q, i in qa if i < len(passages)]
    print(f"{len(passages)} passages | {len(qa)} questions ({round(time.time()-t0,1)}s)", flush=True)

    # ---- lexical (LiveMemory) ----
    lm = LiveMemory(path=REPO / "data" / "graph_scale" / "live_memory" / "_real_tmp.jsonl")
    lm.items.clear(); lm.inv.clear(); lm.df.clear()
    for c in passages:
        lm.remember(c, source="squad", persist=False)
    lex1 = lex5 = 0
    tl = time.time()
    for q, gold in qa:
        hits = lm.recall(q, k=5)
        texts = [h["text"] for h in hits]
        lex1 += int(bool(texts) and texts[0] == passages[gold])
        lex5 += int(passages[gold] in texts)
    lex_ms = (time.time() - tl) / max(1, len(qa)) * 1000

    # ---- static_avg (bag-of-embeddings) ----
    emb = LD.Embeddings.load(D.EMB_DIR)
    tok = D.Tokenizer(emb)
    W = tok.warmstart_matrix(128)

    def bag(texts):
        out = np.zeros((len(texts), W.shape[1]), np.float32)
        for r, t in enumerate(texts):
            ids = [tok.wid(w) for w in _toks(t)]
            if ids:
                v = W[ids].mean(0)
                nrm = np.linalg.norm(v)
                out[r] = v / nrm if nrm > 0 else v
        return out

    FV = bag(passages)
    st1 = st5 = 0
    for q, gold in qa:
        qv = bag([q])[0]
        sims = FV @ qv
        top5 = np.argpartition(-sims, min(5, len(sims) - 1))[:5]
        top5 = top5[np.argsort(-sims[top5])]
        st1 += int(len(top5) and top5[0] == gold)
        st5 += int(gold in top5)

    rep = {"benchmark": "Layer A real-world recall (SQuAD dev: question -> gold passage)",
           "n_passages": len(passages), "n_questions": len(qa),
           "lexical_recall@1": round(lex1 / len(qa), 4), "lexical_recall@5": round(lex5 / len(qa), 4),
           "lexical_ms_per_q": round(lex_ms, 3),
           "static_avg_recall@1": round(st1 / len(qa), 4), "static_avg_recall@5": round(st5 / len(qa), 4),
           "reading": "on REAL paraphrase, does lexical already suffice? if recall@5 is high, Layer A's "
                      "shipped index is good enough for real recall and the synthetic collapse was a "
                      "regime artifact; a trained retriever is justified only by the residual gap.",
           "elapsed_s": round(time.time() - t0, 1)}
    print("\nRESULT live_memory_real", json.dumps(rep, ensure_ascii=False))
    (REPO / "reports" / "benchmarks").mkdir(parents=True, exist_ok=True)
    (REPO / "reports" / "benchmarks" / f"live_memory_real_{time.strftime('%Y%m%d_%H%M')}.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp = REPO / "data" / "graph_scale" / "live_memory" / "_real_tmp.jsonl"
    if tmp.exists():
        tmp.unlink()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
