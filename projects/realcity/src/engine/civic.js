// civic.js — city pulse (CT-track world system, self-driving).
//
// Drives the ambient civic layer off window.__REALCITY_CITY__: streetlights that follow the day
// phase, two looping bus routes, an emergency ambulance state machine fed by report(), and a
// dawn-only garbage truck. No other module is imported — time/weather are read from
// city.systems.* (guarded, may be absent early) and cross-talk is via window CustomEvents.
//
// Public API -> window.__REALCITY_CIVIC__ = { buses, incidents, report(kind,at), streetlights }
//              (also attached to city.systems.civic; adds ambulance, garbage, siren)

const TICK_MS = 1000
const BUS_SPEED = 8 // units/sec
const BUS_STOP_SECONDS = 3
const BUS_ARRIVE_RADIUS = 2
const AMBULANCE_SPEED = 16
const AMBULANCE_ONSCENE_SECONDS = 10
const AMBULANCE_ARRIVE_RADIUS = 3
const GARBAGE_SPEED = 6
const GARBAGE_ARRIVE_RADIUS = 3
const DEMO_INCIDENT_EVERY_HOURS = 10

// Fallback landmark coordinates (used only if a runtime city.landmark lookup fails, so routes still
// form). These are the stable world anchor points, not a knowledge table.
const LANDMARK_FALLBACK = {
  central_station: { x: -148, z: 52 },
  aster_exchange: { x: 142, z: -132 },
  river_cafe: { x: -236, z: -236 },
  hanbit_hospital: { x: 300, z: -198 },
  maker_yard: { x: -332, z: 172 },
  market_lane: { x: -284, z: -314 },
  mirae_school: { x: 366, z: 312 },
  neon_square: { x: 72, z: 470 },
  south_depot: { x: 588, z: -542 },
}

const ROUTE_DEFS = [
  { id: 'blue', ids: ['central_station', 'market_lane', 'river_cafe', 'mirae_school'] },
  { id: 'green', ids: ['central_station', 'aster_exchange', 'hanbit_hospital', 'neon_square', 'maker_yard'] },
]

const GARBAGE_ROUTE_IDS = ['south_depot', 'market_lane', 'central_station', 'neon_square']

// ---- module state -------------------------------------------------------------------------------
let cityRef = null
let started = false
let routes = []
let routesById = new Map()
let buses = []
let incidents = []
let ambulance = null
let garbage = null
const streetlights = { on: false }
let incidentSeq = 0
let internalMinutes = 10 * 60 + 30 // fallback sim-clock if city.systems.clock is absent
let lastHour = null
let hoursSinceDemo = 0

const api = {
  buses,
  incidents,
  report,
  streetlights,
  ambulance: null,
  garbage: null,
  siren: false,
}

