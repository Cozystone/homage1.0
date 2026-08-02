# -*- coding: utf-8 -*-
"""Train the frame tagger on human sentences, hold out by article, and test what the regex cannot do.

    python scripts/train_frame_tagger.py

WHERE THE LABELS COME FROM, and this is the part that has to be honest. `mine_constructions_v2.mine()`
located a bone's subject and object INSIDE a human sentence for 9,302 bones -- stem-tolerant, head-aware,
alias-expanded. That alignment is supervision the corpus already contained: it says which tokens are the
subject, which are the object, and therefore which lie between them. No rule generated these labels and
no model wrote them; they are the graph and the sentence agreeing about the same fact.

HELD OUT BY ARTICLE, NOT BY SENTENCE. Two sentences from one Wikipedia article share entities and
phrasing, so a sentence-level split leaks. This is the same discipline that caught a silent town-split
fallback in the depth work earlier: the split is checked and the run aborts if it degenerates.

REGISTERED BEFORE TRAINING:
    1  beats a positional baseline (first span SUBJ, next REL, rest OBJ) on held-out ARTICLES
    2  beats a label-shuffled control -- if a model trained on scrambled labels scores the same, the
       features are reading position and not language
    3  IT TAGS AN IMPERATIVE, which the incumbent cannot represent at all: `builder.py:151` excludes
       position 0 from the verb search and an imperative's verb is at position 0. This is the failure
       that started the whole line and it is the one test that cannot be passed by degrees.
    4  and it works where the inverse speaker abstains -- coverage that is NOT capped by what the
       speaker can say, which is the entire reason for building a tagger rather than more constructions

Nothing pretrained is loaded. Weights start at zero.
"""
from __future__ import annotations

import collections
import io
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.cgsr.frame_tagger import FrameTagger, LABELS, norm            # noqa: E402
from packages.image_schema.inverse_speaker import InverseSpeaker            # noqa: E402
from packages.realizer_struct.frame_realizer import FRAMES                  # noqa: E402
from scripts.mine_constructions_v2 import find, stem                        # noqa: E402

PAIRS = Path("data/graph_scale/bones_to_text.jsonl")
OUT = Path("data/language/frame_tagger.json")
WEIGHTS = Path("data/language/frame_tagger.npz")


