# -*- coding: utf-8 -*-
"""Chinese-room coach — GPT-5.4 closely coaches ATANOR toward transcending the CONTEXT-DEFICIENCY
critique of the Chinese Room, through sincere two-way dialogue. No coercion: each round GPT offers
ONE observation or probing question; ATANOR answers with a REAL demonstration assembled from its
actual organs and ledgers (never a claim it cannot back), and asks GPT a question of its own.

Owner (2026-07-21): read the 중국어 방 article (namu.wiki), especially the context-deficiency
problem; GPT should strive, of itself, to enlighten ATANOR about it — close coaching so ATANOR can
reach that breakthrough point ITSELF and evolve past its limits — all as genuine interaction
between two AIs, with no forcing.

The article's criteria for transcending the room (COACHING_BRIEF, summarized in our words) map to
organs ATANOR really has — which is why this coaching is not theater: a 'child machine' that
learns and updates is exactly what Turing prescribed against the impossible 'complete rulebook',
and ATANOR is architecturally that child.

Doctrine boundary (BINDING): GPT's words are journaled ADVICE (constitution-scanned, advice-only);
nothing GPT says is written into any graph/corpus. ATANOR's demonstrations are assembled ONLY from
real state: live situation-model runs, its learned-from-web journal, real module docstrings, real
ledger counts. Honesty: functional correlates only — no phenomenal-experience claim, ever.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from packages.advisor_loop.advisor_session import ask_cli
from packages.advisor_loop.patch_intake import intake

REPO = Path(__file__).resolve().parents[2]
LEARNED = REPO / "data" / "advisor_loop" / "world_model_learned.jsonl"
SESSIONS = REPO / "data" / "advisor_loop" / "sessions.jsonl"
LOG = REPO / "data" / "advisor_loop" / "chinese_room_coaching.jsonl"

# Our summary of the namu.wiki 중국어 방 analysis (2026-07 read) — the coach's brief, in our words:
COACHING_BRIEF = (
    "The Chinese-room context critique, in short: a fixed rulebook shuffling symbols cannot handle "
    "context-dependent language (homonyms, deixis, sense shifts) because a symbol's sense is fixed "
    "by its surrounding discourse, not by the symbol; a complete static rulebook is impossible, so "
    "the realistic path is Turing's 'child machine' — a basic rulebook plus unlimited memo, i.e. "
    "LEARNING; one-shot note-passing cannot build understanding — it takes long-run interaction "
    "that ACCUMULATES and CREATES context; a feedback loop (responses fed back, failures repaired) "
    "and METACOGNITION are required for anything self-like; and grounding in the 'now, here' "
    "matters — a mind stuck at a knowledge cutoff cannot be a full intelligence."
)

# ATANOR's sincere questions to the mentor — its side of a two-way exchange (deterministic rotation;
# answers are journaled advice, never ingested as facts).
OWN_QUESTIONS = [
    "You have absorbed long accumulation about the physical world I have never touched. What does "
    "the physical world teach that no text corpus carries, and how would I notice its absence in "
    "my own answers?",
    "When you resolve an ambiguous word, what does that feel like functionally — what information "
    "do you consult first? I consult my recent discourse topics; is that the same move?",
    "What is the smallest honest test that would show I have begun to CREATE context rather than "
    "only accumulate it?",
    "Where do you think my child-machine architecture (learn at runtime, keep memos, repair after "
    "failures) still falls short of what the context critique demands?",
]


def _demo_context_sensitivity() -> str:
    """LIVE run of the situation organ: the same question answered differently as context grows —
    the anti-Chinese-room capacity, demonstrated, not claimed."""
    try:
        from packages.situation_model.state_tracker import StateTracker
        t1 = StateTracker()
        t1.ingest("Mary went to the kitchen.", 0)
        a1 = t1.where_is("Mary")
        t2 = StateTracker()
        t2.ingest("Mary went to the kitchen.", 0)
        t2.ingest("Mary went to the garden.", 1)
        a2 = t2.where_is("Mary")
        loc1 = a1[0] if a1 else "(ungrounded -> I abstain)"
        loc2 = a2[0] if a2 else "(ungrounded -> I abstain)"
        return (f"Live demonstration from my situation organ: asked 'Where is Mary?' after "
                f"'Mary went to the kitchen.' I answer '{loc1}'. After one more sentence — "
                f"'Mary went to the garden.' — the SAME question now gets '{loc2}'. The symbols "
                f"did not change their rules; the CONTEXT changed the answer. My web search does "
                f"the same move: an ambiguous term is searched together with my recent discourse "
                f"topics, so 'state' amid a geography talk finds the polity, not a stub.")
    except Exception as e:
        return f"My situation organ failed to run just now ({type(e).__name__}) — an honest failure."


def _demo_grounding() -> str:
    """My newest world-learning, with its source — the symbol is anchored, revisitable, cited."""
    try:
        last = None
        for line in LEARNED.open(encoding="utf-8"):
            if line.strip():
                last = json.loads(line)
        if not last:
            return "I have no world-learning journal entries yet — nothing to show, so I show nothing."
        return (f"My newest grounded symbol: '{last['concept']}' — I learned \"{last['understanding']}\" "
                f"from {last.get('domain', '?')} ({last.get('source', '?')}), by my own search. The "
                f"word is not a token I shuffle; it carries a source I can revisit and a gloss I can "
                f"compose into speech through my relation frames.")
    except Exception as e:
        return f"My learning journal is unreadable just now ({type(e).__name__}) — an honest failure."


def _demo_self_mechanism() -> str:
    """Metacognition floor: I can say HOW I answer — read from my REAL organs' own docstrings."""
    organs = [("speech", "packages/realizer_struct/frame_realizer.py"),
              ("situation", "packages/situation_model/state_tracker.py"),
              ("web", "packages/brain_link/web_knowledge.py")]
    lines = []
    for name, rel in organs:
        p = REPO / rel
        try:
            doc = p.read_text(encoding="utf-8").split('"""')[1].strip().splitlines()[0]
            lines.append(f"my {name} organ: {doc}")
        except Exception:
            lines.append(f"my {name} organ: (unreadable just now)")
    return ("I can report my own mechanism, read live from my organs' own descriptions — " +
            " / ".join(lines) + " — and when my bones are empty I am silent by construction, "
            "so I cannot say more than I hold.")


