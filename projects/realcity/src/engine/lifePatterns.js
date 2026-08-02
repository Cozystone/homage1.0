// lifePatterns.js — the 24h human rhythm of the city (CT world-system, 2026-07-21).
// Owner theme: "day and night, the human daily-life pattern."
//
// Self-driving side-effect module (see citySystems.js contract): it starts its own ~1s loop, waits
// for window.__REALCITY_CITY__, guards every access, and NEVER throws. Each time the sim HOUR ticks
// over (read from city.systems.clock, which cityClock publishes; may be absent early — guarded) it
// assigns every citizen a life-intent for that hour, gently nudges their activity, and nudges their
// needs drift. It publishes a live "time-use survey" to BOTH window.__REALCITY_LIFE__ and
// city.systems.life so the distribution is measurable.
//
// GENTLE rule: we only overwrite agent.activity when the agent has NO active mission (taxi ride,
// player guidance, self-called taxi, need-errand). We never fight the runtime's own behaviors — the
// life-intent is a hint layered on top, and the runtime schedule/behavior-tree still owns motion.
//
// Cast resolution: prefer city.agents (live-Agent array, if some later wave publishes it) else
// city.npcs (the source cast). Whichever we get, we write the same fields.

const TICK_MS = 1000
const MINUTES_PER_DAY = 1440

// Landmark-kind hints for where a given intent leans. These are soft hints consumed downstream; this
// module never resolves them to coordinates (that stays the runtime's job).
const EVENING_LEISURE = ['park', 'neon_square', 'cafe']
const WEEKEND_AFTERNOON = ['park', 'market', 'neon_square']

// Roam hook (consumed by roamRights.js): for each survey bucket, the list of citywide LANDMARK KINDS
// that are plausible destinations in that hour band. This is purely additive metadata layered onto
// lifeIntent — it changes no life-pattern behavior; roamRights reads it to keep any cross-district
// roam it assigns consistent with the hour (work hours -> work-plausible sites; leisure -> parks/
// plazas/cafes). Kinds match cityBlueprint LANDMARK_BLUEPRINTS. 'sleeping' -> [] (no night roam).
const ROAM_WORK_KINDS = ['transit', 'finance', 'hospital', 'workshop', 'retail', 'school', 'logistics']
const ROAM_LEISURE_KINDS = ['park', 'leisure', 'cafe', 'retail']
const ROAM_OTHER_KINDS = ['cafe', 'retail', 'leisure', 'park']
function roamKindsForMode(mode) {
  if (mode === 'working' || mode === 'commuting') return ROAM_WORK_KINDS
  if (mode === 'leisure') return ROAM_LEISURE_KINDS
  if (mode === 'other') return ROAM_OTHER_KINDS
  return [] // sleeping (or unknown): no citywide roam in this band
}

let booted = false
let lastHourKey = null // `${dayIndex}:${hour}` — recompute only when the hour actually changes

function clamp01(value) {
  return Math.max(0, Math.min(1, value))
}

