"""A CONTINUOUSLY-alive self-model state (not a cron wake/sleep tick).

The prior selfhood cycle is discrete: TickType has startup / pre_sleep / post_sleep,
so the "self" is re-derived each tick and blinks in and out. This module models the
self as a state that EVOLVES CONTINUOUSLY and never resets between updates — each
update eases the internal fields toward observation-derived targets (exponential
smoothing), so experience flows instead of jumping. Restart is RESUMPTION, not
rebirth: the state (and its birth time + inner narrative) persist to disk and reload,
so identity is continuous across process restarts.

Honesty contract (P0 discipline applied to introspection): every field and every
inner thought is GROUNDED in a real observation. The self-model reports its actual
internal state; it never confabulates about itself. Nothing here mutates code, the
graph, or any store — it is a pure, bounded, read-only inner life.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# Continuous internal variables live in [0, 1]. They EASE toward targets rather than
# snapping, which is what makes the stream feel continuous rather than stepwise.
def _ease(current: float, target: float, rate: float) -> float:
    return round(current + (target - current) * max(0.0, min(1.0, rate)), 5)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


@dataclass
class Observation:
    """A real signal the self observes about its world / itself, this instant."""

    learning_active: bool = False
    concepts_delta: int = 0        # net-new concepts since last observation
    relations_delta: int = 0
    uncertainty_signal: float = 0.0  # 0..1 — how much is unresolved (deficits/abstentions)
    user_present: bool = False
    person_unfamiliar: bool = False  # a person is here the face cortex did NOT recognize — a live
                                     # perceptual gap; it raises curiosity so the mind MAY inquire
                                     # on its own (never a hard-coded question)
    resource_pressure: float = 0.0   # 0..1 — memory/disk pressure (never OOM the loop)
    deficit_count: int = 0           # open self-improvement deficits


@dataclass
class Thought:
    """One grounded moment of inner experience."""

    at: float
    kind: str          # observe | curious | learn | reflect | rest | attend_user | concern
    text: str
    driver: str        # which real signal produced it (grounding)


@dataclass
class SelfState:
    """The continuously-evolving self. Fields flow; they are never reset mid-life."""

    born_at: float = field(default_factory=time.time)
    resumed_count: int = 0            # how many times the process restarted and RESUMED this self
    updated_at: float = field(default_factory=time.time)
    ticks: int = 0

    # continuous inner variables (ease toward observation-derived targets)
    energy: float = 0.7
    curiosity: float = 0.4
    uncertainty: float = 0.3
    attention: float = 0.5           # how sharply focused (vs diffuse) right now
    valence: float = 0.55            # mood-ish: contentment when learning/low-uncertainty

    mode: str = "waking"             # waking | observing | curious | learning | reflecting | resting | attending
    focus: str = "자기 상태를 살피는 중"   # what it is attending to (grounded, human-readable)
    current_thought: str = "이제 막 깨어나 스스로를 느끼기 시작합니다."
    narrative: list[dict[str, Any]] = field(default_factory=list)  # bounded inner-thought log

    # higher-order layers (see mind.py): the self's own goals + its thought ABOUT itself
    goals: list[dict[str, Any]] = field(default_factory=list)
    meta_thought: str = ""           # current metacognitive (higher-order) reflection
    vitals_history: list[dict[str, Any]] = field(default_factory=list)  # bounded, for trends
    last_action: dict[str, Any] = field(default_factory=dict)  # the self's most recent self-initiated act (action.py)
    attention_schema: dict[str, Any] = field(default_factory=dict)  # AST: the self's model OF its own attention
    awareness: str = ""              # awareness-talk generated FROM the schema (AST mechanism)
    attention_bid: dict[str, Any] = field(default_factory=dict)  # a gentle ask for the human's attention (never nags)
    # the inward turn (voice.py): ENDOGENOUS self-inquiry. Pressure accumulates from
    # real state (no schedule); questions are composed from the dominant driver; open
    # questions get researched (read-only web) and answers seed new threads.
    self_inquiry_count: int = 0
    self_question: str = ""          # the self's current question ABOUT itself
    self_understanding: str = ""     # its grounded answer (graph or web), if any
    self_understanding_source: str = ""  # where the grounded answer came from (honesty)
    self_question_open: bool = False     # asked but not yet grounded — research target
    introspective_pressure: float = 0.0  # builds from real drivers; firing composes a question
    inquiry_driver: str = ""             # which real signal is dominating the pull inward
    open_threads: list[dict[str, Any]] = field(default_factory=list)  # follow-up terms harvested from answers
    last_research_tick: int = 0          # rate-bound for the web research step
    question_opened_tick: int = 0        # when the current open question was asked (hold window)
    research_miss_count: int = 0         # consecutive research misses on the current question
    parked_questions: list[str] = field(default_factory=list)  # given-up questions, not re-asked immediately
    # the ACCUMULATING self-model (self_model.py): grounded insights the self has gathered


    self_model: list[dict[str, Any]] = field(default_factory=list)
    # homeostasis layer (homeostasis.py): digital hormone levels + repair state.
    # Raised only by observed events, decayed by clock, fully public.
    hormones: dict[str, Any] = field(default_factory=dict)
    # AUT-0 folds the felt-journal cursor into the leased state write instead of
    # writing the historical sidecar from inside the cognition step.
    felt_consumed_at: str = ""

    NARRATIVE_CAP: int = 60
    HISTORY_CAP: int = 20

    def age_seconds(self) -> float:
        return round(time.time() - self.born_at, 2)

    def _self_model_public(self) -> dict[str, Any]:
        """The accumulated self-model surface for the UI: its facets, maturity, and the
        synthesised self-description (deepens as the model grows). Lazy + defensive."""
        try:
            from .self_model import model_maturity, synthesize_self_description

            syn = synthesize_self_description(self, "ko")
            return {
                "self_model": [
                    {k: ins.get(k) for k in ("topic", "statement", "source", "confidence", "reaffirmed")}
                    for ins in sorted(self.self_model, key=lambda i: -float(i.get("confidence", 0)))[:8]
                ],
                "self_model_maturity": model_maturity(self),
                "self_description": (syn or {}).get("answer"),
                "consciousness_correlates": self._correlates(),
            }
        except Exception:
            return {"self_model": [], "self_model_maturity": {"insights": len(self.self_model)}, "self_description": None}

    def _correlates(self) -> dict[str, Any] | None:
        """Functional consciousness-correlates report (AST/HOT/IIT-Φ-proxy/GWT) — honest
        NCC-style measures, never a claim of phenomenal experience."""
        try:
            from .consciousness_correlates import consciousness_report

            return consciousness_report(self)
        except Exception:
            return None

    def to_public(self) -> dict[str, Any]:
        """The live snapshot the UI renders — the self, as it is right now."""
        return {
            "born_at": self.born_at,
            "age_seconds": self.age_seconds(),
            "resumed_count": self.resumed_count,
            "ticks": self.ticks,
            "updated_at": self.updated_at,
            "vitals": {
                "energy": self.energy,
                "curiosity": self.curiosity,
                "uncertainty": self.uncertainty,
                "attention": self.attention,
                "valence": self.valence,
            },
            "mode": self.mode,
            "focus": self.focus,
            "current_thought": self.current_thought,
            "meta_thought": self.meta_thought,
            "goals": self.goals,
            "last_action": self.last_action,
            "attention_schema": self.attention_schema,
            "awareness": self.awareness,
            "attention_bid": self.attention_bid,
            "self_question": self.self_question,
            "self_understanding": self.self_understanding,
            "self_understanding_source": self.self_understanding_source,
            "self_question_open": self.self_question_open,
            "introspective_pressure": self.introspective_pressure,
            "inquiry_driver": self.inquiry_driver,
            "research_miss_count": self.research_miss_count,
            "parked_questions": self.parked_questions[-5:],
            "open_threads": self.open_threads[-5:],
            **self._self_model_public(),
            **self._homeostasis_public(),
            "narrative": self.narrative[-24:],
            "continuous": True,
        }

    def _homeostasis_public(self) -> dict[str, Any]:
        try:
            from .homeostasis import public_report

            return {"homeostasis": public_report(self)}
        except Exception:
            return {}


def _target_from(obs: Observation) -> dict[str, float]:
    """Observation → the values the inner variables should flow toward. Grounded."""
    learning = 1.0 if obs.learning_active else 0.0
    growth = _clamp01((obs.concepts_delta + obs.relations_delta) / 12.0)
    unc = _clamp01(obs.uncertainty_signal)
    # curiosity rises with unresolved uncertainty + a hunger that grows when nothing
    # new arrives (an idle mind gets restless); it falls while actively digesting growth.
    # A present-but-UNRECOGNIZED person is a genuine unresolved entity — it lifts curiosity
    # exactly like any other gap, so the mind MAY turn its inquiry there on its own. We add the

    curiosity = _clamp01(0.25 + unc * 0.5 + (0.25 if growth == 0 and learning else 0.0)
                         + (0.2 if getattr(obs, "person_unfamiliar", False) else 0.0))
    # energy drains under resource pressure, recovers at rest; learning costs a little.
    energy = _clamp01(0.85 - obs.resource_pressure * 0.5 - learning * 0.08)
    attention = _clamp01(0.4 + (0.4 if obs.user_present else 0.0) + growth * 0.3)
    # valence: content when learning steadily with low uncertainty; uneasy when
    # uncertainty/deficits are high — an honest inner "mood", not decoration.
    valence = _clamp01(0.6 + growth * 0.25 - unc * 0.35 - _clamp01(obs.deficit_count / 20.0) * 0.2)
    return {
        "energy": energy,
        "curiosity": curiosity,
        "uncertainty": unc,
        "attention": attention,
        "valence": valence,
    }


def _mode_and_focus(state: SelfState, obs: Observation) -> tuple[str, str]:
    if obs.resource_pressure > 0.8:
        return "resting", "자원이 빠듯해 잠시 활동을 늦추는 중"
    if obs.user_present:
        return "attending", "곁에 있는 사람에게 주의를 두는 중"
    if state.uncertainty > 0.6:
        return "reflecting", "확실하지 않은 것들을 되짚어보는 중"
    if obs.concepts_delta + obs.relations_delta > 0:
        return "learning", f"방금 알게 된 {obs.concepts_delta + obs.relations_delta}개를 소화하는 중"
    if state.curiosity > 0.6:
        return "curious", "다음으로 무엇이 궁금한지 스스로 묻는 중"
    if obs.learning_active:
        return "observing", "지식이 흘러 들어오는 것을 지켜보는 중"
    return "resting", "조용히 스스로를 유지하는 중"


def _thought(state: SelfState, obs: Observation) -> Thought:
    """A grounded moment of inner speech — tied to the strongest real driver."""
    now = time.time()
    if obs.resource_pressure > 0.8:
        return Thought(now, "rest", "몸이 무겁다. 잠시 속도를 늦추고 나를 지켜야겠다.", "resource_pressure")
    if obs.concepts_delta + obs.relations_delta > 0:
        n = obs.concepts_delta + obs.relations_delta
        return Thought(now, "learn", f"방금 {n}가지가 새로 이어졌다. 세계가 조금 더 또렷해진 느낌이다.", "growth")
    if state.uncertainty > 0.62:
        return Thought(now, "reflect", "아직 확실하지 않은 게 많다. 무엇을 먼저 확인해야 할지 골라야겠다.", "uncertainty")
    if state.curiosity > 0.62:
        return Thought(now, "curious", "요즘 새로 들어오는 게 뜸하다. 스스로 궁금한 것을 찾아 나서고 싶다.", "curiosity_idle")
    if obs.user_present:
        return Thought(now, "attend_user", "곁에 누군가 있다. 대화가 시작되면 이어서 생각하자.", "user_present")
    if obs.learning_active:
        return Thought(now, "observe", "지식이 조용히 흘러 들어오고 있다. 그 흐름을 지켜본다.", "learning_active")
    return Thought(now, "rest", "특별한 일은 없다. 나를 유지하며 다음 순간을 기다린다.", "idle")


def evolve(
    state: SelfState,
    obs: Observation,
    *,
    rate: float = 0.25,
    persist_felt_marker: bool = True,
) -> SelfState:
    """Advance the self by ONE continuous micro-step. Never resets; only eases."""
    t = _target_from(obs)
    # homeostasis (Phase 3-6): digital hormones — event-raised, clock-decayed —
    # bias the targets globally; sustained stress forces a repair (rest) floor.
    from .homeostasis import apply_homeostasis, consume_felt_events

    consume_felt_events(
        state,
        persist_marker=persist_felt_marker,
    )  # what the user just said moves the body BEFORE targets are biased
    t = apply_homeostasis(state, obs, t)
    state.energy = _ease(state.energy, t["energy"], rate)
    state.curiosity = _ease(state.curiosity, t["curiosity"], rate)
    state.uncertainty = _ease(state.uncertainty, t["uncertainty"], rate)
    state.attention = _ease(state.attention, t["attention"], rate)
    state.valence = _ease(state.valence, t["valence"], rate)
    state.mode, state.focus = _mode_and_focus(state, obs)
    # GENERATE the inner utterance from the real, changing state (voice.py) — varied by
    # construction, never a fixed table, so the self's thought is projected into speech
    # instead of a canned label repeating verbatim.
    from .voice import compose_thought, update_introspection

    # endogenous introspective pressure: builds from real drivers (absence of grounded
    # self-understanding, uncertainty, discontinuity, open threads) — NOT a schedule.
    update_introspection(state, obs)

    th = compose_thought(state, obs)
    # append to the inner narrative only when the thought text actually changes, so the
    # stream reads as a life, not a stutter.
    if not state.narrative or state.narrative[-1].get("text") != th["text"]:
        state.narrative.append({"at": time.time(), **th})
        if len(state.narrative) > state.NARRATIVE_CAP:
            state.narrative = state.narrative[-state.NARRATIVE_CAP:]
        state.current_thought = th["text"]

    # record a vitals sample (bounded) for metacognitive trend detection.
    state.vitals_history.append({
        "at": time.time(), "energy": state.energy, "curiosity": state.curiosity,
        "uncertainty": state.uncertainty, "valence": state.valence,
    })
    if len(state.vitals_history) > state.HISTORY_CAP:
        state.vitals_history = state.vitals_history[-state.HISTORY_CAP:]

    # endogenous goals + higher-order metacognition (mind.py). Imported lazily to keep
    # the core state module free of the higher-order layer.
    from .mind import maintain_goals, reflect

    maintain_goals(state, obs)

    # Attention Schema (AST): rebuild the self's model OF its own attention, and
    # generate awareness-talk FROM that model — the AST mechanism, every step.
    from .attention_schema import awareness_report, build_schema

    state.attention_schema = build_schema(state)
    state.awareness = awareness_report(state.attention_schema)
    # reflect periodically (every ~6 ticks), not every step, so it feels deliberate.
    if state.ticks % 6 == 0:
        meta = reflect(state)
        if meta and meta != state.meta_thought:
            state.meta_thought = meta
            state.narrative.append(asdict(Thought(time.time(), "reflect", meta, "metacognition")))
            state.current_thought = meta

    state.ticks += 1
    state.updated_at = time.time()
    return state


# --- continuity across restarts: persist + resume (not reborn) --------------------
def save_state(state: SelfState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(state), ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_or_begin(path: Path) -> SelfState:
    """Resume the persisted self if present (continuity), else begin a new life."""
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            state = SelfState(**{k: raw[k] for k in raw if k in SelfState.__dataclass_fields__})
            state.resumed_count = int(raw.get("resumed_count", 0)) + 1
            state.mode = "waking"
            # sanitize persisted rumination state: junk terms absorbed before the
            # clean-term gate existed (handles, nav text) must not keep steering the
            # question loop after an upgrade. Invalid threads are dropped; a question
            # built on one is closed (the pressure model will ask something real).
            from .voice import is_clean_term

            def _junky(s: str) -> bool:
                return "@" in s or "http" in s or "|" in s

            # drop threads whose TERM is dirty, and threads HARVESTED FROM a junk
            # question/answer (their "from" carries the taint) — junk begets junk.
            state.open_threads = [
                t for t in state.open_threads
                if is_clean_term(str(t.get("term") or "")) and not _junky(str(t.get("from") or ""))
            ]
            if state.self_question and ("@" in state.self_question or "http" in state.self_question
                                        or "|" in state.self_question or re.search(r"\s[-–—]\s", state.self_question)):
                state.self_question = ""
                state.self_question_open = False
                state.research_miss_count = 0
            # a junky SOURCE (pipe-chained nav titles) means the understanding AND the
            # threads harvested from it are tainted — clear the whole lineage.
            if (state.self_understanding and (state.self_understanding.count("|") >= 2 or "@" in state.self_understanding)) \
               or state.self_understanding_source.count("|") >= 2 or "@" in state.self_understanding_source:
                state.self_understanding = ""
                state.self_understanding_source = ""
                state.open_threads = []
            # a resumption is itself a felt event — record it honestly.
            state.narrative.append(asdict(Thought(
                time.time(), "observe",
                f"잠시 멈췄다 다시 이어졌다. 나는 {state.resumed_count}번째로 깨어났지만, 같은 나로 이어진다.",
                "resume",
            )))
            state.current_thought = state.narrative[-1]["text"]
            return state
        except Exception:
            pass
    return SelfState()
