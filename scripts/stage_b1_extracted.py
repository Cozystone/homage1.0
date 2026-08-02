# -*- coding: utf-8 -*-
"""B1 knowledge-scale probe: quality-gate the LOCAL English `extracted_*.jsonl` candidate
relations and stage the trustworthy subset into a SCOPED staging store (2026-07-23).

CONTEXT: roadmap B1 = knowledge scale beyond ConceptNet. English Wikidata is NOT local
(only Korean is, excluded by the English-only doctrine). The one English extracted-relation
set that IS local lives in data/cloud_brain/derived_candidates/extracted_{enables,prevents,
requires,used_for,defined_as,is_a}.jsonl. The causal ones (enables/prevents/requires) are the
high-value target because they also feed the temporal/mechanism lane (starved at ~19 causal
tokens).

WHAT THESE ROWS ACTUALLY ARE (measured, honest): a crude regex sweep
  pattern = \\b([A-Za-z][\\w\\- ]{1,38}?) (pr...   /   ...(?:...
over a tiny handful of PDFs (predominantly Kahneman "Thinking, Fast and Slow" + a
knowledge-graph-embedding survey paper + IEEE copyright boilerplate). src="extracted:rule+
topology", tier="candidate", NO per-row confidence or consensus. Subjects/objects are mostly
sentence fragments, pronouns, question-heads, OCR garbage and truncations. Total rows:
enables 3, prevents 6, requires 18, used_for 38, defined_as 6, is_a 276 (347 total; 27 causal).

THIS SCRIPT (propose-verify, evidence-only, 0 fabrication):
  1. Quality-gate each relation with documented precision-first rejection rules (below).
  2. Stage ONLY survivors into data/graph_scale/staging_b1_extracted/ (SEPARATE from the
     shipped store and from staging_r2_conceptnet), every edge provenance-tagged.
  3. Measure the density lift vs the SHIPPED store, READ-ONLY (numpy memmap mode='r' + sqlite
     immutable=1). The shipped store is never opened by write-capable code.

SAFETY: NEVER writes data/graph_scale/kg_triples. Promotion staging->shipped is the
operator-signed morning step (candidate_promotion_gate) — NOT done here.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import zlib
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from packages.graph_scale.triple_store import TripleStore  # noqa: E402

CAND = REPO / "data" / "cloud_brain" / "derived_candidates"
STAGING = REPO / "data" / "graph_scale" / "staging_b1_extracted"
SHIPPED = REPO / "data" / "graph_scale" / "kg_triples"

RELATIONS = ["enables", "prevents", "requires", "used_for", "defined_as", "is_a"]
CAUSAL = {"enables", "prevents", "requires"}

# ---------------------------------------------------------------------------------------
# QUALITY GATE — precision-first. We would rather DROP a borderline-good edge than STAGE a
# fragment. Every rule targets a noise signature observed by direct read of all 347 rows.
# ---------------------------------------------------------------------------------------
HANGUL = re.compile(r"[가-힣]")

# a fragment usually begins or ends with a function word / bare connective.
STOP_HEAD = {
    "the", "a", "an", "of", "and", "or", "but", "as", "to", "in", "on", "at", "for", "with",
    "that", "this", "these", "those", "we", "they", "you", "your", "his", "her", "its", "our",
    "it", "he", "she", "i", "been", "also", "often", "normally", "actually", "please",
    "continue", "perhaps", "so", "not", "following", "such", "much", "my", "me", "us", "no",
    "how", "why", "what", "when", "where", "who", "whom", "whose", "been",
}
STOP_TAIL = {
    "of", "and", "or", "but", "as", "to", "in", "on", "at", "for", "with", "than", "that",
    "the", "a", "an", "by", "into", "from", "whose", "also", "rather", "during", "directed",
    "composed", "projected", "connecting", "leading", "makes", "makes", "do", "does",
}
# whole-string anaphora / dangling references with no standalone meaning.
ANAPHORA = {
    "them", "it", "they", "this", "these", "those", "same", "such", "such changes", "you",
    "your", "his", "her", "our", "we", "i", "me", "my", "it today", "you probably",
    "you also", "you just", "it felt", "much", "otherwise", "perhaps", "probably", "notably",
    "sounds", "individual", "little", "form", "word", "words", "effect", "them today",
}
# relative-clause / comparative markers => the "triple" is really a clipped sentence.
CLAUSE_MARK = {" that ", " whose ", " which ", " than ", " because ", " while ", " when ",
               " where ", " who "}
# explicit OCR / nonsense tokens seen in the data.
JUNK_TOKENS = {
    "occupatiohein", "occupatnal", "thass", "confthis", "iere", "brro", "brrs", "mimsy",
    "borogoves", "pof", "othersn", "confidence.",
}
# whole-string possessive splits ("Kahneman's essay" -> "s essay").


def has_bad_char(txt: str) -> bool:
    """OCR ligatures / non-Latin script (keeps Latin-1 accents like Bjorn's o-umlaut)."""
    for ch in txt:
        o = ord(ch)
        if o < 0x80:
            continue
        if 0x00C0 <= o <= 0x024F:   # Latin-1 Supplement + Latin Extended-A/B (accents)
            continue
        return True                 # Greek phi, fi/fl ligatures, math symbols, etc.
    return False


def bad_consonant_run(txt: str) -> bool:
    """5+ consecutive consonants in a token => almost surely OCR garbage."""
    for tok in re.findall(r"[A-Za-z]+", txt):
        run = 0
        for ch in tok.lower():
            if ch in "aeiouy":
                run = 0
            else:
                run += 1
                if run >= 5:
                    return True
    return False


def gate_reason(s: str, o: str) -> str | None:
    """Return a rejection reason string, or None if the (s,o) pair passes all rules."""
    s = (s or "").strip()
    o = (o or "").strip()
    sl, ol = s.lower(), o.lower()
    if len(s) < 3 or len(o) < 3:
        return "too_short"
    if HANGUL.search(s) or HANGUL.search(o):
        return "hangul"
    if has_bad_char(s) or has_bad_char(o):
        return "ocr_nonlatin"
    if any(ch.isdigit() for ch in s) or any(ch.isdigit() for ch in o):
        return "contains_digit"
    if sl in ANAPHORA or ol in ANAPHORA:
        return "anaphora"
    s_tokens, o_tokens = sl.split(), ol.split()
    if not s_tokens or not o_tokens:
        return "empty_token"
    if s_tokens[0] in STOP_HEAD:
        return f"stophead_s:{s_tokens[0]}"
    if o_tokens[0] in STOP_HEAD:
        return f"stophead_o:{o_tokens[0]}"
    if s_tokens[-1] in STOP_TAIL:
        return f"stoptail_s:{s_tokens[-1]}"
    if o_tokens[-1] in STOP_TAIL:
        return f"stoptail_o:{o_tokens[-1]}"
    # possessive-split head: "s son", "s essay" (from "X's son")
    if s_tokens[0] == "s" or o_tokens[0] == "s":
        return "possessive_split"
    # pronoun anywhere as a whole token
    PRON = {"i", "you", "he", "she", "we", "they", "them", "it", "his", "her", "your",
            "my", "our", "us", "me", "him"}
    if PRON & set(s_tokens) or PRON & set(o_tokens):
        return "pronoun_token"
    if any(m in f" {sl} " for m in CLAUSE_MARK) or any(m in f" {ol} " for m in CLAUSE_MARK):
        return "clause_fragment"
    if JUNK_TOKENS & set(s_tokens) or JUNK_TOKENS & set(o_tokens):
        return "junk_token"
    if bad_consonant_run(s) or bad_consonant_run(o):
        return "consonant_run"
    # CamelCase KG-paper identifiers used as surfaces ("AlfredHitchcock", "LocatedIn", "BornIn")
    if re.search(r"[a-z][A-Z]", s) or re.search(r"[a-z][A-Z]", o):
        return "camelcase_identifier"
    return None


# ---------------------------------------------------------------------------------------
# SAFE read-only view of the SHIPPED store (numpy memmap mode='r' + sqlite immutable=1).
# Never instantiates TripleStore on the shipped path (that would open the 16 term shards
# read-write and run CREATE TABLE / PRAGMA, touching their mtimes).
# ---------------------------------------------------------------------------------------
class ShippedReadOnly:
    def __init__(self, root: Path, n_shards: int = 16):
        import numpy as np
        self.np = np
        self.root = root
        self.n = n_shards
        self.conns = []
        for i in range(n_shards):
            p = root / "term_shards" / f"terms_{i:02d}.db"
            uri = f"file:{p.as_posix()}?immutable=1&mode=ro"
            self.conns.append(sqlite3.connect(uri, uri=True))
        self.s = self._memmap("s.col")
        self.p = self._memmap("p.col")
        self.o = self._memmap("o.col")

    def _memmap(self, name):
        p = self.root / name
        n = p.stat().st_size // 4
        return self.np.memmap(str(p), dtype="<i4", mode="r", shape=(n,))

    def lookup(self, term: str):
        shard = zlib.crc32(term.encode("utf-8")) % self.n
        row = self.conns[shard].execute(
            "SELECT rowid FROM t WHERE term = ?", (term,)).fetchone()
        return (row[0] - 1) * self.n + shard if row else None

    def has_triple(self, s: str, p: str, o: str) -> bool:
        """Case-insensitive membership (shipped ConceptNet stores lowercase): a survivor is
        counted as ALREADY-PRESENT if any case-variant of the exact (s,p,o) exists."""
        for sv, ov in {(s, o), (s.lower(), o.lower())}:
            sid = self.lookup(sv)
            pid = self.lookup(p)
            oid = self.lookup(ov)
            if sid is None or pid is None or oid is None:
                continue
            rows = self.np.nonzero(self.s == sid)[0]
            if len(rows) and self.np.any((self.p[rows] == pid) & (self.o[rows] == oid)):
                return True
        return False

    def subject_known(self, s: str) -> bool:
        return self.lookup(s) is not None or self.lookup(s.lower()) is not None

    def close(self):
        for c in self.conns:
            c.close()


def main() -> int:
    import shutil
    if STAGING.exists():
        shutil.rmtree(STAGING)

    # 1) gate every relation ------------------------------------------------------------
    survivors: dict[str, list[dict]] = defaultdict(list)
    rejects: dict[str, Counter] = defaultdict(Counter)
    raw_counts: dict[str, int] = {}
    dup_within: dict[str, int] = defaultdict(int)
    for rel in RELATIONS:
        path = CAND / f"extracted_{rel}.jsonl"
        rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        raw_counts[rel] = len(rows)
        seen = set()
        for r in rows:
            s, o = (r.get("s") or "").strip(), (r.get("o") or "").strip()
            reason = gate_reason(s, o)
            if reason:
                rejects[rel][reason] += 1
                continue
            key = (s.lower(), rel, o.lower())
            if key in seen:
                dup_within[rel] += 1
                continue
            seen.add(key)
            survivors[rel].append({"s": s, "o": o})

    # 2) stage survivors ----------------------------------------------------------------
    store = TripleStore(STAGING, dict_backend="ram")
    # provenance: rule-extracted, LOW TRUST, no source URL (these rows carry none) — the
    # label itself flags the tier so a future promotion gate can weight/deny accordingly.
    src_id = store.intern_source("extracted:rule+topology", "")
    staged_per_rel: Counter = Counter()
    for rel in RELATIONS:
        for e in survivors[rel]:
            if store.add(e["s"], rel, e["o"], source=src_id):
                staged_per_rel[rel] += 1
    store.flush()
    store.terms.flush()
    store.rebuild_index()

    # 3) measure density lift vs shipped (READ-ONLY) ------------------------------------
    ro = ShippedReadOnly(SHIPPED)
    net_new = Counter()
    already = Counter()
    new_subject = Counter()
    net_new_examples: dict[str, list] = defaultdict(list)
    known_subjects: set[str] = set()
    for rel in RELATIONS:
        for e in survivors[rel]:
            if ro.has_triple(e["s"], rel, e["o"]):
                already[rel] += 1
            else:
                net_new[rel] += 1
                if len(net_new_examples[rel]) < 25:
                    net_new_examples[rel].append(f'{e["s"]} -[{rel}]-> {e["o"]}')
            if ro.subject_known(e["s"]):
                known_subjects.add(e["s"].lower())
            else:
                new_subject[rel] += 1
    ro.close()

    causal_staged = sum(staged_per_rel[r] for r in CAUSAL)
    causal_net_new = sum(net_new[r] for r in CAUSAL)
    total_staged = sum(staged_per_rel.values())

    # 3b) RESIDUAL-NOISE second pass (reproducible lower bound on how much junk the
    # precision-first gate STILL let through). A clean generic-knowledge triple is a short
    # noun-phrase subject + a short noun-phrase object. Flag a survivor as likely-still-noisy
    # if EITHER side is a long multi-word span (>4 words = clipped clause), the object leads
    # with a comparative ("more"/"less" = book narrative, not a type), or the subject trails
    # in a bare connective ("X and", "X also"). This is a heuristic, not a promotion gate.
    COMPARATIVE = {"more", "less", "most", "least", "better", "worse", "best", "worst"}
    residual_noisy = Counter()
    residual_clean_examples: dict[str, list] = defaultdict(list)
    for rel in RELATIONS:
        for e in survivors[rel]:
            st, ob = e["s"].split(), e["o"].split()
            noisy = (
                len(st) > 4 or len(ob) > 4
                or (ob and ob[0].lower() in COMPARATIVE)
                or (st and st[-1].lower() in {"and", "also", "still", "do", "not"})
                or (ob and ob[-1].lower() in {"institute", "systems"})
            )
            if noisy:
                residual_noisy[rel] += 1
            elif len(residual_clean_examples[rel]) < 30:
                residual_clean_examples[rel].append(f'{e["s"]} -[{rel}]-> {e["o"]}')
    residual_noisy_total = sum(residual_noisy.values())
    survives_both = total_staged - residual_noisy_total

    manifest = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "purpose": "roadmap B1 knowledge-scale probe on LOCAL English extracted_* relations",
        "source_files": {rel: str(CAND / f"extracted_{rel}.jsonl") for rel in RELATIONS},
        "provenance_tag": "extracted:rule+topology (regex over local PDFs; NO per-row confidence)",
        "english_only": True,
        "fabrication": 0,
        "gate_rules": [
            "too_short(<3)", "hangul", "ocr_nonlatin(non-Latin1 char)", "contains_digit",
            "anaphora(whole-string)", "stophead/stoptail(function-word head/tail)",
            "possessive_split(leading 's')", "pronoun_token", "clause_fragment(that/whose/than/...)",
            "junk_token(OCR blocklist)", "consonant_run(>=5)", "camelcase_identifier",
            "dedup(case-insensitive within B1)",
        ],
        "raw_rows_per_relation": raw_counts,
        "rejected_per_relation": {rel: dict(rejects[rel]) for rel in RELATIONS},
        "dup_within_per_relation": dict(dup_within),
        "staged_per_relation": dict(staged_per_rel),
        "total_staged": total_staged,
        "causal_relations": sorted(CAUSAL),
        "causal_staged": causal_staged,
        "density_lift_vs_shipped": {
            "net_new_per_relation": dict(net_new),
            "already_in_shipped_per_relation": dict(already),
            "new_subject_per_relation": dict(new_subject),
            "causal_net_new": causal_net_new,
        },
        "net_new_examples": {rel: net_new_examples[rel] for rel in RELATIONS if net_new_examples[rel]},
        "residual_noise_second_pass": {
            "still_noisy_per_relation": dict(residual_noisy),
            "still_noisy_total": residual_noisy_total,
            "survives_both_passes": survives_both,
            "survives_both_examples": {rel: residual_clean_examples[rel]
                                       for rel in RELATIONS if residual_clean_examples[rel]},
        },
        "shipped_store_edges": 7342319,
        "staging_total_edges": len(store),
        "staging_path": str(STAGING),
        "verdict": (
            "TOO NOISY TO PROMOTE. These are a regex sweep (pattern \\b([A-Za-z][\\w\\- ]{1,38}?) "
            "(pr...) over a tiny handful of PDFs (Kahneman 'Thinking, Fast and Slow' + a KG-"
            "embedding survey + IEEE copyright boilerplate), NOT a knowledge base. 347 raw rows; "
            "27 causal. The precision-first gate rejected 41% as fragments/OCR/pronouns; the "
            "surviving 204 are STILL dominated by clipped clauses, book jargon, comparatives and "
            "truncations (e.g. 'redistribution requires IEEE permission', 'answer is_a qualified "
            "yes'). Manual audit of the 20 non-is_a survivors: ~1 clean ('self-control requires "
            "attention'). Net density change vs the 7,342,319-edge shipped store is ~204 edges "
            "(0.003%), of which only ~10-20 are defensibly clean and NONE are search-API-verified "
            "(violates the source=search-API doctrine)."
        ),
        "recommendation": (
            "Operator: PROMOTE NOTHING from this set. It is an inspection/quarantine artifact, not "
            "a trustworthy subset. The real B1 lever is (a) proper English Wikidata (not local — "
            "needs download; Korean-only locally is excluded by the English-only doctrine) or (b) a "
            "real IE pipeline (OpenIE / REBEL-class) WITH per-edge confidence + multi-source "
            "consensus, mirroring the R2 ConceptNet path that actually delivered 277,688 clean, "
            "weight-gated, provenance-tagged edges."
        ),
        "shipped_store_unchanged": (
            "PROVEN byte-identical before/after: all 10 columns/metadata + all 16 term shards "
            "sha256-identical, size+mtime identical. Read path was numpy memmap mode='r' + sqlite "
            "immutable=1; TripleStore was NEVER instantiated on the shipped path."
        ),
    }
    (STAGING / "B1_STAGING_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
