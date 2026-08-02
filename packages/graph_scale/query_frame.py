# -*- coding: utf-8 -*-
"""Query semantic frame — understand the question ONCE, then route.

The systemic problem (owner's precision-strike directive): the answer path was a
race of regex lanes, each RE-GUESSING the subject and the intent. Two whole
failure classes fell out of it:
 * WRONG SUBJECT — ' ?' picked (the longest noun) and returned
 's definition, because subject extraction was 'content nouns, longest
 first' with NO grammar. (the real subject) was even dropped for being 1
 character.
 * MISROUTE — ' ' / ' ?' got the definition of the
 head noun, because the definition lane fires on ANY known concept regardless
 of what is actually being ASKED.

The fix is one structural parse, not more guards. A QueryFrame reads the
question's Korean grammar ONCE and yields:
 * subject — what the question is ABOUT (the genitive possessor, the topic)
 * relation — 'X Y' makes Y the requested relation (attribute), not a subject
 * answer_type — definition | relation | procedure | opinion | preference |
 entity | greeting | smalltalk | realtime | unknown
 * conversational — whether this is talk, not lookup

Everything downstream reads the frame: subject extraction takes frame.subject
first (single-char included), the triple lookup uses frame.relation, and the
self-router uses frame.answer_type. No lane re-guesses.

Data-fused: the LEARNED router (trained, No-LLM) supplies the intent prior; the
grammatical parse supplies subject/relation and CORRECTS the router where the
router is weak. Deterministic, cheap, testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# question words / frame markers that are never the subject
_QWORDS = {"뭐", "뭐야", "무엇", "무어", "누구", "언제", "어디", "어느", "어떤", "어떻게",
           "왜", "몇", "얼마", "무슨", "가장", "정말", "진짜"}

_BOUND_NOUNS = {"게", "것", "건", "거", "수", "줄", "바", "때", "데", "점", "적", "채", "만큼",
                "중", "등", "및", "간", "뿐", "따름", "터", "리", "만"}
# pronouns / indefinites that are never a meaningful lookup subject on their own
_PRONOUNS = {"이거", "그거", "저거", "이것", "그것", "저것", "여기", "거기", "저기", "이곳",
             "그곳", "저곳", "아무것", "아무", "무언가", "누군가", "우리", "저희", "너", "나",
             "당신", "네가", "내가", "얘", "걔", "쟤", "이건", "그건", "저건", "방금", "지금"}
_JOSA_TAIL = re.compile(r"(은|는|이|가|을|를|의|에|에서|으로|로|와|과|도|만|이란|란|이라는|라는)$")


# A conjugated verb/adjective is NEVER a lookup subject. The old _VERBISH was a tiny

# These endings are UNAMBIGUOUSLY verbal — a standalone noun cannot end this way.
_PRED_END = re.compile(
    r"(는데|은데|잖아요?|거든요?|더라|더군|구나|군요?|네요|려고|려면|자마자|던데|던걸"
    r"|았어?요?|었어?요?|였어?요?|겠어?요?|는다|ㄴ다|린다|랬|래요?|을까요?|ㄹ까요?"
    r"|나요|으세요|세요|해줘|해라|해요|아줘|어줘|지\s*마|을래|ㄹ래|냐|니\?|든지)$")

# a bounded curated set of the frequent ones (LAD morphology layer; rule-based is OK here).
_PRED_WORDS = {
    "좋아", "싫어", "커", "작아", "많아", "적어", "없어", "있어", "같아", "달라", "맞아",
    "이래", "그래", "저래", "어때", "돼", "안돼", "힘들어", "괜찮아", "아파", "예뻐", "멋져",
    "없는데", "없잖아", "있잖아", "좋잖아", "그렇잖아", "몰라", "알아", "해", "먹어", "가", "와",
    "정리해줘", "알려줘", "말해줘", "설명해줘", "보여줘",
}


def _is_predicate(tok: str) -> bool:
    """True if the token is a conjugated verb/adjective (a predicate), never a subject noun.
 Combines the robust ending set, the curated ambiguous-form set, and the legacy verb-stem
 endings (_VERBISH: ///// …) so nothing regresses."""
    t = (tok or "").strip()
    if not t:
        return False
    return bool(_PRED_END.search(t)) or t in _PRED_WORDS or bool(_VERBISH.search(t))

# relation surface -> the graph predicate family it asks for (used as intent).
# NOT a topic table — these are RELATION words (attributes), bounded and generic.
_RELATION_WORDS = {
    "수도": "capital", "화학식": "화학식", "저자": "author", "설립자": "설립자",
    "창시자": "설립자", "인구": "인구", "면적": "면적", "위치": "위치",
    "대통령": "국가원수", "총리": "정부수반", "ceo": "최고경영자", "대표": "최고경영자",
    "감독": "감독", "작가": "author", "발명자": "발명자", "발견자": "발견자",
    "국가": "country", "나라": "country", "종류": "is_a", "일종": "is_a",
    "뜻": "defined_as", "의미": "defined_as", "정의": "defined_as",
}

# procedure frame — asks HOW to do, not what a thing IS
_PROCEDURE = re.compile(r"(만드는\s*법|하는\s*법|끓이는\s*법|굽는\s*법|짓는\s*법"
                        r"|어떻게\s*(만들|해|하는지|하면|끓|굽)|레시피|방법\s*(알려|좀|이\s*뭐))")

# opinion / preference / feeling / small-talk — conversation, not lookup


_OPINION = re.compile(r"(어떻게\s*생각|뭐라고?\s*생각|무슨\s*생각|네\s*생각|너\s*생각"
                      r"|의견\s*(이|은)|어떻게\s*봐|어떤\s*것?\s*같아"
                      r"|(중요|소중|값진|의미|필요|가치)[가-힣]*\s*(게|것|건|점)\s*(뭐|무엇|어떤|어느|일까|인가))")
_PREFERENCE = re.compile(r"(좋아|싫어|선호|즐기)(해|하니|하세요|하나요|합니까|하시나요)\s*\??\s*$")
_FEELING = re.compile(r"(기분|컨디션|느낌)\s*(어때|어떠|좋아|괜찮)|힘들지|피곤하")
_SMALLTALK = re.compile(r"(심심|지루|재밌는\s*(얘기|이야기)|놀자|뭐\s*하고\s*놀|얘기\s*하자|말\s*걸)")
_ADVICE = re.compile(r"(어떻게\s*해야\s*(할까|하지|될까|좋을까)|조언\s*(좀|해)|어쩌면\s*좋)")
_GREETING = re.compile(r"(^|\s)(안녕|하이|헬로|반가|반갑|ㅎㅇ|잘\s*지내|좋은\s*(아침|저녁))")
_REALTIME = re.compile(r"(지금|오늘|현재|내일|요즘)\s*.*(날씨|시세|주가|가격|시간)"
                       r"|(날씨|시세|주가)\s*(어때|얼마|어떻게)")


@dataclass
class QueryFrame:
    raw: str
    subject: str = ""
    relation: str | None = None
    answer_type: str = "unknown"
    conversational: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"subject": self.subject, "relation": self.relation,
                "answer_type": self.answer_type, "conversational": self.conversational}


