# -*- coding: utf-8 -*-
""" — raise the learned router over the bar so regex lanes can come off.

Owner (2026-07-12): " ." The distilled router's ceiling is LABELED DATA,
not architecture. The rule lanes are a labeling function; every logged turn (q → lane the rules
chose) is a training row. We already have thousands. Two honest, standard levers to convert that
into holdout accuracy:

 1. PARAPHRASE AUGMENTATION — each (q, lane) row is multiplied into label-preserving surface
 variants ( swap, spacing, punctuation, -ending, light filler). The intent is identical,
 only the surface changes, so the router learns the invariant instead of memorizing strings.
 2. PER-LANE READINESS — the aggregate holdout hides that some wheels are ALREADY removable while
 others starve. We report holdout per lane, so a wheel at ≥ bar can come off NOW even before
 the whole set does — .

Writes the augmented candidate to a SEPARATE path (never clobbers production). Promotion of any
lane stays a deliberate, measured step. Run: python scripts/wheel_promote.py
"""
from __future__ import annotations

import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

_JOSA = {"은": "는", "는": "은", "이": "가", "가": "이", "을": "를", "를": "을",
         "과": "와", "와": "과", "에게": "한테", "한테": "에게"}


def _variants(q: str, rng: random.Random, k: int) -> list[str]:
    """k label-preserving paraphrases of q. Surface-only — the intent never moves."""
    out: set[str] = set()
    base = q.strip()
    tries = 0
    while len(out) < k and tries < k * 4:
        tries += 1
        v = base

        toks = v.split()
        if toks and rng.random() < 0.6:
            i = rng.randrange(len(toks))
            for p, alt in _JOSA.items():
                if toks[i].endswith(p) and len(toks[i]) > len(p):
                    toks[i] = toks[i][: -len(p)] + alt
                    break
            v = " ".join(toks)
        if rng.random() < 0.4:  # spacing jitter
            v = v.replace(" ", "", 1) if " " in v and rng.random() < 0.5 else v + " "
        if rng.random() < 0.4:  # punctuation / ending
            v = v.rstrip("?!. ") + rng.choice(["", "?", "!", "...", "요", "용", " ㅎㅎ"])
        v = v.strip()
        if v and v != base:
            out.add(v)
    return list(out)


def _load_pairs(min_support: int) -> list[tuple[str, str]]:
    from packages.flywheel.self_improvement import _rows
    pairs = [(str(r.get("q") or "").strip(), str(r.get("lane") or "").strip())
             for r in _rows() if r.get("q") and r.get("lane")]
    pairs = [(q, l) for q, l in pairs if q and l]
    cnt = Counter(l for _q, l in pairs)
    return [(q, l) for q, l in pairs if cnt[l] >= min_support]


def _per_lane_holdout(rows: list[tuple[str, str]], seed: int = 7) -> dict:
    """Train, then report holdout accuracy overall AND per lane, on a 10% split the augmented
    copies never leak into (we split the ORIGINALS, then augment only the train side)."""
    import numpy as np
    from packages.learned_router.router import _hash_features, DIM, MODEL_DIR, train

    rng = random.Random(seed)
    by_lane: dict[str, list[str]] = defaultdict(list)
    for q, l in rows:
        by_lane[l].append(q)
    train_rows: list[tuple[str, str]] = []
    hold_rows: list[tuple[str, str]] = []
    for lane, qs in by_lane.items():
        qs = list(dict.fromkeys(qs))  # dedupe within lane
        rng.shuffle(qs)
        cut = max(1, len(qs) // 10)
        hold_rows += [(q, lane) for q in qs[:cut]]
        for q in qs[cut:]:
            train_rows.append((q, lane))
            for v in _variants(q, rng, k=3):  # augment ONLY the train side → no leakage
                train_rows.append((v, lane))
    res = train(train_rows, epochs=25, out_path=MODEL_DIR / "router_lane_promote.npz",
                meta_path=MODEL_DIR / "router_lane_promote.meta.json")
    # score the untouched holdout with the freshly trained candidate
    data = np.load(MODEL_DIR / "router_lane_promote.npz")
    W, b = data["W"], data["b"]
    classes = sorted({l for _q, l in train_rows})
    cidx = {c: i for i, c in enumerate(classes)}
    per = defaultdict(lambda: [0, 0])
    for q, lane in hold_rows:
        if lane not in cidx:
            continue
        z = W @ _hash_features(q) + b
        ok = int(classes[int(z.argmax())] == lane)
        per[lane][0] += ok
        per[lane][1] += 1
    lane_acc = {l: (c[0] / c[1], c[1]) for l, c in per.items() if c[1] > 0}
    overall = sum(c[0] for c in per.values()) / max(1, sum(c[1] for c in per.values()))
    return {"trained_rows": len(train_rows), "holdout_overall": round(overall, 3),
            "train_acc": round(res.get("train_acc", 0), 3), "lane_acc": lane_acc}


def main() -> None:
    bar = 0.85
    print("=== 보조바퀴 승격 (paraphrase-augmented distillation) ===\n")
    base = _load_pairs(min_support=6)
    print(f"labeled turns (min_support 6): {len(base)} over {len({l for _q,l in base})} lanes")
    r = _per_lane_holdout(base)
    print(f"augmented train rows: {r['trained_rows']} | train_acc {r['train_acc']} "
          f"| holdout {r['holdout_overall']*100:.1f}%\n")
    print(f"레인별 홀드아웃 (떼기 바 {bar*100:.0f}%):")
    removable = []
    for lane, (acc, n) in sorted(r["lane_acc"].items(), key=lambda kv: -kv[1][0]):
        mark = "REMOVABLE ✅" if acc >= bar and n >= 3 else ("근접" if acc >= 0.7 else "KEEP")
        if acc >= bar and n >= 3:
            removable.append(lane)
        print(f"  {lane:34s} {acc*100:3.0f}%  (n={n})  {mark}")
    print(f"\n지금 뗄 수 있는 레인 {len(removable)}개: {', '.join(removable) or '없음 — 데이터 더 필요'}")
    print("살찌우기: 실트래픽이 쌓이거나 아레나가 약한 레인을 채굴 타깃으로 지정하면 이 수치가 오릅니다.")


if __name__ == "__main__":
    main()
