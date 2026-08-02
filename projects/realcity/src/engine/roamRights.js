// roamRights.js — occupation-based CITYWIDE roam rights (CT world-system, 2026-07-21).
// Owner mandate: "agents may move freely across the WHOLE city by their occupation — no district
// locks." This module grants roam rights; it never restricts an agent to a district.
//
// Self-driving side-effect module (see citySystems.js contract): it starts its own interval loop,
// waits for window.__REALCITY_CITY__, guards every access, NEVER throws, and logs once on boot. It
// imports nothing — all cross-talk goes through window globals + city.systems, exactly like the
// clock / weather / lifePatterns siblings.
//
// It does NOT invent movement. To send an agent to a coordinate it writes the SAME field the runtime
// already honors: agent.needErrand = { targetId: <landmark id>, ... }. Actors.jsx targetFor() reads
// needErrand.targetId, resolves the landmark from its places Map (built from city.landmarks), and
// routes the agent there on foot — or, for a long cross-town hop, the runtime's own
// shouldUseAutonomousTaxi()/startAutonomousNpcTaxi() puts them in a fleet taxi. When the errand's
// durationMinutes elapse, the runtime's updateNeedErrand() clears it and returns the agent to its
// daily schedule. We simply choose a cross-district destination and hand it over.
//
// HARD RULES (enforced below):
//   * Never override an agent with an active mission, self-taxi, boarding-taxi, or existing errand.
//   * Never touch brain / dialogueBrain (we only write movement/errand fields).
//   * Occupation biases WHICH kinds of place; every role keeps FULL cross-district reach.

const TICK_MS = 5000            // module heartbeat
const SAMPLE_EVERY_MS = 30000   // coverage: sample agent positions vs the district grid every 30s
const CLEAR_AFTER_MS = 240000   // janitor: release any roam errand we set that lingers > ~4 real min
const FALLBACK_WAVE_MS = 165000 // reassign cadence when no sim clock is available (~2.75 real min)
const MIN_ROAM_STEP_MIN = 120   // reassign every ~2..4 SIM-HOURS (city.systems.clock sim-minutes)
const MAX_ROAM_STEP_MIN = 240
const ROAM_DURATION_MIN = 150   // roam errand length, in store sim-minutes (runtime expires it)
const CROSS_DISTRICT_MIN_DIST = 120 // prefer a target at least this far so the walk reads as "across town"
const WAVE_FRACTION = 0.35      // assign at most this fraction of currently-free agents per wave

// The landmark kinds that exist in the city (cityBlueprint LANDMARK_BLUEPRINTS: one landmark per
// kind, spread across the six districts). Full list == full-city roam rights.
const ALL_KINDS = ['transit', 'finance', 'cafe', 'hospital', 'workshop', 'retail', 'school', 'leisure', 'park', 'logistics']

// Occupation roam profiles: the citywide place KINDS each occupation plausibly circulates through.
// Every profile still reaches across districts — the default is the whole city (full roam rights).
function roamKindsForRole(role) {
  const r = String(role == null ? '' : role).toLowerCase()
  if (/courier|taxi|driver|delivery|security|patrol/.test(r)) return ALL_KINDS // constant citywide waypoints
  if (/shopkeeper|merchant|barista|vendor|clerk|grocer/.test(r)) return ['retail', 'logistics', 'cafe', 'transit'] // market<->depot<->home
  if (/doctor|nurse|medic|paramedic|clinician/.test(r)) return ['hospital', 'cafe', 'retail', 'park', 'transit'] // hospital + errands across town
  if (/teacher|student|professor|tutor|pupil/.test(r)) return ['school', 'park', 'leisure', 'cafe'] // school + park + library-ish
  if (/engineer|custodian|technician|mechanic|gardener|worker/.test(r)) return ['workshop', 'logistics', 'finance', 'transit', 'park'] // rotating worksites anywhere
  if (/retiree|elder|senior|pensioner/.test(r)) return ['park', 'retail', 'cafe', 'leisure'] // parks/markets anywhere
  if (/artist|designer|musician|maker/.test(r)) return ['leisure', 'cafe', 'park', 'retail']
  if (/banker|finance|accountant|analyst/.test(r)) return ['finance', 'transit', 'cafe', 'retail']
  return ALL_KINDS // default: full city rights
}

