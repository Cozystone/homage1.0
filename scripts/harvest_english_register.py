# -*- coding: utf-8 -*-
"""Harvest English REGISTER (discourse moves, not facts) from a StackExchange dump.

WHY (the documented #1 fluency bottleneck)
 The English core answers correctly but tastes like a dictionary ("coffee is a kind of
 acquired taste."). Binding memory: corpus COMPOSITION, not size, is the bottleneck — and
 the existing register harvester literally requires Hangul (`re.search(r"[-]", frag)`),
 so the English core has NO register source at all. english.stackexchange.com is ideal
 material: careful, idiomatic English prose ABOUT English, in exactly the answer-shape our
 composer needs (opener → body → transition → hedge).

WHAT IS HARVESTED — and what is deliberately not
 Discourse MOVES: sentence-initial spans that carry stance/flow and no content —
 openers "The short answer is that …", "Strictly speaking, …"
 transitions "That said, …", "In other words, …"
 hedges "As far as I know, …", "I would say …"
 Content never crosses: a span qualifies only if its tokens are function/discourse words.
 Facts from StackExchange do NOT enter the knowledge store through this path (
 is about the graph; this writes a JSON surface asset the composer may draw from).

DISCIPLINE (the diet-flood lesson, BINDING)
 Feeding a corpus into the speech path polluted the pack once before (P0 23→18). So:
 * harvest → INSPECT the bank → wire into the composer as a separate step;
 * after wiring, warm battery + seal dev battery BEFORE claiming improvement;
 * the bank is a versioned file the composer reads if present — deleting it reverts.

SOURCE + LICENSE
 StackExchange dumps are CC BY-SA 4.0. The bank records the dump name, date and license;
 only sentence-initial discourse spans (<=6 words, content-free) are retained, no post
 bodies, no usernames (never even parsed).

USAGE
 python scripts/harvest_english_register.py --posts D:/atanor_corpora/stackexchange/english/Posts.xml
 python scripts/harvest_english_register.py --posts ... --min-score 5 --min-posts 40
"""
from __future__ import annotations

import argparse
import html
import io
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "registers" / "english_register_bank.json"

_ROW = re.compile(r'<row\s+(.*?)/>')
_ATTR = re.compile(r'(\w+)="([^"]*)"')
_TAG = re.compile(r"<[^>]+>")
_DROP_BLOCK = re.compile(r"<(code|blockquote|pre)\b.*?</\1>", re.S | re.I)
_WS = re.compile(r"\s+")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
_URL = re.compile(r"https?://\S+")
_WORD = re.compile(r"[A-Za-z']+")

# The discourse lexicon: words allowed inside a register span. Function words + stance verbs +
# discourse adverbs. A span with any token OUTSIDE this set carries content and is rejected —
# that is the wall between learning HOW people speak and copying WHAT they said.
_DISCOURSE = set("""
a an the this that these those it its there here
i you we one they he she
is are was were be been being am do does did done has have had having
can could may might must shall should will would
not no nor never n't
and or but so yet nor because although though while whereas if unless until when whenever
of to in on at by for with from as into onto upon about over under between among within without
more most less least very quite rather fairly pretty almost nearly just only even also too
however therefore thus hence moreover furthermore nevertheless nonetheless meanwhile instead
additionally likewise similarly again further conversely alternatively equally incidentally
otherwise anyway besides indeed certainly probably possibly perhaps maybe arguably apparently
generally usually typically normally often sometimes rarely strictly technically literally
essentially basically actually really simply clearly obviously naturally frankly honestly
say said saying says mean means meant note noted noting think thought put puts putting
depends depend seems seem seemed appears appear suppose suspect imagine guess reckon
short long answer question point case sense word words term terms other others way ways
matter fact issue thing things example instance contrast comparison summary
first second third finally lastly
worth keep bear mind far know knowledge speaking speak strictly
yes no course
""".split())

# spans that end mid-thought are noise even when content-free
_BAD_END = {"the", "a", "an", "of", "to", "in", "on", "at", "by", "and", "or", "but",
            "is", "are", "was", "were", "very", "more", "most", "not", "as", "with", "that"}


def _clean_body(body: str) -> str:
    body = html.unescape(body)
    body = _DROP_BLOCK.sub(" ", body)      # quoted text and code are not the answerer's voice
    body = _TAG.sub(" ", body)
    body = _URL.sub(" ", body)
    return _WS.sub(" ", body).strip()


