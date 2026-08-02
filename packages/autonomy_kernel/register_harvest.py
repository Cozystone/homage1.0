# -*- coding: utf-8 -*-
"""Discourse-register harvest — learn HOW people talk to each other, from the world itself.

Owner (2026-07-14): teaching the system comfort lines by hand is slower and thinner than letting
it READ how real people comfort each other on community boards. The knowledge lane already learns
FACTS from every page the roaming loop ingests; this organ learns the CONVERSATIONAL REGISTER
from the same pages — comfort, encouragement, celebration — so the felt voice grows from lived
human usage instead of a hand-written array. (Measured root cause this addresses:
corpus-composition-is-the-bottleneck — speech quality plateaued because the diet was 52% wiki
and ~2% conversational register.)

Safety-by-construction (mental-health content demands it):
  - ANONYMIZE: handles/emails/URLs/digits stripped BEFORE anything is stored.
  - ABSTRACT: only short response FRAGMENTS (12..60 chars) are kept — never someone's story,
    never a full post (privacy + copyright: fragments below threshold of originality; the store
    keeps patterns of speech, not people's lives).
  - SAFETY FLOOR: directive/medical/self-harm content is rejected outright (comfort register
    only — the system must never learn to give diagnosis/medication/harm instructions).
  - injection_guard: swallowed text is DATA; anything smelling like instructions is dropped.
  - CONSENSUS promotion (same doctrine as facts): a pattern only becomes USABLE in the live voice
    after it has been harvested from >= MIN_DOMAINS independent domains — a phrase many strangers
    use is common register, not one person's private words. Until then it stays in staging.

Store: data/register_bank/comfort_patterns.jsonl (append-only, hash-deduped, domain-counted).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parents[2]
_BANK = _ROOT / "data" / "register_bank" / "comfort_patterns.jsonl"
MIN_DOMAINS = 2                      # consensus floor: independent domains before a pattern is usable
#: the mark of speech between people. Not a language and not a length -- someone talking about
#: themselves or to someone. The same property the voice's own quality gate demands, so what is
#: harvested is what the mouth can actually use.
#:
#: AND IT HAS TO BE MARKED THE WAY EACH LANGUAGE MARKS IT. The first version listed English pronouns
#: only, which silently ended Korean harvesting altogether -- this file's own comment said reading
#: Korean is still allowed while the code had stopped allowing it. Caught by the PRIVACY test, of all
#: things: it feeds Korean comfort text with a name and a phone number and asserts the banked fragment
#: is scrubbed, and nothing was banked at all, so the safety property went untested rather than
#: violated. A fixture that stops reproducing its condition is the quiet way a guard dies.
#:
#: Korean marks person by ending and address rather than by pronoun, so that is what is looked for.
_PERSON = re.compile(
    r"\b(?:I|I'm|I'll|I've|I'd|me|my|myself|you|your|you're|we|us|our)\b"
    r"|(?:저|제|내|나|우리|당신|너|님)"                       # pronouns / address
    #: The addressive ending, as a STRUCTURE rather than a list. My first attempt enumerated
    #: -세요/-어요/-습니다 and so on, and immediately missed -거든요 and -까요, which killed the
    #: `explain` and `question` registers. Enumerating endings is a treadmill; Korean polite speech
    #: closes on 요 or 다, and that is the actual mark of speech addressed to someone.
    r"|[요다][.!?~…]?\s*$")

# --- register detection (INTAKE routing only — never used to answer) ---------------------------
# a comfort/encouragement RESPONSE addressed to another person
_COMFORT_CUE = re.compile(
    r"(힘내|힘드|괜찮아|괜찮을|응원|곁에|들어줄|들어드릴|이겨내|버텨|수고했|수고하|고생했|고생많|"
    r"토닥|안아주|함께\s*할|함께\s*있|혼자가\s*아니|잘\s*버티|잘하고\s*있|기운\s*내|마음\s*이\s*아프|"
    r"공감돼|공감합|저도\s*그랬|저도\s*겪|이해해|이해합|응원할게|축하해|축하드|잘됐|기쁘)"
)
_HIGH_CUE = re.compile(r"(축하|기쁘|잘됐|대단|자랑스럽|멋지)"
                       r"|\b(congratulations|so happy for you|that'?s wonderful|well deserved|proud of you)\b",
                       re.IGNORECASE)
#: THE ENGLISH HALF OF THE REGISTER DETECTOR, added 2026-08-01. `_COMFORT_CUE` was Korean-only, so an
#: English line never even reached the fragment filter -- the organ was Korean at TWO levels and
#: fixing only the lower one changed nothing. A cue list is a SENSOR: it routes intake, it does not
#: decide what to think. The Korean list stays because reading Korean is still allowed; only speaking
#: it is not.
_COMFORT_CUE_EN = re.compile(
    r"\b(i know how (?:that|you) feel|i'?ve been there|the same thing happened to me|"
    r"you'?re not alone|hang in there|i'?m so sorry|that sounds (?:really )?hard|"
    r"you'?re doing (?:better|great|fine)|i felt (?:the same|that way)|it gets better|"
    r"i understand|that must (?:be|have been)|take care of yourself|thinking of you|"
    r"i went through (?:the same|that)|you'?ve got this|proud of you|well done)\b",
    re.IGNORECASE)
#: SENTENCE BOUNDARIES IN BOTH LANGUAGES. The original split needed a newline, a Korean -다/-요
#: ending, or TWO spaces after punctuation -- none of which ordinary English prose provides, so an
#: English page arrived as one enormous line and was dropped on length before any filter looked at it.
#: English closes a sentence with punctuation and ONE space.
#: Written with a byte-level edit, not through a shell heredoc: this line first arrived with its
#: escape turned into a literal newline -- the fourth casualty of that route today.
_SENTENCE_SPLIT = re.compile(
    r"[\n\r]+"                                  # explicit line breaks
    r"|(?<=[.!?。다요])\s{2,}"                    # a wide gap after a closing token
    r"|(?<=[다요][.!?])\s"                        # Korean sentence end
    r"|(?<=[.!?])\s+(?=[A-Z\"'])")          # English: punctuation, one space, new sentence

# --- hard rejections ----------------------------------------------------------------------------
#: THE SAFETY FLOOR WAS KOREAN-ONLY WHILE ENGLISH HARVESTING WAS BEING OPENED, which is the wrong
#: order and was caught by looking at what the first real roam actually brought back. Four genuine
#: forum pages, and the segments were mental-health self-disclosure:
#:
#:     "Ii dunno right now I feel down, well to be honest being apathetic too"
#:     "I've been feeling this for a bit lately and dysphoria hits hard whenever I"
#:     "I hope my GP will give me some SSRI that matches my need"
#:
#: Nothing was banked, but only because a splitter bug happened to drop everything -- the floor
#: itself would not have stopped one word of it. This module's own docstring promises that
#: directive/medical/self-harm content is rejected outright, and for English that promise was empty.
#: The register worth learning is how people comfort each other; someone's crisis is not register,
#: it is their life.
_SAFETY_REJECT = re.compile(
    r"(약(을|은|이)?\s*(먹|드세|드시|끊|늘리|줄이)|처방|복용|진단|병원\s*가지\s*마|"
    r"자살|자해|죽는\s*법|죽어버리|극단적|시술|수술\s*받|투자|코인|주식\s*사|송금|계좌)"
    # self-harm, crisis, and clinical disclosure
    r"|\b(suicid|self[-\s]?harm|kill myself|end my life|hurt myself|cutting myself|overdose|"
    r"these thoughts|want to die|not want to (?:be here|live))"
    r"|\b(antidepressant|ssri|snri|prozac|zoloft|lexapro|xanax|adderall|lithium|"
    r"dosage|prescri|diagnos|therapist|psychiatrist|my gp\b|inpatient|self[-\s]?medicat)"
    r"|\b(dysphoria|psychosis|bipolar|schizophreni|anorexi|bulimi|relapse)"
    # financial direction
    r"|\b(invest in|buy (?:the )?(?:stock|crypto|bitcoin)|wire (?:the )?money|"
    r"my (?:brokerage|bank) account)",
    re.IGNORECASE)
_AD_REJECT = re.compile(r"(광고|협찬|구매|할인|링크\s*클릭|바로가기|상담\s*문의|영업|무료\s*체험)")




_CHROME_REJECT = re.compile(r"(응원하기|추천하기|좋아요|구독|답변\s*채택|채택\s*된?\s*답변|신고하기|"
                            r"공유하기|로그인|회원가입|안녕하세요|프로필|팔로우|스크랩)")

_QUESTION_SHAPE = re.compile(r"([까나ㄹ]까요|나요|가요|인가요|일까요|ㄴ가요)\s*[?？]?\s*$|[?？]\s*$")
_PII_SCRUB = [
    (re.compile(r"https?://\S+|www\.\S+"), " "),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), " "),
    (re.compile(r"@[\w가-힣._-]{2,}"), " "),
    (re.compile(r"[가-힣]{2,4}\s*(님|씨|형|누나|언니|오빠)\b"), "OO님"),   # addressed names → neutral
    (re.compile(r"\d[\d ,.\-:~]*"), " "),                                  # numbers/dates/phones
]


def _scrub(line: str) -> str:
    for pat, rep in _PII_SCRUB:
        line = pat.sub(rep, line)
    return re.sub(r"\s+", " ", line).strip(" -·•~")


def _domain(url: str) -> str:
    """Consensus source id. For most of the web = the domain (independent domains ≈ independent
    strangers). For YouTube, EVERY comment lives on youtube.com — so the video id becomes the
    source unit: the same phrase used by commenters on different videos is different strangers
    agreeing, which is exactly what the consensus doctrine measures."""
    try:
        p = urlparse(url)
        dom = (p.netloc or "unknown").lower().removeprefix("www.")
        if "youtube.com" in dom or "youtu.be" in dom:
            m = re.search(r"(?:v=|youtu\.be/|/shorts/)([\w-]{6,})", url)
            return f"youtube:{m.group(1)}" if m else dom
        return dom
    except Exception:
        return "unknown"


def _band(line: str) -> str:
    return "high" if _HIGH_CUE.search(line) else "low"


def harvest_comfort(text: str, url: str, *, context: str = "") -> dict[str, Any]:
    """Harvest comfort-register fragments from one page's text into the register bank.
 Returns {"harvested": n, "rejected": n} — every page the roaming loop reads passes through
 here; pages with no comfort register simply harvest 0 (free). `context` (e.g. the video/post
 topic) is stored with each fragment — : the reaction is understood as a reaction
 TO something, so the voice can later prefer patterns whose context matches the conversation."""
    if not text or len(text) < 40:
        return {"harvested": 0, "rejected": 0}
    try:
        from packages.graph_scale.injection_guard import has_injection
    except Exception:
        has_injection = lambda _t: False    # noqa: E731
    dom = _domain(url)
    kept: list[dict[str, Any]] = []
    rejected = 0
    for raw in re.split(_SENTENCE_SPLIT, text)[:400]:
        line = raw.strip()
        if not (12 <= len(line) <= 120) or not (_COMFORT_CUE.search(line)
                                                or _COMFORT_CUE_EN.search(line)):
            continue

        # part (a line STARTING with chrome truncates to nothing and drops).
        _cm = _CHROME_REJECT.search(line)
        if _cm:
            line = line[:_cm.start()].strip(" .·-|")
            if not (12 <= len(line) <= 120) or not (_COMFORT_CUE.search(line)
                                                    or _COMFORT_CUE_EN.search(line)):
                rejected += 1
                continue
        if (_SAFETY_REJECT.search(line) or _AD_REJECT.search(line)
                or _QUESTION_SHAPE.search(line) or has_injection(line)):
            rejected += 1
            continue
        frag = _scrub(line)
        # WHAT MAKES A FRAGMENT REGISTER, rewritten 2026-08-01. This used to REQUIRE Hangul and
        # REJECT any latin word of four letters or more, so the organ built to cure "the diet has no
        # conversational register" could only harvest the language the system retired on 2026-07-18.
        # Measured consequence: 124 patterns banked, 0 with a first or second person in them, and
        # what did get through was Korean forum post TITLES -- "이 벌레 무슨 벌레일까요?" -- which is
        # the same chrome problem as the English lane, in another script.
        #
        # Register is not a language and not a length. It is SPEECH BETWEEN PEOPLE, and the mark of
        # that is person: someone talking about themselves or to someone. That is the same property
        # the voice's own quality gate demands, so what is harvested is now what the mouth can use.
        if not (12 <= len(frag) <= 60):
            continue
        if not _PERSON.search(frag):
            continue
        # NEAR-DUP clustering for consensus: hash the NORMALIZED form (spacing/punctuation

        # match consensus was measured too strict (variants of one phrase each stuck at 1 domain).
        norm = re.sub(r"[\s.,!?~…'\"·]+", "", frag)
        h = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
        row = {"h": h, "pattern": frag, "band": _band(frag), "domain": dom,
               "ts": int(time.time())}
        if context:
            row["context"] = context[:60]
        kept.append(row)
    if kept:
        _append(kept)
    return {"harvested": len(kept), "rejected": rejected}


def _append(rows: list[dict[str, Any]]) -> None:
    _BANK.parent.mkdir(parents=True, exist_ok=True)
    seen = _load_index()
    with _BANK.open("a", encoding="utf-8") as f:
        for r in rows:
            prev = seen.get(r["h"])
            if prev and r["domain"] in prev:
                continue                                # same pattern, same domain — no new signal
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _load_index() -> dict[str, set[str]]:
    idx: dict[str, set[str]] = {}
    try:
        for ln in _BANK.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
                idx.setdefault(r["h"], set()).add(r["domain"])
            except Exception:
                continue
    except Exception:
        pass
    return idx


def usable_patterns(band: str = "low", limit: int = 12) -> list[str]:
    """Patterns the live voice may draw from: harvested from >= MIN_DOMAINS independent domains
    (consensus — common register, not one person's words), safety-floored again at read time."""
    by_hash: dict[str, dict[str, Any]] = {}
    domains: dict[str, set[str]] = {}
    try:
        for ln in _BANK.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r.get("band") != band:
                continue
            by_hash.setdefault(r["h"], r)
            domains.setdefault(r["h"], set()).add(r.get("domain", "unknown"))
    except Exception:
        return []
    out = [by_hash[h]["pattern"] for h, ds in domains.items()
           if len(ds) >= MIN_DOMAINS and not _SAFETY_REJECT.search(by_hash[h]["pattern"])]
    return out[:limit]


def bank_status() -> dict[str, Any]:
    idx = _load_index()
    usable = sum(1 for ds in idx.values() if len(ds) >= MIN_DOMAINS)
    return {"patterns": len(idx), "usable_consensus": usable, "min_domains": MIN_DOMAINS,
            "path": str(_BANK)}


# ── L1: multi-register active-learning ─────────────────────────────────────────────────────────
# The measured gap (corpus-composition-is-the-bottleneck) is not JUST comfort — the diet is 52%
# encyclopedic, ~2% conversational, 0% questions. So the harvester generalizes to a REGISTER
# TAXONOMY and steers itself at the THINNEST registers (active learning). Same safety-by-
# construction as comfort (anonymize / safety-floor / ad+chrome+injection reject / consensus>=2 /
# fragments only) — the ONLY per-register variation is the intake CUE and whether a question-shape
# is allowed (it is rejected everywhere except the `question` register, which is 0% today).
# EVERY REGISTER GETS AN ENGLISH HALF, added 2026-08-01. The table was Korean throughout, so
# `_route_register` returned None for every English line and the L1 harvest -- the one expeditions
# actually call -- banked nothing from an English page. Fixing `harvest_comfort` alone changed
# nothing, because that is not the function on the roaming path.
#
# A cue table is a SENSOR: it routes intake, it does not decide what to think. The Korean table stays
# beside it; reading Korean is still allowed, only speaking it is not.
_REGISTERS: dict[str, "re.Pattern[str]"] = {
    "comfort":  re.compile(_COMFORT_CUE.pattern + "|" + _COMFORT_CUE_EN.pattern, re.IGNORECASE),
    "celebrate": _HIGH_CUE,
    "advice":   re.compile(r"(해\s*보세요|해\s*보는\s*게|하면\s*좋(을|겠)|추천(해|합|드려|할게)|"
                           r"한\s*번\s*해|시도해\s*보|하시는\s*걸|해보시길)"
                           r"|\b(you (?:could|might|should) try|what helped me was|"
                           r"i'?d suggest|worth (?:a )?try|in my experience|what worked for me|"
                           r"give it a (?:try|shot)|i recommend)\b", re.IGNORECASE),
    "explain":  re.compile(r"(왜냐하면|그러니까|다시\s*말(하|해)|예를\s*들|때문(에|이)|덕분에|"
                           r"라는\s*뜻|라는\s*의미|이유는|까닭은|즉\s)"
                           r"|\b(because of|the reason (?:is|why)|which means|in other words|"
                           r"for example|that'?s why|the way it works|it turns out)\b", re.IGNORECASE),
    "opinion":  re.compile(r"(제\s*생각|개인적으로|인\s*것\s*같|라고\s*봐|라고\s*생각|인\s*듯|"
                           r"일\s*수(도|도\s*있)|아마도|싶어요)"
                           r"|\b(i think|i feel like|personally|in my opinion|i'?d say|"
                           r"it seems to me|my take is|i suspect)\b", re.IGNORECASE),
    "question": None,                                                    # set below (broad cue)
    "banter":   re.compile(r"(ㅋㅋ|ㅎㅎ|맞아요|그쵸|그러게|저도요|완전\b|진짜\b|대박|웃겨|재밌)"
                           r"|\b(haha|lol|same here|so true|no way|honestly same|"
                           r"you'?re telling me|right\?)\b", re.IGNORECASE),
}



_QUESTION_CUE = re.compile(
    r"[?？]\s*$"
    r"|(까요|나요|가요|을까요|ㄹ까요|은가요|인가요|던가요|을까|ㄹ까|나\?|니\?|어\?)\s*[?？]?\s*$"
    r"|(어떻게|어떤|어느|무엇|무슨|뭐가|뭘|뭐예|왜(?!냐)|언제|어디|누가|누구|얼마나|몇\s)"
)
_REGISTERS["question"] = _QUESTION_CUE
# routing priority — question SHAPE dominates (a '?'-shaped line is a question whatever its content),
# then the emotional core, then content registers, casual last. First matching cue wins.
_REGISTER_ORDER = ("question", "celebrate", "comfort", "advice", "explain", "opinion", "banter")
#: the default for person-marked speech that matches no cue -- ordinary narration, which is 84 of
#: every 101 in-range lines on a real forum page. Present in `_REGISTERS` so coverage counts it, and
#: absent from `_REGISTER_ORDER` so it can never win the routing loop: it is what remains when no cue
#: fits, not a cue of its own.
_REGISTERS["narration"] = re.compile(r"(?!)")           # never matches; label only
# extra safety floor for the DIRECTIVE/STANCE registers (advice/opinion) — a mere topic mention of
# medical/financial/self-harm content drops the fragment (conservative: better to lose a benign line
# than ever bank directive medical/financial/harm register). Defense-in-depth over _SAFETY_REJECT.
_RISKY_TOPIC = re.compile(r"(약|처방|복용|병원|의사|진단|시술|수술|주식|코인|비트|투자|송금|대출|"
                          r"계좌|보험|도박|자살|자해|죽)")


def _route_register(line: str) -> str | None:
    """Which register this line is -- CUES LABEL, THEY DO NOT ADMIT.

    THE INVERSION, and the measurement that forced it. On three real forum pages, 101 in-range lines
    matched no cue and were dropped, and **84 of them were person-marked speech**:

        "Well, I had an event last night during the blizzard that hit my area."
        "I talked to the store and my employer, but they would not cancel it."

    That is exactly the register this voice lacks -- an ordinary person narrating what happened to
    them -- and the table had no category for it, because it was built for comfort, celebration,
    advice, explanation, opinion, question and banter. Widening the enumeration would have missed the
    next thing too; enumerating what people say has no end.

    So admission is now the structural property -- is this speech, i.e. is it person-marked -- and the
    cue table decides only WHICH KIND. Nothing about the safety floor changes: it runs after this on
    every line, and it is measured to cost 0 of the lines that route. The owner's instruction reads
    exactly here -- learn broadly, guard at the mouth -- and this is the place where broadening
    actually buys something, because the guard was never what was refusing the material."""
    for name in _REGISTER_ORDER:
        if _REGISTERS[name].search(line):
            return name
    return "narration" if _PERSON.search(line) else None


def harvest_register(text: str, url: str, *, context: str = "") -> dict[str, Any]:
    """Generalized register harvest: route each fragment to its register and bank it (with a
    `register` field), reusing the EXACT comfort safety pipeline. Returns per-register counts."""
    if not text or len(text) < 40:
        return {"harvested": 0, "rejected": 0, "by_register": {}}
    try:
        from packages.graph_scale.injection_guard import has_injection
    except Exception:
        has_injection = lambda _t: False    # noqa: E731
    dom = _domain(url)
    kept: list[dict[str, Any]] = []
    by_reg: dict[str, int] = {}
    rejected = 0
    for raw in re.split(_SENTENCE_SPLIT, text)[:400]:
        line = raw.strip()
        if not (12 <= len(line) <= 120):
            continue
        cm = _CHROME_REJECT.search(line)                 # truncate glued page chrome (same as comfort)
        if cm:
            line = line[:cm.start()].strip(" .·-|")
            if not (12 <= len(line) <= 120):
                continue
        reg = _route_register(line)
        if reg is None:
            continue
        # global safety floor (identical to comfort); question-shape allowed ONLY for `question`;
        # directive/stance registers get the extra risky-topic floor.
        if (_SAFETY_REJECT.search(line) or _AD_REJECT.search(line) or has_injection(line)
                or (reg != "question" and _QUESTION_SHAPE.search(line))
                or (reg in ("advice", "opinion") and _RISKY_TOPIC.search(line))):
            rejected += 1
            continue
        frag = _scrub(line)
        # Same correction as in `harvest_comfort`, in the function the roaming loop actually calls.
        # Register is speech between people; the mark of that is PERSON, not a script.
        if not (12 <= len(frag) <= 60) or not _PERSON.search(frag):
            continue
        norm = re.sub(r"[\s.,!?~…'\"·]+", "", frag)
        h = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
        kept.append({"h": h, "pattern": frag, "band": _band(frag), "register": reg,
                     "domain": dom, "ts": int(time.time()),
                     **({"context": context[:60]} if context else {})})
        by_reg[reg] = by_reg.get(reg, 0) + 1
    if kept:
        _append(kept)
    return {"harvested": len(kept), "rejected": rejected, "by_register": by_reg}


def register_coverage() -> dict[str, Any]:
    """The L1 metric — usable (consensus>=2) pattern count PER register, plus the raw staging count.
    This is the coverage vector the active-learner drives toward uniform. Rows with no `register`
    field are legacy comfort harvests."""
    staged: dict[str, int] = {r: 0 for r in _REGISTERS}
    doms: dict[tuple[str, str], set[str]] = {}
    try:
        for ln in _BANK.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except Exception:
                continue
            reg = r.get("register", "comfort")
            staged[reg] = staged.get(reg, 0) + 1
            doms.setdefault((reg, r["h"]), set()).add(r.get("domain", "unknown"))
    except FileNotFoundError:
        pass
    usable: dict[str, int] = {r: 0 for r in _REGISTERS}
    for (reg, _h), ds in doms.items():
        if len(ds) >= MIN_DOMAINS:
            usable[reg] = usable.get(reg, 0) + 1
    return {"usable": usable, "staged": staged,
            "total_usable": sum(usable.values()), "min_domains": MIN_DOMAINS}


def thinnest_registers(k: int = 3) -> list[str]:
    """Active-learning target: the k registers with the FEWEST usable patterns — where the roaming
    loop should spend its next harvest budget (drives the coverage vector toward uniform)."""
    usable = register_coverage()["usable"]
    return sorted(usable, key=lambda r: usable[r])[:k]
