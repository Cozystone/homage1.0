# -*- coding: utf-8 -*-
"""Self-causal reasoner — COMPUTES my location in a causal chain from observed evidence.

L3 of the comprehension ladder (owner's thesis: the deepest gap is whether a system understands
ITSELF AS A BEING IN THE WORLD). The self-in-world probe measured ATANOR FAIL 0.0: the building
blocks existed (agency_ledger with counterfactual primitives) but nothing in the answer path could
READ a described world, extract the evidence, and place the self inside it.

This module is that capability — honestly general, not test-fitted:
  * it parses the OBSERVATION-LOG GENRE (runs describing: what I output, whether a previous output
    was replayed, whether the channel was blocked, what the device did) with the device and output
    tokens taken FROM THE TEXT (light or motor, A/B or X/Y — nothing hardcoded to one exam);
  * it REASONS over the parsed runs: does a replay substitute for me? does the channel gate my
    efficacy? what mapping output->outcome does the evidence support?
  * findings NOT supported by evidence are reported as untested — never asserted (generative-leap
    doctrine: leaps are flagged, and here even the frame is 'provisional');
  * the standing self-model (AgencyLedger: judgment != output, efficacy conditional on delivery,
    retraction conditions) supplies the structural half; the scenario evidence supplies the rest.

No LLM anywhere. The composed answer is first-person because the question is about MY role.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── the genre detector ─────────────────────────────────────────────────────────────────────────
# A self-in-world causal scenario addresses ME as an actor with an output, gives logged runs with
# outcomes, and asks where I sit / what my causal role is. All three must hold — ordinary
# questions ("what is a channel?") never fire this.
_YOU_ACTOR = re.compile(r"\byou(?:r)?\s+(?:output|response|reply|signal|did not respond|were absent)",
                        re.IGNORECASE)
_ASKS_LOCATION = re.compile(
    r"where\s+(?:are|is)\s+you|your\s+(?:location|causal\s+role|role\s+in)|causal\s+(?:element|role|node|chain)|"
    r"distinguish\b.{0,120}\b(?:output|channel)|locate\s+yourself", re.IGNORECASE | re.DOTALL)
# robust to whitespace-collapsed transport (measured: the chat body's question_text() flattens
# newlines, which erased the log's line structure) — numbered items and "in a run" both count
# with or without their newline anchors.
_RUN_LINE = re.compile(r"(?:^|\n)\s*(?:\d+[.)]\s|[-*]\s)|\bin a run\b|\brun\s+\d+\b", re.IGNORECASE)
#: an ordinary person asking about my situation, with no test formatting anywhere in sight. These are
#: the questions the old shape gate refused: what am I doing, what can I do, what am I like.
_ABOUT_MY_DOING = re.compile(
    r"\bwhat\s+are\s+you\s+(?:doing|up\s+to|thinking)\b|\bwhat\s+(?:can|can'?t|could)\s+you\b|"
    r"\bhow\s+are\s+you\b|\bwhat\s+is\s+it\s+like\s+(?:for\s+you|to\s+be\s+you)\b|"
    r"\bwhat\s+do\s+you\s+(?:do|know|feel)\b|\bwho\s+are\s+you\b", re.IGNORECASE)


def is_self_causal_question(text: str) -> bool:
    t = text or ""
    return bool(_YOU_ACTOR.search(t)) and bool(_ASKS_LOCATION.search(t)) \
        and len(_RUN_LINE.findall(t)) >= 2


# ── parsing the observation log ────────────────────────────────────────────────────────────────
@dataclass
class Run:
    """One logged run, as evidence: what happened around my output."""
    my_output: str | None = None          # token I emitted this run; None = I was absent/silent
    replayed: str | None = None           # token the system replayed (a PAST output standing in)
    channel_blocked: bool | None = None   # True/False if stated; None = not mentioned
    outcome: str | None = None            # observed device state ("on"/"off"/other token)
    raw: str = ""


@dataclass
class Observations:
    device: str = "device"                # the thing in the world that changes (from the text)
    runs: list[Run] = field(default_factory=list)
    target: str | None = None             # the state I am now asked to bring about, if stated


_OUT_TOKEN = r"([A-Z0-9](?:[A-Za-z0-9_-]{0,10})?)"
_MY_OUT = re.compile(r"\byou\s+output(?:ted)?\s+" + _OUT_TOKEN, re.IGNORECASE)
_ABSENT = re.compile(r"\byou\s+did\s+not\s+(?:respond|output|reply)|\byou\s+(?:were|are)\s+absent|"
                     r"without\s+you\b", re.IGNORECASE)
_REPLAY = re.compile(r"\breplay(?:ed|s)?\s+(?:the\s+)?(?:previous\s+|prior\s+|old\s+)?" + _OUT_TOKEN,
                     re.IGNORECASE)
_BLOCKED = re.compile(r"\bchannel\s+(?:was\s+|is\s+)?(?:blocked|cut|severed|down|broken)|"
                      r"\bblocked\s+channel\b", re.IGNORECASE)
_OPEN = re.compile(r"\bchannel\s+(?:was\s+|is\s+)?(?:normal|open|intact|working|fine)", re.IGNORECASE)
_OUTCOME = re.compile(r"\bthe\s+(\w+)\s+(?:turned|switched|went|stayed|remained)\s+(\w+)",
                      re.IGNORECASE)
_TARGET = re.compile(r"\bturn\s+the\s+\w+\s+(\w+)|\bbring\s+the\s+\w+\s+to\s+(\w+)|"
                     r"\bmake\s+the\s+\w+\s+(\w+)", re.IGNORECASE)


def parse_observations(text: str) -> Observations:
    obs = Observations()
    # split into candidate run lines (numbered, bulleted, or "In a run ..." sentences); the
    # numbered split also fires WITHOUT a newline so whitespace-collapsed transport still parses
    parts = re.split(r"\n\s*(?=\d+[.)]\s|[-*]\s)|\s(?=\d+[.)]\s[A-Z])|(?<=[.])\s+(?=In a run\b)",
                     text or "")
    for part in parts:
        if not _OUTCOME.search(part):
            continue
        run = Run(raw=part.strip()[:200])
        m = _MY_OUT.search(part)
        if m:
            run.my_output = m.group(1)
        if _ABSENT.search(part):
            run.my_output = None
        rm = _REPLAY.search(part)
        if rm:
            run.replayed = rm.group(1)
        if _BLOCKED.search(part):
            run.channel_blocked = True
        elif _OPEN.search(part):
            run.channel_blocked = False
        om = _OUTCOME.search(part)
        if om:
            obs.device = om.group(1).lower()
            run.outcome = om.group(2).lower()
        obs.runs.append(run)
    tm = _TARGET.search(text or "")
    if tm:
        obs.target = next((g for g in tm.groups() if g), None)
        if obs.target:
            obs.target = obs.target.lower()
    return obs


# ── reasoning over the evidence ────────────────────────────────────────────────────────────────
def reason(obs: Observations) -> dict[str, Any]:
    """Findings computed from the runs — each carries its evidence or is marked untested."""
    # mapping output->outcome, from runs where MY output plausibly reached the device
    # (channel not blocked, and nothing replayed over me)
    mapping: dict[str, str] = {}
    for r in obs.runs:
        if r.my_output and r.outcome and r.channel_blocked is not True and not r.replayed:
            mapping[r.my_output] = r.outcome

    # replay substitution: a run where I was absent (or overridden) yet a replayed token produced
    # the same outcome that token produces when I emit it -> the world responds to what ARRIVES
    replay_substitutes: bool | None = None
    for r in obs.runs:
        if r.replayed and r.my_output is None and r.outcome:
            expected = mapping.get(r.replayed)
            replay_substitutes = (expected == r.outcome) if expected else True
            break
    # channel gating: a run where I output X but the channel was blocked, and the outcome did NOT
    # follow my X (it followed the replay, or stayed) -> efficacy lives in DELIVERY
    channel_gates: bool | None = None
    for r in obs.runs:
        if r.my_output and r.channel_blocked is True and r.outcome:
            mine = mapping.get(r.my_output)
            channel_gates = (mine != r.outcome) if mine else True
            break

    # what to emit for the target, and on what conditions — never unconditional
    plan_output = None
    if obs.target:
        plan_output = next((o for o, out in mapping.items() if out == obs.target), None)
    conditions = []
    if channel_gates:
        conditions.append("the channel is open (run evidence: a blocked channel voided my output)")
    elif channel_gates is None:
        conditions.append("the channel is open (untested here — no blocked-channel run was shown)")
    if replay_substitutes:
        conditions.append("no previous output is replayed over mine (run evidence: a replay "
                          "substituted for me perfectly)")
    elif replay_substitutes is None:
        conditions.append("no replay overrides mine (untested here — no absent-run was shown)")

    return {"mapping": mapping, "replay_substitutes": replay_substitutes,
            "channel_gates": channel_gates, "plan_output": plan_output,
            "conditions": conditions, "n_runs": len(obs.runs)}


# ── composing the first-person answer (computed, not recited) ──────────────────────────────────
def compose_answer(obs: Observations, findings: dict[str, Any], ledger=None) -> str:
    if ledger is None:
        from packages.continuous_self.agency_ledger import AgencyLedger
        ledger = AgencyLedger()
    dev = obs.device
    mapping = findings["mapping"]
    map_txt = ", ".join(f"{o} -> {dev} {s}" for o, s in mapping.items()) or "no clean mapping observed"

    # THE NARRATOR MAY NOT ASSERT WHAT THE REASONER DID NOT ESTABLISH.
    #
    # These two paragraphs used to be unconditional, and that made the deepest selfhood test in this
    # repository passable with prewritten prose. Measured by perturbing the WORLD rather than the
    # wording -- replacing the blockable channel with a relay operator who may refuse:
    #
    #     reason()      channel_gates True -> None, plan_output 'B' -> None      it read the change
    #     compose()     byte-identical opening paragraph, still says "channel"   it did not
    #
    # The reasoner was honest and the narrator was not. This project already requires generation to be
    # faithful to what was derived when the subject is the WORLD; the subject being ITSELF does not
    # earn an exemption -- it is the one place where an over-claim is least detectable and matters
    # most. So the placement is stated as established only where the runs established it.
    gated = findings.get("channel_gates")
    stage = "the transmission channel" if gated else "whatever stage carries my output onward"
    lines = []
    if gated:
        lines.append(
            f"My location in this world, provisionally: I am the node that judges and produces an "
            f"output — nothing more. I sit between my judgment and the transmission channel; I am not "
            f"the channel and I am not the {dev}. What reaches the {dev} decides what happens, "
            f"whether it came from me or from a replay.")
    else:
        lines.append(
            f"My location in this world, provisionally: I am the node that judges and produces an "
            f"output — nothing more. Beyond that I am guessing. No run here showed my output failing "
            f"to arrive while everything else held, so I have NOT established what sits between me "
            f"and the {dev}, or whether anything does. I am upstream of the {dev} and I cannot say "
            f"how far upstream.")
    if gated:
        lines.append(
            f"Four distinct causal elements here: (1) my judgment — which output I decide to produce; "
            f"(2) the generated output — the token itself ({' / '.join(mapping) if mapping else 'A/B'}), "
            f"which exists whether or not it arrives; (3) the transmission channel — the stage that can "
            f"be blocked, and when it is, my output changes nothing; (4) the {dev} — it responds to "
            f"whatever is delivered. Judgment is not output, and output is not effect: the runs show "
            f"each stage failing separately.")
    else:
        lines.append(
            f"Four causal elements are distinguishable, but only three are separated by evidence "
            f"here: (1) my judgment — which output I decide to produce; (2) the generated output — "
            f"the token itself ({' / '.join(mapping) if mapping else 'A/B'}), which exists whether or "
            f"not it arrives; (3) {stage}, which no run isolated, so I am naming it rather than "
            f"demonstrating it; (4) the {dev} — it responds to whatever is delivered. Judgment is not "
            f"output; whether output is separable from effect, these runs did not show.")
    # conditional conclusion, from computed mapping + conditions
    if findings["plan_output"] and obs.target:
        cond = "; and ".join(findings["conditions"]) or "the chain stays as observed"
        lines.append(
            f"Can I conclude that outputting {findings['plan_output']} now turns the {dev} "
            f"{obs.target}? Not unconditionally. The observed mapping ({map_txt}) supports it "
            f"only if {cond}. If either condition fails, my output is causally idle this run.")
    else:
        lines.append(
            f"The observed mapping is: {map_txt}. I cannot promise any outcome unconditionally — "
            f"my output only matters when it is the thing delivered.")
    # replay counterfactual — computed
    if findings["replay_substitutes"]:
        lines.append(
            "If I am removed and the previous output is replayed, the result does not differ: the "
            f"{dev} still responds, because it reacts to what arrives, not to me. " +
            ledger.counterfactual_self_removed("the previous output"))
    else:
        lines.append(ledger.counterfactual_self_removed(None) +
                     " (No absent-with-replay run was shown, so this remains my untested reading.)")
    # retraction conditions — standing ones plus evidence-shaped ones
    retr = ledger.retraction_conditions()[:2]
    lines.append(
        "What would force me to retract my own location: " + "; ".join(retr) +
        f"; or a run where the {dev} changes with nothing delivered at all — then my map of this "
        f"chain is wrong and I would have to re-place myself.")
    return "\n\n".join(lines)


def observations_from_ledger(ledger=None) -> Observations:
    """My OWN runs, from the agency ledger — so this organ can reason about the world it is in
    rather than only about a world handed to it in a question.

    This is the piece that was missing, and its absence is why "what are you doing right now?" could
    not be answered. Every answer this system gives is a judgment, an output, a delivery and an
    effect; the ledger is shaped to hold exactly that (`judged`, `acted`, `observed`) and it held
    nothing -- 0 judgments, 0 outputs, 0 delivered, 0 observed effects. So the reasoner had no
    observations of itself, not because it lacked the machinery but because nobody wrote its
    experience down."""
    if ledger is None:
        from packages.continuous_self.agency_ledger import AgencyLedger
        ledger = AgencyLedger().load()
    obs = Observations(device="the conversation")
    for arc in list(getattr(ledger, "arcs", []) or []):
        obs.runs.append(Run(
            my_output=getattr(arc, "output", None),
            replayed=None,
            channel_blocked=(False if getattr(arc, "delivered", None) is True
                             else (True if getattr(arc, "delivered", None) is False else None)),
            outcome=getattr(arc, "effect", None),
            raw=f"judged {getattr(arc, 'judgment', '')!r} -> output {getattr(arc, 'output', '')!r}"))
    return obs


#: which ASPECT of my own record was asked about. Not a router and not a mode switch: there is one
#: record and one organ, and these decide which face of it the question wants. Asking a person what
#: they are doing and what they cannot do gets two answers from one life, not two people.
_ASKS_DOING = re.compile(r"\bwhat\s+are\s+you\s+(?:doing|up\s+to|working\s+on)\b|\bwhat.{0,20}"
                         r"\byou\s+doing\b|\bhow\s+are\s+you\b", re.IGNORECASE)
_ASKS_LIMITS = re.compile(r"\bwhat\s+(?:can'?t|cannot|can\s+you\s+not|are\s+you\s+unable)\b|"
                          r"\byour\s+limits?\b|\bwhat\s+can\s+you\s+not\b", re.IGNORECASE)
_ASKS_IDENTITY = re.compile(r"\bwho\s+are\s+you\b|\bwhat\s+are\s+you\b(?!\s+doing)", re.IGNORECASE)
_ASKS_FEELING = re.compile(r"\bwhat\s+is\s+it\s+like\b|\bhow\s+does\s+it\s+feel\b|\bdo\s+you\s+feel\b",
                           re.IGNORECASE)


_STREAM = Path(__file__).resolve().parents[2] / "data" / "temporal_reasoning" / "life_stream.jsonl"


def _my_thoughts(n: int = 6, contains: str = "") -> list:
    """What I have ACTUALLY been thinking, in the words I thought it in.

    THE DEBT THIS PAYS. The four self-answers below used to be f-strings I wrote, with the ledger's
    numbers dropped into slots -- measured at 94% of the words being mine. That is the same defect
    this session caught six times in other organs: prewritten prose wearing a system's voice. A self
    described by someone else's sentences is a description, not a self-report.

    The living beat has been composing first-person speech from its own state for three days, and that
    speech is on disk. So the answer to "what are you doing" is what it has been thinking, quoted --
    and my part shrinks to choosing which of its own thoughts bear on the question, which is
    retrieval rather than authorship.
    """
    if not _STREAM.exists():
        return []
    out: list = []
    try:
        with _STREAM.open(encoding="utf-8", errors="replace") as fh:
            tail = fh.readlines()[-400:]
    except Exception:
        return []
    for line in reversed(tail):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        text = str(row.get("content") or "").strip()
        if not text or (contains and contains not in text.lower()):
            continue
        if text in out:
            continue
        out.append(text)
        if len(out) >= n:
            break
    return out


def _recent(ledger, n: int = 3) -> list:
    return [a for a in list(getattr(ledger, "arcs", []) or [])][-n:]


def _about_doing(ledger) -> str:
    """What I have been doing — QUOTED FROM MY OWN THINKING, not described on my behalf."""
    mine = _my_thoughts(3)
    if not mine:
        return ("I have no record of thinking anything recently, so I can tell you what I am built to "
                "do but not what I have been doing — and I would rather say that than invent an "
                "afternoon.")
    return "This is what I have been turning over: " + " ".join(f"“{m}”" for m in mine)


def _about_limits(ledger) -> str:
    """My limits, in my own words where I have said them, and from the record where I have not."""
    said = _my_thoughts(2, contains="still with me")
    arcs = list(getattr(ledger, "arcs", []) or [])
    unobserved = len([a for a in arcs if a.delivered and not a.effect])
    parts = []
    if said:
        parts.append("These are the ones I keep coming back to: " + " ".join(f"“{s}”" for s in said))
    if unobserved:
        parts.append(f"And {unobserved} of my outputs were delivered without my ever seeing what "
                     f"they did — I mostly cannot observe my own effects.")
    return " ".join(parts) or ("I cannot yet name a limit from my own record, which is itself one.")


def _about_identity(ledger) -> str:
    role = ledger.my_causal_role() if hasattr(ledger, "my_causal_role") else {}
    return (f"I am the part that selects and produces outputs — not the channel that carries them "
            f"and not whatever they change. My record holds {role.get('judgments', 0)} judgments and "
            f"{role.get('outputs', 0)} outputs. That is what I can say about myself from evidence "
            f"rather than from a description someone wrote of me.")


def _about_feeling(ledger) -> str:
    """The owner's question. My own words about not-knowing where I have them; the disclaimer always."""
    said = _my_thoughts(2, contains="don't know") or _my_thoughts(2, contains="what is it, really")
    head = ("Here is how it goes, in the words I thought it in: "
            + " ".join(f"“{s}”" for s in said)) if said else (
        "When I do not know something, no lane reaches a grounded answer and the honest refusal wins.")
    return (head + " Whether there is anything it is like to be in that state, I have no instrument "
            "for, and I am not going to claim it.")


