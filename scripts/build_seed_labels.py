# -*- coding: utf-8 -*-
"""Build the operator-review seed: real sentences in the registers no label source can reach.

    python scripts/build_seed_labels.py [n]

WHY A SEED IS NECESSARY AND NOT ONE OPTION AMONG THREE. Yesterday's chain, measured end to end:

    the intake needs a learned tagger, because a 31-verb list is a training wheel
    the tagger needs labels
    every label source in this project runs through the GRAPH -- alignment for wiki prose, distant
      supervision for dialogue -- and the graph has no commands
    so no volume of either produces a single labelled imperative

And the model was eliminated as a suspect: ACE2 fine-tuned reaches 0.740 on wiki and 0.851 on dialogue,
absorbs both registers without a trade-off, and still yields NOTHING on "Avoid the ghosts." -- 0 of 5
probes, and the verb never tagged as the relation. The gap is in the labels, and the only label path that
does not pass through the graph is a person.

FOUR RULES THIS FILE FOLLOWS, because a seed set is easy to poison.

    harvested where harvesting works        questions and short declaratives come from text already on
                                           disk, so the English is real and only the LABELS are new.
    AUTHORED where it does not              the imperative section IS written by me and every line is
                                           marked source=claude. Two harvest heuristics were tried and
                                           both were contaminated (see `shape`), and the reason is
                                           structural: a command addressed to an agent does not occur in
                                           an encyclopedia or in editor talk. Pretending otherwise would
                                           have handed the operator 150 lines that are not imperatives.
    selection is by SHAPE, not by lexicon   a question mark; eight words or fewer. These decide what
                                           reaches the review desk and never reach the model as a rule --
                                           selection heuristics do not train anything.
    only sentences the model FAILS on       labelling what it already reads teaches nothing. This is
                                           active learning and it is also what keeps the batch small.
    a HELD-OUT third is reserved            labelled by the operator, never trained on, so improvement is
                                           measured on imperatives the model has genuinely not seen.

WHAT THE OPERATOR IS ASKED FOR. A proposed tagging is shown, because reviewing is faster than authoring
-- but agreement with a proposal is weaker evidence than a correction, so the review file records which
lines were CHANGED and the report counts them separately. If almost nothing is changed, that is a signal
the proposals were leading the witness, not that the model was right.
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[1]
SOURCES = [REPO / "data" / "graph_scale" / "dialogue_register.jsonl",
           REPO / "data" / "graph_scale" / "dialogue_grounded.jsonl"]
OUT_REVIEW = Path("data/language/seed_review.tsv")
OUT_JSON = Path("data/language/seed_candidates.json")
_S = re.compile(r"(?<=[.!?])\s+")
_SPK = re.compile(r"^\s*[AB]\s*:\s*")
_W = re.compile(r"[^a-z0-9 ]+")
DET = {"the", "a", "an", "your", "all", "this", "that", "these", "those", "it", "them", "me", "us",
       "him", "her", "his", "their", "my", "our", "its"}
PRON = {"i", "you", "he", "she", "it", "we", "they", "there", "this", "that", "who", "what"}
LABELS = ("OUT", "SUBJ", "REL", "OBJ")


def norm(s: str) -> str:
    return " ".join(_W.sub(" ", (s or "").lower()).split())


def shape(sent: str) -> str | None:
    """Which register bucket, by tests that are actually RELIABLE. None otherwise.

    TWO IMPERATIVE DETECTORS WERE TRIED AND BOTH WERE CONTAMINATED, measured rather than assumed:

        first token not a determiner, second token a determiner
            -> caught "now it shows up in history lists" and "if his comrades are similar", because
               pronouns were in the determiner set
        first token appears after the infinitive marker "to"
            -> `the` follows "to" 5,912 times and `it` 722, since English spells the preposition and
               the infinitive marker identically. Candidates came back as "You closed [[Wikipedia..."
               and "Thanks for letting me know."

    A third heuristic is not the answer, because the reason is structural: A COMMAND ADDRESSED TO AN
    AGENT DOES NOT OCCUR in an encyclopedia or in editor talk. That register lives in manuals, recipes,
    game guides -- and in what the operator types at ATANOR. Harvesting imperatives from Wikipedia was
    the wrong idea, not a badly tuned one.

    So only the two reliable buckets are harvested here, and the imperative section of the review file
    is AUTHORED, with authorship marked."""
    raw = sent.strip()
    w = norm(raw).split()
    if not (3 <= len(w) <= 12):
        return None
    if raw.endswith("?"):
        return "question"
    if len(w) <= 8:
        return "short declarative"
    return None


#: Commands of the kind ATANOR will actually be given. WRITTEN BY CLAUDE and marked as such, so the
#: bias is visible and the operator can replace any line rather than inherit my phrasing. The held-out
#: third of this section should be replaced outright with the operator's own wording -- a model that
#: only reads commands I would have written has learned my habits, not English imperatives.
AUTHORED_COMMANDS = [
    "Avoid the ghosts.", "Eat the pellets.", "Chase the blue ghost.", "Move to the left.",
    "Go to the corner.", "Stay away from the wall.", "Follow the corridor.", "Collect the cherries.",
    "Leave the tunnel.", "Wait for the fruit.", "Take the shortest path.", "Guard the exit.",
    "Turn at the junction.", "Keep away from the red ghost.", "Head for the power pellet.",
    "Open the door.", "Close the window.", "Put the key on the table.", "Give the book to Mary.",
    "Bring me the report.", "Show the results.", "Delete the old file.", "Save the current state.",
    "Read the second paragraph.", "Answer the question.", "Explain the difference.",
    "Find the nearest exit.", "Count the remaining lives.", "Compare the two graphs.",
    "Stop the engine.",
]


def harvest(cap_per_bucket: int, seen: set):
    buckets: dict = {"imperative-shaped": [], "question": [], "short declarative": []}
    for path in SOURCES:
        if not path.exists():
            continue
        with io.open(path, encoding="utf-8") as f:
            for line in f:
                if all(len(v) >= cap_per_bucket for v in buckets.values()):
                    return buckets
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                for ln in str(d.get("text") or "").split("\n"):
                    for s in _S.split(_SPK.sub("", ln.strip())):
                        s = s.strip()
                        b = shape(s)
                        if not b or len(buckets[b]) >= cap_per_bucket:
                            continue
                        key = norm(s)
                        if key in seen or len(key) < 8:
                            continue
                        seen.add(key)
                        buckets[b].append(s)
    return buckets


def load_tagger():
    """The current best reader, so the batch is what it CANNOT do."""
    import torch
    from tokenizers import Tokenizer

    import scripts.ace2_finetune_spans as F
    from scripts.train_frame_tagger import build_examples
    ex, arts = build_examples()
    uniq = sorted(set(arts))
    rng = np.random.default_rng(0)
    held = set(rng.choice(uniq, size=max(2, len(uniq) // 5), replace=False).tolist())
    tr = [e for e, a in zip(ex, arts) if a not in held][:6000]
    tok = Tokenizer.from_file(str(F.TOKJSON))
    sd = torch.load(F.CKPT, map_location="cpu")
    sd = sd.get("model", sd)
    vocab, dm = sd["tok_emb.weight"].shape
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    m = F.SpanTagger(True, vocab, dm, dev).fit([F.encode(tok, t, l) for t, l in tr], 2, 1e-4)
    return m, tok, dev, F, torch


def tag(m, tok, dev, F, torch, words):
    ids, _y = F.encode(tok, words, [0] * len(words))
    text = " ".join(words)
    e = tok.encode(text)
    starts, pos = [], 0
    for w in words:
        starts.append(text.index(w, pos))
        pos = starts[-1] + len(w)
    m.enc.eval()
    with torch.no_grad():
        t = torch.tensor([ids]).to(dev)
        pr = m.logits(t, torch.zeros_like(t, dtype=torch.bool)).argmax(-1)[0].cpu().numpy()
    out = []
    for st in starts:
        lab = 0
        for ti, (a, b) in enumerate(e.offsets):
            if ti >= len(pr):
                break
            if a == st or (a <= st < b):
                lab = int(pr[ti])
                break
        out.append(lab)
    return out


def main() -> None:
    from packages.cgsr.cgsr.ingestion.learned_intake import ordered_spans
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    per = target  # harvest generously; the model's failures thin it out

    buckets = {k: v for k, v in harvest(per, set()).items() if k in ("question", "short declarative")}
    print("harvested by shape, from text already on disk:")
    for k, v in buckets.items():
        print(f"  {k:<20} {len(v)}")

    m, tok, dev, F, torch = load_tagger()
    print("\ncurrent best reader loaded (ACE2 fine-tuned: wiki 0.740, dialogue 0.851)\n")

    rows = []
    for cmd in AUTHORED_COMMANDS:
        w = norm(cmd).split()
        tags = tag(m, tok, dev, F, torch, w)
        rows.append({"shape": "imperative (AUTHORED by claude)", "sentence": cmd, "tokens": w,
                     "proposed": [LABELS[t] for t in tags], "source": "claude"})
    kept = {k: 0 for k in buckets}
    quota = {"question": target // 2, "short declarative": target - target // 2}
    for bucket, sents in buckets.items():
        for s in sents:
            if kept[bucket] >= quota[bucket]:
                break
            w = norm(s).split()
            tags = tag(m, tok, dev, F, torch, w)
            if ordered_spans(w, tags) is not None:
                continue                     # the model already reads it; nothing to learn here
            rows.append({"shape": bucket, "sentence": s, "tokens": w,
                         "proposed": [LABELS[t] for t in tags], "source": "harvested"})
            kept[bucket] += 1

    rng = np.random.default_rng(7)
    rng.shuffle(rows)
    cut = len(rows) // 3
    for i, r in enumerate(rows):
        r["split"] = "HELDOUT" if i < cut else "train"

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    with io.open(OUT_REVIEW, "w", encoding="utf-8") as f:
        f.write('# ATANOR seed labels for operator review. Tab-separated, 5 columns.\n')
        f.write('#\n')
        f.write('# HOW TO LABEL: one tag per token, in order, space separated.\n')
        f.write('#   SUBJ  the doer      REL  the verb / connective      OBJ  what it acts on\n')
        f.write('#   OUT   everything else (articles, adverbs, anything outside the three roles)\n')
        f.write('# AN IMPERATIVE HAS NO SUBJECT: leave SUBJ unused and tag the VERB as REL.\n')
        f.write('#   Avoid the ghosts.  ->  REL OUT OBJ\n')
        f.write('# Edit the LAST column only. The token count must stay the same.\n')
        f.write('#\n')
        f.write('# The imperative lines say AUTHORED by claude in the shape column -- I wrote them, because two\n')
        f.write('# harvest heuristics for imperatives were both contaminated, and commands to an agent do not\n')
        f.write('# occur in encyclopedic or editor-talk text. Please REWRITE them in your own wording, especially\n')
        f.write('# the HELDOUT ones: a model that only reads commands I would have written has learned my habits.\n')
        f.write('# A line you CHANGE is evidence; a line waved through unchanged counts for less, and the two are\n')
        f.write('# reported separately.\n')
        f.write('#\n')
        f.write('# split<TAB>shape<TAB>sentence<TAB>tokens<TAB>labels\n')
        for r in rows:
            f.write('%s\t%s\t%s\t%s\t%s\n' % (r['split'], r['shape'], r['sentence'],
                                          ' '.join(r['tokens']), ' '.join(r['proposed'])))

    print(f"{len(rows)} review lines, by shape:")
    for k in sorted({r["shape"] for r in rows}):
        print(f"  {k:<20} {sum(1 for r in rows if r['shape'] == k)}")
    print(f"  held out (never trained on): {cut}")
    print(f"\nreview file: {OUT_REVIEW}")
    print("examples as proposed (these are the model's guesses, not answers):")
    for r in rows[:6]:
        pairs = " ".join(f"{t}/{l}" for t, l in zip(r["tokens"], r["proposed"]))
        print(f"  [{r['shape']:<18}] {pairs}")


if __name__ == "__main__":
    main()