def _spans(sentence: str) -> list[str]:
    """Sentence-initial discourse spans: 2..6 words, cut at a comma or the span end, every
    token in the discourse lexicon, not ending on a dangling function word."""
    lead = sentence[:80]
    comma = lead.find(",")
    out: list[str] = []
    words = _WORD.findall(lead)
    if not (2 <= len(words)):
        return out
    # comma-bounded move ("That said," / "In other words," / "Also,") — the strongest signal.
    # Single-word markers are allowed here: the additive family the composer actually needs
    # ("Also,", "Moreover,", "Furthermore,") is one word + comma, and the first harvest missed
    # the entire class by requiring 2+ words.
    if 0 < comma <= 40:
        head = _WORD.findall(lead[:comma])
        if 1 <= len(head) <= 6 and all(w.lower() in _DISCOURSE for w in head) and \
                head[-1].lower() not in _BAD_END:
            out.append(" ".join(head) + ",")
    # copula-bounded opener ("The short answer is") — keep the verb, drop the content after
    for n in range(2, min(7, len(words) + 1)):
        head = words[:n]
        if head[-1].lower() in ("is", "are", "means", "depends", "say", "put") and \
                all(w.lower() in _DISCOURSE for w in head) and \
                head[-1].lower() not in _BAD_END:
            out.append(" ".join(head))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts", required=True)
    ap.add_argument("--min-score", type=int, default=5,
                    help="answer score floor — community validation is the quality gate")
    ap.add_argument("--min-posts", type=int, default=40,
                    help="a span must appear in this many DISTINCT answers to be register, "
                         "not one author's tic")
    ap.add_argument("--limit", type=int, default=0, help="debug: stop after N rows")
    args = ap.parse_args()

    opener_posts: dict[str, set[int]] = defaultdict(set)
    transition_posts: dict[str, set[int]] = defaultdict(set)
    answers = kept = 0
    t0 = time.time()

    with open(args.posts, encoding="utf-8", errors="ignore") as fh:
        for i, line in enumerate(fh):
            if args.limit and i >= args.limit:
                break
            m = _ROW.search(line)
            if not m:
                continue
            attrs = dict(_ATTR.findall(m.group(1)))
            if attrs.get("PostTypeId") != "2":
                continue
            answers += 1
            try:
                if int(attrs.get("Score", "0")) < args.min_score:
                    continue
            except ValueError:
                continue
            pid = int(attrs.get("Id", "0"))
            body = _clean_body(attrs.get("Body", ""))
            if len(body) < 60:
                continue
            kept += 1
            sents = _SENT.split(body)
            for j, s in enumerate(sents[:12]):
                s = s.strip()
                if not (10 <= len(s) <= 400):
                    continue
                for span in _spans(s):
                    key = span.lower()
                    (opener_posts if j == 0 else transition_posts)[key].add(pid)
            if kept % 50000 == 0:
                print(f"  …answers={answers} kept={kept}  {time.time()-t0:.0f}s")

    def bank(d: dict[str, set[int]]) -> list[dict]:
        rows = [{"span": k, "posts": len(v)} for k, v in d.items() if len(v) >= args.min_posts]
        rows.sort(key=lambda r: -r["posts"])
        return rows

    openers, transitions = bank(opener_posts), bank(transition_posts)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": "english.stackexchange.com data dump (2024-04-07)",
        "license": "CC BY-SA 4.0 — https://archive.org/details/stackexchange",
        "harvested_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "method": ("sentence-initial discourse spans, every token in the discourse lexicon, "
                   f"score>={args.min_score}, distinct-answer support>={args.min_posts}; "
                   "no content words, no bodies, no usernames retained"),
        "answers_scanned": answers,
        "answers_kept": kept,
        "openers": openers,
        "transitions": transitions,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nanswers={answers} kept(score>={args.min_score})={kept}  {time.time()-t0:.0f}s")
    print(f"openers={len(openers)}  transitions={len(transitions)}  -> {OUT}")
    print("\ntop openers:")
    for r in openers[:15]:
        print(f"  {r['posts']:6d}  {r['span']}")
    print("top transitions:")
    for r in transitions[:15]:
        print(f"  {r['posts']:6d}  {r['span']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
