# -*- coding: utf-8 -*-
""" → EpistemicGraph + . (ConceptNet + /)
 is_a , (,) . 
 ( ). No LLM.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
CAND = REPO / "data" / "cloud_brain" / "derived_candidates"

ISA_FILES = ["conceptnet_is_a.jsonl", "wikidata_ko_is_a.jsonl", "wikipedia_ko_is_a.jsonl",
             "wikipedia_ko_concrete_is_a.jsonl", "is_a_closure.jsonl"]

FACT_FILES = [("conceptnet_capable_of.jsonl", "capable_of"), ("conceptnet_has_property.jsonl", "has_property"),
              ("conceptnet_has_part.jsonl", "has_part"), ("conceptnet_part_of.jsonl", "part_of"),
              ("conceptnet_used_for.jsonl", "used_for"), ("conceptnet_located_in.jsonl", "located_in"),
              ("conceptnet_원인.jsonl", "원인"), ("conceptnet_구성요소.jsonl", "구성요소")]


def _norm(x: str) -> str:
    return str(x).strip().lower()


def _good_value(s: str, o: str) -> bool:
    """ ([[storage-efficiency-and-intake-filter]] ) — :
 , (6↑/50↑= ), . ↓ ↑ ( )."""
    if not s or not o or s == o:
        return False
    if len(o) > 50 or len(o.split()) > 6:
        return False
    return True


def _iter(fn: str, limit: int):
    p = CAND / fn
    if not p.exists():
        return
    n = 0
    with p.open(encoding="utf-8") as f:
        for line in f:
            if limit and n >= limit:
                break
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("s") and r.get("o"):
                yield r; n += 1


def _seed_schemas(sch):
    """L2 — ( ). , ."""
    sch.add("식당", triggers=["레스토랑", "restaurant", "diner"],
            slots={"staff": "웨이터", "구성원": "손님과 종업원", "목적": "식사"},
            steps=["자리에 앉는다", "주문한다", "먹는다", "계산한다", "나간다"])
    sch.add("병원", triggers=["hospital", "clinic"],
            slots={"staff": "의사와 간호사", "목적": "진료"})
    sch.add("학교", triggers=["school"], slots={"staff": "교사", "목적": "교육", "구성원": "학생과 교사"})


def load_real_brain(max_isa: int = 200000, max_facts: int = 30000, with_schema: bool = True,
                    with_store: bool = True):
    """ . with_store= kg_triples . _load_stats."""
    from packages.reasoning_vm.epistemic_memory import EpistemicGraph
    sch = None
    if with_schema:
        from packages.reasoning_vm.schema_layer import SchemaLayer
        sch = SchemaLayer(); _seed_schemas(sch)
    g = EpistemicGraph(schema=sch, spreading=True)
    n_isa = 0
    for fn in ISA_FILES:
        for r in _iter(fn, max_isa):
            s_n, o_n = _norm(r["s"]), _norm(r["o"])
            if s_n and o_n and s_n != o_n:
                g.add_isa(s_n, o_n); n_isa += 1
    n_fact = 0; n_skip = 0
    for fn, pred in FACT_FILES:
        for r in _iter(fn, max_facts):
            s_n, o_n = _norm(r["s"]), _norm(r["o"])
            if not _good_value(s_n, o_n):
                n_skip += 1; continue
            w = float(r.get("weight", 1.0))
            g.add_fact(s_n, pred, o_n, sources=max(1, min(5, round(w))))
            n_fact += 1
    g._load_stats = {"is_a_edges": n_isa, "facts": n_fact, "facts_filtered": n_skip,
                     "predicates": [p for _f, p in FACT_FILES], "schema_seeded": bool(with_schema)}
    if with_store:
        try:
            from packages.graph_scale.triple_store import TripleStore
            store = TripleStore(str(REPO / "data" / "graph_scale" / "kg_triples"))

            def _lookup(s: str, p: str):
                try:
                    preds = ("defined_as", "is_a") if p == "defined_as" else (p,)
                    rows = store.facts_about(s, limit=16, preds=preds)
                    vals = [o for _s, _p, o in rows if o]
                    if p == "defined_as":
                        vals = [v for v in vals if not any(w in v for w in ("어미", "관형사", "따위에 붙어", "붙는 조사", "More information"))] or vals
                        vals.sort(key=lambda v: (any("가" <= c <= "힣" for c in v), len(v)), reverse=True)
                    if not vals:
                        return None
                    return vals
                except Exception:
                    return None
            g.store_lookup = _lookup
            g._load_stats["store"] = f"kg_triples {store._count:,} triples (on-demand)"
        except Exception as e:
            g._load_stats["store"] = f"unavailable: {type(e).__name__}"
    return g



_ART = re.compile(r"^(?:a|an|the)\s+", re.I)
_PATTERNS = [

    (re.compile(r"^what can (.+?) do\??$", re.I), "capable_of"),
    (re.compile(r"^what (?:is|are) (.+?) used for\??$", re.I), "used_for"),
    (re.compile(r"^what (?:is|are) (.+?) made of\??$", re.I), "has_part"),
    (re.compile(r"^(?:what are the parts of|parts of) (.+?)\??$", re.I), "has_part"),
    (re.compile(r"^what (?:is|are) (.+?) (?:a )?part of\??$", re.I), "part_of"),
    (re.compile(r"^where (?:is|are) (.+?)\??$", re.I), "located_in"),
    (re.compile(r"^what causes (.+?)\??$", re.I), "원인"),
    (re.compile(r"^(?:properties|nature|characteristics) of (.+?)\??$", re.I), "has_property"),

    (re.compile(r"^(.+?)(?:은|는|이|가)?\s*무엇을?\s*할 수\s*있", re.I), "capable_of"),
    (re.compile(r"^(.+?)(?:은|는|이|가)?\s*(?:어디|무엇)에?\s*(?:쓰|사용)", re.I), "used_for"),
    (re.compile(r"^(.+?)의?\s*(?:부분|구성 ?요소)", re.I), "has_part"),
    (re.compile(r"^(.+?)(?:은|는)?\s*어디에?\s*있", re.I), "located_in"),
    (re.compile(r"^(.+?)의?\s*원인", re.I), "원인"),
    (re.compile(r"^(.+?)의?\s*(?:특징|성질)", re.I), "has_property"),
    (re.compile(r"^(.+?)(?:은|는|이|가)?\s*(?:뭐야|무엇|뭔가요|뜻이?|정의)", re.I), "defined_as"),
    (re.compile(r"^what is (?:a |an |the )?(.+?)\??$", re.I), "defined_as"),                     # what is X
]


def _clean_subject(s: str) -> str:
    return _norm(_ART.sub("", s.strip().rstrip("?").strip()))


def parse_question(q: str) -> Optional[tuple[str, str]]:
    """ → (, ). 's|p' 's.p' . None()."""
    q = q.strip()
    if "|" in q:
        s, _, p = q.partition("|"); return _clean_subject(s), p.strip()
    m = re.fullmatch(r"\s*([^.]+)\.([a-z_가-힣]+)\s*", q)     # s.p
    if m:
        return _clean_subject(m.group(1)), m.group(2)
    for pat, pred in _PATTERNS:
        m = pat.search(q)
        if m and m.group(1).strip():
            return _clean_subject(m.group(1)), pred
    return None



_VERIFY_PATTERNS = [
    (re.compile(r"^can (?:a |an |the )?(.+?) (.+?)\??$", re.I), "capable_of"),  # can X Y → X capable_of Y?
    (re.compile(r"^(?:is|are) (.+?) (?:a|an|the) (.+?)\??$", re.I), "is_a"),   # is X a Y?
    (re.compile(r"^(.+?)(?:은|는|이|가)?\s*(.+?)\s*(?:할 수 있|수 있)", re.I), "capable_of"),
    (re.compile(r"^(.+?)(?:은|는|이|가)\s*(.+?)(?:일까|인가|이야|야|니|입니까)\??$", re.I), "is_a"),
]


def parse_verify_question(q: str) -> Optional[tuple[str, str, str]]:
    """ → (, , ). 's|p|o' . None()."""
    q = q.strip()
    if q.count("|") == 2:
        s, p, o = q.split("|"); return _clean_subject(s), p.strip(), _norm(o)
    for pat, pred in _VERIFY_PATTERNS:
        m = pat.search(q)
        if m and m.group(1).strip() and m.group(2).strip():
            return _clean_subject(m.group(1)), pred, _clean_subject(m.group(2))
    return None
