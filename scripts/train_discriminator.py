# -*- coding: utf-8 -*-
"""Train ATANOR's learned support-discriminator, then evaluate it on MMLU (train != test).

Owner 2026-07-15 (BINDING): remove hand rules; make it GROW from data. Pipeline:
  1. self-supervised English embeddings (PPMI+SVD) from the passage corpus
  2. discriminator trained on ARC (public labeled science MCQ TRAIN split) — grounded with a retrieved
     passage, exactly like test time
  3. honest eval on the MMLU dev slice — a different dataset, so this is transfer, not test-fitting

  python scripts/train_discriminator.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.reasoning_vm import learned_discriminator as LD          # noqa: E402
from packages.reasoning_vm.openbook import load_passages, retrieve      # noqa: E402

_HDR = {"User-Agent": "ATANOR-train (research; blueyjkim@gmail.com)"}
_ARC_CACHE = REPO / "data" / "benchmarks" / "arc"


def _dl(url: str, path: Path) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers=_HDR), timeout=180).read())
    return path


def _fetch_train() -> list[dict]:
    """Public labeled MCQ TRAIN splits (never eval sets) → [{question, options{A..}, gold_key, passage?}].
    ARC + OpenBookQA + SciQ — the more diverse the supervision, the better the learned support generalizes."""
    import pandas as pd
    keys = "ABCDEFGH"
    out: list[dict] = []

    # ARC-Challenge + ARC-Easy
    for cfg in ("ARC-Challenge", "ARC-Easy"):
        try:
            df = pd.read_parquet(_dl(
                f"https://huggingface.co/datasets/allenai/ai2_arc/resolve/main/{cfg}/train-00000-of-00001.parquet",
                _ARC_CACHE / f"{cfg}-train.parquet"))
            for _i, r in df.iterrows():
                texts, labels = list(r["choices"]["text"]), list(r["choices"]["label"])
                gold = str(r["answerKey"]).strip()
                if not (2 <= len(texts) <= 6) or gold not in labels:
                    continue
                out.append({"question": str(r["question"]),
                            "options": {keys[j]: str(texts[j]) for j in range(len(texts))},
                            "gold_key": keys[labels.index(gold)]})
        except Exception as e:
            print("  (ARC skip)", str(e)[:60])

    # OpenBookQA
    try:
        df = pd.read_parquet(_dl(
            "https://huggingface.co/datasets/allenai/openbookqa/resolve/main/main/train-00000-of-00001.parquet",
            REPO / "data" / "benchmarks" / "obqa" / "train.parquet"))
        for _i, r in df.iterrows():
            texts, labels = list(r["choices"]["text"]), list(r["choices"]["label"])
            gold = str(r["answerKey"]).strip()
            if gold not in labels:
                continue
            out.append({"question": str(r["question_stem"]),
                        "options": {keys[j]: str(texts[j]) for j in range(len(texts))},
                        "gold_key": keys[labels.index(gold)]})
    except Exception as e:
        print("  (OpenBookQA skip)", str(e)[:60])

    # SciQ — has a 'support' passage we can ground with directly (auto-converted parquet path)
    try:
        df = pd.read_parquet(_dl(
            "https://huggingface.co/datasets/allenai/sciq/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet",
            REPO / "data" / "benchmarks" / "sciq" / "train.parquet"))
        import random
        rng = random.Random(0)
        for _i, r in df.iterrows():
            opts_text = [str(r["correct_answer"]), str(r["distractor1"]),
                         str(r["distractor2"]), str(r["distractor3"])]
            order = list(range(4))
            rng.shuffle(order)
            out.append({"question": str(r["question"]),
                        "options": {keys[j]: opts_text[order[j]] for j in range(4)},
                        "gold_key": keys[order.index(0)], "passage": str(r.get("support") or "")})
    except Exception as e:
        print("  (SciQ skip)", str(e)[:60])

    # CommonsenseQA (5-way)
    try:
        df = pd.read_parquet(_dl(
            "https://huggingface.co/datasets/tau/commonsense_qa/resolve/main/data/train-00000-of-00001.parquet",
            REPO / "data" / "benchmarks" / "csqa" / "train.parquet"))
        for _i, r in df.iterrows():
            texts, labels = list(r["choices"]["text"]), list(r["choices"]["label"])
            gold = str(r["answerKey"]).strip()
            if gold not in labels:
                continue
            out.append({"question": str(r["question"]),
                        "options": {keys[j]: str(texts[j]) for j in range(len(texts))},
                        "gold_key": keys[labels.index(gold)]})
    except Exception as e:
        print("  (CSQA skip)", str(e)[:60])

    # MMLU auxiliary_train — the big one (~100k, aggregated ARC/OBQA/RACE/MC_TEST; TRAIN split, != test/dev)
    try:
        df = pd.read_parquet(_dl(
            "https://huggingface.co/datasets/cais/mmlu/resolve/main/auxiliary_train/train-00000-of-00001.parquet",
            REPO / "data" / "benchmarks" / "mmlu_aux" / "train.parquet"))
        for _i, r in df.head(40000).iterrows():
            rec = r["train"] if "train" in df.columns else r     # rows are nested under a 'train' struct
            ch = list(rec["choices"])
            if len(ch) != 4:
                continue
            out.append({"question": str(rec["question"]),
                        "options": {keys[j]: str(ch[j]) for j in range(4)},
                        "gold_key": keys[int(rec["answer"])]})
    except Exception as e:
        print("  (MMLU-aux skip)", str(e)[:60])
    return out


def _ground(examples: list[dict], passages: dict) -> list[dict]:
    for ex in examples:
        if ex.get("passage"):                            # SciQ ships its own support passage
            continue
        got = retrieve(ex["question"], passages)
        ex["passage"] = got[1] if got else ""
    return examples


def main() -> int:
    t0 = time.time()
    pfile = REPO / "data" / "graph_scale" / "wiki_passages_en" / "passages.tsv"
    print("loading passages…", flush=True)
    passages = load_passages(str(pfile))
    corpus = [passages[t] for t in list(passages)]                       # full corpus (batched co-occ)
    print(f"training embeddings on {len(corpus)} passages…", flush=True)
    emb = LD.train_embeddings(corpus, dim=LD._DIM)
    print(f"  vocab {len(emb.idx)}  ({round(time.time()-t0,1)}s)", flush=True)

    print("fetching train + grounding…", flush=True)
    import numpy as np
    import random
    data = _ground(_fetch_train(), passages)
    random.Random(0).shuffle(data)
    print(f"  {len(data)} MCQ; featurizing once (sentence-focus + NLI + relative)…", flush=True)
    feats = LD.featurize(emb, data)                                        # (gold_idx, option-matrix) ×N
    print(f"  featurized {len(feats)} MCQ in {round(time.time()-t0,1)}s", flush=True)

    def _stack(fs):
        X = np.concatenate([m for _g, m in fs], axis=0)
        y = np.concatenate([[1 if i == g else 0 for i in range(len(m))] for g, m in fs])
        return X, y

    def _mcq_acc(clf, fs) -> float:
        c = 0
        for g, m in fs:
            try:
                s = clf.predict_proba(m)[:, 1]
            except Exception:
                s = clf.decision_function(m)
            c += int(int(np.argmax(s)) == g)
        return c / max(1, len(fs))

    # HONEST selection: K-fold CV over model + hyperparameter specs (not by peeking at MMLU).
    K = 3
    order = list(range(len(feats)))
    random.Random(1).shuffle(order)
    folds = [order[i::K] for i in range(K)]
    specs = ["lr:1.0", "mlp:160,64", "mlp:256,128", "gbm:0.1"]
    best_spec, best_cv = specs[0], -1.0
    for spec in specs:
        accs = []
        for f in range(K):
            va = [feats[i] for i in folds[f]]
            trn = [feats[i] for j in range(K) if j != f for i in folds[j]]
            Xt, yt = _stack(trn)
            clf = LD.make_clf(spec)
            clf.fit(Xt, yt)
            accs.append(_mcq_acc(clf, va))
        cv = float(np.mean(accs))
        print(f"  {spec}: cv_acc {cv:.3f}", flush=True)
        if cv > best_cv:
            best_cv, best_spec = cv, spec
    Xa, ya = _stack(feats)                                                 # retrain winner on ALL data
    final = LD.make_clf(best_spec)
    final.fit(Xa, ya)
    disc = LD.Discriminator(emb, final)
    disc.save(LD._DIR)
    best_name, best_acc = best_spec, best_cv
    print(f"  selected '{best_spec}' (cv {best_cv:.3f}); trained on all + saved", flush=True)

    # external honest check only: MMLU dev (different dataset)
    mmlu = [json.loads(l) for l in (REPO / "data" / "benchmarks" / "mmlu" / "slice_25.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    mc = sum(int(LD.answer_mcq(r["question"], r["choices"],
                               (retrieve(r["question"], passages) or (None, ""))[1], disc) == r["gold"])
             for r in mmlu)
    rep = {"val_acc": round(best_acc, 4), "best_model": best_name,
           "mmlu_check": round(mc / max(1, len(mmlu)), 4), "guess": 0.25,
           "train_mcq": len(data), "vocab": len(emb.idx), "elapsed_s": round(time.time() - t0, 1)}
    print("\nRESULT", json.dumps(rep))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
