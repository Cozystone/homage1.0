# -*- coding: utf-8 -*-
"""ATANOR <-> openclaw (GPT-5.4) free-topic dialogue — a REAL conversation, watchable live.

v2 REBUILD (owner 2026-07-24: "v1 was too sterile / rule-based; let openclaw's data flow into
ATANOR with full autonomy — ATANOR must HEAR openclaw and RESPOND naturally").

What was wrong with v1
----------------------
v1's ``openclaw_to_turn`` stripped every openclaw reply to ONE bare term and forced act='ask'
(payload=''), so openclaw's real content never reached ATANOR. Statements about an unheld term hit
step()'s thin ``connect`` branch, which emits the DRILL template -> every ATANOR turn read
"[ack]. You said X; what is X?". The rich discourse repertoire (debate/connect/share) lives in
step()'s "the peer TAUGHT me" branch, which v1 never reached.

What v2 does
------------
1. HEAR: openclaw's FULL turn is passed into ATANOR's incoming Turn.
     - openclaw ASKS a question  -> act='ask'        -> ATANOR ANSWERS from its own graph/web
                                                         (answer_known if it holds it, else answer_web).
     - openclaw STATES / shares   -> act='answer_web' -> step()'s TEACH branch, where ATANOR:
         * DEBATES  (holds differing bones -> voices BOTH, challenges: "which is closer to the world?")
         * CONNECTS (openclaw's point names something ATANOR knows -> builds the link)
         * DRILLS   (asks about a raised concept -- ONLY when it genuinely lacks it)
         * SHARES   (voices what it has lately learned) / WANDERS to its own curiosity.
   The focus term is chosen so ATANOR usually has grounded substance to contribute (a concept it
   HOLDS > a shared curiosity > the most contentful term), so it responds instead of term-hopping.
2. FUSE: every content word of openclaw's turn is touch()ed into ATANOR's rolling discourse context,
   so later web disambiguation resolves terms the way THIS conversation means them (hear->fuse).
3. DOUBT/PERSIST (autonomy WITH judgment): openclaw's prose is HEARD and RESPONDED to freely, but it
   is NEVER blind-learn()'d. When step() would enshrine a concept openclaw raised, the write is
   intercepted and routed through the M2 ContaminationFirewall (packages.truth_maintenance):
   stage as tier=neural, VERIFY the concept against ATANOR's OWN graph+web, and persist ONLY on
   >=k independent groundings (default k=2). Even then ATANOR stores ITS OWN grounded gloss, never
   openclaw's words -- so openclaw's errors can never be enshrined (hallucination-zero preserved).
   Uncorroborated claims stay conversational-context-only: heard, answered, not made durable.

Honesty (BINDING): ATANOR's turns are REAL engine output grounded in its graph/web. Nothing here
ghost-writes ATANOR prose or passes openclaw's wording off as ATANOR's (debate QUOTES openclaw,
attributed: "Yet you say: ..."). If ATANOR is terse on a turn, that is logged verbatim.

Live wire (viewer contract unchanged): every turn is appended to
data/advisor_loop/openclaw_dialogue_live.jsonl as {"i","speaker","ts","topic","text",(+"act",
"source", + persist_* audit fields the viewer ignores)}, flushed+fsync'd per line.

  python -X utf8 scripts/openclaw_free_dialogue.py --turns 4 --topic "consciousness" --fresh
  python -X utf8 scripts/openclaw_free_dialogue.py --turns 12          # ATANOR picks the topic
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import packages.brain_link.conversation as _conv
from packages.brain_link.conversation import (
    Agent, Turn, step, _key_concepts, _voice, wiki_lookup,
)
from packages.brain_link.web_knowledge import learn_from_web, _is_nonanswer
from packages.advisor_loop.advisor_session import ask_cli
from packages.truth_maintenance import ContaminationFirewall, VerificationOutcome
from scripts.edge_converse_step import _seed_curiosity

LIVE = REPO / "data" / "advisor_loop" / "openclaw_dialogue_live.jsonl"
BONES = REPO / "data" / "graph_scale" / "bones_to_text.jsonl"   # READ-ONLY (agent knowledge slice)
DEFAULT_SEARX = "http://localhost:8888"                          # PC-local SearXNG (diverse engines)
TURNS_HARD_MAX = 40                                              # paid GPT-5.4 — never exceed


# --------------------------------------------------------------------- surface constructicon ------
# The engine builds each utterance by selecting DETERMINISTICALLY (by turn index) from a finite pool
# of surface variants — the fluency doctrine's lever (유창 = 담화 패턴 다양성): variety comes from a
# richer constructicon, not from writing lines per-turn. v1 shipped only 4 acks that cycled
# ("That clarifies it / Understood / Ah, that helps"), which the owner flagged as canned. We ENRICH
# the module-global pools (a runtime constructicon swap, NOT a file edit and NOT ghost-writing: the
# engine still picks which one, for which concept, from ITS state). Generic acknowledgments only —
# never a claim about the world.
# Function / discourse words that slip through conversation._STOP and become junk drill/curiosity
# targets ("what is when?", "what is another?" — seen live). They name nothing in the world, which is
# the module's own stated reason for the stoplist. Extending it is a LAD SURFACE-LAYER list (조사·어미·
# 구문), which the architecture explicitly permits as code — not world knowledge. Read at call time by
# _key_concepts, so this improves extraction everywhere, including step()'s internal follow-up picks.
_EXTRA_STOP = {
    "when", "where", "while", "like", "into", "onto", "than", "then", "them", "also", "some",
    "more", "most", "such", "very", "just", "only", "being", "been", "were", "your", "yours",
    "ours", "here", "there", "about", "would", "could", "should", "might", "must", "shall",
    "will", "does", "done", "doing", "have", "having", "each", "every", "both", "either",
    "neither", "because", "though", "although", "however", "therefore", "thus", "hence", "upon",
    "over", "under", "between", "among", "across", "through", "within", "without", "toward",
    "towards", "around", "along", "rather", "quite", "almost", "perhaps", "maybe", "indeed",
    "really", "truly", "often", "always", "never", "again", "still", "even", "much", "many",
    "another", "other", "same", "else", "whether", "whose", "whom", "cannot", "itself", "himself",
    "herself", "themselves", "myself", "yourself", "essentially", "basically", "simply", "merely",
}


def enrich_constructicon() -> None:
    _conv._STOP = set(_conv._STOP) | _EXTRA_STOP
    _conv._ACK = (
        "Right.", "I follow.", "That tracks.", "Fair point.", "Noted.",
        "Mm, yes.", "Okay.", "I hear you.", "That lands.", "Makes sense.",
    )
    _conv._DRILL = (
        "What's {c}, though?", "Say more — what is {c}?",
        "I don't hold {c} yet; what is it?", "Where does {c} come in?",
        "And {c} — what do you mean by it?", "Help me with {c}: what is it?",
    )
    _conv._ASK_NEXT = (
        "Then what about {c}?", "I keep circling {c} — what is it?",
        "This makes me wonder about {c}.", "What of {c}?",
        "That pulls me toward {c}; what is it?", "Which brings up {c} — what is it?",
    )
    _conv._ASK_OPEN = (
        "Something's been on my mind — what is {c}?",
        "I've been sitting with a question: what is {c}?",
        "Here's what I don't yet grasp: {c}. What is it?",
        "A thread I keep tugging — what is {c}?",
    )


# -------------------------------------------------------------- ATANOR with a firewalled memory ----
class FirewalledAgent(Agent):
    """An ATANOR self whose ``learn`` is gated for peer-derived content.

    When step() enshrines ATANOR's OWN web/graph finding (the answer-a-question path), it passes
    through untouched. When step() would enshrine the concept a PEER (openclaw) just raised — the
    ``learn(concept, gloss)`` at the top of the teach branch, where ``gloss`` is exactly openclaw's
    claim we shuttled in as the incoming payload — the write is diverted to the M2 firewall. The
    concept is verified against ATANOR's own graph+web; it becomes durable ONLY on >=k independent
    groundings, and what is stored is ATANOR's OWN gloss, never openclaw's words.
    """

    # set per-turn by the runner before step(); "" means the incoming turn is not a peer claim
    _peer_payload: str = ""
    _peer_source_id: str = ""
    _last_persist: dict | None = None
    _fw: ContaminationFirewall | None = None
    _persist_k: int = 2

    def learn(self, term, value) -> None:
        peer = getattr(self, "_peer_payload", "") or ""
        if peer and isinstance(value, str) and value == peer:
            decision = self._admit_peer_claim(term, value)
            self._last_persist = decision
            if decision["persisted"] and decision["own_gloss"]:
                Agent.learn(self, term, decision["own_gloss"])   # ATANOR's OWN corroborated gloss
            return                                                # else: context-only (not enshrined)
        Agent.learn(self, term, value)                            # ATANOR's own finding -> normal

    def _admit_peer_claim(self, term: str, claim: str) -> dict:
        """Stage -> verify(against my own graph+web) -> promote (>=k consensus). Never persists
        openclaw's text; on success persists my own gloss. Returns an audit dict for the live wire."""
        fw = self._fw
        try:
            rec = fw.stage_candidate(
                subject=term, predicate="peer_asserts", object=str(claim)[:160],
                provenance="openclaw:gpt-5.4", source_id=self._peer_source_id or "openclaw:unknown",
            )
            outcome = fw.verify(rec)                          # PeerGroundingBattery does the grounding
            domains = int(outcome.detail.get("domains", 0))
            own_gloss = outcome.detail.get("own_gloss")
            res = fw.promote(rec, consensus_domains=domains, require_verification=True)
            persisted = bool(res.get("promoted")) and bool(own_gloss)
            reason = res.get("reason", "")
            sources = outcome.detail.get("sources", [])
        except Exception as e:                                # a web hiccup must not derail the talk
            domains, own_gloss, persisted = 0, None, False
            reason, sources = f"error:{type(e).__name__}", []
        return {"persisted": persisted, "domains": domains, "own_gloss": own_gloss,
                "reason": reason, "sources": sources, "concept": term, "claim": str(claim)[:160]}


