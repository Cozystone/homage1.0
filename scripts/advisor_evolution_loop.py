# -*- coding: utf-8 -*-
"""Continuous advisor evolution loop — ATANOR keeps consulting frontier minds to seek advice, learn,
be evaluated, and evolve. Rotates real advisor CLIs, mines its OWN worst weakness each round, asks,
routes the reply through the constitution (injection scan + patch intake), and journals.

Advisors are REAL coding/reasoning CLIs present on this box: ollama (local dolphin3, free/unlimited),
codex, claude, and openclaw — whose 'main' agent is backed by openai-codex/gpt-5.4, a real GPT-5.4
advisor. Paid CLIs are OPT-IN and rate-limited so an overnight run can't surprise-bill; ollama runs
freely.

Five round types share the paid-advisor cost gate (rarest modulo first, so all fire over a night):
(a) weakness consults (mine → ask), (b) every 5th: COMPREHENSIVE GPT-5.4 code audit (flaws ATANOR
missed), (c) every 7th: WORLD-MENTOR (curriculum in, ATANOR self-learns facts via its own web),
(d) every 3rd: DIALOGUE-COACH (GPT watches the live two-ATANOR transcript like game film, picks
fine-grained structural deficiencies, seeds practice topics the dialogue adopts as curiosity),
(e) every 11th: CHINESE-ROOM close coaching (sincere GPT<->ATANOR exchange on transcending the
context-deficiency critique; ATANOR answers with real demonstrations from its own organs).

  python scripts/advisor_evolution_loop.py                 # ollama only (free), forever
  python scripts/advisor_evolution_loop.py --advisors ollama,openclaw,codex --paid-every-min 15
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.advisor_loop.advisor_session import ask_cli
from packages.advisor_loop.chinese_room_coach import run_session as chinese_room_session
from packages.advisor_loop.comprehensive_review import run_review
from packages.advisor_loop.dialogue_coach import coach_round
from packages.advisor_loop.patch_intake import intake
from packages.advisor_loop.question_miner import mine
from packages.advisor_loop.world_mentor import run_round as world_round
from packages.self_repair.repair_cycle import run_cycle as repair_cycle

LOG = REPO / "data" / "advisor_loop" / "evolution.log"
FREE = {"ollama"}                          # unlimited; paid advisors gated by --paid-every-min
# core files GPT-5.4 comprehensively audits, one per review round (rotated)
REVIEW_FILES = ["packages/realizer_struct/frame_realizer.py",
                "packages/situation_model/state_tracker.py",
                "packages/brain_link/web_knowledge.py",
                "packages/code_reason/code_situation.py"]
REVIEW_EVERY = 5                           # every 5th round is a comprehensive GPT-5.4 code audit
WORLD_EVERY = 7                            # every 7th round GPT-5.4 mentors ATANOR's WORLD MODEL
COACH_EVERY = 3                            # every 3rd round GPT-5.4 watches the LIVE dialogue (game film)
ROOM_EVERY = 11                            # every 11th round: Chinese-room close coaching session
REPAIR_EVERY = 13                          # every 13th round: CLOSE THE LOOP — actually fix something


def _log(line: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%m-%d %H:%M:%S')}  {line}\n")


def main() -> int:
    # default rotation: free local ollama + GPT-5.4 (openclaw) + codex, the paid ones cost-gated.
    adv = (sys.argv[sys.argv.index("--advisors") + 1].split(",")
           if "--advisors" in sys.argv else ["ollama", "openclaw", "codex"])
    paid_every = (int(sys.argv[sys.argv.index("--paid-every-min") + 1]) * 60
                  if "--paid-every-min" in sys.argv else 900)
    _log(f"=== evolution loop start: advisors={adv}, paid gate={paid_every//60}min ===")
    last_paid = 0.0
    ri = 0

    def _room(i: int) -> None:
        """Chinese-room close coaching: sincere GPT<->ATANOR exchange (real demonstrations)."""
        s = chinese_room_session(rounds=2, advisor="openclaw", now_utc=time.time())
        head = (s["exchanges"][-1]["coach"].strip().splitlines() or [""])[0][:90]
        _log(f"[openclaw] CHINESE-ROOM coaching x{s['rounds']} | coach: {head}")

    def _world(i: int) -> None:
        """World mentor: ATANOR retrospects its gaps, gets a CURRICULUM, self-learns via web."""
        w = world_round(learn_first=3, advisor="openclaw", now_utc=time.time(), harvest=True)
        gaps = ", ".join(w["gaps"]["foundational_gaps"][:5])
        learned = ", ".join(r["concept"] for r in w["learned"])
        head = (w["curriculum"].strip().splitlines() or [""])[0][:80]
        _log(f"[openclaw] WORLD-MENTOR gaps=[{gaps}] -> self-learned=[{learned}] | curriculum: {head}")
        try:
            from packages.continuous_self.stakes import journal_tick
            journal_tick({"round": "world-mentor"}, did="learn")   # causal record: learning's effect
        except Exception:
            pass

    def _review(i: int) -> None:
        """Comprehensive code audit: broad critique + flaws ATANOR missed."""
        src = REVIEW_FILES[(i // REVIEW_EVERY) % len(REVIEW_FILES)]
        r = run_review(advisor="openclaw", source_rel=src, now_utc=time.time())
        first = (r["critique"].strip().splitlines() or [""])[0][:90]
        _log(f"[openclaw] COMPREHENSIVE review of {src} -> intake={r['intake_status']} "
             f"paths={r['intake_paths']} | critique: {first}")

    def _coach(i: int) -> None:
        """Dialogue game film: GPT watches the LIVE two-ATANOR transcript, picks fine-grained
        deficiencies, seeds practice topics the running dialogue adopts as its own curiosity."""
        c = coach_round(advisor="openclaw", now_utc=time.time())
        if c.get("skipped"):
            _log(f"[openclaw] dialogue-coach skipped: {c['skipped']}")
            return
        head = (c["critique"].strip().splitlines() or [""])[0][:90]
        _log(f"[openclaw] DIALOGUE-COACH topics={c['topics_seeded']} | {head}")

    def _repair(i: int) -> None:
        """The CLOSED loop: take the most-repeated repairable defect the advisors keep reporting,
        get a real patch, stage it, judge it by tests + battery, keep or revert. The step that used
        to require a human reading logs in the morning."""
        r = repair_cycle(advisor="openclaw", now_utc=time.time())
        _log(f"[openclaw] SELF-REPAIR {r['outcome']}: {r.get('detail','')[:80]}"
             + (f" | {r.get('path','')}" if r.get("path") else "")
             + (f" | new_failures={r['new_failures']}" if r.get("new_failures") else ""))
        try:
            from packages.continuous_self.stakes import journal_tick
            journal_tick({"round": "self-repair", "outcome": r.get("outcome")}, did="repair")
        except Exception:
            pass

    # special paid rounds, RAREST modulo first so every kind fires over a night
    SPECIALS = [(REPAIR_EVERY, "self-repair", _repair), (ROOM_EVERY, "chinese-room", _room),
                (WORLD_EVERY, "world-mentor", _world), (REVIEW_EVERY, "review", _review),
                (COACH_EVERY, "dialogue-coach", _coach)]

    while True:
        if "openclaw" in adv and ri > 0 and time.time() - last_paid >= paid_every:
            fired = False
            for every, name, fn in SPECIALS:
                if ri % every == 0:
                    last_paid = time.time()
                    try:
                        fn(ri)
                    except Exception as e:
                        _log(f"[openclaw] {name} round failed: {type(e).__name__}")
                    fired = True
                    break
            if fired:
                ri += 1
                time.sleep(90)
                continue
        # STAKES (plan S1): unfaced self-defects shrink the freedom to wander — consult pacing
        # stretches under coherence debt, and the budget is journaled with the round.
        try:
            from packages.continuous_self.stakes import discretionary_budget
            _budget = discretionary_budget()
        except Exception:
            _budget = 1.0
        qs = mine(max_questions=5)
        if not qs:
            _log("no residual weaknesses to consult on — sleeping 30m")
            time.sleep(1800)
            continue
        q = qs[ri % len(qs)]                              # rotate through top weaknesses
        advisor = adv[ri % len(adv)]
        ri += 1
        if advisor not in FREE:
            if time.time() - last_paid < paid_every:      # cost gate for paid advisors
                advisor = "ollama"
            else:
                last_paid = time.time()
        try:
            ex = ask_cli(advisor, q.prompt(), timeout_s=180)
        except Exception as e:
            _log(f"[{advisor}] unavailable on '{q.topic}': {type(e).__name__}")
            time.sleep(60)
            continue
        cand = intake(advisor, ex.reply, summary=f"advice on {q.topic}")
        _log(f"[{advisor}] asked '{q.topic}' (residual {q.residual:.3f}) -> "
             f"intake={cand.status} injection={ex.injection_findings}"
             + (f" reason={cand.reason}" if cand.reason else ""))
        time.sleep(90 / max(0.3, _budget))                 # coherence debt slows free wandering
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