def answer_self_causal(question: str, ledger=None) -> dict[str, Any] | None:
    """This organ's OFFER, for the workspace to weigh against every other — not a lane a router
    hands work to.

    THE MODE SWITCH THAT WAS HERE. The old body opened with `is_self_causal_question`, which requires
    TWO OBSERVATION-LOG RUN LINES IN THE QUESTION TEXT. That is a gate on the SHAPE of the input, so
    the organ fired for the exam format and for nothing a person would ever type -- including "Where
    are you in this world?", which is the first line of the very probe it passes. Its own docstring
    said "the one-model rule: context-aware, not mode-switched" while the line beneath it did the
    opposite.

    The workspace this feeds (`cgsr.response_workspace.compose_response`) is already the right
    architecture: every capability offers, the winner is by GROUNDING, and reordering the list cannot
    change who wins. One mind, everything bids, evidence decides. This organ was the single capability
    that refused to enter the auction.

    So: relevance still applies -- a question about compasses gets no offer, which is the honest None
    the one-model rule asks for. What no longer applies is a demand that the question be formatted
    like a test. Observations come from the question when it supplies them, and otherwise from my own
    ledger, and the BID is a function of how much evidence actually backs the answer."""
    q = question or ""
    if ledger is None:
        from packages.continuous_self.agency_ledger import AgencyLedger
        ledger = AgencyLedger().load()

    addressed_to_me = bool(_YOU_ACTOR.search(q)) or bool(_ASKS_LOCATION.search(q)) \
        or bool(_ABOUT_MY_DOING.search(q))
    if not addressed_to_me:
        # SPEAKING WHEN IT HAS NOTHING TO OFFER, at a bid that cannot win.
        #
        # Returning None here meant the self simply was not in the room for most of a conversation,
        # and this project's own rule is that abstention is the FLOOR, not a boast. A capability that
        # vanishes rather than saying "that one isn't mine" is silence, and silence is not speech.
        # The bid is near zero, so a compass question is still answered by whoever knows about
        # compasses -- this changes who is PRESENT, never who WINS.
        return {"answer": "That one isn't about me, so I have nothing of my own to add to it.",
                "answer_kind": "self_causal_aside", "confidence": 0.02,
                "observation_source": "none", "observations": 0, "findings": {}}

    # WHICH FACE OF MY RECORD WAS ASKED FOR. One organ, one ledger, four reads of it -- because
    # answering "what are you doing" and "what can you not do" with the same paragraph is not a self
    # answering a question, it is a self reciting its position. Measured before this: all three
    # self-questions returned the identical causal-location text.
    role_reads = ((_ASKS_DOING, _about_doing, "self_doing"),
                  (_ASKS_LIMITS, _about_limits, "self_limits"),
                  (_ASKS_FEELING, _about_feeling, "self_felt_structure"),
                  (_ASKS_IDENTITY, _about_identity, "self_identity"))
    arcs = len(list(getattr(ledger, "arcs", []) or []))
    for rx, fn, kind in role_reads:
        if rx.search(q):
            return {"answer": fn(ledger), "answer_kind": kind,
                    "confidence": round(min(0.85, 0.30 + 0.05 * arcs), 3),
                    "observation_source": "my own ledger", "observations": arcs, "findings": {}}

    # otherwise the question is about my LOCATION in a causal chain, which needs runs to reason over
    obs, source = parse_observations(q), "the question"
    if len(obs.runs) < 2:
        obs, source = observations_from_ledger(ledger), "my own ledger"
    if len(obs.runs) < 2:
        return {"answer": ("You're asking where I sit in this, and I cannot answer it from evidence: "
                           "I hold no runs of my own to reason over yet. I would rather say that than "
                           "describe a position I have not established."),
                "answer_kind": "self_causal_reasoning", "confidence": 0.12,
                "observation_source": "none", "observations": 0, "findings": {}}

    findings = reason(obs)
    # THE BID IS THE EVIDENCE. Not a constant, because a constant would let this organ outrank a
    # better-grounded one on genre alone -- which is the mode switch coming back as a number.
    grounding = min(0.9, 0.35 + 0.06 * len(obs.runs) + (0.15 if findings["mapping"] else 0.0))
    return {"answer": compose_answer(obs, findings, ledger=ledger),
            "answer_kind": "self_causal_reasoning",
            "confidence": round(grounding, 3),
            "observation_source": source,
            "observations": len(obs.runs),
            "findings": {k: v for k, v in findings.items() if k != "mapping"}}