let booted = false
let waveCounter = 0
let lastSampleAt = 0
let lastWaveWallAt = 0
let lastAssignSimMinutes = null
let nextStepMinutes = randStep()
let initialWaveDone = false

// coverage state
const visitedByAgent = new Map()     // agentId -> Set(districtId)  (Map of visited-district sets)
const districtSampleCounts = new Map() // districtId -> number of position samples seen there
const assignedIds = new Set()        // distinct agents ever sent on a citywide roam
let assignmentsTotal = 0
const lastAssignments = []           // most-recent-first [{ id, role, to }]

function randStep() {
  return Math.floor(MIN_ROAM_STEP_MIN + Math.random() * (MAX_ROAM_STEP_MIN - MIN_ROAM_STEP_MIN))
}

// Stable non-negative hash of an id string (matches lifePatterns' hashId) for deterministic spread.
function hashId(id) {
  const text = String(id == null ? '' : id)
  let hash = 0
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

// True when a runtime-owned behavior owns the agent — we must not fight it.
function isBusy(agent) {
  return !!(agent.mission || agent.selfTaxi || agent.boardingTaxi || agent.needErrand)
}

// Live cast = the Agent instances Actors.jsx publishes to city.agents (what the mover actually reads).
function resolveCast(city) {
  if (city && Array.isArray(city.agents) && city.agents.length) return city.agents
  return []
}

// The day-relative minute base the RUNTIME times errands against. Actors.jsx measures an errand's
// remaining life with store.timeMinutes (day-relative 0..1440), so we anchor startedAt to that exact
// value when the store is exposed (dev global); otherwise we fall back to the sim clock's day-minutes.
function runtimeMinutes(city) {
  try {
    const store = (typeof window !== 'undefined') ? window.__REALCITY_STORE__ : null
    const tm = store && typeof store.getState === 'function' ? store.getState().timeMinutes : null
    if (Number.isFinite(tm)) return ((tm % 1440) + 1440) % 1440
  } catch (_) { /* ignore and fall back to the clock */ }
  const clock = city && city.systems && city.systems.clock
  if (clock && Number.isFinite(clock.simMinutes)) return ((clock.simMinutes % 1440) + 1440) % 1440
  if (clock && Number.isFinite(clock.hour)) return ((clock.hour * 60 + (Number(clock.minute) || 0)) % 1440 + 1440) % 1440
  return 0
}

// Position -> district id via the engine's own district grid (city.districtAt is the DISTRICT_BLUEPRINT
// classifier). Falls back to a coarse fixed grid cell if districtAt is unavailable.
function districtIdAt(city, x, z) {
  try {
    if (city && typeof city.districtAt === 'function') {
      const d = city.districtAt(x, z)
      if (d && d.id) return d.id
    }
  } catch (_) { /* fall through to grid */ }
  const CELL = 400
  return `g${Math.floor((Number(x) || 0) / CELL)}:${Math.floor((Number(z) || 0) / CELL)}`
}

// Kinds this agent may roam to now = occupation profile, narrowed to the current hour band when
// lifePatterns has published one. Empty result (e.g. the sleeping band) means "do not roam now".
function allowedKindsFor(agent) {
  const roleKinds = roamKindsForRole(agent.role)
  const li = agent.lifeIntent
  if (li && li.mode === 'sleeping') return [] // night: stay home, no citywide roam
  const band = li && Array.isArray(li.targetKinds) ? li.targetKinds : null
  if (!band || !band.length) return roleKinds
  const intersection = roleKinds.filter(k => band.includes(k))
  if (intersection.length) return intersection
  return band // band is authoritative for the hour if the occupation profile doesn't overlap it
}

// Assign one free agent a cross-district destination by writing the field the mover honors.
function assignRoam(city, agent, landmarks) {
  if (!agent || typeof agent !== 'object' || isBusy(agent)) return false
  const pos = agent.pos
  if (!pos || !Number.isFinite(pos.x) || !Number.isFinite(pos.z)) return false

  const kinds = allowedKindsFor(agent)
  if (!kinds.length) return false // band says no roam (e.g. asleep)

  const here = districtIdAt(city, pos.x, pos.z)
  let pool = landmarks.filter(l => l && kinds.includes(l.kind))
  if (!pool.length) pool = landmarks.slice() // full-city fallback: any landmark is fair game

  const crossDistrict = pool.filter(l => districtIdAt(city, l.x, l.z) !== here)
  const reachSet = crossDistrict.length ? crossDistrict : pool
  const farEnough = reachSet.filter(l => Math.hypot(l.x - pos.x, l.z - pos.z) > CROSS_DISTRICT_MIN_DIST)
  const finalPool = farEnough.length ? farEnough : reachSet
  if (!finalPool.length) return false

  const pick = finalPool[hashId(`${agent.id}:${waveCounter}`) % finalPool.length]
  if (!pick || !pick.id) return false

  // Same shape the runtime's own startNeedErrand()/startLlmDirectedErrand() produce, so every
  // downstream reader (targetFor, updateNeedErrand, snapshot, autonomy) sees defined fields.
  agent.needErrand = {
    id: `roam_${agent.id}_${waveCounter}`,
    reason: 'roam',
    label: 'citywide roam',
    activity: `heading across town to ${pick.name}`,
    targetId: pick.id,
    targetName: pick.name,
    startedAt: runtimeMinutes(city),
    durationMinutes: ROAM_DURATION_MIN,
    forced: false,
    cognitiveReason: `occupation "${agent.role || 'citizen'}" carries citywide roam rights`,
    cognitionPolicy: 'occupation-citywide-roam',
    mobilityMode: 'walk',
    mobilitySource: null,
    mobilityDockName: null,
    sharedMobilityTrip: null,
    roamRights: true,          // our marker so the janitor can recognise its own errands
    assignedWallAt: Date.now(),
  }
  // Let the runtime replan the route cleanly from scratch (same reset startNeedErrand does).
  agent.walkRoute = null
  agent.walkPlan = null

  assignmentsTotal += 1
  assignedIds.add(agent.id)
  lastAssignments.unshift({ id: agent.id, role: agent.role || 'citizen', to: pick.name })
  if (lastAssignments.length > 12) lastAssignments.length = 12
  return true
}

// One assignment wave: pick free agents (rotated so a different subset leads each wave) and send a
// capped fraction of them across a district line.
function runWave(city) {
  const cast = resolveCast(city)
  const landmarks = Array.isArray(city.landmarks) ? city.landmarks : []
  if (!cast.length || !landmarks.length) return 0

  waveCounter += 1
  const free = cast.filter(a => a && typeof a === 'object' && !isBusy(a))
  if (!free.length) return 0
  free.sort((a, b) => hashId(`${a.id}:${waveCounter}`) - hashId(`${b.id}:${waveCounter}`))

  const cap = Math.max(6, Math.round(free.length * WAVE_FRACTION))
  let assigned = 0
  for (const agent of free) {
    if (assigned >= cap) break
    if (assignRoam(city, agent, landmarks)) assigned += 1
  }
  return assigned
}

// Janitor: release any roam errand WE set that outlives its wall-clock cap (defends against a build
// where the runtime's store clock and our fallback base disagree and the errand never counts down).
function cleanupStuck(city, now) {
  const cast = resolveCast(city)
  for (const agent of cast) {
    const errand = agent && agent.needErrand
    if (!errand || !errand.roamRights) continue
    if (now - (Number(errand.assignedWallAt) || 0) > CLEAR_AFTER_MS) {
      agent.needErrand = null
      agent.walkRoute = null
      agent.walkPlan = null
      // brief cooldown so the runtime's own need-errand logic doesn't fire on the same frame
      agent.needErrandCooldown = Math.max(Number(agent.needErrandCooldown) || 0, 30)
    }
  }
}

// Sample where everyone is now and fold it into the visited-district sets (the coverage measure).
function sampleCoverage(city) {
  const cast = resolveCast(city)
  for (const agent of cast) {
    if (!agent || !agent.pos || !Number.isFinite(agent.pos.x)) continue
    const d = districtIdAt(city, agent.pos.x, agent.pos.z)
    let set = visitedByAgent.get(agent.id)
    if (!set) { set = new Set(); visitedByAgent.set(agent.id, set) }
    set.add(d)
    districtSampleCounts.set(d, (districtSampleCounts.get(d) || 0) + 1)
  }
}

// Public coverage read-out: how much of the city agents are actually reaching.
function coverage() {
  const union = new Set()
  let sizeSum = 0
  let maxPerAgent = 0
  for (const set of visitedByAgent.values()) {
    sizeSum += set.size
    if (set.size > maxPerAgent) maxPerAgent = set.size
    for (const d of set) union.add(d)
  }
  const agentsTracked = visitedByAgent.size
  return {
    agentsAssigned: assignedIds.size,
    assignmentsTotal,
    distinctDistrictsVisited: {
      agentsTracked,
      distinctDistrictsTotal: union.size,
      avgPerAgent: agentsTracked ? Number((sizeSum / agentsTracked).toFixed(2)) : 0,
      maxPerAgent,
      byDistrict: Object.fromEntries(districtSampleCounts),
    },
    lastAssignments: lastAssignments.slice(0, 5),
  }
}

// Shared state object (same identity on the window global and city.systems.roam).
const api = {
  coverage,
  get agentsAssigned() { return assignedIds.size },
}

function loop() {
  try {
    const city = (typeof window !== 'undefined') ? window.__REALCITY_CITY__ : null
    if (!city) return // wait for the city handle
    if (!city.systems) city.systems = {}
    if (city.systems.roam !== api) city.systems.roam = api

    const now = Date.now()

    if (now - lastSampleAt >= SAMPLE_EVERY_MS) {
      sampleCoverage(city)
      lastSampleAt = now
    }

    cleanupStuck(city, now)

    // Nothing to move until the live cast and landmarks exist.
    const cast = resolveCast(city)
    if (!cast.length || !(Array.isArray(city.landmarks) && city.landmarks.length)) return

    // First contact: one immediate wave so roam rights take effect right away.
    if (!initialWaveDone) {
      runWave(city)
      initialWaveDone = true
      const clock0 = city.systems && city.systems.clock
      lastAssignSimMinutes = clock0 && Number.isFinite(clock0.simMinutes) ? clock0.simMinutes : null
      lastWaveWallAt = now
      return
    }

    // Cadence: every ~2..4 sim-hours off the master clock; fall back to a wall timer if it is absent.
    const clock = city.systems && city.systems.clock
    if (clock && Number.isFinite(clock.simMinutes)) {
      if (lastAssignSimMinutes == null) { lastAssignSimMinutes = clock.simMinutes; return }
      if (clock.simMinutes - lastAssignSimMinutes >= nextStepMinutes) {
        runWave(city)
        lastAssignSimMinutes = clock.simMinutes
        nextStepMinutes = randStep()
      }
    } else if (now - lastWaveWallAt >= FALLBACK_WAVE_MS) {
      runWave(city)
      lastWaveWallAt = now
    }
  } catch (_) {
    /* never throw out of the loop */
  }
}

function boot() {
  if (booted || typeof window === 'undefined') return
  booted = true
  // Expose immediately so peers can read a valid (empty) coverage before the first wave lands.
  window.__REALCITY_ROAM__ = api
  try {
    console.log('[realcity] roam rights online')
  } catch (_) {
    /* console unavailable — ignore */
  }
  setInterval(loop, TICK_MS)
  loop()
}

boot()

export {}
