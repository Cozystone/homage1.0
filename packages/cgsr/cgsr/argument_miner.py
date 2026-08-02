# -*- coding: utf-8 -*-
"""Learn the STRUCTURE of an argument from real prose — not a hand-fixed move order.

Track F, free-argument layer. The old discourse participation used ONE fixed shape for every
argument (claim → concession → rebuttal, always). The owner's standing rule: hardcoding what the
cognition does at each step IS rule-based — the move order must be LEARNED from data and vary.

So this miner reads a corpus of real argumentative prose and induces a Markov transition model over
ARGUMENT MOVES. The move of each clause is read off its leading discourse connective — a closed-class
signal (because / but / although / for example / therefore …), the same legitimate linguistic cue the
realizer already mines for clause fusion. Nothing about WHICH move follows WHICH is written by hand:
the transition probabilities come entirely from how humans actually sequence these connectives.

Move inventory (the 'parts of speech' of an argument — argumentation-theory structure, not content):
  CLAIM        a bare asserted position (a clause with no argumentative connective)
  GROUND       a reason offered for a claim            (because, since, as, given that)
  CONCESSION   granting the other side a point         (although, though, granted, to be fair)
  REBUTTAL     pushing back after/against a point      (but, however, yet, still, that said)
  EXAMPLE      a concrete instance                     (for example, for instance, such as)
  IMPLICATION  what follows from the reasoning         (so, therefore, thus, which means)
  QUALIFY      the limit / scope of the claim          (usually, often, in general, at least)

The learned model is P(next_move | current_move) + start/end distributions. It is data, re-mined as
the AI reads more prose; the planner samples from it (argument_planner). No fabrication: the miner
only counts real transitions in real text; it invents nothing.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[3]
MODEL_PATH = REPO / "data" / "track_f" / "argument_transitions.json"

MOVES = ("CLAIM", "GROUND", "CONCESSION", "REBUTTAL", "EXAMPLE", "IMPLICATION", "QUALIFY")

# Closed-class discourse connectives → move. Ordered longest-first within a move so multi-word cues
# match before their single-word prefixes. These are the ONLY hand-specified thing (the lexical
# signal); the sequencing they reveal is entirely learned.
_CUES: list[tuple[str, str]] = [
    # IMPLICATION
    ("as a result", "IMPLICATION"), ("which means", "IMPLICATION"), ("that means", "IMPLICATION"),
    ("that is why", "IMPLICATION"), ("that's why", "IMPLICATION"), ("therefore", "IMPLICATION"),
    ("consequently", "IMPLICATION"), ("hence", "IMPLICATION"), ("thus", "IMPLICATION"),
    ("so ", "IMPLICATION"),
    # CONCESSION
    ("to be fair", "CONCESSION"), ("it is true that", "CONCESSION"), ("it's true that", "CONCESSION"),
    ("i agree that", "CONCESSION"), ("admittedly", "CONCESSION"), ("granted", "CONCESSION"),
    ("of course", "CONCESSION"), ("although", "CONCESSION"), ("though", "CONCESSION"),
    ("even if", "CONCESSION"), ("sure,", "CONCESSION"),
    # REBUTTAL
    ("on the other hand", "REBUTTAL"), ("that said", "REBUTTAL"), ("even so", "REBUTTAL"),
    ("nevertheless", "REBUTTAL"), ("nonetheless", "REBUTTAL"), ("however", "REBUTTAL"),
    ("whereas", "REBUTTAL"), ("but ", "REBUTTAL"), ("yet ", "REBUTTAL"), ("still,", "REBUTTAL"),
    # EXAMPLE
    ("for example", "EXAMPLE"), ("for instance", "EXAMPLE"), ("such as", "EXAMPLE"),
    ("e.g.", "EXAMPLE"), ("like when", "EXAMPLE"),
    # GROUND
    ("given that", "GROUND"), ("seeing that", "GROUND"), ("because", "GROUND"),
    ("since ", "GROUND"), ("in that ", "GROUND"),
    # QUALIFY
    ("in most cases", "QUALIFY"), ("in general", "QUALIFY"), ("generally", "QUALIFY"),
    ("typically", "QUALIFY"), ("usually", "QUALIFY"), ("often", "QUALIFY"),
    ("tends to", "QUALIFY"), ("at least", "QUALIFY"), ("for the most part", "QUALIFY"),
]

# split a text into clauses: sentence enders, and the connective cues themselves open a new clause
_SENT = re.compile(r"[.!?]+")
_CONNECTIVE_SPLIT = re.compile(
    r"\b(because|since|although|though|but|however|yet|still|therefore|thus|hence|so|"
    r"for example|for instance|such as|granted|admittedly|whereas|nevertheless|nonetheless|"
    r"consequently|usually|often|generally|typically|that said|even so|on the other hand)\b",
    re.IGNORECASE)


def label_move(clause: str) -> str:
    """The argument move of one clause, from its leading/opening discourse cue (CLAIM if none)."""
    c = " " + clause.strip().lower()
    best = ("", "CLAIM", 10 ** 9)
    for cue, move in _CUES:
        i = c.find(" " + cue)
        if i != -1 and i < best[2]:          # earliest-appearing cue wins → the clause's leading move
            best = (cue, move, i)
    return best[1]


def clause_moves(text: str) -> list[str]:
    """The ordered sequence of argument moves in a passage: split into clauses, label each."""
    moves: list[str] = []
    for sent in _SENT.split(text or ""):
        sent = sent.strip()
        if len(sent) < 6:
            continue
        # break the sentence at each connective so 'X because Y but Z' → three labelled clauses
        parts = _CONNECTIVE_SPLIT.split(sent)
        # re-stitch: split() keeps the delimiters as separate items — glue each delimiter to what
        # follows it so the cue leads its clause
        clauses: list[str] = []
        buf = parts[0]
        i = 1
        while i < len(parts):
            cue, rest = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
            if buf.strip():
                clauses.append(buf)
            buf = cue + rest
            i += 2
        if buf.strip():
            clauses.append(buf)
        for cl in clauses:
            if len(cl.strip()) >= 6:
                moves.append(label_move(cl))
    return moves


def mine(texts: Iterable[str]) -> dict:
    """Induce the transition model P(next|cur) + start/end distributions from real passages."""
    trans: dict[str, Counter] = defaultdict(Counter)
    start: Counter = Counter()
    end: Counter = Counter()
    unigram: Counter = Counter()
    n_seq = 0
    for text in texts:
        seq = clause_moves(text)
        if len(seq) < 2:
            continue
        n_seq += 1
        start[seq[0]] += 1
        end[seq[-1]] += 1
        for m in seq:
            unigram[m] += 1
        for a, b in zip(seq, seq[1:]):
            trans[a][b] += 1
    # normalize to probabilities (kept alongside raw counts for auditing)
    trans_p = {a: {b: round(c / sum(cnts.values()), 4) for b, c in cnts.items()}
               for a, cnts in trans.items()}

    def _norm(cnt: Counter) -> dict:
        tot = sum(cnt.values()) or 1
        return {k: round(v / tot, 4) for k, v in cnt.items()}

    return {
        "n_sequences": n_seq,
        "moves": list(MOVES),
        "start": _norm(start),
        "end": _norm(end),
        "unigram": _norm(unigram),
        "transitions": trans_p,
        "transitions_raw": {a: dict(c) for a, c in trans.items()},
    }


def _iter_corpus(path: Path, field: str | None, limit: int | None) -> Iterable[str]:
    """Yield text bodies from a .jsonl (a given field) or a plain-text file (one doc per line)."""
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if limit and n >= limit:
                break
            line = line.strip()
            if not line:
                continue
            if field:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                val = obj.get(field, "")
                if isinstance(val, list):
                    val = " ".join(str(x) for x in val)
                text = str(val)
            else:
                text = line
            if text:
                n += 1
                yield text


def mine_file(path: str | Path, *, field: str | None = "text", limit: int | None = None,
              save: bool = True) -> dict:
    model = mine(_iter_corpus(Path(path), field, limit))
    if save:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        MODEL_PATH.write_text(json.dumps(model, ensure_ascii=False, indent=1), encoding="utf-8")
    return model


def load_model() -> dict | None:
    if MODEL_PATH.exists():
        try:
            return json.loads(MODEL_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else str(
        REPO / "data" / "graph_scale" / "dialogue_grounded.jsonl")
    fld = sys.argv[2] if len(sys.argv) > 2 else "text"
    lim = int(sys.argv[3]) if len(sys.argv) > 3 else None
    m = mine_file(src, field=fld, limit=lim)
    print(f"sequences: {m['n_sequences']}")
    print("start:", m["start"])
    print("unigram:", m["unigram"])
    print("transitions from CLAIM:", m["transitions"].get("CLAIM"))
    print("transitions from GROUND:", m["transitions"].get("GROUND"))
    print("transitions from CONCESSION:", m["transitions"].get("CONCESSION"))
    print("saved →", MODEL_PATH)
