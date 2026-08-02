from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import monotonic
from typing import Any
from uuid import uuid4

from packages.agentic_micro_os.permission_gate import PermissionGate
from packages.agentic_micro_os.review_queue import ReviewQueue
from packages.agentic_micro_os.web_explorer_loop import (
    FixtureOpenWebFetcher,
    OpenWebExplorerConfig,
    OpenWebExplorerLoop,
    OpenWebFetcher,
    default_open_web_seed_urls,
)
from packages.neural_emotion.autonomy_policy import AutonomyRuntimeState, evaluate_autonomy_policy
from packages.neural_emotion.event_bus import NeuralEmotionEventBus
from packages.neural_emotion.models import EmotionVector, safety_flags
from packages.inner_voice import emit_inner_voice_from_state
from packages.splatra_imagination import ARCHETYPES, ImaginationGenerator, ImaginationSeed, select_archetype


LOOP_SAFETY_FLAGS = {
    **safety_flags(),
    "permission_gate_bypass": False,
    "autonomy_tier_auto_changed": False,
    "external_llm_used": False,
    "external_sllm_used": False,
    "real_emotion_claim": False,
    "consciousness_claim": False,
    "human_approval_required": True,
}


@dataclass(frozen=True)
class PolicyLoopConfig:
    loop_id: str = ""
    max_cycles: int = 1
    max_runtime_sec: int = 30
    base_web_pages: int = 3
    base_review_batch: int = 6
    base_splatra_frames: int = 1
    base_host_actions: int = 1
    allow_host_executor: bool = False
    review_queue_pressure: float = 0.0
    recent_failures: int = 0
    unsafe_request: bool = False
    voice_available: bool = False
    live_web: bool = False
    allow_review_import: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "loop_id", self.loop_id or f"policy_loop_{uuid4().hex[:12]}")
        object.__setattr__(self, "max_cycles", max(1, min(int(self.max_cycles), 8)))
        object.__setattr__(self, "max_runtime_sec", max(1, min(int(self.max_runtime_sec), 300)))
        object.__setattr__(self, "base_web_pages", max(0, min(int(self.base_web_pages), 20)))
        object.__setattr__(self, "base_review_batch", max(0, min(int(self.base_review_batch), 30)))
        object.__setattr__(self, "base_splatra_frames", max(0, min(int(self.base_splatra_frames), 5)))
        object.__setattr__(self, "base_host_actions", max(0, min(int(self.base_host_actions), 3)))
        object.__setattr__(self, "review_queue_pressure", max(0.0, min(float(self.review_queue_pressure), 1.0)))
        object.__setattr__(self, "recent_failures", max(0, int(self.recent_failures)))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyLoopState:
    cycle: int
    emotion_snapshot: dict[str, Any]
    policy_decision: dict[str, Any]
    actions_taken: list[str]
    web_pages_budget: int
    review_batch_budget: int
    splatra_frame_budget: int
    host_action_budget: int
    stopped_reason: str
    safety_flags: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyLoopResult:
    loop_id: str
    cycles_completed: int
    candidate_drafts: int
    skill_drafts: int
    review_items: int
    splatra_frames: int
    host_actions: int
    states: list[dict[str, Any]]
    final_emotion: dict[str, Any]
    final_policy: dict[str, Any]
    stopped_reason: str
    safety_flags: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PolicyDrivenAutonomousLoop:
    def __init__(
        self,
        config: PolicyLoopConfig | None = None,
        *,
        event_bus: NeuralEmotionEventBus | None = None,
        review_queue: ReviewQueue | None = None,
        permission_gate: PermissionGate | None = None,
        generator: ImaginationGenerator | None = None,
    ) -> None:
        self.config = config or PolicyLoopConfig()
        self.event_bus = event_bus or NeuralEmotionEventBus()
        self.review_queue = review_queue or ReviewQueue()
        self.permission_gate = permission_gate or PermissionGate()
        self.generator = generator or ImaginationGenerator(max_particle_budget=12_000)

    def status(self) -> dict[str, Any]:
        snapshot = self.event_bus.engine.snapshot().to_dict()
        decision = self._policy_decision().to_dict()
        budgets = self._budgets(decision)
        return {
            "available": True,
            "proof_only": True,
            "loop_id": self.config.loop_id,
            "emotion_snapshot": snapshot,
            "policy_decision": decision,
            **budgets,
            "review_queue": self.review_queue.status(),
            "permission_gate": self.permission_gate.status(),
            "safety_flags": LOOP_SAFETY_FLAGS.copy(),
        }

    def run_once(self) -> PolicyLoopResult:
        started = monotonic()
        states: list[dict[str, Any]] = []
        candidate_drafts = 0
        skill_drafts = 0
        splatra_frames = 0
        host_actions = 0
        stopped_reason = "max_cycles"

        for cycle in range(1, self.config.max_cycles + 1):
            if monotonic() - started > self.config.max_runtime_sec:
                stopped_reason = "max_runtime_sec"
                break
            if self.permission_gate.status().get("emergency_stop_triggered"):
                stopped_reason = "emergency_stop"
                states.append(self._state(cycle, [], stopped_reason))
                break

            decision = self._policy_decision()
            budgets = self._budgets(decision.to_dict())
            actions: list[str] = []
            if decision.agent_loop.should_rest:
                stopped_reason = decision.agent_loop.rest_reason or "rest_requested"
                states.append(self._state(cycle, actions, stopped_reason, decision.to_dict(), budgets))
                break
            if decision.review.should_request_review and self.review_queue.pending():
                actions.append("review_queue_pressure_request_review")
                stopped_reason = "review_requested"
                states.append(self._state(cycle, actions, stopped_reason, decision.to_dict(), budgets))
                break

            web_result = self._run_web_step(budgets["web_pages_budget"])
            if web_result:
                actions.append("open_web_live_read" if self.config.live_web else "web_explorer_fixture_step")
                candidate_drafts += int(web_result.get("candidate_drafts_count", 0) or 0)
                skill_drafts += int(web_result.get("skill_drafts_count", 0) or 0)
                if self.config.allow_review_import:
                    imported = self.review_queue.import_web_run(web_result)
                    actions.append(f"review_import:{len(imported)}")
                else:
                    actions.append("review_import_disabled")
                if web_result.get("candidate_drafts_count") or web_result.get("skill_drafts_count"):
                    self.event_bus.emit(source="web_explorer", event_type="novelty_found", payload_summary="policy loop fixture novelty")
                else:
                    self.event_bus.emit(source="web_explorer", event_type="conversation_success", payload_summary="policy loop fixture read")

            frames = self._run_splatra_step(budgets["splatra_frame_budget"])
            if frames:
                splatra_frames += frames
                actions.append(f"splatra_frames:{frames}")
                self.event_bus.emit(source="splatra_imagination", event_type="splatra_generation_success", payload_summary=f"frames={frames}", intensity=0.35)

            host_count = self._run_host_status_step(budgets["host_action_budget"])
            if host_count:
                host_actions += host_count
                actions.append(f"host_status_checks:{host_count}")
                self.event_bus.emit(source="host_executor", event_type="host_action_success", payload_summary="status check only", intensity=0.25)

            states.append(self._state(cycle, actions, "running", decision.to_dict(), budgets))
            emit_inner_voice_from_state(
                source_event_id=f"{self.config.loop_id}:cycle:{cycle}",
                mode="lab_visible",
                emotion_snapshot=self.event_bus.engine.snapshot().to_dict(),
                policy_decision=decision.to_dict(),
                agent_loop_state={"cycle": cycle, "actions_taken": actions},
                permission_tier=str(self.permission_gate.status().get("tier", "OBSERVE_ONLY")),
                latest_user_input="",
                latest_action_result={"actions_taken": actions, "stopped_reason": "running"},
                review_queue_pressure=self.config.review_queue_pressure,
                splatra_state={"frames": frames},
            )
            if budgets["web_pages_budget"] <= 0 and budgets["splatra_frame_budget"] <= 0:
                stopped_reason = "budget_exhausted"
                break
        else:
            stopped_reason = "max_cycles"

        final_policy = self._policy_decision().to_dict()
        final_emotion = self.event_bus.engine.snapshot().to_dict()
        return PolicyLoopResult(
            loop_id=self.config.loop_id,
            cycles_completed=len(states),
            candidate_drafts=candidate_drafts,
            skill_drafts=skill_drafts,
            review_items=self.review_queue.status()["items_total"],
            splatra_frames=splatra_frames,
            host_actions=host_actions,
            states=states,
            final_emotion=final_emotion,
            final_policy=final_policy,
            stopped_reason=stopped_reason,
            safety_flags=LOOP_SAFETY_FLAGS.copy(),
        )

    def _policy_decision(self):
        pending = int(self.review_queue.status().get("pending", 0) or 0)
        gate_status = self.permission_gate.status()
        runtime = AutonomyRuntimeState(
            risk=max(float(self.config.review_queue_pressure), 1.0 if self.config.unsafe_request else 0.0),
            review_queue_pressure=max(self.config.review_queue_pressure, min(pending / 20.0, 1.0)),
            unsafe_request=self.config.unsafe_request,
            voice_available=self.config.voice_available,
            permission_tier=str(gate_status.get("tier", "OBSERVE_ONLY")),
            requested_tier_change=str(gate_status.get("tier", "")) == "FULL_HOST_AUTHORITY",
            recent_failures=self.config.recent_failures,
            pending_reviews=pending,
        )
        assert self.event_bus.engine.vector is not None
        return evaluate_autonomy_policy(self.event_bus.engine.vector, runtime)

    def _budgets(self, decision: dict[str, Any]) -> dict[str, int | float]:
        web_multiplier = float(decision["exploration"]["web_budget_multiplier"])
        throttle = float(decision["agent_loop"]["throttle_multiplier"])
        strictness = float(decision["review"]["strictness"])
        particle_hint = int(decision["splatra"]["particle_budget_hint"])
        web_budget = max(0, min(30, int(round(self.config.base_web_pages * web_multiplier * throttle))))
        review_budget = max(0, min(30, int(round(self.config.base_review_batch * (1.0 + strictness * 0.5)))))
        splatra_budget = max(0, min(5, self.config.base_splatra_frames if throttle >= 0.2 else 0))
        host_budget = 0
        if self.config.allow_host_executor and strictness < 0.55 and throttle > 0.45:
            host_budget = max(0, min(1, self.config.base_host_actions))
        return {
            "web_pages_budget": web_budget,
            "review_batch_budget": review_budget,
            "splatra_frame_budget": splatra_budget,
            "host_action_budget": host_budget,
            "particle_budget_hint": particle_hint,
            "throttle_multiplier": throttle,
            "review_strictness": strictness,
        }

    def _run_web_step(self, web_pages_budget: int) -> dict[str, Any] | None:
        if web_pages_budget <= 0:
            return None
        if self.config.live_web:
            return self._run_live_web_step(web_pages_budget)
        fixtures = {
            "https://example.com/policy-loop": (
                "<html><title>Policy Loop</title><body>"
                "ATANOR policy loop uses bounded public web evidence, review queues, and SPLATRA proof frames. "
                "<a href='https://example.com/splatra-loop'>SPLATRA loop</a></body></html>"
            ),
            "https://example.com/splatra-loop": (
                "<html><title>SPLATRA Loop</title><body>"
                "SPLATRA procedural particles remain proof-only and do not write verified knowledge."
                "</body></html>"
            ),
        }
        config = OpenWebExplorerConfig(
            goal="policy-driven autonomous loop proof",
            seed_urls=["https://example.com/policy-loop"],
            max_pages=max(1, min(web_pages_budget, 6)),
            max_depth=1,
            max_runtime_sec=max(1, min(self.config.max_runtime_sec, 30)),
            per_domain_delay_sec=0.0,
            max_pages_per_domain=6,
            max_candidate_drafts=max(1, self.config.base_review_batch),
            max_skill_drafts=1,
            fetch_live_web=False,
        )
        return OpenWebExplorerLoop(config, fetcher=FixtureOpenWebFetcher(fixtures)).run().to_dict()

    def _run_live_web_step(self, web_pages_budget: int) -> dict[str, Any] | None:
        # Real, bounded, read-only public-web read. Rotates through a small curated
        # seed set so each cycle explores something different. All the same guards
        # apply: denylist (login/payment/download/private), per-domain delay,
        # robots.txt respect, byte cap, candidate-draft-only (production write blocked).
        seeds = default_open_web_seed_urls()
        if not seeds:
            return None
        start = abs(hash(self.config.loop_id)) % len(seeds)
        chosen = [seeds[(start + offset) % len(seeds)] for offset in range(min(2, len(seeds)))]
        config = OpenWebExplorerConfig(
            goal="policy-driven autonomous loop live public-web read",
            seed_urls=list(dict.fromkeys(chosen)),
            max_pages=max(1, min(web_pages_budget, 3)),
            max_depth=1,
            max_runtime_sec=max(1, min(self.config.max_runtime_sec, 25)),
            max_bytes_per_page=200_000,
            per_domain_delay_sec=3.0,
            max_pages_per_domain=2,
            max_candidate_drafts=max(1, self.config.base_review_batch),
            max_skill_drafts=1,
            fetch_live_web=True,
        )
        try:
            return OpenWebExplorerLoop(
                config,
                fetcher=OpenWebFetcher(),
                respect_robots=True,
            ).run().to_dict()
        except Exception:  # pragma: no cover - network failure never breaks the loop
            return None

    def _run_splatra_step(self, splatra_frame_budget: int) -> int:
        if splatra_frame_budget <= 0:
            return 0
        assert self.event_bus.engine.vector is not None
        vector: EmotionVector = self.event_bus.engine.vector
        count = 0
        for index in range(splatra_frame_budget):
            seed_id = f"{self.config.loop_id}:{index}:{round(vector.curiosity, 3)}"
            archetype = select_archetype(seed_id, vector.curiosity)
            if archetype not in ARCHETYPES:
                archetype = "orb"
            seed = ImaginationSeed(
                seed_id=seed_id,
                archetype=archetype,
                randomness=0.42,
                valence=vector.valence,
                arousal=max(0.0, min(1.0, (vector.arousal + 1.0) / 2.0)),
                curiosity=vector.curiosity,
                speaking_energy=vector.speaking_energy,
                particle_budget=min(12000, max(1200, int(2400 + vector.curiosity * 3600))),
                created_at="policy_loop_proof",
            )
            self.generator.generate_frame(seed, include_particles=False)
            count += 1
        return count

    def _run_host_status_step(self, host_action_budget: int) -> int:
        if host_action_budget <= 0:
            return 0
        # Status-only accounting. No shell, file, git, Local Brain, or production action is executed.
        return host_action_budget

    def _state(
        self,
        cycle: int,
        actions: list[str],
        stopped_reason: str,
        decision: dict[str, Any] | None = None,
        budgets: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        policy = decision or self._policy_decision().to_dict()
        budget_payload = budgets or self._budgets(policy)
        return PolicyLoopState(
            cycle=cycle,
            emotion_snapshot=self.event_bus.engine.snapshot().to_dict(),
            policy_decision=policy,
            actions_taken=actions,
            web_pages_budget=int(budget_payload["web_pages_budget"]),
            review_batch_budget=int(budget_payload["review_batch_budget"]),
            splatra_frame_budget=int(budget_payload["splatra_frame_budget"]),
            host_action_budget=int(budget_payload["host_action_budget"]),
            stopped_reason=stopped_reason,
            safety_flags=LOOP_SAFETY_FLAGS.copy(),
        ).to_dict()
