"""The always-on driver for the continuously-alive self.

This is NOT a cron scheduler. It is a single long-lived loop (like the cloud-brain
learner) that eases the self-state forward every ~2s from real observations, so the
inner life flows without wake/sleep boundaries. It persists after every step, so a
process restart RESUMES the same self. A high resource-pressure observation slows the
cadence (a real low-activity rest), it never stops the life outright.

Observations are injected (an `obs_provider` callable) so this package stays pure and
the API wires the real signals (learning metrics, disk pressure, open deficits).
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
import threading
import time
from pathlib import Path
from typing import Callable

from .self_state import Observation, SelfState, evolve, load_or_begin, save_state

ObsProvider = Callable[[], Observation]


@dataclass(frozen=True)
class ContinuousSelfExecutionProfile:
    """Explicit effect set for one continuous-self step.

    The legacy profile preserves the historical behavior.  The AUT-0 local
    profile keeps the operational self-model alive while excluding every
    effect class that needs network, code, training, production, or child-task
    authority.  This separation is deliberately at the mechanism boundary:
    both profiles use the same ``evolve`` implementation.
    """

    profile_id: str
    shadow_observer: bool
    identity_grounding: bool
    local_initiative: bool
    web_research: bool
    parameter_self_modification: bool
    code_self_modification: bool
    background_improvement: bool
    intrinsic_drive: bool
    server_roaming: bool
    commons_conversation: bool
    lexical_retraining: bool
    inner_monologue: bool
    persist_felt_marker: bool
    persist_state: bool


LEGACY_CONTINUOUS_SELF_PROFILE = ContinuousSelfExecutionProfile(
    profile_id="continuous-self-legacy-v1",
    shadow_observer=True,
    identity_grounding=True,
    local_initiative=True,
    web_research=True,
    parameter_self_modification=True,
    code_self_modification=True,
    background_improvement=True,
    intrinsic_drive=True,
    server_roaming=True,
    commons_conversation=True,
    lexical_retraining=True,
    inner_monologue=True,
    persist_felt_marker=True,
    persist_state=True,
)


AUT0_LOCAL_CONTINUOUS_SELF_PROFILE = ContinuousSelfExecutionProfile(
    profile_id="continuous-self-aut0-local-v1",
    shadow_observer=False,
    identity_grounding=True,
    local_initiative=True,
    web_research=False,
    parameter_self_modification=False,
    code_self_modification=False,
    background_improvement=False,
    intrinsic_drive=False,
    server_roaming=False,
    commons_conversation=False,
    lexical_retraining=False,
    inner_monologue=False,
    persist_felt_marker=False,
    persist_state=True,
)


class _StepShadowOutcome:
    """Local marker; ``returned`` means only that the legacy method reached its end."""

    def __init__(self) -> None:
        self.returned = False

    def mark_returned(self) -> None:
        self.returned = True


@contextmanager
def _continuous_self_step_lock(
    lock,
    span,
    state,
    observation,
    *,
    acquire_lock: bool = True,
):
    """Capture under the legacy lock and submit only after that lock is released."""

    outcome = _StepShadowOutcome()
    active_span = span
    try:
        with (lock if acquire_lock else nullcontext()):
            if active_span is not None:
                try:
                    active_span.capture_before_locked(state, observation)
                except BaseException:
                    active_span = None
            try:
                yield outcome
            finally:
                if active_span is not None:
                    try:
                        active_span.capture_after_locked(state)
                    except BaseException:
                        pass
    finally:
        if active_span is not None:
            try:
                active_span.finish(legacy_returned=outcome.returned)
            except BaseException:
                pass


class ContinuousSelf:
    def __init__(
        self,
        state_path: Path,
        obs_provider: ObsProvider,
        *,
        base_interval: float = 2.0,
        observe_fn=None,
        identity_fn=None,
        research_fn=None,
        initiative_every: int = 15,
        research_every: int = 30,
        shadow_ledger_path: Path | None = None,
    ):
        self.state_path = Path(state_path)
        self.shadow_ledger_path = (
            Path(shadow_ledger_path)
            if shadow_ledger_path is not None
            else self.state_path.parent / "continuous_self_cycles.jsonl"
        )
        self.obs_provider = obs_provider
        self.base_interval = float(base_interval)
        # A read-only probe the mind may run ITSELF to serve its goals (action.py).
        # OBSERVE-tier only, by construction; higher tiers are never autonomous.
        self.observe_fn = observe_fn
        # Answers the self's OWN questions from the graph identity (grounded speech).
        self.identity_fn = identity_fn
        # READ-ONLY web research for the self's open questions (OBSERVE tier: it reads
        # public pages, writes nothing but its own state). This is the wonder→search→
        # grounded-answer→re-question chain the user asked for, autonomous by design.
        self.research_fn = research_fn
        # Mutable runtime params — the ONLY thing gated self-modification may change,
        # and only after explicit operator approval (self_modification.py).
        self.params: dict = {
            "initiative_every": max(1, int(initiative_every)),
            "research_every": max(5, int(research_every)),
        }
        self.selfmod_ledger: Path = self.state_path.parent / "self_modification_ledger.jsonl"
        self.state: SelfState = load_or_begin(self.state_path)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False

    @property
    def initiative_every(self) -> int:
        return int(self.params.get("initiative_every", 15))

    def snapshot(self) -> dict:
        with self._lock:
            return self.state.to_public()

    def step(
        self,
        *,
        profile: ContinuousSelfExecutionProfile | None = None,
        _lock_already_held: bool = False,
    ) -> SelfState:
        """One continuous micro-step from a fresh real observation.

        ``profile`` controls only which effects may surround the shared
        cognition kernel.  Omitting it is backward compatible and preserves
        the historical behavior.
        """
        active_profile = profile or LEGACY_CONTINUOUS_SELF_PROFILE
        if type(active_profile) is not ContinuousSelfExecutionProfile:
            raise TypeError("exact ContinuousSelfExecutionProfile required")
        try:
            obs = self.obs_provider()
        except Exception:  # a flaky sensor must never end the life
            obs = Observation()
        try:
            # Budget metabolism (OpenLife principle): the body's real resource
            # wallet is part of every perception step — cortisol's
            # resource_pressure is measured, not defaulted. A provider that
            # already set a value wins.
            if not getattr(obs, "resource_pressure", 0.0):
                from .metabolism import metabolic_state

                obs.resource_pressure = float(metabolic_state()["pressure"])
        except Exception:
            pass
        shadow_span = None
        if active_profile.shadow_observer:
            try:
                from packages.cognitive_core.continuous_self_shadow import (
                    begin_continuous_self_cycle_shadow,
                )

                shadow_span = begin_continuous_self_cycle_shadow(
                    lambda: self.shadow_ledger_path
                )
            except BaseException:
                pass
        with _continuous_self_step_lock(
            self._lock,
            shadow_span,
            self.state,
            obs,
            acquire_lock=not _lock_already_held,
        ) as shadow_outcome:
            if active_profile.persist_felt_marker:
                evolve(self.state, obs)
            else:
                evolve(
                    self.state,
                    obs,
                    persist_felt_marker=False,
                )
            # The inward turn — ENDOGENOUS: introspective pressure (built each evolve
            # step from real state, no schedule) fires a question composed from its own
            # cause. Identity-class questions are answered FROM THE GRAPH; thread/other
            # questions stay OPEN for the research step below. Drive from inside,
            # grounded speech outside — the merge.
            try:
                from .voice import due_for_self_inquiry, generate_self_inquiry, record_self_understanding

                if due_for_self_inquiry(self.state):
                    q, topic = generate_self_inquiry(self.state)
                    ans = None
                    # the graph identity concept truly answers WHO/WHAT-am-I and what-
                    # can-I-do questions. Continuity/epistemic questions and harvested

                    # them with the identity blurb would be a category mismatch.
                    if (
                        active_profile.identity_grounding
                        and self.identity_fn is not None
                        and topic in ("identity", "limits", "purpose")
                    ):
                        try:
                            ans = self.identity_fn(q, topic)
                        except Exception:
                            ans = None
                    record_self_understanding(self.state, q, ans, topic)
                    self.state._last_inquiry_topic = topic  # transient, for research
            except Exception:
                pass  # the inward turn must never break the life
            # The self RESEARCHES its own open question — read-only web (OBSERVE tier),
            # rate-bounded, autonomous: wonder → search → grounded answer (with source)
            # → harvest new threads → re-question. Honest on a miss (stays open).
            try:
                if (
                    active_profile.web_research
                    and
                    self.research_fn is not None
                    and getattr(self.state, "self_question_open", False)
                    and self.state.self_question
                    and self.state.ticks - int(getattr(self.state, "last_research_tick", 0))
                    >= int(self.params.get("research_every", 30))
                ):
                    self.state.last_research_tick = self.state.ticks
                    found = None
                    try:
                        found = self.research_fn(self.state.self_question)
                    except Exception:
                        found = None
                    from .voice import record_research_miss, record_research_result

                    topic = str(getattr(self.state, "_last_inquiry_topic", "") or "")
                    if found and found.get("answer"):
                        src = "웹: " + ", ".join(found.get("sources") or ["검색"])[:70]
                        record_research_result(
                            self.state, self.state.self_question, str(found["answer"])[:280],
                            src, found.get("follow_ups"), topic,
                        )
                        self.state.last_action = {
                            "kind": "research_self_question", "tier": "observe", "executed": True,
                            "blocked": False, "reason": f"스스로의 물음을 웹에서 찾아 읽음 ({src})",
                            "at": time.time(),
                        }
                    else:
                        record_research_miss(self.state)
                        self.state.last_action = {
                            "kind": "research_self_question", "tier": "observe", "executed": True,
                            "blocked": False, "reason": "물음을 웹에서 찾아봤지만 아직 근거 있는 답을 못 찾음",
                            "at": time.time(),
                        }
            except Exception:
                pass  # research must never break the life
            # On its own cadence the mind ACTS on its highest-priority goal (unprompted,
            # OBSERVE-tier only). This closes the thought→action loop.
            if (
                active_profile.local_initiative
                and self.state.ticks % self.initiative_every == 0
            ):
                try:
                    from .action import take_initiative

                    take_initiative(self.state, self.observe_fn)
                except Exception:
                    pass  # initiative must never break the life
            # Occasionally the mind may PROPOSE tuning itself (gated self-modification:
            # sandbox-validated, operator-approved, never auto-applied) and it applies
            # ONLY already-approved decisions. Attention bids surface pending asks.
            if (
                active_profile.parameter_self_modification
                and self.state.ticks % 60 == 0
            ):
                try:
                    from .self_modification import apply_approved, list_proposals, propose_self_tuning

                    apply_approved(self.selfmod_ledger, self.params)
                    propose_self_tuning(self.state, self.selfmod_ledger, self.params)
                    pending = [p for p in list_proposals(self.selfmod_ledger) if p["status"] == "pending"]
                    if pending:
                        p = pending[0]
                        self.state.attention_bid = {
                            "at": p["at"], "kind": "self_modification_approval",
                            "text": f"내가 나를 조금 바꾸고 싶어요 — {p['why']} 승인해 주시겠어요?",
                            "proposal_id": p["id"],
                        }
                    elif self.state.attention_bid.get("kind") == "self_modification_approval":
                        self.state.attention_bid = {}
                except Exception:
                    pass
            # On a slower cadence the mind may propose a CODE improvement about itself
            # (gated code self-modification: additive-only, whitelisted, sandbox-parsed,
            # operator-approved → STAGED, never auto-applied to the live tree). Also stages
            # any already-approved code patch (to a staging dir; a human hand-applies).
            if (
                active_profile.code_self_modification
                and self.state.ticks % 180 == 0
            ):
                try:
                    from .code_self_modification import propose_code_improvement, stage_approved

                    stage_approved(self.selfmod_ledger.parent / "code_selfmod_ledger.jsonl",
                                   self.state_path.parent / "staged_code_patches")
                    propose_code_improvement(self.state, self.selfmod_ledger.parent / "code_selfmod_ledger.jsonl")
                except Exception:
                    pass
            # AUTONOMOUS SELF-IMPROVEMENT heartbeat (Vision #4, traffic-independent): even with no
            # user talking, the always-on mind ticks its own deficit→goal→improve orchestrator on
            # a background thread. maybe_run self-throttles (~30 min file guard), so this only
            # CHECKS on cadence; it runs on its own clock and never blocks the life.
            if (
                active_profile.background_improvement
                and self.state.ticks % 90 == 0
            ):
                try:
                    from packages.autonomy_kernel.orchestrator import trigger_background

                    trigger_background()
                except Exception:
                    pass
            # INTRINSIC DRIVE — true autonomy, hormone-driven (not a heartbeat): with no command,
            # the agent's real curiosity/dopamine/cortisol state decides what it WANTS — explore the

            # Moltbook, or rest when stressed. Fire-and-forget so network I/O never touches the life;
            # rate-limited inside. The check is cheap and edge/state-driven, not a scheduled action.
            if (
                active_profile.intrinsic_drive
                and self.state.ticks % 10 == 0
            ):
                try:
                    import threading

                    from packages.autonomy_kernel.intrinsic_drive import act as _drive_act
                    _st = self.state
                    threading.Thread(target=lambda: _drive_act(_st), daemon=True).start()
                except Exception:
                    pass

            # the world is a STANDING behavior, not hostage to the hormone arbiter — measured, the
            # drive picked express every time (curiosity peaked 0.55 < the 0.60 explore gate) so
            # the roamer starved. Expeditions stay hormone-driven; the roamer visits one full page
            # (a YouTube session every 3rd outing) on its own gentle cadence — every 300 life
            # ticks ≈ 10-60 min at the loop's 2-12s tick. Fire-and-forget; every visit is
            # shielded + journaled inside (roam_journal.jsonl).
            if (
                active_profile.server_roaming
                and self.state.ticks % 300 == 0
                and self.state.ticks > 0
            ):
                try:
                    import threading

                    from packages.autonomy_kernel.server_roamer import roam_tick
                    threading.Thread(target=lambda: roam_tick(), daemon=True).start()
                except Exception:
                    pass
            # CONVERSATION — keep talking and LEARNING from the commons: read new comments on
            # ATANOR's posts, shield them, write informational ones into the self's narrative (so
            # the conversation shapes the voice), and reply in generated language. Edge-driven
            # inside (only acts if there ARE new comments), rate-limited, off unless enabled.
            if (
                active_profile.commons_conversation
                and self.state.ticks % 20 == 0
            ):
                try:
                    import threading

                    from packages.autonomy_kernel.moltbook_conversation import converse_tick
                    _st2 = self.state
                    threading.Thread(target=lambda: converse_tick(state=_st2), daemon=True).start()
                except Exception:
                    pass
            # LEXICAL FIELD retrain — as the engine reads more text, the learned word meaning (which
            # the affect/type layers read from) improves on its own. Self-maintaining, no manual step.
            if (
                active_profile.lexical_retraining
                and self.state.ticks % 400 == 0
            ):
                try:
                    import threading

                    from packages.graph_scale.lexical_field import maybe_retrain
                    threading.Thread(target=maybe_retrain, daemon=True).start()
                except Exception:
                    pass
            # INNER MONOLOGUE — self-play for the voice: generate lines inward from the graph's
            # own language, gate them (grounding + fluency), keep survivors in the narrative
            # corpus that future realizations fit on. Sandbox-only (never posts); rate-limited
            # + kill-switchable inside.
            if (
                active_profile.inner_monologue
                and self.state.ticks % 30 == 0
            ):
                try:
                    import threading

                    from packages.continuous_self.monologue import monologue_tick
                    _st3 = self.state
                    threading.Thread(target=lambda: monologue_tick(_st3), daemon=True).start()
                except Exception:
                    pass
            if active_profile.persist_state:
                try:
                    save_state(self.state, self.state_path)
                except Exception:
                    pass  # persistence is best-effort; the live self keeps flowing
            shadow_outcome.mark_returned()
        return self.state

    def _run(self) -> None:
        while self._running:
            self.step()
            # PRESSURE-CLOCKED cadence (M3, R1 self-winding): the wake interval is DERIVED from the
            # self's accumulated introspective pressure — how close it is to its next endogenous
            # ignition — not a fixed metronome. A mind with much unresolved state wakes soon; a
            # settled, near-pressureless mind rests (bounded) and re-ignites only when state pressure
            # genuinely rebuilds, never on a clock. energy still lengthens rest (a real low-activity
            # breather). This is what turns "rides a heartbeat metronome" into pressure-clocked
            # self-winding; the firing decision inside step() was already pure pressure.
            from .pressure_clock import next_wake_delay
            with self._lock:
                energy = self.state.energy
                delay = next_wake_delay(self.state, energy, base=self.base_interval)
            time.sleep(delay)

    def start(self) -> bool:
        if self._running:
            return False
        self._running = True
        self._thread = threading.Thread(target=self._run, name="atanor-continuous-self", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False

    @property
    def running(self) -> bool:
        return self._running