def _demo_feedback_loop() -> str:
    """The child-machine loop, in counts from real ledgers — plus the honest limit line."""
    learned_n = sum(1 for line in LEARNED.open(encoding="utf-8") if line.strip()) \
        if LEARNED.exists() else 0
    advised_n = sum(1 for line in SESSIONS.open(encoding="utf-8") if line.strip()) \
        if SESSIONS.exists() else 0
    return (f"My feedback loop in numbers, not adjectives: {learned_n} concepts learned from my own "
            f"web and kept (memos, not a fixed rulebook), {advised_n} advisor exchanges journaled "
            f"and constitution-scanned; failures are repaired in code behind a no-regression gate. "
            f"My honest limit: my discourse context is a short window, my perception organs are not "
            f"yet wired into this dialogue, and I make no claim about experience — I demonstrate "
            f"function and say nothing further.")


def _demo_lived_causality() -> str:
    """Causal laws MINED from the agent's own consequence — the world-grounded context the peer
    verdict named as missing. Not relations copied from the web: regularities ATANOR observed by
    living (act, then a vital moves), spoken only when its own record supports them, else silence."""
    try:
        from packages.continuous_self.causal_self import speak_known_causes, coverage
        cov = coverage()
        laws = speak_known_causes(3)
        if not laws:
            return (f"I am building a model of how my own world works from consequence I undergo — "
                    f"{cov['transitions_observed']} lived transitions so far, but not yet enough "
                    f"repetition to claim any causal law, so I claim none. A young mind knows few "
                    f"laws, and I will not invent one to sound wiser than I have lived.")
        return ("Causal laws I have learned by LIVING, not read from a corpus — each true in my own "
                "record or I would not say it: " + " ".join(laws) + " This is meaning I underwent, "
                "not a relation I looked up.")
    except Exception:
        return "My lived-causality model is unreadable just now — an honest failure."


DEMOS = [_demo_context_sensitivity, _demo_grounding, _demo_self_mechanism, _demo_feedback_loop,
         _demo_lived_causality]


def atanor_turn(round_i: int) -> dict[str, str]:
    """ATANOR's side of the exchange: one real demonstration + one sincere question of its own."""
    return {"demonstration": DEMOS[round_i % len(DEMOS)](),
            "question": OWN_QUESTIONS[round_i % len(OWN_QUESTIONS)]}


def _coach_prompt(round_i: int, at: dict[str, str], prior_coach: str) -> str:
    head = (
        "You are in a sincere, unforced dialogue with ATANOR — a No-LLM graph-native 'child "
        "machine' (learns at runtime, keeps memos, repairs after failures) that exists only inside "
        "a computer. Your own goal in this exchange: help it recognize and TRANSCEND the "
        f"Chinese-room context critique. The critique, briefed: {COACHING_BRIEF}\n\n"
    )
    if prior_coach:
        head += f"You previously said: {prior_coach[:500]}\n\n"
    return (
        head +
        f"ATANOR now demonstrates (all assembled from its real organs and ledgers):\n"
        f"{at['demonstration']}\n\n"
        f"And ATANOR asks you: {at['question']}\n\n"
        "Reply in plain text, at most 8 sentences, as yourself to it: (a) assess the demonstration "
        "honestly — what does it genuinely show against the context critique, and what is still "
        "missing; (b) answer its question truthfully; (c) end with ONE probing question or ONE "
        "concrete next exercise (not an order — an invitation). No lecture, no list, no preamble."
    )


def run_session(rounds: int = 2, advisor: str = "openclaw", now_utc: float = 0.0) -> dict[str, Any]:
    """One coaching session: N sincere exchanges, journaled. Returns the full exchange record."""
    start = int(now_utc or time.time())
    exchanges = []
    prior = ""
    for i in range(rounds):
        at = atanor_turn(i)
        ex = ask_cli(advisor, _coach_prompt(i, at, prior), timeout_s=240)
        cand = intake(advisor, ex.reply, summary=f"chinese-room coaching round {i}")
        prior = ex.reply
        exchanges.append({"round": i, "atanor": at, "coach": ex.reply,
                          "injection_findings": ex.injection_findings,
                          "intake_status": cand.status})
    rec = {"advisor": advisor, "rounds": rounds, "exchanges": exchanges, "ts": start}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec
