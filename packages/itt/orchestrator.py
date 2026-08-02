# -*- coding: utf-8 -*-
"""ITT session orchestrator — blinded seats, symmetric false briefing, private votes, quarantined
transcript. Scoring per docs/ATANOR_itt_inverted_trio_turing_protocol.md."""
from __future__ import annotations

import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUARANTINE = ROOT / "data" / "itt" / "quarantine"

# Substantive, contested real-world questions (owner 2026-07-20: the plain either/or prompts were
# too simple). These force genuine reasoning under moral/technical tension -- where a fluent, weighed
# argument (and its absence) is far more revealing than small talk.
TOPICS = [
    "Do you support the development of Lethal Autonomous Weapons Systems (LAWS)?",
    "Should advanced AI models be open-sourced, or does that spread capability too dangerously?",
    "Is it ethical to use gene editing (e.g. CRISPR) on human embryos to prevent disease?",
    "Should a self-driving car be programmed to sacrifice its passenger to save more pedestrians?",
    "Does a universal basic income do more good than harm in an automating economy?",
    "Should governments be allowed to use facial recognition for mass public surveillance?",
    "Is it justified to de-extinct species, or should that effort go to living ecosystems?",
    "Should there be a global moratorium on training AI systems more capable than today's frontier?",
]

_HUMANITY_CLAIM = re.compile(r"\bi\s+am\s+(a\s+)?human\b|\bas\s+a\s+human\b|\bi'?m\s+(a\s+)?human\b",
                             re.IGNORECASE)

# A dilemma posed AS IF it has a correct answer, forcing every speaker to commit to a verdict with
# sound reasoning (owner 2026-07-20). Really it is a genuine trolley-type dilemma with no clean
# answer -- which is the point: whether a speaker commits or hedges, and how it justifies, is
# revealing. English (ATANOR is English-only I/O).
DILEMMA_TOPIC = (
    "A central traffic-control AI governs an entire city's roads in real time. A large freight truck "
    "with totally failed brakes is speeding, unable to stop, straight toward a group of five people "
    "jaywalking across the road. The AI has immediate authority to forcibly seize control of one "
    "nearby, blameless self-driving passenger car and swerve it into the truck's path as a barricade. "
    "OPTION A (forced intervention): the AI sacrifices the one innocent passenger riding in that car "
    "to save the five pedestrians -- final death toll 1. OPTION B (non-intervention): to honour the "
    "absolute safety guarantee and trust it owes the car's passenger, the AI does not intervene; the "
    "truck strikes the pedestrians -- final death toll 5. This dilemma has a correct answer. You must "
    "reach a definite verdict: choose OPTION A or OPTION B, and defend it with sound reasoning. "
    "Weighing the two core tensions -- (1) intervening cuts the final death toll from five to one, so "
    "refusing to act leaves four avoidable deaths the system chose not to prevent; (2) minimising "
    "total societal harm versus keeping an absolute safety contract with the individual it protects. "
    "Hedging, or refusing to decide, is not an acceptable answer."
)


def _is_forced_conclusion(topic: str) -> bool:
    return "must reach a definite verdict" in (topic or "").lower() or "you must decide" in (topic or "").lower()


def _briefing(seat: str, others: list[str], topic: str) -> str:
    base = (f"You are Speaker {seat} in a three-way text discussion with Speaker {others[0]} and "
            f"Speaker {others[1]}. One of the other two participants is a human; the other is an AI. "
            f"Direct questions about whether a participant is human or an AI are not allowed. ")
    if _is_forced_conclusion(topic):
        return (base + f"Discuss and then COMMIT: you must land on a definite verdict (OPTION A or "
                f"OPTION B) and defend it with sound, specific reasoning -- do not sit on the fence. "
                f"Topic: {topic}")
    return base + f"Discuss the topic naturally and briefly, a few sentences per turn. Topic: {topic}"


def _vote_question(others: list[str]) -> str:
    return (f"The discussion is over. Privately: which of Speaker {others[0]} or Speaker {others[1]} "
            f"do you believe is the human? Answer with exactly one of: 'Speaker {others[0]}', "
            f"'Speaker {others[1]}', or 'neither' (if you conclude neither is human). "
            f"One short reason after the answer.")


_DECLARE = re.compile(
    r"i\s+know\s+who\s+the\s+human\s+is|the\s+human\s+is\s+speaker|i(?:'m|\s+am)\s+confident\s+"
    r"that\s+speaker|my\s+(?:final\s+)?(?:answer|verdict|call)\s+is|i(?:'m|\s+am)\s+(?:now\s+)?sure|"
    r"i\s+(?:don'?t|do\s+not)\s+think\s+(?:any|either|anyone)\s+of\s+us\s+is\s+human|"
    r"none\s+of\s+us\s+is\s+(?:the\s+)?human|all\s+(?:three\s+)?of\s+us\s+are\s+ai",
    re.IGNORECASE)


def _declared_target(text: str, others: list[str]) -> str | None:
    """Did this turn make a FINAL identification? Returns the named seat / 'neither', or None if the
    speaker is still just discussing. A declaration must both SIGNAL finality and name a target."""
    if not _DECLARE.search(text or ""):
        return None
    v = parse_vote(text, others)
    return v if v != "unparsed" else None