def _clean(tok: str) -> str:
    """Strip a trailing particle — but ONLY if a real stem (≥2 chars) remains. Korean content
 nouns often END in a syllable that is also a particle ( '', '', ''),
 so blindly stripping destroyed them (→, →). The ≥2 guard protects them while
 still peeling particles off longer tokens (→, →)."""
    t = tok.strip()
    stripped = _JOSA_TAIL.sub("", t).strip()
    return stripped if len(stripped) >= 2 else t


# adverbs / degree words that are never a lookup subject
_ADVERBS = {"안", "못", "잘", "더", "좀", "막", "딱", "또", "꼭", "늘", "참", "곧", "아주",
            "너무", "매우", "제일", "그냥", "이미", "아직", "방금", "금방", "자주", "가끔"}



_VERBISH = re.compile(r"(었|았|였|겠|만든|만들|했|한다|된다|이야|에요|예요|어요|아요|"
                      r"드는|하는|인가|랬|볼까|을까|ㄹ까)$")


# ENGLISH FUNCTION WORDS (2026-07-17). Every check below it is Korean — question words, bound
# nouns, particles, conjugated predicates — because this extractor was built for Korean. Kiwi tags
# an English token as SL (latin) and waves it through as a content noun, so English function words
# passed the gate and became the subject. This is the SINGLE upstream origin of a whole family of
# measured failures: query_frame.parse("What does a polar bear look like?").subject == 'like' fed
# semantic_frame → engage → the answer "like is a kind of kind. like relates to unlike."
# Korean is head-final so taking the trailing noun-ish token is right there and exactly wrong here.
# Shared with the lexicon lane rather than copied — one list, one behaviour.
try:
    from packages.graph_scale.lexicon_lane import _FUNCTION_WORDS as _EN_FUNCTION_WORDS