def build_examples(cap_articles: int = 4000):
    """(tokens, labels) per aligned sentence, tagged with the article it came from."""
    aliases = collections.defaultdict(set)
    rows = []
    with io.open(PAIRS, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            for b in d.get("bones") or []:
                if len(b) >= 3 and b[1] == "alias":
                    aliases[norm(str(b[0]))].add(str(b[2]))
                    aliases[norm(str(b[2]))].add(str(b[0]))
            if d.get("bones") and d.get("text"):
                rows.append(d)

    ex, arts = [], []
    seen_articles: dict = {}
    for d in rows:
        text = (d.get("text") or "").strip()
        if not text or not (4 <= len(text.split()) <= 32):
            continue
        art = str(d.get("subject") or "")
        if art not in seen_articles and len(seen_articles) >= cap_articles:
            continue
        w = norm(text).split()
        st = [stem(x) for x in w]
        for b in d.get("bones") or []:
            if len(b) < 3:
                continue
            s, _r, o = (str(x).strip() for x in b)
            a = find(w, st, s, aliases)
            c = find(w, st, o, aliases)
            if not a or not c or a[1] > c[0]:
                continue
            lab = [0] * len(w)
            for i in range(a[0], a[1]):
                lab[i] = 1
            for i in range(a[1], c[0]):
                lab[i] = 2
            for i in range(c[0], c[1]):
                lab[i] = 3
            if 2 not in lab:
                continue                      # no relation span: nothing to learn about the connective
            ex.append((w, lab))
            arts.append(art)
            seen_articles.setdefault(art, 0)
            break
    return ex, arts


def positional_baseline(toks: list) -> list:
    """The obvious rule, so the model has to be better than obvious: first token subject, second the
    relation, the rest object."""
    lab = [3] * len(toks)
    if toks:
        lab[0] = 1
    if len(toks) > 1:
        lab[1] = 2
    return lab


def token_f1(gold: list, pred: list) -> tuple:
    g = np.array(gold)
    p = np.array(pred)
    out = {}
    for k, name in enumerate(LABELS):
        if k == 0:
            continue
        tp = int(((g == k) & (p == k)).sum())
        fp = int(((g != k) & (p == k)).sum())
        fn = int(((g == k) & (p != k)).sum())
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        out[name] = 2 * prec * rec / max(prec + rec, 1e-9)
    return out, float((g == p).mean())


def evaluate(model, data) -> dict:
    accs, f1s = [], collections.defaultdict(list)
    for toks, gold in data:
        pred = model(toks)
        f, a = token_f1(gold, pred)
        accs.append(a)
        for k, v in f.items():
            f1s[k].append(v)
    return {"acc": float(np.mean(accs)),
            **{f"f1_{k}": float(np.mean(v)) for k, v in f1s.items()}}


def main() -> None:
    ex, arts = build_examples()
    uniq = sorted(set(arts))
    print(f"{len(ex)} aligned sentences over {len(uniq)} articles")
    if len(uniq) < 20:
        sys.exit("too few distinct articles to hold out by article; the split would be meaningless")

    rng = np.random.default_rng(0)
    held = set(rng.choice(uniq, size=max(2, len(uniq) // 5), replace=False).tolist())
    tr = [e for e, a in zip(ex, arts) if a not in held]
    te = [e for e, a in zip(ex, arts) if a in held]
    print(f"train {len(tr)} sentences / test {len(te)} sentences, split BY ARTICLE "
          f"({len(uniq) - len(held)} vs {len(held)})")
    if not te or not tr:
        sys.exit("the article split degenerated; refusing to report a number from it")
    assert not ({a for e, a in zip(ex, arts) if e in tr} & held), "article leak"

    model = FrameTagger()
    hist = model.fit(tr)
    print(f"trained from zero weights; mean token loss {hist['loss'][0]:.3f} -> {hist['loss'][-1]:.3f}\n")

    base = evaluate(positional_baseline, te)
    got = evaluate(model.tag, te)

    shuf = FrameTagger()
    sh = [(t, list(rng.permutation(l))) for t, l in tr]
    shuf.fit(sh, epochs=3)
    ctrl = evaluate(shuf.tag, te)

    print(f"{'arm':<26}{'token acc':>11}{'F1 SUBJ':>10}{'F1 REL':>9}{'F1 OBJ':>9}")
    for nm, r in (("positional baseline", base), ("label-shuffled control", ctrl),
                  ("LEARNED tagger", got)):
        print(f"{nm:<26}{r['acc']:>11.3f}{r['f1_SUBJ']:>10.3f}{r['f1_REL']:>9.3f}{r['f1_OBJ']:>9.3f}")

    print(f"\n-> 1. beats the positional baseline on held-out articles: "
          f"{got['acc'] > base['acc']}  ({base['acc']:.3f} -> {got['acc']:.3f})")
    print(f"-> 2. beats the label-shuffled control: {got['acc'] > ctrl['acc'] + 0.05}  "
          f"({ctrl['acc']:.3f})")

    print("\n-> 3. THE IMPERATIVE, which the incumbent cannot represent at all:")
    inv = InverseSpeaker(sorted(FRAMES))
    for s in ("Avoid the ghosts.", "Eat the pellets.", "Move to the left.",
              "Sandra travelled to the office."):
        sp = model.spans(s)
        old = inv.best(s)[0]
        print(f"     {s:<32} tagger {str(sp):<44} speaker {old}")
    imp_ok = all(model.spans(s) is not None for s in ("Avoid the ghosts.", "Eat the pellets."))
    print(f"   imperatives receive a structure: {imp_ok}")

    unread = [t for t, _l in te if inv.best(" ".join(t))[0] is None]
    cov = sum(1 for t in unread if model.spans(" ".join(t)) is not None) / max(len(unread), 1)
    print(f"\n-> 4. on held-out sentences the SPEAKER cannot read ({len(unread)} of {len(te)}), the "
          f"tagger returns a structure for {cov:.1%}")
    print("   which is the point: the tagger's coverage is not capped by what the speaker can say.")

    WEIGHTS.parent.mkdir(parents=True, exist_ok=True)
    model.save(WEIGHTS)
    OUT.write_text(json.dumps({"n_train": len(tr), "n_test": len(te), "articles": len(uniq),
                               "baseline": base, "shuffled": ctrl, "learned": got,
                               "imperative_ok": bool(imp_ok), "coverage_beyond_speaker": cov,
                               "loss": hist["loss"]}, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT} and {WEIGHTS}")


if __name__ == "__main__":
    main()
