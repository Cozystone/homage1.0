# -*- coding: utf-8 -*-
"""Narrative corpus — the growing body of LANGUAGE the self's voice is fit on.

Owner (2026-07-10): " ATANOR , 
 " — realize_thought speaks by fitting HolographicLM on lived
language; this module is the pipeline that makes that language ACCUMULATE instead of evaporate.

Two mining lanes feed one persistent store (data/surface_brain/narrative_corpus.jsonl):
 * moltbook — shielded informational comments from the commons (dissection lane output);
 * expedition — clean candidate/consensus sentences from autonomous reading;
 * monologue — the self-play loop's own accepted sentences (closing the flywheel).

HARD BOUNDARY (answer-pack vs cloud-graph split applies here too): this corpus is SURFACE
LANGUAGE ONLY — register, rhythm, token connectivity. It is never read as a fact store and
never feeds answers directly; facts stay in the gated graph. A single-source sentence is fine
HERE (we're learning how people phrase things, not whether they're right).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "data" / "surface_brain" / "narrative_corpus.jsonl"

# ── multiprocess sharding (split-then-merge): each learner process OWNS one file so two
# processes never write the same path (the single-writer contract). ATANOR_CORPUS_SHARD=<id>
# makes this process WRITE narrative_corpus.shard<id>.jsonl; reads always UNION main + every
# shard (lock-free, append-only). With no shard env the behaviour is byte-identical to before.
# See docs/ATANOR_multiprocess_sharding_design.md.
_SHARD_ENV = "ATANOR_CORPUS_SHARD"


def _shard_id() -> str | None:
    v = (os.environ.get(_SHARD_ENV) or "").strip()
    return v or None


def _write_path() -> Path:
    sid = _shard_id()
    return CORPUS if sid is None else CORPUS.with_name(f"narrative_corpus.shard{sid}.jsonl")


def _read_paths() -> list[Path]:
    """main + every shard file (sorted, deterministic). A shard worker still READS the union
    for cross-shard dedup and a complete diet; it only WRITES its own file."""
    shards = sorted(CORPUS.parent.glob("narrative_corpus.shard*.jsonl"))
    paths = ([CORPUS] if CORPUS.exists() else []) + shards
    return paths or [CORPUS]


def _tail_entries(window: int) -> list[dict[str, Any]]:
    """Newest `window` parsed entries across main + all shard files, merged by ISO timestamp
    (append-only files are already per-file chronological; the merge orders across files)."""
    rows: list[tuple[str, dict[str, Any]]] = []
    for p in _read_paths():
        try:
            lines = p.read_text(encoding="utf-8").splitlines()[-window:]
        except Exception:
            continue
        for line in lines:
            try:
                e = json.loads(line)
            except Exception:
                continue
            rows.append((str(e.get("at") or ""), e))
    rows.sort(key=lambda r: r[0])
    return [e for _, e in rows[-window:]]


# The sLLM diet target (owner's 150k-line goal). The old 20k cap contradicted that goal — it kept
# the voice starved. 150k JSONL lines ≈ ~15MB, safe in memory during a rotate; the historical OOM
# was the 10.2M-term KG dictionary, NOT this bounded ring. Env-overridable for tuning.
_MAX_LINES = int(os.getenv("ATANOR_CORPUS_MAX_LINES", "150000") or 150000)
_MIN_LEN, _MAX_LEN = 8, 240
                              # floor in the language branches is the real fragment filter (2026-07-13)

_URLISH = re.compile(r"https?://|www\.|\.com|\.org|\.net", re.I)
_MARKUPISH = re.compile(r"[{}<>\[\]|=]{2,}|&#\d+;|\\u[0-9a-f]{4}", re.I)
# page furniture that the weak gate let through (measured in the live diet 2026-07-11:

# captions, TOC/nav crumbs, section numbers, figure labels — not language worth learning.
_DEBRIS = re.compile(r"\[이미지\]|\[영상\]|\[화면 구성\]|Powered by|MediaWiki|둘러보기|목차|각주|"
                     r"편집\s*\]|그림\s*\d|·|…\s*$|\d+\.\d+\.?\s*$")


def _quality(text: str) -> bool:
    """Keep only sentences that can TEACH the voice something: real prose, not debris. The voice
    is fit on THIS diet — every junk line here is a junk phrase it may one day speak."""
    t = text.strip()
    if not (_MIN_LEN <= len(t) <= _MAX_LEN):
        return False
    if _URLISH.search(t) or _MARKUPISH.search(t) or _DEBRIS.search(t):
        return False
    if re.match(r"^\d+\s", t):
        return False
    letters = sum(1 for ch in t if ch.isalpha() or "가" <= ch <= "힣")
    if letters < len(t) * 0.55:           # mostly symbols/numbers → not language worth learning
        return False
    hangul = sum(1 for ch in t if "가" <= ch <= "힣")
    latin = sum(1 for ch in t if ch.isascii() and ch.isalpha())

    # ENGLISH ONLY (doctrine, 2026-07-18: ATANOR thinks in English; the I/O boundary refuses
    # Korean — one exit, one filter). The old Korean-acceptance branch predated that decision and
    # became the pollution door: Naver board debris like '…이런 옷 뭔가요' ends in a legitimate
    # Korean sentence-ender, sailed through, and was then FIT AS THE SELF'S OWN VOICE —
    # compose_thought spoke portal junk as 'I' (test_voice red, 2026-07-21). The voice's diet is
    # the voice's identity; only clean English sentences may feed it.
    if hangul > 0:
        return False
    if latin >= letters * 0.85:                   # pure English (or other Latin) sentence
        if not re.search(r"[.!?]['\"\)\]]?\s*$", t):
            return False                  # must end like a sentence, not a fragment
        return len(t.split()) >= 3
    return False


def _hash(text: str) -> str:
    return hashlib.md5(text.strip().encode("utf-8")).hexdigest()[:16]


# ── REGISTER (owner 2026-07-11, diet acceleration): the wiki-volume lane is 55% encyclopedic

# corpus TAIL, so a wiki flood makes it recite like an encyclopedia. We don't fight the volume
# (declaratives ARE the grammar skeleton); we make CONSUMPTION register-aware so the scarce
# conversational/question/emotive lines (the human register) are over-sampled into the voice's
# diet. Classification is shallow surface morphology — no model, no table of facts.
# English register morphology (ported 2026-07-21 with the English-only diet; the Korean-era
# patterns classified nothing once the intake refused Korean, so the balancer sampled blind).
_R_FIRST = re.compile(r"\b(I|I'm|I've|I'd|I'll|my|me|we|our|us|you|your)\b")
_R_QUESTION = re.compile(r"[?]\s*$|^(what|why|how|where|who|when|which|is it|are you|do you|"
                         r"did you|can you|could|would|should|shall)\b", re.I)
_R_EMOTION = re.compile(r"\b(love|loved|happy|glad|sad|lonely|excited|excites|afraid|scared|"
                        r"miss|missed|warm|wonderful|beautiful|grateful|thankful|hurts?|joy|"
                        r"tired|relieved|proud|sorry|hope|hoping|feel|feels|feeling|felt)\b", re.I)
_R_DECL = re.compile(r"\b(is|are|was|were)\s+(a|an|the|made|known|used|called|considered|"
                     r"composed|defined|located)\b|\b(refers to|consists of|is defined as)\b", re.I)

def register(text: str) -> str:
    """Shallow register tag for a sentence: question | conversational | emotive | encyclopedic |
    narrative. Surface morphology only (sentence endings, first-person, feeling words)."""
    t = (text or "").strip()
    if _R_QUESTION.search(t):
        return "question"
    if _R_FIRST.search(t):
        return "conversational"
    if _R_EMOTION.search(t):
        return "emotive"
    if _R_DECL.search(t):
        return "encyclopedic"
    return "narrative"


# the human-voice registers we want OVER-represented in the fit relative to their store frequency
_VOICE_REGISTERS = ("question", "conversational", "emotive")


def _load_hashes() -> set[str]:
    out: set[str] = set()
    for p in _read_paths():          # union main + shards so a shard never re-adds a known line
        try:
            with p.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        out.add(str(json.loads(line).get("h") or ""))
                    except Exception:
                        continue
        except Exception:
            continue
    return out


def add_lines(lines: list[str], *, source: str) -> int:
    """Append quality-filtered, deduped sentences. Returns how many were actually added.
    Caller contract: text must already be POST-SHIELD (both current callers shield first)."""
    cand = [t.strip() for t in lines if _quality(t or "")]
    if not cand:
        return 0
    seen = _load_hashes()
    added = 0
    write_path = _write_path()          # main, or this process's own shard file
    try:
        write_path.parent.mkdir(parents=True, exist_ok=True)
        with write_path.open("a", encoding="utf-8") as fh:
            for t in cand:
                h = _hash(t)
                if h in seen:
                    continue
                seen.add(h)
                fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "h": h,
                                     "source": source, "text": t}, ensure_ascii=False) + "\n")
                added += 1
    except Exception:
        return added
    _rotate_if_needed()
    return added


def _rotate_if_needed() -> None:
    # rotate only THIS process's file (single-writer). Global rotation across shards is the
    # offline compactor's job (scripts/corpus_compactor.py), never a concurrent writer's.
    path = _write_path()
    try:
        # cheap fast-path: a JSONL line here is >40 bytes, so a file under _MAX_LINES*40 CANNOT be
        # over the cap — skip reading the whole file (now up to ~15MB) into memory on every append.
        if path.stat().st_size < _MAX_LINES * 40:
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > _MAX_LINES:
            path.write_text("\n".join(lines[-_MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def corpus_tail(n: int = 80, *, sources: tuple[str, ...] | None = None,
                balanced: bool = False) -> list[str]:
    """The newest n corpus sentences (optionally filtered by source) — realize_thought's diet.

    balanced=True: register-aware sampling. Reaches back through more history and caps the
    encyclopedic register at ~⅓ of the return, filling the rest from the scarce human-voice
    registers (question/conversational/emotive) + narrative — so a wiki-declarative flood in
    the raw tail can't make the voice recite like an encyclopedia. Recency preserved within
    each register; falls back to plain tail if history is too thin."""
    try:
        window = n * (12 if balanced else 3)
        rows: list[tuple[str, str]] = []          # (text, register)
        for e in _tail_entries(window):           # union of main + shard files, newest window
            if sources and str(e.get("source") or "") not in sources:
                continue
            t = str(e.get("text") or "").strip()
            if t:
                rows.append((t, register(t) if balanced else ""))
        if not balanced:
            return [t for t, _ in rows][-n:]
        if len(rows) < n:
            return [t for t, _ in rows]
        # bucket by register, newest-last within each
        buckets: dict[str, list[str]] = {}
        for t, rg in rows:
            buckets.setdefault(rg, []).append(t)
        enc_cap = max(1, n // 3)                   # encyclopedic ceiling
        out: list[str] = []
        # 1) pull the voice registers first (most recent of each), round-robin so none dominates
        voice_pool = {r: list(reversed(buckets.get(r, []))) for r in _VOICE_REGISTERS}
        voice_pool["narrative"] = list(reversed(buckets.get("narrative", [])))
        target_voice = n - enc_cap
        while len([x for x in out]) < target_voice and any(voice_pool.values()):
            for r in (*_VOICE_REGISTERS, "narrative"):
                if voice_pool[r]:
                    out.append(voice_pool[r].pop(0))
                    if len(out) >= target_voice:
                        break
        # 2) fill remaining slots with the newest encyclopedic lines (bounded)
        for t in reversed(buckets.get("encyclopedic", [])):
            if len(out) >= n:
                break
            out.append(t)
        # 3) if still short (thin history), top up from anything newest-first
        if len(out) < n:
            seen = set(out)
            for t, _ in reversed(rows):
                if t not in seen:
                    out.append(t)
                    seen.add(t)
                    if len(out) >= n:
                        break
        return out[:n]
    except Exception:
        return []


def stats() -> dict[str, Any]:
    try:
        by: dict[str, int] = {}
        by_reg: dict[str, int] = {}
        total = 0
        for p in _read_paths():          # union main + every shard
            try:
                fh = p.open("r", encoding="utf-8")
            except Exception:
                continue
            with fh:
                for line in fh:
                    try:
                        e = json.loads(line)
                        s = str(e.get("source") or "?")
                    except Exception:
                        continue
                    by[s] = by.get(s, 0) + 1
                    rg = register(str(e.get("text") or ""))
                    by_reg[rg] = by_reg.get(rg, 0) + 1
                    total += 1
        # voice-register share = how conversational the diet is (encyclopedic flood pushes it down)
        voice = sum(by_reg.get(r, 0) for r in _VOICE_REGISTERS)
        return {"total": total, "by_source": by, "by_register": by_reg,
                "voice_share": round(voice / total, 3) if total else 0.0}
    except Exception:
        return {"total": 0, "by_source": {}, "by_register": {}, "voice_share": 0.0}


# ── miners ─────────────────────────────────────────────────────────────────────────────────

_SENT_SPLIT = re.compile(r"(?<=[.!?다요죠네까])\s+")


def mine_text(text: str, *, limit: int = 12) -> list[str]:
    """Split running text (a comment, a paragraph) into corpus-worthy sentences."""
    segs = [s.strip() for s in _SENT_SPLIT.split(text or "") if s.strip()]
    return [s for s in segs if _quality(s)][:limit]


def mine_triples(triples: list[tuple[str, str, str]], *, limit: int = 20) -> list[str]:
    """Knowledge triples → narrative sentences, via the graph's OWN utterance machinery
 (grounded_composer themed corpus), not a fresh phrasing table. Falls back to the minimal
 copula frame (josa-corrected) only when the composer holds no utterance for the concept —
 the same + fallback the composer itself uses."""
    out: list[str] = []
    for s, _r, o in triples[:limit]:
        s, o = str(s).strip(), str(o).strip()
        if not s or not o:
            continue
        line = None
        try:
            from packages.grounded_composer.creative_composer import _themed_corpus
            themed, _src, _con = _themed_corpus(s)
            line = next((t for t in (themed or []) if s in t and o in t), None)
        except Exception:
            pass
        if line is None:
            # the Korean copula fallback died with the English-only doctrine (2026-07-18):
            # the voice's diet is English, so what feeds it must be too — the structural
            # frame realizer words the triple faithfully, in English, by construction.
            try:
                from packages.realizer_struct.frame_realizer import realize
                line = realize([[s, str(_r).strip() or "is_a", o]])
            except Exception:
                line = None
        if line and _quality(line):
            out.append(line)
    return out