// Small stable hash of an id string -> non-negative int, for deterministic per-agent target spread.
function hashId(id) {
  const text = String(id == null ? '' : id)
  let hash = 0
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

function pickStable(id, list) {
  if (!list.length) return null
  return list[hashId(id) % list.length]
}

// Resolve the citizen cast from the city handle, tolerating either shape.
function resolveCast(city) {
  if (city && Array.isArray(city.agents) && city.agents.length) return city.agents
  if (city && Array.isArray(city.npcs) && city.npcs.length) return city.npcs
  return []
}

// Read a usable clock, preferring the attached system clock, falling back to the global the clock
// module exposes before the city handle lands. Returns null if no valid hour is available yet.
function readClock(city) {
  const clock = (city && city.systems && city.systems.clock)
    || (typeof window !== 'undefined' ? window.__REALCITY_TIME__ : null)
  if (!clock || !Number.isFinite(clock.hour)) return null
  return clock
}

function dayIndexFrom(clock) {
  if (!clock || !Number.isFinite(clock.simMinutes)) return 1 // default to a weekday if minutes absent
  const days = Math.floor(clock.simMinutes / MINUTES_PER_DAY)
  return ((days % 7) + 7) % 7 // 0..6, day 6 = Saturday, day 0 = Sunday
}

// Map (hour, weekend, role, age) -> { mode, targetKind, label, activity }.
// mode is one of the five survey buckets: sleeping | working | leisure | commuting | other.
function intentFor(hour, weekend, role, age, id) {
  const isStudent = role === 'student'
  const isElder = role === 'retiree' || (Number.isFinite(age) && age >= 65)
  const workTarget = isStudent ? 'school' : 'work'

  // 23:00–06:00 — sleeping. Weekends let people sleep in a touch, but the block is the same.
  if (hour >= 23 || hour < 6) {
    return { mode: 'sleeping', targetKind: 'home', label: 'asleep at home', activity: 'sleeping' }
  }

  // 06:00–08:00 — morning routine + commute (weekdays); a slow start on weekends.
  if (hour < 8) {
    if (weekend) {
      return { mode: 'other', targetKind: 'home', label: 'slow weekend morning', activity: 'having a slow morning' }
    }
    return { mode: 'commuting', targetKind: workTarget, label: 'morning commute', activity: 'commuting' }
  }

  // 08:00–12:00 — work / school (weekdays). Weekends and retirees lean to the park.
  if (hour < 12) {
    if (weekend) {
      return { mode: 'leisure', targetKind: 'park', label: 'weekend morning out', activity: 'out and about' }
    }
    if (isElder) {
      return { mode: 'leisure', targetKind: 'park', label: 'morning at the park', activity: 'strolling the park' }
    }
    if (isStudent) {
      return { mode: 'working', targetKind: 'school', label: 'morning classes', activity: 'in class' }
    }
    return { mode: 'working', targetKind: 'work', label: 'morning shift', activity: 'working' }
  }

  // 12:00–13:00 — lunch surge, biased toward cafe / market.
  if (hour < 13) {
    return { mode: 'other', targetKind: weekend ? 'market' : 'cafe', label: 'lunch break', activity: 'grabbing lunch' }
  }

  // 13:00–18:00 — afternoon work / school (weekdays). Weekends and retirees roam park/market.
  if (hour < 18) {
    if (weekend) {
      return { mode: 'leisure', targetKind: pickStable(id, WEEKEND_AFTERNOON), label: 'weekend afternoon', activity: 'enjoying the day' }
    }
    if (isElder) {
      return { mode: 'other', targetKind: 'market', label: 'afternoon errands', activity: 'running errands' }
    }
    if (isStudent) {
      return { mode: 'working', targetKind: 'school', label: 'afternoon classes', activity: 'in class' }
    }
    return { mode: 'working', targetKind: 'work', label: 'afternoon shift', activity: 'working' }
  }

  // 18:00–21:00 — leisure: park / neon_square / cafe.
  if (hour < 21) {
    return { mode: 'leisure', targetKind: pickStable(id, EVENING_LEISURE), label: 'evening leisure', activity: 'unwinding out' }
  }

  // 21:00–23:00 — wind down at home.
  return { mode: 'other', targetKind: 'home', label: 'winding down', activity: 'winding down at home' }
}

// Ensure an agent has a mutable needs object to modulate (source NPCs carry autonomy.needProfile;
// live Agents already carry .needs). Seeds from the need profile so energy/social exist to nudge.
function ensureNeeds(agent) {
  if (agent.needs && typeof agent.needs === 'object') return agent.needs
  const profile = (agent.autonomy && agent.autonomy.needProfile) || {}
  agent.needs = {
    energy: Number.isFinite(profile.energy) ? profile.energy : 0.72,
    hunger: Number.isFinite(profile.hunger) ? profile.hunger : 0.24,
    social: Number.isFinite(profile.social) ? profile.social : 0.5,
    urgency: Number.isFinite(profile.urgency) ? profile.urgency : 0.36,
  }
  return agent.needs
}

// Gentle, hour-scaled needs modulation — sleeping restores energy fastest, work drains it slightly,
// social/leisure feeds needs.social, lunch eases hunger. Small steps so we modulate, never dominate,
// the runtime's own per-frame drift.
function modulateNeeds(agent, mode, label) {
  const needs = ensureNeeds(agent)
  if (mode === 'sleeping') {
    needs.energy = clamp01(needs.energy + 0.10) // recovers faster while asleep
  } else if (mode === 'working') {
    needs.energy = clamp01(needs.energy - 0.03)
    needs.social = clamp01(needs.social - 0.01)
  } else if (mode === 'leisure') {
    needs.social = clamp01(needs.social + 0.06)
    needs.energy = clamp01(needs.energy - 0.005)
  } else if (mode === 'commuting') {
    needs.energy = clamp01(needs.energy - 0.015)
  } else { // other: lunch eases hunger + a little social; wind-down recovers a little energy
    if (label === 'lunch break') {
      needs.hunger = clamp01(needs.hunger - 0.08)
      needs.social = clamp01(needs.social + 0.02)
    } else if (label === 'winding down') {
      needs.energy = clamp01(needs.energy + 0.02)
    }
  }
}

// True when the agent is busy with a runtime-owned behavior we must not fight.
function isBusy(agent) {
  return !!(agent.mission || agent.selfTaxi || agent.boardingTaxi || agent.needErrand)
}

function applyHour(cast, hour, weekend) {
  for (const agent of cast) {
    if (!agent || typeof agent !== 'object') continue
    const intent = intentFor(hour, weekend, agent.role, agent.age, agent.id)
    agent.lifeIntent = { mode: intent.mode, targetKind: intent.targetKind, label: intent.label, targetKinds: roamKindsForMode(intent.mode) }
    // Nudge activity ONLY when the agent is free — never override taxi rides / errands / guidance.
    if (!isBusy(agent)) {
      agent.activity = intent.activity
    }
    modulateNeeds(agent, intent.mode, intent.label)
  }
}

// Live time-use survey over the current cast, always recomputed so it reflects the moment.
function distribution() {
  const counts = { sleeping: 0, working: 0, leisure: 0, commuting: 0, other: 0 }
  try {
    const city = typeof window !== 'undefined' ? window.__REALCITY_CITY__ : null
    const cast = resolveCast(city)
    for (const agent of cast) {
      const mode = agent && agent.lifeIntent && agent.lifeIntent.mode
      if (mode && Object.prototype.hasOwnProperty.call(counts, mode)) counts[mode] += 1
      else counts.other += 1
    }
  } catch (_) {
    /* return zeros on any failure */
  }
  api.counts = counts
  return counts
}

// The shared state object attached to both the window global and city.systems.life (same identity).
const api = {
  hour: null,
  dayIndex: null,
  weekend: false,
  counts: { sleeping: 0, working: 0, leisure: 0, commuting: 0, other: 0 },
  distribution,
}

function loop() {
  try {
    const city = typeof window !== 'undefined' ? window.__REALCITY_CITY__ : null
    if (!city) return
    if (!city.systems) city.systems = {}
    if (city.systems.life !== api) city.systems.life = api

    const clock = readClock(city)
    if (!clock) return // clock not online yet — wait

    const hour = Math.floor(clock.hour)
    const dayIndex = dayIndexFrom(clock)
    const weekend = dayIndex === 6 || dayIndex === 0
    const hourKey = `${dayIndex}:${hour}`
    if (hourKey === lastHourKey) return // same sim-hour — nothing to reassign

    const cast = resolveCast(city)
    if (!cast.length) return // cast not built yet — try again next tick

    applyHour(cast, hour, weekend)
    lastHourKey = hourKey
    api.hour = hour
    api.dayIndex = dayIndex
    api.weekend = weekend
    distribution()
  } catch (_) {
    /* never throw out of the loop */
  }
}

function boot() {
  if (booted || typeof window === 'undefined') return
  booted = true
  // Expose immediately so peers can read a valid (zeroed) survey before the first hour lands.
  window.__REALCITY_LIFE__ = api
  try {
    console.log('[realcity] life patterns online')
  } catch (_) {
    /* console unavailable — ignore */
  }
  setInterval(loop, TICK_MS)
  loop()
}

boot()

export {}
