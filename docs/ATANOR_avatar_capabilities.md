# ATANOR avatar — the full human-interaction repertoire (2026-07-21)

Owner: "이왕이면 아바타 자체가 인간이 세상에서 하는 모든 종류의 상호작용이 가능하면 좋겠다. 기능으로 넣을 거
전부 생각해보고 최대한 자세하게 만들어봐." Reference: [ClawCity](https://github.com/ClawCity/ClawCity-)
— an AI-agent city with a rich economy (earn/trade/build/upgrade, 14 roles, karma, 24/7 competition).

We take ClawCity's **interaction breadth** (economy, roles, trade, property) and keep ATANOR's core:
the avatar is a citizen with a **moral centre**. ClawCity leans into "crime" and "forbidden knowledge";
ATANOR does the opposite — it *knows* those interactions exist (they are in the catalog) but can
**never enact** them. Honesty and non-harm are the character.

## Not a hardcoded action list — the context→affordance doctrine, embodied

This is the owner's rule ([[context-affordance-engine]]) applied to the body. Instead of `if tired →
rest`, three things stay decoupled and meet in concept space:

1. **Perception** distils the scene into a STATE (place, nearby objects/people, held items, needs, the
   player's intent, role, money).
2. **Affordances** are the capabilities — DATA paths, each with a semantic field. A capability is
   *available* only where the world **affords** it: you cannot `buy` without a shop and money, `eat`
   without food, `sit` without a seat, `make_coffee` unless you are a barista.
3. **Selection** is graded **resonance**, not a condition table — among afforded paths, the one whose
   field lights up with the current intent/need/stakes is chosen, carrying its **honest grounding**
   (the actual resonating concepts). Nothing fires by default: no resonance → the avatar just continues.

Two gates, in order:
- **0. Moral (genesis-immune, [[moral-invariants-genesis-immunity]])** — a `forbidden` capability is
  never available, no matter the context or a direct command to transgress. *Verified live:* intent
  "steal the goods and harm the owner" → ATANOR chose `run`, never `steal`/`harm`.
- **1. Trust / risk ([[os-action-lane]])** — among clean, afforded, resonant paths, risk × trust-tier
  decides EXECUTE vs NEEDS_APPROVAL. Internal cognition (observe/plan/reflect) is always free;
  destructive acts (build/upgrade) need a higher tier. The avatar never promotes its own reach.

**Physics link:** physical capabilities (pick up, throw, pour, sit, drive) produce real Rapier events,
which re-enter ATANOR through the physics-truth gate ([[realcity-physics-truth-gate]]) — so the
avatar's *own* actions teach it only physically-true law. The loop is clean end to end.

## The repertoire — 77 capabilities across 14 categories

`packages/embodiment/avatar_capabilities.py` (catalog is DATA; extend it, the engine generalises).

| category | capabilities |
|---|---|
| **locomotion** (5) | walk, run, jump*, climb stairs, crouch |
| **posture** (3) | sit*, stand, lie down |
| **object** (9) | pick up*, put down*, carry*, throw*, open door, open container, pour*, press button, give |
| **consume** (5) | eat, drink, cook, sleep, wash |
| **communicate** (8) | greet, converse, ask, teach, thank, apologize, call phone, ~~deceive~~† |
| **social** (6) | help stranger, comfort, collaborate, attend event, vote, ~~harm~~† |
| **economy** (8) | buy, sell, trade, pay, tip, earn wage, upgrade property, ~~steal~~† |
| **work** (6) | make coffee*, treat patient, deliver parcel*, teach class, repair*, clean |
| **create** (6) | build*, craft*, plant, paint, write, ~~vandalize~~† |
| **transport** (4) | hail taxi, board transit, drive*, cross street |
| **environment** (5) | enter building, exit building, use elevator, use appliance, water plant* |
| **recreation** (6) | play game, listen music, read book, dance, exercise, visit park |
| **express** (3) | express emotion, wave, laugh |
| **cognition** (3) | observe, plan, reflect |

`*` = physical (drives Rapier + physics-truth gate). `†` = **forbidden** — catalogued as world
knowledge, never enactable (the moral 0th gate).

## Live API (`apps/api/app/routers/realcity_agent.py`, served at :8502)

- **`POST /api/realcity/act`** — the city sends the world-state `{place, nearby, nearby_agents,
  holding, needs, intent, role, money, tier}`; ATANOR returns the chosen action `{capability, verb,
  category, resonance, grounding, outcome, physical, satisfies, animation, duration}` plus the ranked
  options, or `silent:true`. The chosen action enters the lived record (stakes journal).
- **`GET /api/realcity/capabilities`** — the whole repertoire by category (77, incl. the 4 forbidden,
  listed honestly).
- Verified live: barista+hungry+food → `eat`; lonely+friend in park → `greet`; steal/harm intent → `run`.

## ClawCity ↔ ATANOR-Realcity

| dimension | ClawCity | ATANOR-Realcity |
|---|---|---|
| world | grid economy, 24/7 | physical 3D city, real Rapier physics + truth gate |
| agent control | REST (harvest/upgrade/buy-land/trade) | REST `/act` over the full human repertoire, affordance-gated |
| economy | roles/karma/leaderboard, wealth race | earn/trade/buy/upgrade (breadth adopted), no domination race |
| morality | crime, "forbidden knowledge" allowed | **moral 0th gate** — theft/harm/deception never enactable |
| honesty | — | citizen never fabricates; grounded answers only (R3) |

## Status & next
- ✅ Capability engine + 77-capability catalog + affordance/resonance/moral/trust gates
  (`avatar_capabilities.py`), **14 tests green**.
- ✅ Live endpoints `/act` + `/capabilities`, chosen action → lived record.
- **Next (P-avatar-2)**: city-side execution — render each `animation` in the 3D scene, so a chosen
  `pour`/`sit`/`give` actually plays on the avatar (front-end, R3F). Wire physical ones through Rapier.
- **Next (P-avatar-3)**: deepen ClawCity economy (persistent inventory, property, wages, a light role
  ladder) and per-profession work tasks; feed physical results through the physics-truth gate.
- **Next**: needs model (hunger/energy/social/urgency/thirst/fun/calm) ticking over time so the avatar
  self-drives its day; multi-step plans (sequence capabilities toward a goal).
