#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the taxonomy backbone the multi-hop reasoner needs — from data the graph
ALREADY HOLDS.

The store is defined_as-heavy (dictionary definitions) and nearly is_a-empty, so the
composition algebra has no edges to walk. But a Korean dictionary definition names its
hypernym as the HEAD NOUN of the defining phrase:

 defined_as → is_a 
 defined_as … → is_a 

Extracting that head noun is a STRUCTURAL/linguistic rule (the shape of a definition),
not world knowledge — the knowledge stays in the stored definition; we only surface the
relation it already asserts. Per the hard rule: knowledge to the GRAPH, never to code.

Precision-first gates (truth > coverage, the standing order):
 * only subjects with exactly ONE hangul definition (multi-sense words like skipped —
 their senses would cross-contaminate);
 * head noun via Kiwi's final NNG/NNP token of the definition; regex fallback only for
 clean noun endings;
 * a small METALINGUISTIC stoplist (// //…) — those heads describe the
 word, not the thing, and would produce confusing verify answers;
 * head must be hangul, >=2 chars, != subject, and not already stated.

Every added edge is (subject, is_a, head) where head is a verbatim span of the stored
definition — auditable, and tombstone-retractable like any other edge.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# heads that describe the WORD, not the THING — is_a here is metalinguistic noise

_STOP_HEADS = {"말", "준말", "옛말", "방언", "낱말", "단어", "표현", "이름", "명칭", "약자",
               "약어", "높임말", "낮춤말", "것", "따위", "때", "경우", "일", "뜻", "의미",
               "사투리", "은어", "속어", "비속어", "줄임말", "어근", "어간", "어미", "접사",
               "접두사", "접미사", "조사", "품사", "명사", "대명사", "동사", "형용사", "부사",
               "감탄사", "관형사", "수사", "형태소", "관용구", "숙어", "글자", "문자", "자모",
               "음절", "발음", "한자어", "외래어", "고유어", "한자", "로마자", "활용형",
               "활용", "표기", "표기법", "말투", "호칭", "칭호", "별칭", "존칭"}


def _is_verbal(head: str, kiwi) -> bool:
    """A verb/adjective mis-picked as head ( is_a ) asserts nothing taxonomic."""
    if kiwi is None or not head.endswith("다"):
        return False
    try:
        toks = kiwi.tokenize(head)
        return len(toks) >= 1 and toks[0].tag in ("VV", "VA", "VX", "VCP", "VCN")
    except Exception:
        return False


def _head_noun(definition: str, kiwi) -> str | None:
    """The final content noun of a Korean defining phrase."""
    d = definition.strip().rstrip(".。 ")
    if not re.search(r"[가-힣]", d):
        return None

    d = re.sub(r"\([^)]*\)\s*$", "", d).strip()
    if kiwi is not None:
        try:
            toks = [t for t in kiwi.tokenize(d)]
            nouns = [t.form for t in toks if t.tag in ("NNG", "NNP")]
            if nouns:
                head = nouns[-1]
                # the head must actually END the phrase (a mid-sentence noun is not
                # the genus): allow trailing copula/josa remnants only
                tail = d[d.rfind(head) + len(head):]
                if re.fullmatch(r"[을를이가은는의로]?\s*", tail):
                    return head
                return None
        except Exception:
            pass
    m = re.search(r"([가-힣]{2,})\s*$", d)
    if m is None:
        return None
    head = m.group(1)


    return None if head.endswith("다") else head


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--apply",
        action="store_true",
        help="disabled: taxonomy writes require E4/E5 and signed mutation promotion",
    )
    ap.add_argument("--limit", type=int, default=0, help="cap extracted edges (0 = no cap)")
    args = ap.parse_args()
    if args.apply:
        print(
            "REFUSING before graph scan: direct taxonomy writes are disabled; "
            "this compiler has not cleared its independent E4/E5 gate."
        )
        return 2

    from packages.graph_scale.answer_bridge import _store
    store = _store()
    if store is None:
        print("no store"); return 1

    kiwi = None
    try:
        from packages.base_brain.neighborhood import _kiwi
        kiwi = _kiwi()
    except Exception:
        pass

    cols = store.open_columns()
    n = len(cols["s"])
    print(f"scanning {n} triples…")
    defs: dict[str, list[str]] = defaultdict(list)
    stated_isa: set[tuple[str, str]] = set()
    for i in range(n):
        p = store.terms.term(int(cols["p"][i]))
        if p == "defined_as":
            s = store.terms.term(int(cols["s"][i]))
            o = store.terms.term(int(cols["o"][i]))
            if re.search(r"[가-힣]", o):
                defs[s].append(o)
        elif p in ("is_a", "subclass_of"):
            stated_isa.add((store.terms.term(int(cols["s"][i])),
                            store.terms.term(int(cols["o"][i]))))

    single = {s: ds[0] for s, ds in defs.items() if len(ds) == 1}
    print(f"subjects with hangul defs: {len(defs)}; single-definition (eligible): {len(single)}")

    edges: list[tuple[str, str, str]] = []
    skipped_stop = skipped_head = 0
    for s, d in single.items():
        head = _head_noun(d, kiwi)
        if head is None:
            skipped_head += 1
            continue
        if head in _STOP_HEADS or head == s or len(head) < 2 or not re.search(r"[가-힣]", head):
            skipped_stop += 1
            continue
        if _is_verbal(head, kiwi):
            skipped_stop += 1
            continue
        if (s, head) in stated_isa:
            continue
        edges.append((s, "is_a", head))
        if args.limit and len(edges) >= args.limit:
            break

    print(f"extracted is_a edges: {len(edges)}  (no-head {skipped_head}, stoplist/self {skipped_stop})")
    for s, p, o in edges[:12]:
        print(f"  {s} {p} {o}")
    print(
        "(shadow report only — no write authority; E4/E5 required before "
        "mutation-batch emission)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