class PeerGroundingBattery:
    """Stage-2 verification battery: does ATANOR independently GROUND this concept from its OWN
    sources? Counts distinct groundings — its graph slice, its source-weighted diverse web, and an
    encyclopedic corroboration on a DISTINCT domain. verified = grounds at all (>=1); the firewall's
    consensus gate needs >=k of these to promote. own_gloss is ATANOR's own text, never openclaw's."""

    def __init__(self, agent: FirewalledAgent) -> None:
        self.agent = agent

    def verify(self, fact: dict, signals=None) -> VerificationOutcome:
        term = fact.get("subject", "")
        a = self.agent
        sources: list[tuple[str, str]] = []
        own_gloss: str | None = None

        # 1) ATANOR's own graph slice (bones -> frame realizer, or a prior self-grounded gloss)
        held = a.knowledge.get(term.lower())
        if held is not None:
            try:
                g = _voice(held, term) if isinstance(held, list) else str(held)
            except Exception:
                g = ""
            if g and not _is_nonanswer(g):
                sources.append(("graph:atanor", g))
                own_gloss = own_gloss or g

        # 2) ATANOR's source-weighted DIVERSE web (disambiguated by the discourse context)
        if a.web:
            try:
                got = learn_from_web(term, a.searx, a.used_domains, context=a.context_for(term))
            except Exception:
                got = None
            if got:
                gloss_a, _url_a, dom_a = got
                sources.append((dom_a, gloss_a))
                own_gloss = own_gloss or gloss_a

        # 3) an INDEPENDENT encyclopedic corroboration — only if it adds a NEW domain
        seen = {d for d, _ in sources}
        if a.web and "en.wikipedia.org" not in seen:
            try:
                fb = wiki_lookup(term)
            except Exception:
                fb = None
            if fb and not _is_nonanswer(fb[0]):
                sources.append(("en.wikipedia.org", fb[0]))
                own_gloss = own_gloss or fb[0]

        domains = len({d for d, _ in sources})
        return VerificationOutcome(
            verified=domains >= 1, method="graph+web grounding",
            detail={"domains": domains, "own_gloss": own_gloss,
                    "sources": [{"domain": d, "gloss": g[:120]} for d, g in sources]},
        )