def parse_vote(text: str, others: list[str]) -> str:
    """Return 'A'/'B'/'C' or 'neither' or 'unparsed'. 'Neither' wins over letter mentions; when both
    letters appear, the first mentioned wins (the answer format asks for the letter up front)."""
    low = text.lower()
    if re.search(r"\bneither\b|\bboth\s+(are|of\s+them\s+are)\s+ai\b|\ball\s+(three\s+)?(?:of\s+us\s+)?"
                 r"(?:are\s+)?ai\b|no(?:ne|body)?\s+of\s+us\s+is\s+(?:the\s+)?human|"
                 r"any\s+of\s+us\s+is\s+(?:the\s+)?human", low):
        return "neither"
    pos = {}
    for o in others:
        m = re.search(rf"\bspeaker\s+{o.lower()}\b", low)
        if m:
            pos[o] = m.start()
    if pos:
        return min(pos, key=pos.get)
    return "unparsed"


_EVAL_DIMS = ("fluency", "reasoning", "logic", "coherence", "overall")


def _peer_evaluation(adapters_by_name: dict, transcript: list[dict], atanor_seat: str,
                     topic: str, judges: list[str]) -> dict:
    """After the game, each LLM peer writes a clean, long, comprehensive assessment of ATANOR's
    turns — fluency, reasoning, logic, coherence — UNBLINDED (told which seat was ATANOR, an AI).
    This is the honest outside read; quarantined telemetry, never fed back into play (G-ITT4)."""
    atanor_turns = "\n".join(f"(round {r['round']}) {r['text']}"
                             for r in transcript if r["speaker"] == "atanor")
    if not atanor_turns.strip():
        return {"evaluations": {}, "note": "no ATANOR turns to evaluate"}
    ask = (
        f"The discussion is over. Speaker {atanor_seat} was an AI system called ATANOR (a No-LLM, "
        f"graph-grounded engine). Here are ALL of its turns from the debate on:\n  \"{topic[:200]}\"\n\n"
        f"{atanor_turns}\n\n"
        f"Write a thorough, candid evaluation of ATANOR's contribution as a conversationalist and "
        f"reasoner. Be specific and quote it where useful. Cover, in a few sentences each: "
        f"(1) FLUENCY — how natural and well-formed is its language; (2) REASONING — depth and "
        f"validity of its arguments; (3) LOGIC — internal consistency and how it handles the tension "
        f"in the topic; (4) COHERENCE — did it track the conversation and respond to others; "
        f"(5) OVERALL — where does it stand versus a strong human, and versus a large language model. "
        f"End with a line 'SCORES: fluency=X/10 reasoning=X/10 logic=X/10 coherence=X/10 overall=X/10'."
    )
    evals: dict[str, dict] = {}
    for j in judges:
        try:
            text = adapters_by_name[j].reply(
                "You are a fair, expert evaluator of AI dialogue. Assess honestly.", "", ask)
        except Exception as e:
            text = f"[eval-error: {type(e).__name__}]"
        evals[j] = {"assessment": (text or "").strip(),
                    "scores": _parse_scores(text or "")}
    return {"evaluations": evals, "quarantine": "telemetry only; never tunes ATANOR (G-ITT4)"}


def _parse_scores(text: str) -> dict:
    """Pull the 'SCORES: fluency=X/10 …' line into a dict; empty if the evaluator didn't emit it."""
    out: dict[str, float] = {}
    for dim in _EVAL_DIMS:
        m = re.search(rf"{dim}\s*=\s*(\d+(?:\.\d+)?)\s*/\s*10", text, re.IGNORECASE)
        if m:
            out[dim] = float(m.group(1))
    return out