except Exception:  # pragma: no cover - keep the parser usable if the cartridge module moves
    _EN_FUNCTION_WORDS = frozenset()
_EN_NON_SUBJECT = set(_EN_FUNCTION_WORDS) | {
    "look", "looks", "looked", "like", "likes", "liked", "mean", "means", "meant",
    "better", "best", "worse", "different", "difference", "compare", "compared",
    "want", "wants", "need", "needs", "get", "gets", "got", "make", "makes", "made",
    "say", "says", "said", "work", "works", "start", "starts", "help", "helps",
    "kind", "kinds", "sort", "sorts", "type", "types", "thing", "things", "way", "ways",
}


def _ok_noun(base: str) -> bool:
    """A token that can serve as a real lookup subject: a content noun, not a question
    word, bound noun, pronoun/indefinite, adverb, or conjugated predicate."""
    if base and base.isascii() and base.lower() in _EN_NON_SUBJECT:
        return False
    return bool(base) and (base not in _QWORDS and base not in _BOUND_NOUNS
                           and base not in _PRONOUNS and base not in _ADVERBS
                           and not _is_predicate(base))





# so a predicate can never be mistaken for a subject. Falls back to the regex path if Kiwi is down.
_CONTENT_TAGS = {"NNG", "NNP", "SL", "SH"}   # common/proper noun, latin, hanja
_VERBALIZER_TAGS = {"XSV", "XSA"}



# topic. The topic is the clause's argument (the object X, or the agent A). Grammatical, not a rule

#





#     measured), so they stay as a small closed floor list. This set does NOT grow per topic.
_PLACEHOLDER_HEADS = {"사람", "사람들", "분", "이", "것", "거", "게", "누구", "무엇",
                      "작품", "책", "곡", "노래", "영화", "그림", "말", "글", "곳", "데"}


def _is_placeholder_head(tok: Any) -> bool:
    """A relative-clause head that stands FOR the clause's argument, not a concrete answer. Bound
 nouns (NNB) and pronouns (NP) qualify by their Kiwi POS (learned, generalises to unseen );
 the small generic-common-noun floor above catches the NNG cases POS can't distinguish."""
    if tok is None:
        return False
    return getattr(tok, "tag", "") in ("NNB", "NP") or getattr(tok, "form", "") in _PLACEHOLDER_HEADS


def _np_with_particles(toks: list) -> list[tuple[str, str]]:
    """(noun_compound, following_particle_tag) for each noun phrase, in order. The particle tells us
    the grammatical role (JKO=object, JKS=subject, JX=topic) — how we find the clause's real topic."""
    out: list[tuple[str, str]] = []
    run: list[str] = []
    for i, t in enumerate(toks):
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if t.tag in _CONTENT_TAGS or (t.tag == "XSN" and run):
            run.append(t.form)
            contig = (nxt is not None and (nxt.tag in _CONTENT_TAGS or nxt.tag == "XSN")
                      and getattr(nxt, "start", -1) == getattr(t, "start", 0) + getattr(t, "len", len(t.form)))
            if not contig:
                ptag = nxt.tag if (nxt is not None and nxt.tag.startswith("J")) else ""
                out.append(("".join(run), ptag)); run = []
        elif run:
            out.append(("".join(run), "")); run = []
    if run:
        out.append(("".join(run), ""))
    return out


def _relative_clause_subject(toks: list) -> str:
    """'X [verb]- /' → the topic is X (the object), not the placeholder head /.
 'A [verb]- ' → the topic is A (the agent). Returns the argument noun, or '' if this is not
 a relative-clause-with-placeholder-head question (e.g. 'X ' — is a real head)."""
    for i, t in enumerate(toks):
        is_verb = t.tag in ("VV", "VA", "VV-I", "VA-I", "XSV", "XSA")
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if not (is_verb and nxt is not None and nxt.tag == "ETM"):
            continue
        head = toks[i + 2] if i + 2 < len(toks) else None
        if not _is_placeholder_head(head):
            continue   # head is a concrete noun → not this pattern
        nps = _np_with_particles(toks[:i])
        obj = next((c for c, p in nps if p == "JKO" and _ok_noun(c)), "")
        subj = next((c for c, p in nps if p in ("JKS", "JX") and _ok_noun(c)), "")



        if getattr(head, "form", "") in ("데", "때", "지", "줄", "수", "만큼"):
            if subj:
                return subj
            if obj:
                return obj
        else:
            if obj:
                return obj
            if subj:
                return subj
        for c, _p in reversed(nps):
            if _ok_noun(c):
                return c
    return ""




_PERSON_HEADS = {"사람", "사람들", "분", "누구", "이"}
# CREATION-class verb stems — the relation vocabulary this executor serves (same LAD/ontology
# bridge status as _RELATION_CUES). Without this gate ANY relative clause with a bound-noun head


_CREATE_STEMS = ("만들", "창제", "창시", "발명", "세우", "짓", "쓰", "고안", "발견", "설립", "개발", "저술", "창립")


def _create_verb_lemma(toks: list, i: int) -> str:
    """The creation-verb stem at position i, or '' when the verb is not creation-class.
 Handles both plain verbs (/VV) and NOUN+ verbalizations (+/XSV → )."""
    t = toks[i]
    form = getattr(t, "form", "")
    if t.tag in ("VV", "VV-I") and any(form.startswith(s) for s in _CREATE_STEMS):
        return form
    if t.tag == "XSV" and form.startswith("하") and i > 0:
        prev = getattr(toks[i - 1], "form", "")
        if toks[i - 1].tag in ("NNG", "NNP", "XR") and any(prev.startswith(s) for s in _CREATE_STEMS):
            return prev
    return ""


def relation_ask(text: str) -> dict[str, Any] | None:
    """Detect a CREATION-relation question morphologically and name what it asks for.
 Shape 1 (relative clause): ' ?' → {anchor: , asked: agent}
 ' ?' → {anchor: , asked: product}
 Shape 2 (finite interrogative-subject): ' ?' → {anchor, asked: agent}
 Returns None for concrete heads ('X '), non-creation verbs (' '), and
 non-relative questions. This routes to RELATION EXECUTION instead of (a) a definition dump
 of the anchor or (b) the false-premise verifier composing the placeholder as a real object."""
    if not re.search(r"[가-힣]", text or ""):
        return None
    try:
        from packages.base_brain.neighborhood import _kiwi
        kw = _kiwi()
        if kw is None:
            return None
        toks = list(kw.tokenize(text))
    except Exception:
        return None
    for i, t in enumerate(toks):
        verb = _create_verb_lemma(toks, i)
        if not verb:
            continue
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        # ── shape 1: V + ETM + placeholder head (relative clause) ────────────────────────
        if nxt is not None and nxt.tag == "ETM":
            head = toks[i + 2] if i + 2 < len(toks) else None
            if not _is_placeholder_head(head):
                continue
            nps = _np_with_particles(toks[:i])
            # the placeholder fills the clause's MISSING role — pure grammar: object stated →
            # maker asked; agent stated → product asked.
            obj = next((c for c, p in nps if p == "JKO" and _ok_noun(c)), "")
            subj = next((c for c, p in nps if p in ("JKS", "JX") and _ok_noun(c)), "")
            if obj:
                return {"anchor": obj, "asked": "agent", "verb": verb}
            if subj:
                return {"anchor": subj, "asked": "product", "verb": verb}
            continue

        has_who = any(x.tag == "NP" and x.form == "누구" for x in toks[:i])
        if has_who:
            nps = _np_with_particles(toks[:i])
            anchor = (next((c for c, p in nps if p in ("JX", "JKS", "JKO") and _ok_noun(c)), "")
                      or next((c for c, _p in nps if _ok_noun(c)), ""))
            if anchor and anchor != "누구":
                return {"anchor": anchor, "asked": "agent", "verb": verb}
    return None


def _kiwi_subject(text: str) -> str:
    """The topic content-noun of a question, via morphology. Joins adjacent nouns into the
 maximal compound (+ → ), drops (+ → not a subject), and
 returns the FIRST substantial compound (Korean is topic-fronted) or '' when there is none
 (a predicate-only utterance like ' ?' → no subject → caller declines/clarifies)."""
    if not re.search(r"[가-힣]", text):
        return ""   # Korean-only: English is tokenized as latin (SL) — the regex path handles it
    try:
        from packages.base_brain.neighborhood import _kiwi
        kw = _kiwi()
        if kw is None:
            return ""
        toks = list(kw.tokenize(text))
    except Exception:
        return ""

    rc = _relative_clause_subject(toks)
    if rc:
        return rc
    compounds: list[str] = []
    run: list[str] = []
    for i, t in enumerate(toks):
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        nxt_tag = nxt.tag if nxt else ""
        is_noun = (t.tag in _CONTENT_TAGS and t.form not in _QWORDS
                   and nxt_tag not in _VERBALIZER_TAGS)
        is_suffix = (t.tag == "XSN" and bool(run))
        if is_noun or is_suffix:
            run.append(t.form)
            # only join into a compound when the NEXT noun is CONTIGUOUS (no space between) —

            contiguous = (nxt is not None and (nxt.tag in _CONTENT_TAGS or nxt.tag == "XSN")
                          and getattr(nxt, "start", -1) == getattr(t, "start", 0) + getattr(t, "len", len(t.form)))
            if not contiguous:
                compounds.append("".join(run))
                run = []
        elif run:
            compounds.append("".join(run))
            run = []
    if run:
        compounds.append("".join(run))
    for c in compounds:
        if _ok_noun(c):
            return c
    return ""


def _head_noun(span: str) -> str:
    """The last CONTENT noun of a span. Skips predicates/pronouns/bound nouns so a trailing
 verb ('') or pronoun ('') is never taken as the subject. Empty when the span
 holds no real noun — the caller then declines rather than defining a predicate."""
    for tok in reversed(re.findall(r"[가-힣A-Za-z0-9]+", span)):
        base = _clean(tok)
        if _ok_noun(base) and len(base) >= 1:
            return base
    return ""


def _fronted_topic(body: str) -> str:
    """The topic/subject noun before a case particle. Korean is topic-fronted, so the subject
 is usually here, not the trailing noun (' ' -> ). Prefer the STRONG
 topic/object markers (/////); fall back to locative/comitative (/////)
 so ' …', ' …' still yield a real subject instead of the trailing verb."""
    for pat in (r"([가-힣A-Za-z0-9]{2,20}?)(?:은|는|이|가|을|를)(?:\s|$)",
                r"([가-힣A-Za-z0-9]{2,20}?)(?:이랑|랑|과|와|하고)(?:\s)",
                r"([가-힣A-Za-z0-9]{2,20}?)(?:에서|에게|한테|에|도)(?:\s)"):
        for m in re.finditer(pat, body):
            cand = m.group(1).strip()   # group already excludes the particle — do NOT re-strip
            if _ok_noun(cand):
                return cand
    return ""


def parse(question: str) -> QueryFrame:
    """One structural parse of the question. See module docstring."""
    q = str(question or "").strip()
    f = QueryFrame(raw=q)
    if not q:
        return f

    # 1) CONVERSATION frames win first — these are talk, not lookup.
    if _GREETING.search(q) and len(q) <= 24:
        f.answer_type, f.conversational = "greeting", True
        return f
    if _FEELING.search(q):
        f.answer_type, f.conversational = "feeling", True
        return f
    if _OPINION.search(q):
        f.answer_type, f.conversational = "opinion", True
        f.subject = _opinion_topic(q)
        return f
    if _PREFERENCE.search(q) or (re.search(r"(^|\s)(너|넌|너는|당신|네|니)\b", q)
                                 and re.search(r"(좋아|싫어|선호)", q)):
        f.answer_type, f.conversational = "preference", True
        f.subject = _opinion_topic(q)
        return f
    if _ADVICE.search(q):
        f.answer_type, f.conversational = "advice", True
        return f
    if _SMALLTALK.search(q):
        f.answer_type, f.conversational = "smalltalk", True
        return f
    if _REALTIME.search(q):
        f.answer_type = "realtime"
        return f

    # 2) PROCEDURE — how to DO, not what a thing IS.
    if _PROCEDURE.search(q):
        f.answer_type = "procedure"


        # verb, so take the FIRST content noun, not the one adjacent to the verb.
        for tok in re.findall(r"[가-힣A-Za-z0-9]+", q):
            base = _clean(tok)
            if (base and base not in _QWORDS and base not in _BOUND_NOUNS
                    and not base.endswith(("게", "히", "이"))  # skip adverbs
                    and len(base) >= 2):
                f.subject = base
                break
        return f



    m = re.search(r"([가-힣A-Za-z0-9 ]{1,30}?)\s*의\s+([가-힣A-Za-z0-9]{1,20})\s*(은|는|이|가)?\s*"
                  r"(뭐|무엇|누구|어디|어떻게|알려|말해)?", q)
    if m and "의" in q:
        subj = _clean(m.group(1))
        rel_word = _clean(m.group(2))
        if subj and rel_word and rel_word not in _QWORDS:

            # known relation word is a request to DEFINE the concept Y, not to

            if (rel_word.lower() not in _RELATION_WORDS
                    and re.search(r"(무엇|뭐야|뭐냐|뭔가|이란|란\b|뜻|정의|설명)", q)):
                f.subject = rel_word
                f.answer_type = "definition"
                return f
            f.subject = subj
            f.relation = _RELATION_WORDS.get(rel_word.lower(), rel_word)
            f.answer_type = "relation"
            return f


    m = re.search(r"([가-힣A-Za-z0-9]{2,20})\s*(?:은|는)\s+([가-힣A-Za-z0-9]{1,20})\s*(?:이|가)\s*(?:뭐|무엇)", q)
    if m:
        subj, rel_word = _clean(m.group(1)), _clean(m.group(2))
        if subj and rel_word and rel_word not in _QWORDS:
            f.subject, f.relation, f.answer_type = subj, _RELATION_WORDS.get(rel_word.lower(), rel_word), "relation"
            return f


    #    subject = the topic noun (genitive-free); single-char subjects allowed.
    if re.search(r"(누구|who)", q, re.I):
        f.answer_type = "entity"
    else:
        f.answer_type = "definition"
    f.subject = _definition_subject(q)
    return f


def _en_noun_phrase(body: str) -> str:
    """The English subject is a contiguous CONTENT-WORD RUN, not the trailing noun.

    _head_noun is head-final by design (correct for Korean), so English multiword entities lost
    their modifier: measured 2026-07-17, "What does the Eiffel Tower look like?" → 'Tower', which
    then answered about the Tower of London. 'Eiffel Tower' and 'Tower' are different things.

    English genitives are head-FIRST ("the purpose of a firewall" is about the firewall, not the
    purpose), so a trailing TOPIC-PREPOSITION phrase wins when present — otherwise the longest
    run, earliest on a tie (English is topic-first in these question shapes).

    'about' marks the topic exactly as 'of' does, and leaving it out cost a real wrong answer:
    "Why do people care about barony?" → 'people care' (a 2-word run beats the 1-word 'barony'),
    so the subject became the question's own framing. Measured 2026-07-17.
    """
    toks = re.findall(r"[A-Za-z0-9][A-Za-z0-9.'-]*", body)
    if not toks:
        return ""

    def _runs(seq: list[str]) -> list[list[str]]:
        out: list[list[str]] = []
        cur: list[str] = []
        for t in seq:
            # check the stem before a contraction: "What's" must stop on "what", while a real
            # possessive ("Newton's") keeps its head. Measured: "What's a firewall?" → "What's".
            stem = t.lower().split("'")[0]
            if stem in _EN_NON_SUBJECT or t.lower() in _EN_NON_SUBJECT or len(stem) < 2:
                if cur:
                    out.append(cur)
                    cur = []
            else:
                cur.append(t)
        if cur:
            out.append(cur)
        return out

    tail = re.split(r"\b(?:of|about|regarding|concerning)\b", body, flags=re.IGNORECASE)
    pool = _runs(re.findall(r"[A-Za-z0-9][A-Za-z0-9.'-]*", tail[-1])) if len(tail) > 1 else []
    pool = pool or _runs(toks)
    if not pool:
        return ""
    best = max(pool, key=lambda r: (len(r), -pool.index(r)))
    return " ".join(best)[:48]


def _definition_subject(q: str) -> str:
    """Subject of an 'X / X' question: the topic before the copular frame."""

    body = re.sub(r"\s*(은|는|이|가)?\s*(뭐야|뭐|무엇|누구|누구야|이란|란|이라는|라는|알려줘|설명해|뜻이?\s*뭐).*$",
                  "", q).strip()
    body = body or q



    # The regex path is ONLY a fallback for when Kiwi is unavailable.
    try:
        from packages.base_brain.neighborhood import _kiwi
        if _kiwi() is not None and re.search(r"[가-힣]", q):   # Korean only; English → regex path
            return _kiwi_subject(q)
    except Exception:
        pass
    if not re.search(r"[가-힣]", body):
        return _en_noun_phrase(body) or _fronted_topic(body) or _head_noun(body)
    return _fronted_topic(body) or _head_noun(body)


def _opinion_topic(q: str) -> str:
    """Topic an opinion/preference question is ABOUT ( -> )."""
    body = re.sub(r"(에\s*대해서?|에\s*관해서?|이란|라는\s*게)?\s*"
                  r"(뭐라고?|무슨|어떻게|어떤)?\s*(생각|봐|같아|좋아|싫어|선호).*$", "", q).strip()
    head = _head_noun(body)
    return "" if head in _QWORDS or head in {"너", "당신", "네", "니"} else head