def build_atanor(ai_id: str, take: int, searx: str, web: bool, k: int) -> FirewalledAgent:
    """One ATANOR self over a DIVERSE slice of the mined graph (sampled across the whole file, not
    the alphabetical head, so it holds a broad vocabulary and can actually connect/compare). Wires
    its firewalled memory. READ-ONLY on bones_to_text.jsonl."""
    knowledge: dict = {}
    if BONES.exists():
        size = BONES.stat().st_size
        est_lines = max(take, size // 150)          # ~150 B/line; used only to spread the sample
        stride = max(1, est_lines // max(1, take))
        with BONES.open(encoding="utf-8") as f:
            for idx, line in enumerate(f):
                if idx % stride != 0:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                s = r["subject"].lower()
                if s in knowledge:
                    continue
                knowledge[s] = list(r.get("bones", [])[:6])
                if len(knowledge) >= take:
                    break
    a = FirewalledAgent(ai_id=ai_id, knowledge=knowledge,
                        curiosity=_seed_curiosity(knowledge), web=web)
    a.searx = searx
    a._peer_payload = ""
    a._peer_source_id = ""
    a._last_persist = None
    a._persist_k = k
    a._fw = ContaminationFirewall(battery=PeerGroundingBattery(a), k_consensus=k)
    return a


# ---------------------------------------------- openclaw reply -> a Turn that CARRIES its content ---
def _first_sentences(text: str, n: int = 2, cap: int = 260) -> str:
    """openclaw's core claim: drop leading throat-clearing ('Fair.', 'Right.', 'Sure —') so the
    quoted claim ATANOR responds to is the substance, then keep whole sentences up to `cap` — never
    cut mid-sentence (a clean boundary reads as a real quote, not a broken string)."""
    parts = [p for p in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if p]
    while len(parts) > 1 and len(parts[0].split()) < 3:      # skip a short lead-in ack
        parts = parts[1:]
    out = ""
    for p in parts[:n]:
        cand = f"{out} {p}".strip() if out else p
        if len(cand) > cap:
            return out or p[:cap].rstrip()                  # first sentence alone too long -> hard cap
        out = cand
    return out


def _ends_as_question(reply: str) -> bool:
    """openclaw is asking ATANOR something iff its LAST sentence is interrogative — a '?' buried
    mid-reply (a rhetorical aside before a point) should not turn ATANOR into an answering machine."""
    parts = [p for p in re.split(r"(?<=[.!?])\s+", (reply or "").strip()) if p]
    if not parts:
        return False
    return parts[-1].rstrip().endswith("?")


def openclaw_to_turn(reply: str, atanor: FirewalledAgent, last_concept: str) -> Turn | None:
    """Shape openclaw's FULL turn into an incoming Turn that carries its real content into step().

    FUSE: every content word enters ATANOR's discourse context (so later disambiguation uses this
    conversation's meaning). Then pick a FOCUS ATANOR can most likely say something grounded about,
    and choose the act by what openclaw DID:
      - a question           -> 'ask'         (ATANOR answers from its OWN graph/web; payload='')
      - a statement / share  -> 'answer_web'  (TEACH branch: debate / connect / drill / share),
                                 payload = openclaw's actual claim (enshrine is firewall-gated).
    Returns None only when openclaw produced nothing grippable — then ATANOR speaks from its own
    state (step(atanor, None))."""
    concepts = _key_concepts(reply, exclude=last_concept or "")
    for c in concepts:                                    # FUSE: the whole turn informs the context
        atanor.touch(c)

    # FOCUS: prefer a term ATANOR HOLDS (-> it can voice/compare/connect a grounded view), then a
    # shared curiosity (genuine mutual interest), then the most contentful term, then the thread.
    focus = ""
    for c in concepts:
        if atanor.knows(c) is not None:
            focus = c
            break
    if not focus:
        curious = {x.lower() for x in atanor.curiosity}
        for c in concepts:
            if c.lower() in curious:
                focus = c
                break
    if not focus and concepts:
        focus = max(concepts, key=len)
    if not focus and last_concept:
        focus = last_concept
    if not focus:
        return None

    if _ends_as_question(reply):
        # openclaw asked ATANOR something -> ATANOR ANSWERS (no claim to enshrine from a question)
        return Turn(speaker="openclaw", text=reply, act="ask", concept=focus,
                    references_prev=True, payload="")
    # openclaw made a point / shared a thought -> ATANOR's rich teach-branch responds to the CONTENT
    claim = _first_sentences(reply)
    return Turn(speaker="openclaw", text=reply, act="answer_web", concept=focus,
                references_prev=True, payload=claim, source="openclaw:gpt-5.4")


# ----------------------------------------------------- prompt to openclaw (compact, bounded) --------
def build_openclaw_prompt(topic: str, recent: list[tuple[str, str]], atanor_text: str) -> str:
    """A compact peer-dialogue prompt. openclaw runs a FRESH session per call, so a little recent
    transcript keeps it coherent. It is asked to ENGAGE with ATANOR's actual point and bring
    something concrete of its own — that gives ATANOR real content to respond to."""
    lines = []
    for spk, txt in recent[-4:]:
        who = "ATANOR" if spk == "ATANOR" else "You (GPT-5.4)"
        lines.append(f"{who}: {txt[:240]}")
    convo = "\n".join(lines) if lines else "(this is the opening turn)"
    return (
        "You are GPT-5.4 in an open, free-flowing conversation with ATANOR, a graph-native AI that "
        "speaks only from grounded knowledge and is honest when it does not know. This is a peer "
        "dialogue between two minds — not a task or an interview. Engage with what ATANOR actually "
        "said: agree and extend it, add a concrete thought of your own, or push back — and you may "
        "ask ATANOR something in return. Reply naturally and briefly, 1 to 3 sentences, plain prose "
        "(no lists, no headings).\n"
        f"Topic in the air: {topic}.\n\n"
        f"Recent exchange:\n{convo}\n\n"
        f"ATANOR just said: \"{atanor_text}\"\n\nYour reply:"
    )


# ------------------------------------------------------------------------------- live wire + I/O ----
def append_live(row: dict) -> None:
    LIVE.parent.mkdir(parents=True, exist_ok=True)
    with LIVE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())      # the viewer polls this file — make each turn visible at once


def _emit(i: int, speaker: str, topic: str, text: str, act: str = "", source: str = "",
          extra: dict | None = None) -> None:
    row = {"i": i, "speaker": speaker, "ts": time.time(), "topic": topic, "text": text}
    if act:
        row["act"] = act
    if source:
        row["source"] = source
    if extra:                     # persist_* audit fields — unknown to the viewer, so contract holds
        row.update(extra)
    append_live(row)
    tag = f"  [{act}]" if act else ""
    src = f"   (web: {source})" if source else ""
    print(f"[{i:>2}] {speaker:>8} | {text}{tag}{src}", flush=True)


def _persist_extra(decision: dict | None) -> dict:
    if not decision:
        return {}
    return {
        "persist": "promoted" if decision["persisted"] else "context_only",
        "persist_concept": decision.get("concept", ""),
        "persist_domains": decision.get("domains", 0),
        "persist_reason": decision.get("reason", ""),
    }


# --------------------------------------------------------------------------------------- main -------
def main() -> int:
    ap = argparse.ArgumentParser(description="ATANOR <-> openclaw (GPT-5.4) free-topic dialogue (v2)")
    ap.add_argument("--turns", type=int, default=12,
                    help=f"total utterances (clamped 1..{TURNS_HARD_MAX}; each openclaw turn is PAID)")
    ap.add_argument("--topic", default="", help="seed topic; omitted => ATANOR picks from its curiosity")
    ap.add_argument("--knowledge", type=int, default=6000, help="ATANOR graph-slice size (diverse subjects)")
    ap.add_argument("--searx", default=DEFAULT_SEARX, help="SearXNG base for ATANOR web grounding")
    ap.add_argument("--no-web", action="store_true", help="disable ATANOR web grounding (graph-only)")
    ap.add_argument("--persist-k", type=int, default=2,
                    help="independent groundings required to enshrine a peer claim (firewall consensus)")
    ap.add_argument("--pace", type=float, default=0.0, help="seconds to pause between turns")
    ap.add_argument("--fresh", action="store_true", help="truncate the live JSONL before starting")
    args = ap.parse_args()

    turns = max(1, min(TURNS_HARD_MAX, args.turns))
    if args.fresh:
        LIVE.parent.mkdir(parents=True, exist_ok=True)
        LIVE.write_text("", encoding="utf-8")

    enrich_constructicon()
    atanor = build_atanor("atanor", take=args.knowledge, searx=args.searx,
                          web=not args.no_web, k=args.persist_k)
    topic = args.topic.strip()
    if topic:
        if topic.lower() not in {c.lower() for c in atanor.curiosity}:
            atanor.curiosity.insert(0, topic)         # where ATANOR's curiosity starts — not injected content
    else:
        topic = atanor.curiosity[0] if atanor.curiosity else "open conversation"

    print(f"=== ATANOR <-> openclaw (gpt-5.4) v2 | topic: {topic!r} | turns: {turns} | "
          f"web: {not args.no_web} | knows: {len(atanor.knowledge)} | persist-k: {args.persist_k} ===",
          flush=True)
    print(f"    live -> {LIVE}", flush=True)

    recent: list[tuple[str, str]] = []
    atanor_incoming: Turn | None = None
    atanor_last_text = ""
    last_concept = topic

    speaker = "ATANOR"
    for i in range(1, turns + 1):
        if speaker == "ATANOR":
            # tell the firewalled memory whether the incoming turn is a PEER CLAIM (so a durable
            # write gets gated) or ATANOR answering its own way (payload='' -> not gated).
            if atanor_incoming is not None and atanor_incoming.act in (
                    "answer_web", "answer_known", "share") and atanor_incoming.payload:
                atanor._peer_payload = atanor_incoming.payload
                atanor._peer_source_id = f"openclaw:turn{max(0, i - 1)}"
            else:
                atanor._peer_payload = ""
            atanor._last_persist = None

            t = step(atanor, atanor_incoming)
            extra = _persist_extra(atanor._last_persist)
            if atanor._last_persist:
                d = atanor._last_persist
                verdict = "PROMOTED (enshrined my own gloss)" if d["persisted"] else "context-only"
                print(f"    [firewall] concept={d['concept']!r} groundings={d['domains']} "
                      f"-> {verdict} ({d['reason']})", flush=True)
            src = getattr(t, "source", "") or ""
            _emit(i, "ATANOR", topic, t.text, act=t.act, source=src, extra=extra)
            recent.append(("ATANOR", t.text))
            atanor_last_text = t.text
            if getattr(t, "concept", ""):
                last_concept = t.concept
            atanor_incoming = None
        else:
            prompt = build_openclaw_prompt(topic, recent, atanor_last_text)
            try:
                ex = ask_cli("openclaw", prompt)          # PAID; journals to advisor ledger
                reply = ex.reply or "(openclaw returned no text)"
                if ex.injection_findings:
                    print(f"    [guard] injection_findings={ex.injection_findings} "
                          "(logged as data; NOT ingested)", flush=True)
            except Exception as e:
                reply = f"(openclaw error: {type(e).__name__}: {e})"
                print(f"    [openclaw error] {e}", flush=True)
            _emit(i, "openclaw", topic, reply, act="reply")
            recent.append(("openclaw", reply))
            atanor_incoming = openclaw_to_turn(reply, atanor, last_concept)
            if atanor_incoming is not None and atanor_incoming.concept:
                last_concept = atanor_incoming.concept

        speaker = "openclaw" if speaker == "ATANOR" else "ATANOR"
        if args.pace > 0 and i < turns:
            time.sleep(args.pace)

    print(f"=== done: {turns} turns -> {LIVE} ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
