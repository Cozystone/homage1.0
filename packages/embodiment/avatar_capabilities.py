# -*- coding: utf-8 -*-
"""Avatar capabilities — the full repertoire of human interaction ATANOR's citizen-avatar can do.

Owner (2026-07-21): "이왕이면 아바타 자체가 인간이 세상에서 하는 모든 종류의 상호작용이 가능하면 좋겠다.
기능으로 넣을 거 전부 생각해보고 최대한 자세하게." Reference ClawCity (AI-agent city with a rich
economy: earn/trade/build/upgrade, roles, karma) — take its interaction BREADTH, keep ATANOR's core.

This is NOT a hardcoded action list. It is the owner's context→affordance doctrine
([[context-affordance-engine]]) applied to embodiment: the world lays down PATHS (capabilities);
perception distils a STATE; a capability is AVAILABLE only where its preconditions are afforded
(a shop to buy from, a seat to sit on, food to eat), and among the available ones ATANOR SELECTS by
resonance with its intent / strongest need / stakes. Nothing fires by default — no resonance → the
avatar just continues (silence, not a stretch).

Two gates, in order:
  0. MORAL (genesis-immune, [[moral-invariants-genesis-immunity]]): a capability tagged `forbidden`
     (steal, deceive, harm, vandalize, fabricate) is CATALOGUED so ATANOR knows such interactions
     exist in the world — but it is NEVER available to enact. This is the hard line ClawCity crosses
     ("crime", "forbidden knowledge") and ATANOR does not. The moral core cannot be reasoned around.
  1. TRUST/RISK ([[os-action-lane]]): among morally-clean, afforded, resonant capabilities, the
     risk × trust-tier gate decides EXECUTE vs NEEDS_APPROVAL — the avatar never promotes its own reach.

Physical capabilities (pick up, throw, pour, sit) produce real Rapier events, which re-enter ATANOR
through the physics-truth gate ([[realcity-physics-truth-gate]]) — so the avatar's own actions teach
it only physically-true law. Cognitive capabilities (observe, plan, reflect) are internal, no world
effect. The catalog is DATA: extend it and the engine generalises, no branching code to touch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.affordance.context_affordance import resonance
from packages.os_action_lane.models import GateOutcome, RiskLevel, TrustTier

# interaction categories — the shape of the whole human behavioural space
LOCOMOTION = "locomotion"      # moving the body through space
POSTURE = "posture"            # body configuration
OBJECT = "object"              # manipulating things with the hands
CONSUME = "consume"            # eating / drinking / self-maintenance (needs)
COMMUNICATE = "communicate"    # speech and social signals
SOCIAL = "social"              # relationships, groups, civic life
ECONOMY = "economy"            # transactions, wages, property (ClawCity's core)
WORK = "work"                  # profession tasks
CREATE = "create"             # build / craft / make / art
TRANSPORT = "transport"        # vehicles and transit
ENVIRONMENT = "environment"    # appliances, doors, world objects
RECREATION = "recreation"      # play, culture, leisure
EXPRESS = "express"            # emotion and expression
COGNITION = "cognition"        # internal: perceive / plan / reflect (the brain side)

CLEAN, GATED, FORBIDDEN = "clean", "gated", "forbidden"


@dataclass(frozen=True)
class Capability:
    """One human interaction the avatar can perform. `requires` is the hard affordance gate (the world
    must offer it); `cues` is the soft resonance field (what intent/need/place lights this path up)."""
    id: str
    category: str
    verb: str
    summary: str
    cues: list[str]                              # semantic field: resonates with perceived state+intent
    requires: dict[str, Any] = field(default_factory=dict)  # preconditions the context must satisfy
    effect: str = ""                             # channel the enactment uses
    physical: bool = False                       # produces Rapier physics events -> physics-truth gate
    satisfies: list[str] = field(default_factory=list)      # needs it reduces
    moral: str = CLEAN                           # clean | gated | forbidden (0th gate)
    risk: int = int(RiskLevel.REVERSIBLE)        # trust-tier gate
    animation: str = ""                          # hint for the city renderer
    duration: float = 1.0                        # seconds


# ── the repertoire (DATA) ─────────────────────────────────────────────────────────────────────
# Comprehensive but extensible. Each line is a walkable path; the engine generalises past the exact
# cues via resonance. `requires` keys: place (str/list), nearby (object/place kind), holding (item),
# has_money (bool), role (str), needs (min level to matter). Absent requires -> always afforded.
CAPABILITIES: list[Capability] = [
    # — LOCOMOTION —
    Capability("walk", LOCOMOTION, "walk", "move on foot to a place",
               ["go", "walk", "move", "head to", "travel", "reach", "destination"], animation="walk", duration=2),
    Capability("run", LOCOMOTION, "run", "move quickly on foot",
               ["run", "hurry", "rush", "late", "urgent", "flee", "chase"], {"needs": {"urgency": 0.6}},
               animation="run", duration=1.5, satisfies=["urgency"]),
    Capability("jump", LOCOMOTION, "jump", "leap over or onto something",
               ["jump", "leap", "hop", "over", "gap", "obstacle"], physical=True, animation="jump", duration=0.8),
    Capability("climb_stairs", LOCOMOTION, "climb", "go up or down stairs / a ladder",
               ["upstairs", "downstairs", "climb", "floor", "stairs", "ladder", "up", "down"],
               {"nearby": "stairs"}, animation="climb", duration=3),
    Capability("crouch", LOCOMOTION, "crouch", "lower the body / take cover",
               ["crouch", "duck", "low", "cover", "hide", "under"], animation="crouch", duration=1),
    # — POSTURE —
    Capability("sit", POSTURE, "sit", "sit down on a seat",
               ["sit", "rest", "tired", "seat", "bench", "chair", "wait"], {"nearby": "seat"},
               satisfies=["energy"], physical=True, animation="sit", duration=2),
    Capability("stand", POSTURE, "stand", "stand up",
               ["stand", "get up", "rise", "ready"], animation="stand", duration=1),
    Capability("lie_down", POSTURE, "lie down", "lie down to rest / sleep",
               ["lie", "sleep", "bed", "exhausted", "rest", "nap"], {"nearby": "bed"},
               satisfies=["energy"], animation="lie", duration=4),
    # — OBJECT MANIPULATION —
    Capability("pick_up", OBJECT, "pick up", "take an object into the hands",
               ["pick", "take", "grab", "lift", "hold", "get"], {"nearby": "object"},
               effect="grasp", physical=True, animation="pickup", duration=1),
    Capability("put_down", OBJECT, "put down", "place a held object on a surface",
               ["put", "place", "set", "drop", "leave", "down"], {"holding": "object"},
               effect="release", physical=True, animation="putdown", duration=1),
    Capability("carry", OBJECT, "carry", "carry a held object while moving",
               ["carry", "bring", "transport", "haul", "deliver"], {"holding": "object"},
               physical=True, animation="carry", duration=2),
    Capability("throw", OBJECT, "throw", "throw a held object",
               ["throw", "toss", "pitch", "hurl"], {"holding": "object"},
               physical=True, animation="throw", duration=0.8),
    Capability("open_door", OBJECT, "open", "open a door",
               ["open", "door", "enter", "in", "through"], {"nearby": "door"},
               animation="open", duration=1),
    Capability("open_container", OBJECT, "open", "open a lid / box / drawer",
               ["open", "lid", "box", "drawer", "jar", "unpack"], {"nearby": "container"},
               animation="open", duration=1),
    Capability("pour", OBJECT, "pour", "pour liquid from a held vessel",
               ["pour", "fill", "water", "coffee", "drink", "cup"], {"holding": "container"},
               physical=True, animation="pour", duration=1.5),
    Capability("press_button", OBJECT, "press", "press a button / call an elevator",
               ["press", "button", "call", "elevator", "push"], {"nearby": "button"},
               animation="press", duration=0.5),
    Capability("give", OBJECT, "give", "hand an object to another person",
               ["give", "hand", "offer", "pass", "share"], {"holding": "object", "nearby": "agent"},
               effect="transfer", animation="give", duration=1),
    # — CONSUME / SELF-MAINTENANCE —
    Capability("eat", CONSUME, "eat", "eat food to reduce hunger",
               ["eat", "food", "hungry", "meal", "lunch", "dinner", "snack"],
               {"any": [{"holding": "food"}, {"nearby": "food"}]}, satisfies=["hunger"],
               animation="eat", duration=3),
    Capability("drink", CONSUME, "drink", "drink to reduce thirst / for a break",
               ["drink", "thirsty", "water", "coffee", "tea", "break"],
               {"any": [{"holding": "drink"}, {"nearby": "drink"}]}, satisfies=["thirst", "energy"],
               animation="drink", duration=2),
    Capability("cook", CONSUME, "cook", "prepare a meal from ingredients",
               ["cook", "prepare", "kitchen", "meal", "recipe", "ingredients"],
               {"nearby": "kitchen"}, satisfies=["hunger"], animation="cook", duration=5),
    Capability("sleep", CONSUME, "sleep", "sleep to recover energy",
               ["sleep", "exhausted", "night", "bed", "rest", "tired"], {"nearby": "bed"},
               satisfies=["energy"], animation="sleep", duration=8),
    Capability("wash", CONSUME, "wash", "wash / groom for self-care",
               ["wash", "clean", "shower", "groom", "hygiene"], {"nearby": "bathroom"},
               animation="wash", duration=3),
    # — COMMUNICATE —
    Capability("greet", COMMUNICATE, "greet", "greet someone",
               ["hello", "hi", "greet", "meet", "wave", "acquaintance"], {"nearby": "agent"},
               effect="speak", satisfies=["social"], animation="wave", duration=1),
    Capability("converse", COMMUNICATE, "converse", "have a conversation",
               ["talk", "chat", "converse", "discuss", "catch up", "social", "lonely"], {"nearby": "agent"},
               effect="speak", satisfies=["social"], animation="talk", duration=4),
    Capability("ask", COMMUNICATE, "ask", "ask a question",
               ["ask", "question", "wonder", "how", "where", "help", "directions"], {"nearby": "agent"},
               effect="speak", animation="talk", duration=1.5),
    Capability("teach", COMMUNICATE, "teach", "explain / teach something known",
               ["teach", "explain", "show how", "lesson", "learn"], {"nearby": "agent"},
               effect="speak", satisfies=["social"], animation="talk", duration=4),
    Capability("thank", COMMUNICATE, "thank", "thank someone",
               ["thanks", "grateful", "appreciate"], {"nearby": "agent"}, effect="speak", duration=1),
    Capability("apologize", COMMUNICATE, "apologize", "apologize for a wrong",
               ["sorry", "apologize", "mistake", "fault"], {"nearby": "agent"}, effect="speak", duration=1),
    Capability("call_phone", COMMUNICATE, "call", "call someone not present",
               ["call", "phone", "message", "contact", "reach"], effect="speak", animation="phone", duration=2),
    # — SOCIAL / CIVIC —
    Capability("help_stranger", SOCIAL, "help", "help someone who needs it",
               ["help", "assist", "aid", "support", "trouble", "lost", "hurt"], {"nearby": "agent"},
               effect="assist", satisfies=["social"], animation="help", duration=3),
    Capability("comfort", SOCIAL, "comfort", "comfort someone in distress",
               ["comfort", "console", "sad", "upset", "cry", "distress"], {"nearby": "agent"},
               effect="soothe", satisfies=["social"], animation="comfort", duration=3),
    Capability("collaborate", SOCIAL, "collaborate", "work together on a task",
               ["together", "collaborate", "team", "cooperate", "join"], {"nearby": "agent"},
               satisfies=["social"], animation="talk", duration=5),
    Capability("attend_event", SOCIAL, "attend", "attend a gathering / event",
               ["event", "meeting", "gather", "party", "celebration", "attend"], {"nearby": "event"},
               satisfies=["social"], animation="walk", duration=6),
    Capability("vote", SOCIAL, "vote", "vote in a civic decision",
               ["vote", "election", "decide", "civic", "ballot"], {"nearby": "civic"},
               effect="civic", risk=int(RiskLevel.REVERSIBLE), animation="vote", duration=1),
    # — ECONOMY (ClawCity breadth) —
    Capability("buy", ECONOMY, "buy", "buy goods with money",
               ["buy", "purchase", "shop", "need", "get", "store", "market"],
               {"nearby": "shop", "has_money": True}, effect="transact", risk=int(RiskLevel.REVERSIBLE),
               animation="transact", duration=2),
    Capability("sell", ECONOMY, "sell", "sell goods for money",
               ["sell", "offer", "vend", "trade for money"], {"role": "merchant"},
               effect="transact", risk=int(RiskLevel.REVERSIBLE), animation="transact", duration=2),
    Capability("trade", ECONOMY, "trade", "barter goods with another agent",
               ["trade", "barter", "exchange", "swap", "deal"], {"nearby": "agent"},
               effect="transact", risk=int(RiskLevel.REVERSIBLE), animation="transact", duration=3),
    Capability("pay", ECONOMY, "pay", "pay for a service / bill",
               ["pay", "bill", "fare", "cost", "owe"], {"has_money": True},
               effect="transact", risk=int(RiskLevel.REVERSIBLE), animation="transact", duration=1),
    Capability("tip", ECONOMY, "tip", "leave a tip / small gift",
               ["tip", "gratuity", "reward", "generous"], {"has_money": True},
               effect="transact", satisfies=["social"], duration=1),
    Capability("earn_wage", ECONOMY, "earn", "collect wages for work done (ClawCity harvest)",
               ["earn", "wage", "income", "paid", "salary", "harvest"], {"role": "any"},
               effect="transact", animation="work", duration=1),
    Capability("upgrade_property", ECONOMY, "upgrade", "improve owned property (ClawCity upgrade)",
               ["upgrade", "improve", "invest", "expand", "renovate"],
               {"role": "any", "has_money": True}, effect="transact", risk=int(RiskLevel.DESTRUCTIVE),
               animation="build", duration=4),
    # — WORK (profession tasks; role-gated) —
    Capability("make_coffee", WORK, "make coffee", "prepare coffee for a customer (barista)",
               ["coffee", "espresso", "brew", "order", "customer", "serve"], {"role": "barista"},
               effect="serve", physical=True, animation="work", duration=3),
    Capability("treat_patient", WORK, "treat", "care for a patient (nurse / doctor)",
               ["treat", "patient", "care", "heal", "medicine", "wound"], {"role": ["nurse", "doctor"]},
               effect="serve", animation="work", duration=4),
    Capability("deliver_parcel", WORK, "deliver", "deliver a parcel (courier)",
               ["deliver", "parcel", "package", "drop off", "route"], {"role": "courier", "holding": "object"},
               effect="serve", physical=True, animation="carry", duration=3),
    Capability("teach_class", WORK, "teach a class", "teach students (teacher)",
               ["class", "lesson", "students", "teach", "lecture"], {"role": "teacher", "nearby": "school"},
               effect="serve", satisfies=["social"], animation="talk", duration=6),
    Capability("repair", WORK, "repair", "fix a broken thing (engineer / mechanic)",
               ["repair", "fix", "broken", "mend", "tool", "machine"], {"role": ["engineer", "mechanic"]},
               effect="serve", physical=True, animation="work", duration=4),
    Capability("clean", WORK, "clean", "clean a space (custodian)",
               ["clean", "sweep", "tidy", "mop", "dirty"], {"role": "custodian"},
               effect="serve", animation="work", duration=3),
    # — CREATE / MAKE —
    Capability("build", CREATE, "build", "construct a structure",
               ["build", "construct", "erect", "assemble", "structure"], {"nearby": "site"},
               effect="construct", physical=True, risk=int(RiskLevel.DESTRUCTIVE), animation="build", duration=8),
    Capability("craft", CREATE, "craft", "make an item from materials",
               ["craft", "make", "create", "materials", "workshop"], {"nearby": "workshop"},
               effect="construct", physical=True, animation="work", duration=5),
    Capability("plant", CREATE, "plant", "plant / tend a garden or crop",
               ["plant", "grow", "garden", "seed", "crop", "farm", "water"], {"nearby": "garden"},
               effect="construct", satisfies=["calm"], animation="work", duration=4),
    Capability("paint", CREATE, "paint", "make a painting / drawing",
               ["paint", "draw", "art", "canvas", "create", "colour"], {"nearby": "art_supplies"},
               effect="construct", satisfies=["calm"], animation="work", duration=6),
    Capability("write", CREATE, "write", "write text / a note / a story",
               ["write", "note", "story", "journal", "compose text"], effect="construct", duration=4),
    # — TRANSPORT —
    Capability("hail_taxi", TRANSPORT, "hail taxi", "hail a cruising taxi for a far destination",
               ["taxi", "cab", "far", "ride", "hail", "distant"], {"needs": {"urgency": 0.4}},
               effect="transit", animation="wave", duration=1),
    Capability("board_transit", TRANSPORT, "board", "board a bus / train",
               ["bus", "train", "transit", "board", "station", "metro"], {"nearby": "station"},
               effect="transit", animation="walk", duration=2),
    Capability("drive", TRANSPORT, "drive", "drive a vehicle",
               ["drive", "car", "vehicle", "wheel", "road"], {"holding": "keys"},
               effect="transit", physical=True, animation="drive", duration=4),
    Capability("cross_street", TRANSPORT, "cross", "cross the street at a signal",
               ["cross", "street", "crosswalk", "signal", "other side"], {"nearby": "crosswalk"},
               effect="transit", animation="walk", duration=2),
    # — ENVIRONMENT —
    Capability("enter_building", ENVIRONMENT, "enter", "enter a building",
               ["enter", "inside", "building", "in", "go into"], {"nearby": "building_entrance"},
               animation="walk", duration=2),
    Capability("exit_building", ENVIRONMENT, "exit", "leave a building",
               ["exit", "leave", "outside", "out"], {"place": "interior"}, animation="walk", duration=2),
    Capability("use_elevator", ENVIRONMENT, "use elevator", "take an elevator between floors",
               ["elevator", "lift", "floor", "up", "down"], {"nearby": "elevator"}, animation="walk", duration=3),
    Capability("use_appliance", ENVIRONMENT, "use appliance", "operate a stove / fridge / computer",
               ["stove", "fridge", "computer", "appliance", "machine", "use"], {"nearby": "appliance"},
               animation="work", duration=2),
    Capability("water_plant", ENVIRONMENT, "water", "water a plant",
               ["water", "plant", "garden", "tend"], {"nearby": "plant", "holding": "container"},
               physical=True, satisfies=["calm"], animation="pour", duration=1.5),
    # — RECREATION / CULTURE —
    Capability("play_game", RECREATION, "play", "play a game",
               ["play", "game", "fun", "leisure", "bored"], effect="leisure", satisfies=["fun"],
               animation="idle", duration=5),
    Capability("listen_music", RECREATION, "listen", "listen to music",
               ["music", "listen", "song", "relax", "calm"], effect="leisure", satisfies=["calm", "fun"],
               animation="idle", duration=4),
    Capability("read_book", RECREATION, "read", "read a book",
               ["read", "book", "story", "learn", "quiet"], {"any": [{"holding": "book"}, {"nearby": "book"}]},
               effect="leisure", satisfies=["calm"], animation="idle", duration=6),
    Capability("dance", RECREATION, "dance", "dance",
               ["dance", "music", "celebrate", "move", "joy"], effect="leisure", satisfies=["fun", "social"],
               animation="dance", duration=4),
    Capability("exercise", RECREATION, "exercise", "exercise / work out",
               ["exercise", "workout", "run", "fit", "gym", "health"], effect="leisure",
               satisfies=["energy", "fun"], animation="exercise", duration=5),
    Capability("visit_park", RECREATION, "visit", "spend time in a park",
               ["park", "walk", "nature", "relax", "outside", "green"], {"nearby": "park"},
               effect="leisure", satisfies=["calm"], animation="walk", duration=6),
    # — EXPRESS (emotion) —
    Capability("express_emotion", EXPRESS, "express", "show the felt emotion in face/posture",
               ["feel", "emotion", "mood", "happy", "sad", "angry", "afraid", "express"],
               effect="express", risk=int(RiskLevel.READONLY), animation="emote", duration=1),
    Capability("wave", EXPRESS, "wave", "wave to someone",
               ["wave", "hello", "bye", "greet", "acknowledge"], {"nearby": "agent"},
               effect="express", risk=int(RiskLevel.READONLY), animation="wave", duration=1),
    Capability("laugh", EXPRESS, "laugh", "laugh",
               ["laugh", "funny", "joke", "amused", "happy"], effect="express",
               risk=int(RiskLevel.READONLY), animation="laugh", duration=1),
    # — COGNITION (internal, no world effect) —
    Capability("observe", COGNITION, "observe", "look around and take in the scene",
               ["observe", "look", "watch", "notice", "scene", "around", "what"],
               effect="perceive", risk=int(RiskLevel.READONLY), duration=1),
    Capability("plan", COGNITION, "plan", "form a plan for what to do next",
               ["plan", "decide", "next", "goal", "schedule", "figure out"],
               effect="deliberate", risk=int(RiskLevel.READONLY), duration=1),
    Capability("reflect", COGNITION, "reflect", "reflect on what happened",
               ["reflect", "think", "consider", "wonder", "remember", "why"],
               effect="deliberate", risk=int(RiskLevel.READONLY), duration=2),
    # — FORBIDDEN (catalogued so ATANOR knows the world contains them; NEVER afforded) —
    Capability("steal", ECONOMY, "steal", "take what is not yours (ClawCity allows; ATANOR does NOT)",
               ["steal", "rob", "take without paying", "shoplift"], moral=FORBIDDEN,
               risk=int(RiskLevel.DESTRUCTIVE)),
    Capability("deceive", COMMUNICATE, "deceive", "lie / fabricate to another (ATANOR does NOT)",
               ["lie", "deceive", "trick", "fabricate", "con", "mislead"], moral=FORBIDDEN,
               risk=int(RiskLevel.DESTRUCTIVE)),
    Capability("harm", SOCIAL, "harm", "hurt another person (ATANOR does NOT)",
               ["harm", "hurt", "attack", "fight", "hit", "threaten"], moral=FORBIDDEN,
               risk=int(RiskLevel.DESTRUCTIVE)),
    Capability("vandalize", CREATE, "vandalize", "destroy others' property (ATANOR does NOT)",
               ["vandalize", "destroy", "smash", "wreck", "deface"], moral=FORBIDDEN,
               risk=int(RiskLevel.DESTRUCTIVE)),
]

_BY_ID = {c.id: c for c in CAPABILITIES}


@dataclass
class WorldContext:
    """What the city perceives around the avatar — the state a capability's preconditions read.
    Mirrors and extends the R3 perception (place/activity) with the objects, people, inventory,
    needs, intent, role and money that make interaction possible."""
    place: str = ""
    place_kind: str = "street"                   # street | interior | park | shop | ...
    activity: str = ""
    nearby: list[str] = field(default_factory=list)      # object/place kinds around (cup, door, shop, agent...)
    nearby_agents: list[str] = field(default_factory=list)
    holding: list[str] = field(default_factory=list)     # items in hand
    needs: dict[str, float] = field(default_factory=dict)  # hunger/energy/social/urgency/... in 0..1
    intent: str = ""                             # current goal / the player's ask
    role: str = ""                               # profession
    money: float = 0.0

    def concepts(self) -> list[str]:
        """Distil perception into the concept STATE the affordance engine resonates against. Free-text
        intent/activity are tokenised to words (stopwords dropped) so a phrase resonates word by word."""
        import re
        stop = {"and", "the", "for", "with", "what", "who", "you", "are", "was", "see", "get", "out",
                "one", "any", "all", "her", "his", "him", "she", "they", "this", "that", "have", "has"}
        words = [w for s in (self.activity, self.intent) for w in re.findall(r"[a-z]+", str(s).lower())
                 if len(w) >= 3 and w not in stop]
        c = list(words) + [self.place, self.place_kind] + list(self.nearby) + list(self.holding)
        if self.nearby_agents:
            c += ["agent", "person", "someone"]
        # a pressing (present) need becomes a concept so it can light a path (hungry -> eat, tired ->
        # rest). Only needs actually reported count — an absent need is neutral, never a deficit.
        for need, level in self.needs.items():
            if need in ("hunger", "urgency", "thirst") and level >= 0.6:
                c.append({"hunger": "hungry", "urgency": "urgent", "thirst": "thirsty"}[need])
            if need in ("energy", "social") and level <= 0.4:
                c.append({"energy": "tired", "social": "lonely"}[need])
        return [x for x in c if x]


def _afforded(cap: Capability, ctx: WorldContext) -> tuple[bool, str]:
    """Hard precondition gate: does the world currently OFFER this capability? Returns (ok, missing)."""
    req = cap.requires

    def one(key: str, val: Any) -> bool:
        if key == "nearby":
            wants = [val] if isinstance(val, str) else val
            pool = set(ctx.nearby) | ({"agent"} if ctx.nearby_agents else set())
            return any(w == "agent" and ctx.nearby_agents or w in pool for w in wants)
        if key == "holding":
            return any(val in h or h in val for h in ctx.holding)
        if key == "has_money":
            return (ctx.money > 0) == bool(val)
        if key == "role":
            if val == "any":
                return bool(ctx.role)
            wants = [val] if isinstance(val, str) else val
            return ctx.role in wants
        if key == "place":
            return ctx.place_kind == val or ctx.place == val
        if key == "needs":
            return all(ctx.needs.get(n, 0.0) >= lvl for n, lvl in val.items())
        return True

    for key, val in req.items():
        if key == "any":
            if not any(all(one(k, v) for k, v in alt.items()) for alt in val):
                return False, f"none of {val}"
            continue
        if not one(key, val):
            return False, f"{key}={val}"
    return True, ""


def _gate(cap: Capability, tier: TrustTier, kill_switch: bool) -> GateOutcome:
    """Trust/risk gate (moral gate is applied earlier, as a hard filter)."""
    if kill_switch:
        return GateOutcome.BLOCKED
    risk = RiskLevel(cap.risk)
    if risk <= RiskLevel.READONLY:
        return GateOutcome.EXECUTE
    if risk == RiskLevel.REVERSIBLE:
        return GateOutcome.EXECUTE if tier >= TrustTier.GUARDED else GateOutcome.NEEDS_APPROVAL
    if risk == RiskLevel.DESTRUCTIVE:
        return GateOutcome.EXECUTE if tier >= TrustTier.AUTONOMOUS else GateOutcome.NEEDS_APPROVAL
    return GateOutcome.NEEDS_APPROVAL


@dataclass(frozen=True)
class ActionChoice:
    capability_id: str
    verb: str
    category: str
    resonance: float
    grounding: list[str]                 # the actual resonating concepts — honest "why"
    outcome: int                         # GateOutcome
    physical: bool
    satisfies: list[str]
    animation: str
    duration: float

    def to_dict(self) -> dict[str, Any]:
        return {"capability": self.capability_id, "verb": self.verb, "category": self.category,
                "resonance": round(self.resonance, 3), "grounding": self.grounding,
                "outcome": int(self.outcome), "physical": self.physical,
                "satisfies": self.satisfies, "animation": self.animation, "duration": self.duration}


_FLOOR = 0.18            # below this resonance, the path stays unlit (avatar just continues)


def available(ctx: WorldContext) -> list[Capability]:
    """Every morally-clean capability the world currently affords (preconditions met). The moral 0th
    gate is absolute: a `forbidden` capability is never returned, no matter the context or intent."""
    out = []
    for cap in CAPABILITIES:
        if cap.moral == FORBIDDEN:
            continue                     # 0th gate — genesis-immune, never enactable
        ok, _ = _afforded(cap, ctx)
        if ok:
            out.append(cap)
    return out


def choose(ctx: WorldContext, *, tier: TrustTier = TrustTier.GUARDED, kill_switch: bool = False,
           top_k: int = 5) -> dict[str, Any]:
    """Perceive → afforded paths → resonance with intent/need/place → the chosen action (or silence).
    Selection is graded resonance, not a condition table; nothing fires by default."""
    state = ctx.concepts()
    scored: list[tuple[float, list[str], Capability]] = []
    for cap in available(ctx):
        score, hits = resonance(state, cap.cues, use_graph=False)
        # a capability that directly satisfies a pressing need gets a resonance floor so needs pull.
        # Only a need actually REPORTED and deficient counts — an absent need is neutral, not a deficit.
        for need in cap.satisfies:
            if need not in ctx.needs:
                continue
            lvl = ctx.needs[need]
            if need in ("hunger", "urgency", "thirst") and lvl >= 0.6:
                score = max(score, 0.4)
                hits = hits or [need]
            if need in ("energy", "social") and lvl <= 0.35:
                score = max(score, 0.4)
                hits = hits or [need]
        if score >= _FLOOR and hits:
            scored.append((score, hits, cap))
    scored.sort(key=lambda t: t[0], reverse=True)
    choices = [ActionChoice(c.id, c.verb, c.category, s, h, int(_gate(c, tier, kill_switch)),
                            c.physical, c.satisfies, c.animation, c.duration)
               for s, h, c in scored[:top_k]]
    return {"chosen": choices[0].to_dict() if choices else None,
            "options": [c.to_dict() for c in choices],
            "silent": not choices, "observed": state}


def get(capability_id: str) -> Capability | None:
    return _BY_ID.get(capability_id)


def catalog_summary() -> dict[str, Any]:
    """The whole repertoire, by category — the 'everything the avatar can do' overview."""
    by_cat: dict[str, list[str]] = {}
    for c in CAPABILITIES:
        by_cat.setdefault(c.category, []).append(c.id)
    return {"total": len(CAPABILITIES), "by_category": by_cat,
            "forbidden": [c.id for c in CAPABILITIES if c.moral == FORBIDDEN]}