// ---- helpers ------------------------------------------------------------------------------------
function num(value, fallback = 0) {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function phaseForHour(hour) {
  const h = ((Math.floor(hour) % 24) + 24) % 24
  if (h >= 5 && h < 8) return 'dawn'
  if (h >= 8 && h < 17) return 'day'
  if (h >= 17 && h < 20) return 'dusk'
  return 'night'
}

function currentHour(city) {
  const clock = city?.systems?.clock
  if (clock && Number.isFinite(Number(clock.hour))) {
    return (((Math.floor(Number(clock.hour)) % 24) + 24) % 24)
  }
  return (((Math.floor(internalMinutes / 60) % 24) + 24) % 24)
}

function currentPhase(city) {
  const clock = city?.systems?.clock
  if (clock && typeof clock.phase === 'string') return clock.phase
  return phaseForHour(currentHour(city))
}

function landmarkCoord(city, id) {
  const found = Array.isArray(city?.landmarks) ? city.landmarks.find(place => place.id === id) : null
  if (found && Number.isFinite(Number(found.x)) && Number.isFinite(Number(found.z))) {
    return { x: Number(found.x), z: Number(found.z), id }
  }
  const fallback = LANDMARK_FALLBACK[id]
  return fallback ? { ...fallback, id } : null
}

function buildWaypoints(city, ids) {
  return ids.map(id => landmarkCoord(city, id)).filter(Boolean)
}

function moveToward(pos, target, step) {
  const dx = target.x - pos.x
  const dz = target.z - pos.z
  const dist = Math.hypot(dx, dz)
  if (dist <= step || dist < 0.001) {
    pos.x = target.x
    pos.z = target.z
    return true // arrived
  }
  pos.x += (dx / dist) * step
  pos.z += (dz / dist) * step
  return false
}

function randomStreetCoord(city) {
  const roads = Array.isArray(city?.roads) ? city.roads : []
  if (roads.length) {
    const road = roads[Math.floor(Math.random() * roads.length)]
    const from = num(road.from, -800)
    const to = num(road.to, 800)
    const along = from + Math.random() * (to - from)
    if (road.axis === 'x') return { x: along, z: num(road.z) }
    return { x: num(road.x), z: along }
  }
  return { x: (Math.random() - 0.5) * 1400, z: (Math.random() - 0.5) * 1400 }
}

// ---- events ------------------------------------------------------------------------------------
function emit(name, detail) {
  try {
    if (typeof window !== 'undefined' && typeof CustomEvent === 'function') {
      window.dispatchEvent(new CustomEvent(name, detail ? { detail } : undefined))
    }
  } catch {
    /* best-effort */
  }
}

function setSiren(on) {
  if (api.siren === on) return
  api.siren = on
  emit('realcity:siren', { on })
}

// ---- incidents / ambulance ---------------------------------------------------------------------
function report(kind, at = {}) {
  try {
    incidentSeq += 1
    const incident = {
      id: `inc_${Date.now().toString(36)}_${incidentSeq}`,
      kind: String(kind || 'incident'),
      at: { x: num(at?.x), z: num(at?.z) },
      state: 'dispatched',
      ts: Date.now(),
    }
    incidents.push(incident)
    return incident
  } catch {
    return null
  }
}

function tickAmbulance(dt) {
  if (!ambulance) return
  if (ambulance.state === 'idle') {
    const next = incidents.find(inc => inc.state === 'dispatched')
    if (!next) return
    ambulance.state = 'dispatch'
    ambulance.incidentId = next.id
    setSiren(true)
  }

  const incident = incidents.find(inc => inc.id === ambulance.incidentId)
  if (!incident) {
    // incident vanished — return home / reset
    ambulance.state = 'idle'
    ambulance.incidentId = null
    setSiren(false)
    return
  }

  if (ambulance.state === 'dispatch') {
    if (moveToward(ambulance.pos, incident.at, AMBULANCE_SPEED * dt) ||
        Math.hypot(incident.at.x - ambulance.pos.x, incident.at.z - ambulance.pos.z) <= AMBULANCE_ARRIVE_RADIUS) {
      ambulance.state = 'onscene'
      incident.state = 'onscene'
      ambulance.timer = AMBULANCE_ONSCENE_SECONDS
    }
  } else if (ambulance.state === 'onscene') {
    ambulance.timer -= dt
    if (ambulance.timer <= 0) {
      ambulance.state = 'returning'
      incident.state = 'returning'
    }
  } else if (ambulance.state === 'returning') {
    if (moveToward(ambulance.pos, ambulance.home, AMBULANCE_SPEED * dt)) {
      incident.state = 'done'
      incidents = incidents.filter(inc => inc.id !== incident.id)
      api.incidents = incidents
      ambulance.state = 'idle'
      ambulance.incidentId = null
      setSiren(false)
    }
  }
}

// ---- buses -------------------------------------------------------------------------------------
function tickBuses(dt) {
  for (const bus of buses) {
    const route = routesById.get(bus.routeId)
    if (!route || !route.waypoints.length) continue
    if (bus.waiting > 0) {
      bus.waiting = Math.max(0, bus.waiting - dt)
      continue
    }
    const target = route.waypoints[bus.targetIdx % route.waypoints.length]
    if (moveToward(bus.pos, target, BUS_SPEED * dt) ||
        Math.hypot(target.x - bus.pos.x, target.z - bus.pos.z) <= BUS_ARRIVE_RADIUS) {
      bus.pos.x = target.x
      bus.pos.z = target.z
      bus.waiting = BUS_STOP_SECONDS
      bus.targetIdx = (bus.targetIdx + 1) % route.waypoints.length // loop forever
    }
  }
}

// ---- garbage truck (dawn only) -----------------------------------------------------------------
function tickGarbage(city, dt) {
  if (!garbage || !garbage.waypoints.length) return
  const active = currentPhase(city) === 'dawn'
  garbage.active = active
  if (!active) return
  const target = garbage.waypoints[garbage.idx % garbage.waypoints.length]
  if (moveToward(garbage.pos, target, GARBAGE_SPEED * dt) ||
      Math.hypot(target.x - garbage.pos.x, target.z - garbage.pos.z) <= GARBAGE_ARRIVE_RADIUS) {
    garbage.idx = (garbage.idx + 1) % garbage.waypoints.length
  }
}

// ---- streetlights ------------------------------------------------------------------------------
function tickStreetlights(city) {
  const phase = currentPhase(city)
  const on = phase === 'dusk' || phase === 'night'
  if (on !== streetlights.on) {
    streetlights.on = on
    emit('realcity:streetlights', { on })
  }
}

// ---- auto-demo ---------------------------------------------------------------------------------
function tickDemoIncidents(city, hour) {
  if (lastHour === null) {
    lastHour = hour
    return
  }
  if (hour === lastHour) return
  lastHour = hour
  hoursSinceDemo += 1
  if (hoursSinceDemo >= DEMO_INCIDENT_EVERY_HOURS) {
    hoursSinceDemo = 0
    report('collision', randomStreetCoord(city))
  }
}

// ---- lifecycle ---------------------------------------------------------------------------------
function init(city) {
  cityRef = city

  routes = ROUTE_DEFS.map(def => ({ id: def.id, waypoints: buildWaypoints(city, def.ids) }))
    .filter(route => route.waypoints.length >= 2)
  routesById = new Map(routes.map(route => [route.id, route]))

  buses = []
  for (const route of routes) {
    const wps = route.waypoints
    buses.push({
      id: `bus_${route.id}_1`,
      routeId: route.id,
      pos: { x: wps[0].x, z: wps[0].z },
      targetIdx: 1 % wps.length,
      waiting: 0,
    })
    if (route.id === 'blue' && wps.length >= 3) {
      // a second, staggered bus so the busiest route reads as a live loop
      const mid = Math.floor(wps.length / 2)
      buses.push({
        id: `bus_${route.id}_2`,
        routeId: route.id,
        pos: { x: wps[mid].x, z: wps[mid].z },
        targetIdx: (mid + 1) % wps.length,
        waiting: 0,
      })
    }
  }

  const hospital = landmarkCoord(city, 'hanbit_hospital') || { x: 300, z: -198 }
  ambulance = {
    pos: { x: hospital.x, z: hospital.z },
    home: { x: hospital.x, z: hospital.z },
    state: 'idle',
    incidentId: null,
    timer: 0,
  }

  const garbageWaypoints = buildWaypoints(city, GARBAGE_ROUTE_IDS)
  const gStart = garbageWaypoints[0] || { x: 588, z: -542 }
  garbage = {
    pos: { x: gStart.x, z: gStart.z },
    home: { x: gStart.x, z: gStart.z },
    waypoints: garbageWaypoints,
    idx: 1 % Math.max(1, garbageWaypoints.length),
    active: false,
  }

  incidents = []
  api.buses = buses
  api.incidents = incidents
  api.report = report
  api.streetlights = streetlights
  api.ambulance = ambulance
  api.garbage = garbage
  api.siren = false

  if (typeof window !== 'undefined') window.__REALCITY_CIVIC__ = api
  city.systems = city.systems || {}
  city.systems.civic = api

  // eslint-disable-next-line no-console
  console.log(`[realcity:civic] ${buses.length} buses on ${routes.length} routes, ambulance ready`)
}

function tick(city, dt) {
  if (!(city?.systems?.clock && Number.isFinite(Number(city.systems.clock.hour)))) {
    internalMinutes = (internalMinutes + dt * 1.25) % (24 * 60)
  }
  // keep the shared incidents reference fresh (ambulance may rebuild the array)
  api.incidents = incidents
  tickStreetlights(city)
  tickBuses(dt)
  tickAmbulance(dt)
  tickGarbage(city, dt)
  tickDemoIncidents(city, currentHour(city))
}

function boot() {
  if (typeof window === 'undefined') return
  let lastTs = Date.now()
  setInterval(() => {
    try {
      const city = window.__REALCITY_CITY__
      if (!city) return
      const now = Date.now()
      const dt = Math.min(3, Math.max(0, (now - lastTs) / 1000))
      lastTs = now
      if (!started) {
        started = true
        init(city)
      }
      tick(city, dt)
    } catch {
      /* self-driving loop must never throw */
    }
  }, TICK_MS)
}

boot()

export {}
