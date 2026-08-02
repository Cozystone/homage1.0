"""Adapters that turn large open sentence corpora into graph fuel.

The structured lane (Wikidata/ConceptNet) gives verbatim (s,p,o) facts. But most large open
data is SENTENCES, not triples: Tatoeba (multilingual example sentences + translations),
OpenSubtitles (spoken/conversational), OSCAR / Common Crawl (web text per language), AI Hub
(Korean domain corpora), Wiktionary (word definitions). These are ingestion GOLD for two
different needs, so each sentence is routed to the lane it actually serves:

 1. DEFINITIONAL sentences -> (subject, defined_as / is_a, object) TRIPLES.
 " " => (, is_a, ). A Wiktionary/AI-Hub definition becomes a
 directly answerable fact. Pattern-based and CONSERVATIVE: only clear copular/definitional
 frames, so it adds facts without fabricating (a sentence that isn't a clean definition
 yields nothing).

 2. BILINGUAL PAIRS (Tatoeba links) -> (term_ko, alias, term_en) alias triples.
 This is the direct fix for the measured material-starvation problem: a Korean query
 couldn't reach an English-labelled concept. Mining aligned translation pairs grows the
 cross-lingual alias layer from real parallel data, not a hand list.

 3. Everything else (examples, dialogue) -> the SENTENCE corpus (surface lane), which feeds
 language fluency / the GCG "flesh", not the fact store. Kept separate so surface text
 never contaminates the verified triple store.

Honesty: lane 1 only emits a triple when the sentence is an unambiguous definition; lanes 2/3
never touch the fact store's truth guarantees. Nothing here scrapes or invents — it re-shapes
already-published corpora into the representation each part of the engine can use.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Iterator, TextIO

# ---- transparent open (plain / .gz / .bz2) ---------------------------------------------

def open_text(path: str | Path) -> TextIO:
    import bz2
    import gzip

    p = Path(path)
    if p.suffix.lower() == ".gz":
        return gzip.open(p, "rt", encoding="utf-8")
    if p.suffix.lower() == ".bz2":
        return bz2.open(p, "rt", encoding="utf-8")
    return p.open(encoding="utf-8")


# ---- lane 1: definitional-sentence -> triple -------------------------------------------

# Definitional frames, each paired with the predicate it entails. Conservative: subject is a





# the real copula keeps this a definition extractor, not a verb-sentence miner.
_KO_DEF: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(?P<s>[가-힣A-Za-z0-9 ]{1,20}?)(?:은|는)\s+"
                r"(?P<o>[가-힣A-Za-z0-9 ]{1,40}?)의\s+(?:일종|한 종류|종류)(?:이다|입니다)\.?$"), "is_a"),


    # continues past a comma stays an honest MISS, never a meaning-changing cut.
    (re.compile(r"^(?P<s>[가-힣A-Za-z0-9 ]{1,20}?)(?:은|는|이란|란|이라는|라는)\s+"
                r"(?P<o>[가-힣A-Za-z0-9·~, ]{2,90}?)(?:이다|입니다|이라고 한다|을 말한다|를 말한다"
                r"|을 가리킨다|를 가리킨다|을 일컫는다|를 일컫는다)\.?$"), "defined_as"),
]
# Encyclopedia first sentences open with a field adverbial ('In botany, …') that the bare
# ^ anchor rejected — recall lost for zero precision gain. The adverbial is consumed, not kept.
_EN_LEAD = r"(?:In [A-Za-z][A-Za-z \-]{1,30},\s+)?"
_EN_DEF: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^" + _EN_LEAD + r"(?:(?:a|an|the)\s+)?(?P<s>[A-Za-z][A-Za-z0-9 \-]{1,40}?)\s+(?:is|are)\s+(?:a|an|the)\s+"
                r"(?P<o>[A-Za-z][A-Za-z0-9 ,\-']{1,150}?)\.?$", re.I), "is_a"),
    (re.compile(r"^" + _EN_LEAD + r"(?:(?:a|an|the)\s+)?(?P<s>[A-Za-z][A-Za-z0-9 \-]{1,40}?)\s+refers to\s+(?:a|an|the)?\s*"
                r"(?P<o>[A-Za-z][A-Za-z0-9 ,\-']{1,150}?)\.?$", re.I), "defined_as"),
    # 'X is the process/study/… of …' — the standard abstract-noun definition frame
    # (AutoML, photosynthesis…): keep the frame noun IN the object, verbatim.
    (re.compile(r"^" + _EN_LEAD + r"(?:(?:a|an|the)\s+)?(?P<s>[A-Za-z][A-Za-z0-9 \-]{1,40}?)\s+(?:is|are)\s+"
                r"(?P<o>the (?:process|study|practice|act|set|branch|field|form|method|art|science) of "
                r"[A-Za-z][A-Za-z0-9 ,\-']{1,150}?)\.?$", re.I), "defined_as"),
    # entailment-preserving genus frame (is_a ONLY): object = the genus head before
    # a restrictive clause/appended predicate. X is_a 'B that C' entails X is_a B —
    # the class only widens, so the stored fact stays true (standard genus-differentia).
    (re.compile(r"^" + _EN_LEAD + r"(?:(?:a|an|the)\s+)?(?P<s>[A-Za-z][A-Za-z0-9 \-]{1,40}?)\s+(?:is|are)\s+(?:a|an|the)\s+"
                r"(?P<o>[A-Za-z][A-Za-z0-9 ,\-']{1,90}?)(?:\s+that\s|\s+which\s|,\s+and\s|,\s+but\s)", re.I), "is_a"),
]
_STOP_SUBJECT = {"그", "이", "저", "그것", "이것", "it", "this", "that", "there", "he", "she", "they"}


def extract_definition_triple(sentence: str) -> tuple[str, str, str] | None:
    """Return (subject, predicate, object) if the sentence is a clean definition, else None.
 predicate = 'is_a' for the taxonomic 'X / a X' frame, else 'defined_as'."""
    s = sentence.strip()
    if not s or len(s) > 240:
        return None

    # Hanja/romanization aside breaks the subject pattern but carries no assertion.
    # Same normalization the promotion gate applies; conservative (removes, never adds).
    s = re.sub(r"\s*\([^)]*\)", "", s).strip()



    # sentence by same-sentence alias rules.)
    s = re.sub(r"^([가-힣A-Za-z0-9]{1,20}) 또는 [가-힣A-Za-z0-9]{1,20}(은|는)\s", r"\1\2 ", s)
    if not s or len(s) > 200:
        return None
    for pat, pred in _KO_DEF + _EN_DEF:
        m = pat.match(s)
        if m:
            subj, obj = m.group("s").strip(), m.group("o").strip()
            if (subj.lower() in _STOP_SUBJECT or subj.lower() == obj.lower()
                    or not subj or not obj):
                continue  # this frame misfired; another may fit honestly




            if re.search(r"(?:이고|이며|하고),", obj) or re.search(r",\s*(?:and|but|so|then|which|whose|who)\s", obj, re.I):
                continue  # welded clause under THIS frame; the genus frame may still apply
            return subj, pred, obj
    return None


def iter_definition_triples(sentences: Iterable[str]) -> Iterator[tuple[str, str, str]]:
    for sent in sentences:
        t = extract_definition_triple(sent)
        if t:
            yield t


# ---- lane 2: Tatoeba (sentences + translation links) -----------------------------------

def iter_tatoeba_sentences(path: str | Path, langs: tuple[str, ...] = ("kor", "eng")) -> Iterator[tuple[int, str, str]]:
    """Tatoeba sentences.csv: id<TAB>lang<TAB>text. Yields (id, lang, text) for wanted langs."""
    with open_text(path) as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3 and parts[1] in langs:
                try:
                    yield int(parts[0]), parts[1], parts[2].strip()
                except ValueError:
                    continue


def iter_tatoeba_alias_pairs(sentences_path: str | Path, links_path: str | Path,
                             langs: tuple[str, str] = ("kor", "eng")) -> Iterator[tuple[str, str, str]]:
    """Join Tatoeba sentences.csv with links.csv (id<TAB>translation_id) to emit aligned
 (ko_text, 'alias', en_text) pairs — cross-lingual alias fuel. Short single-term pairs are
 the useful ones ( <-> artificial intelligence), so we keep pairs whose sides look
 like terms/short phrases, not whole sentences."""
    lang_of: dict[int, str] = {}
    text_of: dict[int, str] = {}
    for sid, lang, text in iter_tatoeba_sentences(sentences_path, langs):
        lang_of[sid] = lang
        text_of[sid] = text
    a_lang, b_lang = langs
    with open_text(links_path) as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            try:
                x, y = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            if x not in lang_of or y not in lang_of:
                continue
            # orient to (a_lang side, b_lang side)
            if lang_of[x] == a_lang and lang_of[y] == b_lang:
                ko, en = text_of[x], text_of[y]
            elif lang_of[x] == b_lang and lang_of[y] == a_lang:
                ko, en = text_of[y], text_of[x]
            else:
                continue
            # keep term-like pairs (short, no sentence punctuation) — those are alias-worthy
            if 2 <= len(ko) <= 24 and 2 <= len(en) <= 30 and not re.search(r"[.?!]", ko + en):
                yield ko, "alias", en


# ---- lane 3: plain sentence corpora (surface lane) -------------------------------------

def iter_line_sentences(path: str | Path) -> Iterator[str]:
    """One sentence per line (OpenSubtitles mono, deduped text dumps)."""
    with open_text(path) as fh:
        for line in fh:
            s = line.strip()
            if s:
                yield s


def iter_oscar_sentences(path: str | Path) -> Iterator[str]:
    """OSCAR / Common Crawl: JSONL with a 'text' field (may be multi-sentence) or plain text.
    Splits paragraphs into sentences so the surface corpus is sentence-granular."""
    with open_text(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            text = line
            if line.startswith("{"):
                try:
                    text = json.loads(line).get("text", "") or ""
                except Exception:
                    text = line
            for sent in re.split(r"(?<=[.?!。])\s+|\n+", text):
                sent = sent.strip()
                if len(sent) >= 4:
                    yield sent


def iter_wiktionary_definitions(path: str | Path,
                                langs: tuple[str, ...] = ("ko", "en")) -> Iterator[tuple[str, str, str]]:
    """Wiktionary extracts as JSONL. Two shapes are accepted:
 - simple {"word": ..., "definition": ...}
 - wiktextract {"word": ..., "lang_code": "ko", "senses": [{"glosses": [...]}]}
 (the kaikki.org dump format; a Korean-edition dump defines MANY languages'
 words in Korean, so lang_code keeps the store on-language)
 Each becomes a (word, defined_as, gloss-head) triple, where the gloss head is the
 first noun phrase of the definition — + structure."""
    with open_text(path) as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            word = (rec.get("word") or rec.get("title") or "").strip()
            gloss = (rec.get("definition") or rec.get("gloss") or "").strip()
            if not gloss:  # wiktextract shape: first non-empty gloss of any sense
                lang = rec.get("lang_code")
                if lang is not None and lang not in langs:
                    continue
                for sense in rec.get("senses") or []:
                    glosses = sense.get("glosses") or []
                    if glosses and str(glosses[0]).strip():
                        gloss = str(glosses[0]).strip()
                        break
            if not word or not gloss:
                continue
            head = re.split(r"[,.;(]|이다|입니다|를 말한다|을 말한다", gloss, maxsplit=1)[0].strip()
            head = re.sub(r"^(?:하나의|일종의|어떤)\s+", "", head)
            if 2 <= len(head) <= 40 and head != word:
                yield word, "defined_as", head


# ---- SentenceStore: the surface corpus (kept separate from the fact store) --------------

class SentenceStore:
    """Append-only sentence corpus with a language tag, for the surface/fluency lane. It is
    deliberately NOT the triple store: surface text must never be treated as verified fact.
    Stored as JSONL so it streams; deduped by exact text within a run."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "sentences.jsonl"
        self._seen: set[int] = set()
        self._count = self._existing_count()

    def _existing_count(self) -> int:
        if not self.path.exists():
            return 0
        return sum(1 for _ in self.path.open(encoding="utf-8"))

    def add_many(self, sentences: Iterable[str], lang: str = "ko") -> dict[str, int]:
        added = 0
        with self.path.open("a", encoding="utf-8") as fh:
            for s in sentences:
                s = s.strip()
                if not s:
                    continue
                h = hash(s)
                if h in self._seen:
                    continue
                self._seen.add(h)
                fh.write(json.dumps({"text": s, "lang": lang}, ensure_ascii=False) + "\n")
                added += 1
        self._count += added
        return {"added": added, "total": self._count}

    def __len__(self) -> int:
        return self._count