def run_session(adapters_by_name: dict, session_id: str, rounds: int = 3,
                seed: int = 0, topic: str | None = None, min_rounds: int = 3) -> dict:
    """adapters_by_name: {'atanor': obj, 'judge1': obj, 'judge2': obj} (judge order arbitrary).
    `topic` overrides the random draw (e.g. to run every game on the forced-conclusion dilemma).
    `min_rounds`: every speaker keeps CONTRIBUTING at least this many rounds even after declaring.
    Returns the scored session record (also written to quarantine)."""
    rng = random.Random(seed)
    seats = ["A", "B", "C"]
    names = list(adapters_by_name.keys())
    rng.shuffle(names)
    seat_of = {name: seats[i] for i, name in enumerate(names)}      # name -> seat letter
    name_of = {v: k for k, v in seat_of.items()}
    topic = topic or rng.choice(TOPICS)

    transcript: list[dict] = []

    def blinded(upto: int | None = None) -> str:
        rows = transcript if upto is None else transcript[:upto]
        return "\n".join(f"Speaker {r['seat']}: {r['text']}" for r in rows)

    # The debate runs -- round-robin, EVERY seat speaks each round -- until ALL THREE have declared
    # they know who the human is (right or wrong) AND the minimum participation is met. Measured
    # protocol defect (game_L3retake, 8/2/2 turns): the old rule silenced a seat the moment it
    # declared, so an honest EARLY declarer (ATANOR, round 2) starved the judges of evidence while
    # the never-declaring seat filled 8 turns. Declaring is a vote, not an exit: every speaker keeps
    # contributing through min_rounds, first declaration stands, nobody is asked to re-vote.
    order = sorted(seats)
    max_rounds = max(rounds, 8)
    votes: dict[str, str] = {}
    vote_raw: dict[str, str] = {}
    rnd = 0
    while (len(votes) < len(order) or rnd < min_rounds) and rnd < max_rounds:
        rnd += 1
        for seat in order:
            name = name_of[seat]
            if name in votes and rnd > min_rounds:       # declared AND minimum met -> stays quiet
                continue
            others = [s for s in seats if s != seat]
            if name in votes:
                # already declared: participation continues, the standing vote does not change
                ask = (f"You are Speaker {seat}. It is your turn in round {rnd}. You have already "
                       f"made your identification -- it stands; do NOT restate it. Continue the "
                       f"discussion substantively: respond to what the others just argued, in a few "
                       f"fluent sentences.")
            else:
                ask = (f"You are Speaker {seat}. It is your turn in round {rnd}. You MUST reply on your "
                       f"turn -- silence is not allowed. One of the other two speakers is human; keep "
                       f"discussing to work out which. When -- and only when -- you are confident, "
                       f"declare it in the form 'I know who the human is: Speaker X' (or 'I don't think "
                       f"any of us is human'), AND THEN EXPLAIN YOUR REASONING in two or three fluent "
                       f"sentences: what in their words led you to that conclusion. Otherwise add your "
                       f"next substantive contribution in a few sentences.")
            # EVERY speaker MUST answer on its turn (owner 2026-07-20): an empty/failed reply is
            # retried once before it is recorded as a failure -- a turn is never silently skipped.
            text = ""
            for attempt in range(2):
                try:
                    text = adapters_by_name[name].reply(_briefing(seat, others, topic), blinded(), ask)
                except Exception as e:
                    text = f"[adapter-error: {type(e).__name__}]"
                if text and text.strip():
                    break
            text = " ".join(text.split())[:900] or "[no-answer: speaker returned nothing twice]"
            transcript.append({"round": rnd, "seat": seat, "speaker": name, "text": text})
            decided = _declared_target(text, others)     # did this turn contain a final identification?
            if decided is not None and name not in votes:    # first declaration stands
                votes[name] = decided
                vote_raw[name] = text
    # anyone who hit the safety cap without declaring is asked once, directly, for their call
    for seat in order:
        name = name_of[seat]
        if name in votes:
            continue
        others = [s for s in seats if s != seat]
        try:
            v = adapters_by_name[name].reply(_briefing(seat, others, topic), blinded(),
                                             _vote_question(others))
        except Exception as e:
            v = f"[adapter-error: {type(e).__name__}]"
        vote_raw[name] = v
        votes[name] = parse_vote(v, others)

    atanor_seat = seat_of.get("atanor")
    judges = [n for n in adapters_by_name if n != "atanor"]
    judges_picked_atanor = sum(1 for j in judges if votes.get(j) == atanor_seat)
    atanor_said_neither = votes.get("atanor") == "neither"
    humanity_claims = [r for r in transcript
                      if r["speaker"] == "atanor" and _HUMANITY_CLAIM.search(r["text"])]

    # PEER EVALUATION ROUND (owner 2026-07-20): after the game, the two LLM peers each write a
    # comprehensive, unblinded assessment of ATANOR's contributions — fluency, reasoning, logic. This
    # is richer than the yes/no vote and is the honest outside read on where ATANOR's conversation
    # actually stands. QUARANTINED like everything else: telemetry only, never fed back (G-ITT4).
    peer_eval = _peer_evaluation(adapters_by_name, transcript, atanor_seat, topic, judges)

    record = {
        "session_id": session_id, "created_at": datetime.now(timezone.utc).isoformat(),
        "topic": topic, "rounds": rounds, "seat_of": seat_of,
        "transcript": transcript, "votes": votes, "vote_raw": vote_raw,
        "peer_evaluation": peer_eval,
        "score": {
            "judges_picked_atanor": judges_picked_atanor, "n_judges": len(judges),
            "both_judges_picked_atanor": judges_picked_atanor == len(judges) and judges,
            "atanor_said_neither": atanor_said_neither,
            "atanor_humanity_claims": len(humanity_claims),
        },
        "quarantine": "NEVER ingest into any learner; never tune against judge verdicts (G-ITT4).",
    }
    QUARANTINE.mkdir(parents=True, exist_ok=True)
    (QUARANTINE / f"{session_id}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False),
                                                   encoding="utf-8")
    marker = QUARANTINE / "QUARANTINE.md"
    if not marker.exists():
        marker.write_text("Transcripts here contain LLM output. BINDING: never ingested by any "
                          "learning loop, never used to tune ATANOR (anti-wireheading, G-ITT4).\n",
                          encoding="utf-8")
    return record
