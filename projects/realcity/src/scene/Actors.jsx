import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { pedestrianSignalForAxis, terrainHeight, trafficPhaseAt, trafficSignalForAxis, trafficSignalForMovement } from '../engine/cityEngine'
import { resolveBuildingCollision } from '../engine/collision'
import { buildAgentCognition, NPC_COGNITION_ARCHITECTURE, shouldStartNeedErrandFromCognition } from '../engine/agentCognition'
import { useCityStore } from '../engine/cityStore'
import { askLocalAutonomy, askLocalNPC, askLocalNPCConversation, fallbackLine, includesPlaceCandidate, llmStatus, matchRequestedPlace, planLocalNPCAction, styleNpcSpeech } from '../engine/localLLM'
import { buildTaxiRoute, routeCurveMetadata, routeDistance, sampleRoute, smoothRouteCorners, taxiPassengerDoorPoint, taxiSpawnForPickup } from '../engine/taxiRouting'
import { DIGITAL_HUMAN_SOURCE, makeHumanStyleRig } from './digitalHumanRig'
import { makeProceduralTexture } from './proceduralTextures'

const forward = new THREE.Vector3(0, 0, 1)
const TAXI_DISPATCH_SPEED = 18
const TAXI_RIDE_SPEED = 24
const TAXI_MIN_RIDE_SECONDS = 14
const TAXI_MAX_RIDE_SECONDS = 120
const TAXI_BOARDING_SECONDS = 1.45
const TAXI_HAIL_RADIUS = 92
const NPC_TAXI_MAX_ACTIVE = 4
const NPC_TAXI_MIN_DISTANCE = 520
const NPC_TAXI_DISPATCH_SPEED = 16
const NPC_TAXI_RIDE_SPEED = 22
const NPC_GLANCE_RADIUS = 24
const NPC_GLANCE_PULSE_RADIUS = 12
const WALK_ROUTE_WAYPOINT_RADIUS = 1.8
const WALK_ROUTE_REPLAN_SECONDS = 2.35
const WALK_ROUTE_MAX_WAYPOINTS = 12
const NEED_ERRAND_MIN_SECONDS = 22
const NEED_ERRAND_DURATION_MINUTES = 22

function formatTime(minutes) {
  return `${Math.floor(minutes / 60)}:${String(Math.floor(minutes % 60)).padStart(2, '0')}`
}

function smoothstep(t) {
  return t * t * (3 - 2 * t)
}

function clampValue(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function scheduleFor(agent, timeMinutes) {
  const hour = timeMinutes / 60
  return agent.schedule.find(slot => hour >= slot.start && hour < slot.end) || agent.schedule[0]
}

function needErrandProfile(agent) {
  const needs = agent.needs || {}
  if (needs.hunger > 0.82) {
    return {
      reason: 'hunger',
      label: 'food break',
      activity: 'getting food',
      targetKinds: ['cafe', 'retail', 'leisure', 'transit'],
      memory: 'I need to step out for food before I keep going.',
    }
  }
  if (needs.energy < 0.22) {
    return {
      reason: 'energy',
      label: 'rest stop',
      activity: 'taking a rest stop',
      targetKinds: ['park', 'cafe', 'leisure'],
      memory: 'I need a short rest before the next part of my day.',
    }
  }
  if (needs.social < 0.18) {
    return {
      reason: 'social',
      label: 'social check-in',
      activity: 'looking for a social check-in',
      targetKinds: ['cafe', 'park', 'retail', 'leisure', 'transit'],
      memory: 'I want to check in with someone before heading back.',
    }
  }
  return null
}

function chooseNeedErrandPlace(agent, places, profile) {
  if (!profile || !places?.size) return null
  const allPlaces = [...places.values()]
  const candidates = allPlaces.filter(place => profile.targetKinds.includes(place.kind))
  const fallback = agent.thirdId ? places.get(agent.thirdId) : null
  const pool = candidates.length ? candidates : fallback ? [fallback] : allPlaces
  if (!pool.length) return null
  const seed = hashValue(`${agent.id}_${profile.reason}_${agent.relationshipCount || 0}`)
  return pool[seed % pool.length]
}

function errandMinutesRemaining(errand, timeMinutes) {
  if (!errand) return 0
  const elapsed = ((timeMinutes - errand.startedAt) + 1440) % 1440
  return Math.max(0, errand.durationMinutes - elapsed)
}

function nearestRoadForPlace(place, roads = []) {
  if (!place || !roads.length) return null
  const linked = roads.find(road => road.id === place.roadId)
  if (linked) return linked

  let best = null
  let bestDistance = Infinity
  for (const road of roads) {
    const along = road.axis === 'x'
      ? clampValue(place.x, road.from, road.to)
      : clampValue(place.z, road.from, road.to)
    const distance = road.axis === 'x'
      ? Math.hypot(place.x - along, place.z - road.z)
      : Math.hypot(place.x - road.x, place.z - along)
    if (distance < bestDistance) {
      best = road
      bestDistance = distance
    }
  }
  return best
}

function sidewalkAccessForPlace(place, offset = { x: 0, z: 0 }, roads = []) {
  const road = nearestRoadForPlace(place, roads)
  if (!road) return null

  const curbOffset = road.width / 2 + 4.9
  if (road.axis === 'x') {
    const side = place.z >= road.z ? 1 : -1
    const x = clampValue(place.x + offset.x * 0.22, road.from + 6, road.to - 6)
    const z = road.z + side * curbOffset
    return {
      x,
      z,
      y: terrainHeight(x, z),
      name: place.name || 'destination',
      kind: place.kind,
      address: place.address,
      roadName: road.name,
      roadId: road.id,
      roadAxis: road.axis,
      entryRule: 'road-sidewalk-access',
    }
  }

  const side = place.x >= road.x ? 1 : -1
  const x = road.x + side * curbOffset
  const z = clampValue(place.z + offset.z * 0.22, road.from + 6, road.to - 6)
  return {
    x,
    z,
    y: terrainHeight(x, z),
    name: place.name || 'destination',
    kind: place.kind,
    address: place.address,
    roadName: road.name,
    roadId: road.id,
    roadAxis: road.axis,
    entryRule: 'road-sidewalk-access',
  }
}

function entranceTargetFor(destination, roads = [], offset = { x: 0, z: 0 }) {
  const interior = destination?.interior
  if (!interior) {
    const sidewalkAccess = roads?.length ? sidewalkAccessForPlace(destination, offset, roads) : null
    if (sidewalkAccess) {
      return {
        ...sidewalkAccess,
        placeName: destination.name,
        address: destination.address,
        roadName: destination.roadName || sidewalkAccess.roadName,
        entryRule: 'road-sidewalk-access',
      }
    }
    const x = destination.x
    const z = destination.z
    return {
      x,
      z,
      y: destination.y ?? terrainHeight(x, z),
      name: destination.name || 'destination',
      kind: destination.kind,
      address: destination.address,
      roadName: destination.roadName,
    }
  }

  const sidewalkAccess = sidewalkAccessForPlace(destination, offset, roads)
  if (sidewalkAccess) {
    return {
      ...sidewalkAccess,
      placeName: destination.name,
      interiorId: destination.id,
    }
  }

  const x = destination.x
  const z = destination.z - interior.depth / 2 - 4.8
  return {
    x,
    z,
    y: terrainHeight(x, z),
    name: `${destination.name || 'building'} entrance`,
    placeName: destination.name,
    kind: destination.kind,
    interiorId: destination.id,
    address: destination.address,
    roadName: destination.roadName,
  }
}

function scheduleTargetForPlace(place, offset = { x: 0, z: 0 }, roads = []) {
  if (!place?.interior?.solidWalls) {
    const x = place.x + offset.x
    const z = place.z + offset.z
    return pedestrianSafeTarget({
      x,
      z,
      y: terrainHeight(x, z),
      name: place.name,
    }, { x: place.x, z: place.z }, roads)
  }

  const entry = entranceTargetFor(place, roads, offset)
  if (entry.entryRule === 'road-sidewalk-access') {
    return {
      ...entry,
      name: place.name,
    }
  }

  const lateral = Math.max(-place.interior.doorWidth * 0.42, Math.min(place.interior.doorWidth * 0.42, offset.x * 0.18))
  const setback = 2.2 + Math.min(5.5, Math.abs(offset.z) * 0.18)
  const x = entry.x + lateral
  const z = entry.z - setback
  return {
    ...entry,
    x,
    z,
    y: terrainHeight(x, z),
    name: place.name,
  }
}

function isSharedMobilityMode(mode) {
  return mode === 'shared-bike' || mode === 'shared-scooter'
}

function sharedMobilityTripPoint(trip, key, activity) {
  const point = trip?.[key]
  if (!point) return null
  return {
    x: point.x,
    z: point.z,
    y: point.y ?? terrainHeight(point.x, point.z),
    name: point.name || (key === 'pickup' ? trip.pickupStationName : trip.returnStationName) || 'GBFS dock',
    roadName: point.roadName,
    roadId: point.roadId,
    roadAxis: point.roadAxis,
    activity,
    entryRule: 'gbfs-dock-access',
    sharedMobilityPhase: trip.phase,
  }
}

function targetFor(agent, places, timeMinutes, roads = []) {
  if (agent.needErrand?.targetId) {
    const place = places.get(agent.needErrand.targetId)
    if (place) {
      const trip = agent.needErrand.sharedMobilityTrip
      if (isSharedMobilityMode(agent.needErrand.mobilityMode) && trip) {
        if (trip.phase === 'walking-to-dock' || trip.phase === 'pickup') {
          return sharedMobilityTripPoint(trip, 'pickup', `walking to ${agent.needErrand.mobilityMode} dock`) || {
            ...scheduleTargetForPlace(place, agent.offset, roads),
            activity: agent.needErrand.activity || agent.needErrand.label || 'need errand',
            needErrand: agent.needErrand,
          }
        }
        if (trip.phase === 'riding-to-return-dock' || trip.phase === 'return') {
          return sharedMobilityTripPoint(trip, 'return', `${agent.needErrand.mobilityMode} ride to return dock`) || {
            ...scheduleTargetForPlace(place, agent.offset, roads),
            activity: agent.needErrand.activity || agent.needErrand.label || 'need errand',
            needErrand: agent.needErrand,
          }
        }
      }
      return {
        ...scheduleTargetForPlace(place, agent.offset, roads),
        activity: agent.needErrand.activity || agent.needErrand.label || 'need errand',
        needErrand: agent.needErrand,
      }
    }
  }

  const slot = scheduleFor(agent, timeMinutes)
  if (slot.target === 'home') {
    return { ...pedestrianSafeTarget(agent.home, agent.pos || agent.home, roads), activity: slot.activity }
  }
  const id = slot.target === 'work' ? agent.workId : agent.thirdId
  const place = places.get(id) || [...places.values()][0]
  return { ...scheduleTargetForPlace(place, agent.offset, roads), activity: slot.activity }
}

function crosswalkCandidatesForRoad(road, roads, intendedCrosswalk = null) {
  if (intendedCrosswalk && Number.isFinite(intendedCrosswalk.x) && Number.isFinite(intendedCrosswalk.z)) {
    const matching = roads.find(item => item.axis !== road.axis && (
      road.axis === 'x'
        ? Math.abs((item.x ?? intendedCrosswalk.x) - intendedCrosswalk.x) < 0.75
        : Math.abs((item.z ?? intendedCrosswalk.z) - intendedCrosswalk.z) < 0.75
    ))
    return [{
      ...(matching || {}),
      axis: matching?.axis || (road.axis === 'x' ? 'z' : 'x'),
      x: road.axis === 'x' ? intendedCrosswalk.x : road.x,
      z: road.axis === 'x' ? road.z : intendedCrosswalk.z,
      width: matching?.width || road.width,
      main: !!matching?.main,
    }]
  }
  return roads.filter(item => item.axis !== road.axis)
}

function crosswalkCorridorAt(x, z, road, roads, intendedCrosswalk = null) {
  const candidates = crosswalkCandidatesForRoad(road, roads, intendedCrosswalk)
  for (const cross of candidates) {
    const crossingX = road.axis === 'x' ? cross.x : road.x
    const crossingZ = road.axis === 'x' ? road.z : cross.z
    if (!Number.isFinite(crossingX) || !Number.isFinite(crossingZ)) continue
    if (road.axis === 'x') {
      if (crossingX < road.from || crossingX > road.to) continue
      if (crossingZ < (cross.from ?? -Infinity) || crossingZ > (cross.to ?? Infinity)) continue
    } else {
      if (crossingZ < road.from || crossingZ > road.to) continue
      if (crossingX < (cross.from ?? -Infinity) || crossingX > (cross.to ?? Infinity)) continue
    }
    const crossingWidth = Math.max(road.width || ROAD_WIDTH, cross.width || road.width || ROAD_WIDTH)
    const signalized = road.main && cross.main
    const priority = road.main || cross.main
    const halfLength = Math.max(8.4, crossingWidth * (signalized ? 0.78 : priority ? 0.68 : 0.56)) + 3.4
    const lateralLimit = (road.width || ROAD_WIDTH) / 2 + 4.85
    const longitudinal = road.axis === 'x' ? Math.abs(x - crossingX) : Math.abs(z - crossingZ)
    const lateral = road.axis === 'x' ? Math.abs(z - road.z) : Math.abs(x - road.x)
    if (longitudinal <= halfLength && lateral <= lateralLimit) {
      return {
        crosswalk: { x: crossingX, z: crossingZ },
        longitudinal,
        lateral,
        halfLength,
        lateralLimit,
        insideDriveLane: lateral <= (road.width || ROAD_WIDTH) / 2 - 0.2,
        control: signalized ? 'traffic-light' : priority ? 'priority-zebra' : 'uncontrolled-gap',
      }
    }
  }
  return null
}

function nearCrosswalk(x, z, road, roads) {
  return !!crosswalkCorridorAt(x, z, road, roads)
}

function pedestrianSafeTarget(target, from = target, roads = []) {
  if (!target || !roads.length) return target
  let x = target.x
  let z = target.z
  let adjustedRoadName = null

  for (const road of roads) {
    if (road.axis === 'x') {
      if (x < road.from || x > road.to) continue
      const lateral = z - road.z
      if (Math.abs(lateral) >= road.width / 2 - 0.35) continue
      const reference = Math.abs(lateral) > 0.15 ? lateral : (from.z ?? z) - road.z
      const side = reference >= 0 ? 1 : -1
      z = road.z + side * (road.width / 2 + 4.4)
      adjustedRoadName = road.name
    } else {
      if (z < road.from || z > road.to) continue
      const lateral = x - road.x
      if (Math.abs(lateral) >= road.width / 2 - 0.35) continue
      const reference = Math.abs(lateral) > 0.15 ? lateral : (from.x ?? x) - road.x
      const side = reference >= 0 ? 1 : -1
      x = road.x + side * (road.width / 2 + 4.4)
      adjustedRoadName = road.name
    }
  }

  if (!adjustedRoadName) return target
  return {
    ...target,
    x,
    z,
    y: terrainHeight(x, z),
    adjustedRoadName,
  }
}

function pushOutdoorFromSolid(city, x, z, radius = 0.86) {
  let px = x
  let pz = z
  const pushFromBox = item => {
    const width = item.w || item.interior?.width || item.footprint?.width || 0
    const depth = item.d || item.interior?.depth || item.footprint?.depth || 0
    if (!width || !depth) return false
    const dx = px - item.x
    const dz = pz - item.z
    const hw = width / 2 + radius
    const hd = depth / 2 + radius
    if (Math.abs(dx) >= hw || Math.abs(dz) >= hd) return false
    const pushX = hw - Math.abs(dx)
    const pushZ = hd - Math.abs(dz)
    if (pushX < pushZ) px = item.x + Math.sign(dx || -1) * hw
    else pz = item.z + Math.sign(dz || -1) * hd
    return true
  }

  for (let pass = 0; pass < 3; pass += 1) {
    let moved = false
    const buildings = city.getNearbyBuildings?.(px, pz) || city.buildings || []
    for (const building of buildings) {
      if (building.h < 3) continue
      moved = pushFromBox(building) || moved
    }
    for (const place of city.landmarks || []) {
      if (!place.interior?.solidWalls) continue
      moved = pushFromBox(place) || moved
    }
    if (!moved) break
  }

  return {
    x: px,
    z: pz,
    y: terrainHeight(px, pz),
  }
}

function roadSeparatesPoints(road, from, to) {
  if (road.axis === 'x') {
    const fromSide = from.z - road.z
    const toSide = to.z - road.z
    const crossesCenter = fromSide * toSide < 0
    const segmentMin = Math.min(from.x, to.x)
    const segmentMax = Math.max(from.x, to.x)
    return crossesCenter && segmentMax >= road.from && segmentMin <= road.to
  }
  const fromSide = from.x - road.x
  const toSide = to.x - road.x
  const crossesCenter = fromSide * toSide < 0
  const segmentMin = Math.min(from.z, to.z)
  const segmentMax = Math.max(from.z, to.z)
  return crossesCenter && segmentMax >= road.from && segmentMin <= road.to
}

function nearestCrosswalkForRoad(road, from, to, roads) {
  const crossRoads = roads.filter(item => item.axis !== road.axis)
  let best = null
  let bestScore = Infinity
  for (const cross of crossRoads) {
    const intersection = road.axis === 'x'
      ? { x: cross.x, z: road.z }
      : { x: road.x, z: cross.z }
    if (road.axis === 'x') {
      if (intersection.x < road.from || intersection.x > road.to) continue
      if (intersection.z < cross.from || intersection.z > cross.to) continue
    } else {
      if (intersection.z < road.from || intersection.z > road.to) continue
      if (intersection.x < cross.from || intersection.x > cross.to) continue
    }
    const score = Math.hypot(from.x - intersection.x, from.z - intersection.z) * 1.25 +
      Math.hypot(to.x - intersection.x, to.z - intersection.z) * 0.35 -
      (cross.main ? 14 : 0)
    if (score < bestScore) {
      best = { ...intersection, crossRoad: cross }
      bestScore = score
    }
  }
  return best
}

function crossingControlForRoad(road, crossRoad) {
  if (road?.main && crossRoad?.main) {
    return {
      type: 'traffic-light',
      priorityRule: 'SUMO tlLogic protected WALK; pedestrians start only when the crossed vehicle link is red',
      minimumGapSeconds: 0,
      source: 'Eclipse SUMO Traffic_Lights',
    }
  }
  if (road?.main || crossRoad?.main) {
    return {
      type: 'priority-zebra',
      priorityRule: 'zebra crossing with conservative vehicle-gap acceptance',
      minimumGapSeconds: 4.5,
      source: 'Eclipse SUMO Pedestrians priority crossing',
    }
  }
  return {
    type: 'uncontrolled-gap',
    priorityRule: 'uncontrolled local crossing; pedestrians enter only after a clear vehicle time slot',
    minimumGapSeconds: 5.2,
    source: 'Eclipse SUMO Pedestrians unprioritized crossing',
  }
}

function pedestrianWaypoint(agent, target, roads = []) {
  const from = { x: agent.pos.x, z: agent.pos.z }
  const crossingRoad = roads
    .filter(road => roadSeparatesPoints(road, from, target))
    .sort((a, b) => {
      const da = a.axis === 'x' ? Math.abs(from.z - a.z) : Math.abs(from.x - a.x)
      const db = b.axis === 'x' ? Math.abs(from.z - b.z) : Math.abs(from.x - b.x)
      return da - db
    })[0]

  if (!crossingRoad) {
    agent.walkPlan = {
      mode: 'direct',
      targetName: target.name || 'destination',
      waypointName: target.name || 'destination',
      waypoint: { x: target.x, z: target.z },
      distanceToTarget: Math.hypot(target.x - from.x, target.z - from.z),
      distanceToWaypoint: Math.hypot(target.x - from.x, target.z - from.z),
    }
    return target
  }

  const crosswalk = nearestCrosswalkForRoad(crossingRoad, from, target, roads)
  if (!crosswalk) {
    agent.walkPlan = {
      mode: 'curb-avoidance',
      roadName: crossingRoad.name,
      targetName: target.name || 'destination',
      waypointName: target.name || 'destination',
      waypoint: { x: target.x, z: target.z },
      distanceToTarget: Math.hypot(target.x - from.x, target.z - from.z),
      distanceToWaypoint: Math.hypot(target.x - from.x, target.z - from.z),
    }
    return target
  }

  const curbOffset = crossingRoad.width / 2 + 4.2
  let approach
  let exit
  if (crossingRoad.axis === 'x') {
    const fromSide = from.z >= crossingRoad.z ? 1 : -1
    const toSide = target.z >= crossingRoad.z ? 1 : -1
    approach = { x: crosswalk.x, z: crossingRoad.z + fromSide * curbOffset, y: terrainHeight(crosswalk.x, crossingRoad.z + fromSide * curbOffset), name: `${crossingRoad.name} crosswalk approach` }
    exit = { x: crosswalk.x, z: crossingRoad.z + toSide * curbOffset, y: terrainHeight(crosswalk.x, crossingRoad.z + toSide * curbOffset), name: `${crossingRoad.name} crosswalk exit` }
  } else {
    const fromSide = from.x >= crossingRoad.x ? 1 : -1
    const toSide = target.x >= crossingRoad.x ? 1 : -1
    approach = { x: crossingRoad.x + fromSide * curbOffset, z: crosswalk.z, y: terrainHeight(crossingRoad.x + fromSide * curbOffset, crosswalk.z), name: `${crossingRoad.name} crosswalk approach` }
    exit = { x: crossingRoad.x + toSide * curbOffset, z: crosswalk.z, y: terrainHeight(crossingRoad.x + toSide * curbOffset, crosswalk.z), name: `${crossingRoad.name} crosswalk exit` }
  }

  const approachDistance = Math.hypot(from.x - approach.x, from.z - approach.z)
  const shouldCross = approachDistance < 2.8 || nearCrosswalk(from.x, from.z, crossingRoad, roads)
  agent.walkPlan = {
    mode: shouldCross ? 'crosswalk-crossing' : 'sidewalk-waypoint',
    roadName: crossingRoad.name,
    crosswalk: { x: crosswalk.x, z: crosswalk.z },
    waypointName: shouldCross ? exit.name : approach.name,
    waypoint: shouldCross ? { x: exit.x, z: exit.z } : { x: approach.x, z: approach.z },
    targetName: target.name || 'destination',
    distanceToTarget: Math.hypot(target.x - from.x, target.z - from.z),
    distanceToWaypoint: shouldCross ? Math.hypot(exit.x - from.x, exit.z - from.z) : approachDistance,
  }
  return shouldCross ? exit : approach
}

function pointDistance(a, b) {
  return Math.hypot((a?.x || 0) - (b?.x || 0), (a?.z || 0) - (b?.z || 0))
}

function nowMs() {
  return typeof performance !== 'undefined' ? performance.now() : Date.now()
}

function walkTargetKey(target) {
  return [
    target?.name || target?.id || 'destination',
    Number(target?.x || 0).toFixed(1),
    Number(target?.z || 0).toFixed(1),
    target?.activity || '',
    target?.interiorId || '',
  ].join(':')
}

function routePoint(point, mode, details = {}) {
  const x = point.x
  const z = point.z
  return {
    ...point,
    x,
    z,
    y: point.y ?? terrainHeight(x, z),
    routeMode: mode,
    routeRoadId: details.roadId || point.roadId || null,
    routeRoadName: details.roadName || point.roadName || null,
    routeRoadAxis: details.roadAxis || point.roadAxis || null,
    waypointName: details.name || point.name || details.roadName || 'waypoint',
    crosswalk: details.crosswalk || null,
    crossingControl: details.crossingControl || point.crossingControl || null,
    crossingPriorityRule: details.crossingPriorityRule || point.crossingPriorityRule || null,
    crossingGapSeconds: details.crossingGapSeconds ?? point.crossingGapSeconds ?? null,
    crossingSource: details.crossingSource || point.crossingSource || null,
  }
}

function pushRoutePoint(waypoints, point, mode, details = {}) {
  if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.z)) return
  const previous = waypoints[waypoints.length - 1]
  if (previous && pointDistance(previous, point) < 0.9) {
    previous.routeMode = previous.routeMode === 'crosswalk-crossing' ? previous.routeMode : mode
    previous.routeRoadId = previous.routeRoadId || details.roadId || point.roadId || null
    previous.routeRoadAxis = previous.routeRoadAxis || details.roadAxis || point.roadAxis || null
    previous.crossingControl = previous.crossingControl || details.crossingControl || point.crossingControl || null
    previous.crossingPriorityRule = previous.crossingPriorityRule || details.crossingPriorityRule || point.crossingPriorityRule || null
    previous.crossingGapSeconds = previous.crossingGapSeconds ?? details.crossingGapSeconds ?? point.crossingGapSeconds ?? null
    previous.crossingSource = previous.crossingSource || details.crossingSource || point.crossingSource || null
    return
  }
  waypoints.push(routePoint(point, mode, details))
}

function crosswalkPairForRoad(road, from, to, roads) {
  const crosswalk = nearestCrosswalkForRoad(road, from, to, roads)
  if (!crosswalk) return null

  const curbOffset = road.width / 2 + 4.2
  const control = crossingControlForRoad(road, crosswalk.crossRoad)
  if (road.axis === 'x') {
    const fromSide = from.z >= road.z ? 1 : -1
    const toSide = to.z >= road.z ? 1 : -1
    const approachZ = road.z + fromSide * curbOffset
    const exitZ = road.z + toSide * curbOffset
    return {
      roadId: road.id,
      roadName: road.name,
      roadAxis: road.axis,
      crossingControl: control.type,
      crossingPriorityRule: control.priorityRule,
      crossingGapSeconds: control.minimumGapSeconds,
      crossingSource: control.source,
      crosswalk: { x: crosswalk.x, z: road.z },
      approach: {
        x: crosswalk.x,
        z: approachZ,
        y: terrainHeight(crosswalk.x, approachZ),
        name: `${road.name} crosswalk approach`,
      },
      exit: {
        x: crosswalk.x,
        z: exitZ,
        y: terrainHeight(crosswalk.x, exitZ),
        name: `${road.name} crosswalk exit`,
      },
    }
  }

  const fromSide = from.x >= road.x ? 1 : -1
  const toSide = to.x >= road.x ? 1 : -1
  const approachX = road.x + fromSide * curbOffset
  const exitX = road.x + toSide * curbOffset
  return {
    roadId: road.id,
    roadName: road.name,
    roadAxis: road.axis,
    crossingControl: control.type,
    crossingPriorityRule: control.priorityRule,
    crossingGapSeconds: control.minimumGapSeconds,
    crossingSource: control.source,
    crosswalk: { x: road.x, z: crosswalk.z },
    approach: {
      x: approachX,
      z: crosswalk.z,
      y: terrainHeight(approachX, crosswalk.z),
      name: `${road.name} crosswalk approach`,
    },
    exit: {
      x: exitX,
      z: crosswalk.z,
      y: terrainHeight(exitX, crosswalk.z),
      name: `${road.name} crosswalk exit`,
    },
  }
}

function nearestSeparatingRoad(from, to, roads, crossedRoads = new Set()) {
  return roads
    .filter(road => roadSeparatesPoints(road, from, to))
    .sort((a, b) => {
      const da = a.axis === 'x' ? Math.abs(from.z - a.z) : Math.abs(from.x - a.x)
      const db = b.axis === 'x' ? Math.abs(from.z - b.z) : Math.abs(from.x - b.x)
      const crossedPenaltyA = crossedRoads.has(a.id) ? 10000 : 0
      const crossedPenaltyB = crossedRoads.has(b.id) ? 10000 : 0
      return da + crossedPenaltyA - (db + crossedPenaltyB)
    })[0] || null
}

function buildPedestrianRoute(from, target, roads = []) {
  const safeTarget = pedestrianSafeTarget(target, from, roads)
  const waypoints = []
  let cursor = { x: from.x, z: from.z, y: terrainHeight(from.x, from.z), name: 'current position' }
  const recovery = pedestrianSafeTarget({ ...cursor, name: 'nearest sidewalk' }, safeTarget, roads)

  if (recovery.adjustedRoadName && pointDistance(cursor, recovery) > 0.75) {
    pushRoutePoint(waypoints, recovery, 'sidewalk-recovery', {
      roadName: recovery.adjustedRoadName,
      name: `${recovery.adjustedRoadName} sidewalk`,
    })
    cursor = recovery
  }

  const crossedRoads = new Set()
  for (let guard = 0; guard < WALK_ROUTE_MAX_WAYPOINTS; guard += 1) {
    const road = nearestSeparatingRoad(cursor, safeTarget, roads, crossedRoads)
    if (!road) break
    const pair = crosswalkPairForRoad(road, cursor, safeTarget, roads)
    if (!pair) break
    if (pointDistance(cursor, pair.approach) > WALK_ROUTE_WAYPOINT_RADIUS) {
      pushRoutePoint(waypoints, pair.approach, 'sidewalk-waypoint', {
        roadId: pair.roadId,
        roadName: pair.roadName,
        roadAxis: pair.roadAxis,
        name: pair.approach.name,
        crosswalk: pair.crosswalk,
        crossingControl: pair.crossingControl,
        crossingPriorityRule: pair.crossingPriorityRule,
        crossingGapSeconds: pair.crossingGapSeconds,
        crossingSource: pair.crossingSource,
      })
    }
    pushRoutePoint(waypoints, pair.exit, 'crosswalk-crossing', {
      roadId: pair.roadId,
      roadName: pair.roadName,
      roadAxis: pair.roadAxis,
      name: pair.exit.name,
      crosswalk: pair.crosswalk,
      crossingControl: pair.crossingControl,
      crossingPriorityRule: pair.crossingPriorityRule,
      crossingGapSeconds: pair.crossingGapSeconds,
      crossingSource: pair.crossingSource,
    })
    cursor = pair.exit
    crossedRoads.add(road.id)
    if (pointDistance(cursor, safeTarget) < WALK_ROUTE_WAYPOINT_RADIUS) break
  }

  if (pointDistance(waypoints[waypoints.length - 1] || cursor, safeTarget) > 0.9 || waypoints.length === 0) {
    pushRoutePoint(waypoints, safeTarget, waypoints.length ? 'destination-approach' : 'direct', {
      roadName: safeTarget.roadName || safeTarget.adjustedRoadName,
      name: safeTarget.name || 'destination',
    })
  }

  return waypoints.slice(0, WALK_ROUTE_MAX_WAYPOINTS)
}

function ensureWalkRoute(agent, target, roads = [], force = false) {
  if (!roads.length) return null
  const key = walkTargetKey(target)
  const existing = agent.walkRoute
  if (!force && existing?.targetKey === key && existing.waypoints?.length) return existing

  const waypoints = buildPedestrianRoute(agent.pos, target, roads)
  agent.walkRoute = {
    targetKey: key,
    targetName: target.name || 'destination',
    activity: target.activity || agent.activity || 'walking',
    waypoints,
    index: 0,
    createdAt: nowMs(),
    replanCount: force ? (existing?.replanCount || 0) + 1 : existing?.replanCount || 0,
    final: { x: target.x, z: target.z },
  }
  agent.stuckTimer = 0
  agent.lastRouteDistance = pointDistance(agent.pos, target)
  agent.routeStatus = waypoints.length > 1
    ? `following ${waypoints.length} sidewalk waypoints to ${target.name || 'destination'}`
    : `walking to ${target.name || 'destination'}`
  return agent.walkRoute
}

function roadForWaypoint(waypoint, roads = []) {
  if (!waypoint || !roads.length) return null
  return roads.find(road => road.id === waypoint.routeRoadId) ||
    roads.find(road => road.name === waypoint.routeRoadName && road.axis === waypoint.routeRoadAxis) ||
    roads.find(road => road.name === waypoint.routeRoadName) ||
    null
}

function pedestrianSignalForCrossing(road, timeMinutes = 0, waypoint = null, mobilitySystem = null) {
  const crossingControl = waypoint?.crossingControl || 'traffic-light'
  if (!road) return { vehicleSignal: 'unknown', walk: true, clearance: false, label: 'unsignalized crossing', crossingControl }
  if (crossingControl !== 'traffic-light') {
    return {
      vehicleSignal: 'gap-check',
      walk: true,
      clearance: false,
      noStart: false,
      pedestrianLinkState: 'G',
      secondsRemaining: 0,
      sourceProgram: crossingControl === 'priority-zebra' ? 'SUMO_PRIORITY_CROSSING' : 'SUMO_UNCONTROLLED_GAP',
      phase: 'gap-acceptance',
      phaseId: crossingControl,
      activeVehicleAxis: null,
      crossingControl,
      crossingPriorityRule: waypoint?.crossingPriorityRule || null,
      minimumGapSeconds: waypoint?.crossingGapSeconds || 4.5,
      requiresGap: true,
      label: crossingControl === 'priority-zebra' ? 'priority zebra gap' : 'uncontrolled clear gap',
    }
  }
  const signal = pedestrianSignalForAxis(road.axis, timeMinutes, mobilitySystem)
  return {
    ...signal,
    crossingControl,
    label: signal.label,
  }
}

function crossingVehicleGapStatus(road, waypoint, store) {
  if (!road || !waypoint?.crosswalk) return { clear: true, nearestSeconds: null, nearestVehicleId: null }
  const minimumGapSeconds = Number(waypoint.crossingGapSeconds || 4.5)
  const crossing = waypoint.crosswalk
  let nearestSeconds = Infinity
  let nearestVehicleId = null
  for (const sample of store.vehicleSamples || []) {
    const sameRoad = sample.laneKey?.startsWith(`${road.id}:`) || sample.activeRoadName === road.name
    if (!sameRoad || !Number.isFinite(sample.x) || !Number.isFinite(sample.z)) continue
    const lateral = road.axis === 'x' ? Math.abs(sample.z - road.z) : Math.abs(sample.x - road.x)
    if (lateral > road.width * 0.78) continue
    const longitudinal = road.axis === 'x' ? Math.abs(sample.x - crossing.x) : Math.abs(sample.z - crossing.z)
    if (longitudinal > 46) continue
    const speed = Math.max(1, Number(sample.speed) || 1)
    const seconds = longitudinal / speed
    if (seconds < nearestSeconds) {
      nearestSeconds = seconds
      nearestVehicleId = sample.id
    }
  }
  if (!Number.isFinite(nearestSeconds)) return { clear: true, nearestSeconds: null, nearestVehicleId: null }
  const clear = nearestSeconds >= minimumGapSeconds
  return {
    clear,
    nearestSeconds: Number(nearestSeconds.toFixed(2)),
    nearestVehicleId,
    minimumGapSeconds,
  }
}

function pedestrianInsideCrosswalkRoad(agent, road) {
  if (!road) return false
  const roads = useCityStore.getState().city?.roads || []
  const corridor = crosswalkCorridorAt(agent.pos.x, agent.pos.z, road, roads, agent.walkPlan?.crosswalk)
  if (!corridor) return false
  if (road.axis === 'x') {
    return agent.pos.x >= road.from - 2 &&
      agent.pos.x <= road.to + 2 &&
      Math.abs(agent.pos.z - road.z) <= road.width / 2 + 1.15
  }
  return agent.pos.z >= road.from - 2 &&
    agent.pos.z <= road.to + 2 &&
    Math.abs(agent.pos.x - road.x) <= road.width / 2 + 1.15
}

function activeCrosswalkForRoad(agent, road) {
  const plan = agent?.walkPlan
  const route = agent?.walkRoute
  const waypoint = route?.waypoints?.[route.index]
  if (plan?.crosswalk && (
    plan.roadId === road.id ||
    plan.roadName === road.name ||
    (!plan.roadId && !plan.roadName && plan.roadAxis === road.axis && /crosswalk/i.test(plan.mode || ''))
  )) {
    return plan.crosswalk
  }
  if (waypoint?.routeMode === 'crosswalk-crossing' && waypoint.crosswalk && (
    waypoint.routeRoadId === road.id ||
    waypoint.routeRoadName === road.name ||
    (!waypoint.routeRoadId && !waypoint.routeRoadName && waypoint.routeRoadAxis === road.axis)
  )) {
    return waypoint.crosswalk
  }
  return null
}

function activeCrosswalkCorridor(agent, point, roads = []) {
  if (!agent || !point || !roads.length) return null
  for (const road of roads) {
    const intended = activeCrosswalkForRoad(agent, road)
    if (!intended) continue
    const corridor = crosswalkCorridorAt(point.x, point.z, road, roads, intended)
    if (corridor) return { ...corridor, road }
  }
  return null
}

function currentWalkWaypoint(agent, target, roads = []) {
  const route = ensureWalkRoute(agent, target, roads)
  if (!route?.waypoints?.length) {
    agent.walkPlan = {
      mode: 'direct',
      targetName: target.name || 'destination',
      waypointName: target.name || 'destination',
      waypoint: { x: target.x, z: target.z },
      distanceToTarget: pointDistance(agent.pos, target),
      distanceToWaypoint: pointDistance(agent.pos, target),
      stableRoute: false,
    }
    return target
  }

  while (
    route.index < route.waypoints.length - 1 &&
    pointDistance(agent.pos, route.waypoints[route.index]) < WALK_ROUTE_WAYPOINT_RADIUS
  ) {
    route.index += 1
  }

  const waypoint = route.waypoints[route.index] || target
  const crossingRoad = waypoint.routeMode === 'crosswalk-crossing' ? roadForWaypoint(waypoint, roads) : null
  const crossingSignal = crossingRoad ? pedestrianSignalForCrossing(crossingRoad, useCityStore.getState().timeMinutes, waypoint, useCityStore.getState().city?.mobilitySystem) : null
  const crossingCorridor = crossingRoad ? crosswalkCorridorAt(agent.pos.x, agent.pos.z, crossingRoad, roads, waypoint.crosswalk) : null
  agent.walkPlan = {
    mode: waypoint.routeMode || 'direct',
    targetName: route.targetName || target.name || 'destination',
    waypointName: waypoint.waypointName || waypoint.name || route.targetName,
    waypoint: { x: waypoint.x, z: waypoint.z },
    crosswalk: waypoint.crosswalk,
    roadId: waypoint.routeRoadId || null,
    roadName: waypoint.routeRoadName || waypoint.roadName || null,
    roadAxis: waypoint.routeRoadAxis || crossingRoad?.axis || null,
    crosswalkSignal: crossingSignal?.label || null,
    crosswalkVehicleSignal: crossingSignal?.vehicleSignal || null,
    crosswalkControl: waypoint.crossingControl || crossingSignal?.crossingControl || null,
    crosswalkPriorityRule: waypoint.crossingPriorityRule || crossingSignal?.crossingPriorityRule || null,
    crosswalkGapSeconds: waypoint.crossingGapSeconds ?? crossingSignal?.minimumGapSeconds ?? null,
    crosswalkSource: waypoint.crossingSource || crossingSignal?.sourceProgram || null,
    crosswalkCorridorMeters: crossingCorridor ? Number((crossingCorridor.halfLength * 2).toFixed(1)) : null,
    crosswalkLaneHold: false,
    crosswalkWaiting: false,
    routeIndex: route.index,
    routePoints: route.waypoints.length,
    stableRoute: true,
    replanCount: route.replanCount || 0,
    distanceToTarget: pointDistance(agent.pos, target),
    distanceToWaypoint: pointDistance(agent.pos, waypoint),
  }
  return waypoint
}

function updateWalkProgress(agent, previous, safe, target, delta, roads = []) {
  const moved = pointDistance(previous, safe)
  const remaining = pointDistance(safe, target)
  const madeProgress = agent.lastRouteDistance == null || remaining < agent.lastRouteDistance - 0.08
  if (madeProgress || moved > 0.035 || remaining < 2.2) {
    agent.stuckTimer = Math.max(0, (agent.stuckTimer || 0) - delta * 2.5)
  } else {
    agent.stuckTimer = (agent.stuckTimer || 0) + delta
  }
  agent.lastRouteDistance = remaining

  const heldCrosswalk = activeCrosswalkCorridor(agent, safe, roads)
  if (heldCrosswalk?.insideDriveLane) {
    agent.stuckTimer = Math.min(agent.stuckTimer || 0, WALK_ROUTE_REPLAN_SECONDS * 0.45)
    agent.routeStatus = `holding ${heldCrosswalk.road.name} crosswalk corridor`
    if (agent.walkPlan) {
      agent.walkPlan.crosswalkLaneHold = true
      agent.walkPlan.crosswalkCorridorMeters = Number((heldCrosswalk.halfLength * 2).toFixed(1))
      agent.walkPlan.crosswalkControl = agent.walkPlan.crosswalkControl || heldCrosswalk.control
    }
    return
  }

  if (agent.stuckTimer <= WALK_ROUTE_REPLAN_SECONDS) return
  const recovery = pedestrianSafeTarget({ x: safe.x, z: safe.z, name: 'sidewalk recovery' }, target, roads)
  if (recovery.adjustedRoadName && pointDistance(safe, recovery) > 0.4 && pointDistance(safe, recovery) < 9) {
    agent.pos.x += (recovery.x - agent.pos.x) * 0.32
    agent.pos.z += (recovery.z - agent.pos.z) * 0.32
    agent.pos.y = terrainHeight(agent.pos.x, agent.pos.z) + 0.95
  }
  agent.walkRoute = null
  agent.routeStatus = `replanning sidewalk route to ${target.name || 'destination'}`
  agent.stuckTimer = 0
}

function enforcePedestrianNorms(agent, previous, next, roads = []) {
  let x = next.x
  let z = next.z

  for (const road of roads) {
    if (road.axis === 'x') {
      if (x < road.from || x > road.to) continue
      const lateral = z - road.z
      if (Math.abs(lateral) >= road.width / 2 - 0.35) continue
      const intended = activeCrosswalkForRoad(agent, road)
      const corridor = crosswalkCorridorAt(x, z, road, roads, intended) || crosswalkCorridorAt(x, z, road, roads)
      if (corridor) {
        if (intended && agent.walkPlan) {
          agent.walkPlan.crosswalkLaneHold = true
          agent.walkPlan.crosswalkCorridorMeters = Number((corridor.halfLength * 2).toFixed(1))
          agent.walkPlan.crosswalkControl = agent.walkPlan.crosswalkControl || corridor.control
        }
        continue
      }
      const previousSide = previous.z >= road.z ? 1 : -1
      z = road.z + previousSide * (road.width / 2 + 3.2)
    } else {
      if (z < road.from || z > road.to) continue
      const lateral = x - road.x
      if (Math.abs(lateral) >= road.width / 2 - 0.35) continue
      const intended = activeCrosswalkForRoad(agent, road)
      const corridor = crosswalkCorridorAt(x, z, road, roads, intended) || crosswalkCorridorAt(x, z, road, roads)
      if (corridor) {
        if (intended && agent.walkPlan) {
          agent.walkPlan.crosswalkLaneHold = true
          agent.walkPlan.crosswalkCorridorMeters = Number((corridor.halfLength * 2).toFixed(1))
          agent.walkPlan.crosswalkControl = agent.walkPlan.crosswalkControl || corridor.control
        }
        continue
      }
      const previousSide = previous.x >= road.x ? 1 : -1
      x = road.x + previousSide * (road.width / 2 + 3.2)
    }
  }

  return { x, z }
}

function resolveAgentMovement(agent, previous, next, target, cityOrRoads) {
  const city = Array.isArray(cityOrRoads) ? null : cityOrRoads
  const roads = Array.isArray(cityOrRoads) ? cityOrRoads : cityOrRoads?.roads
  let safe = roads?.length ? enforcePedestrianNorms(agent, previous, next, roads) : next

  if (!city?.getNearbyBuildings) return safe

  const [fullX, fullZ] = resolveBuildingCollision(city, previous.x, previous.z, safe.x, safe.z, 0.68)
  const collided = Math.hypot(fullX - safe.x, fullZ - safe.z) > 0.03
  if (!collided) {
    agent.blockedContacts = 0
    return { x: fullX, z: fullZ }
  }

  const [xOnlyX, xOnlyZ] = resolveBuildingCollision(city, previous.x, previous.z, safe.x, previous.z, 0.68)
  const [zOnlyX, zOnlyZ] = resolveBuildingCollision(city, previous.x, previous.z, previous.x, safe.z, 0.68)
  const candidates = [
    { x: fullX, z: fullZ },
    { x: xOnlyX, z: xOnlyZ },
    { x: zOnlyX, z: zOnlyZ },
    previous,
  ]
  let best = candidates[0]
  let bestScore = Infinity
  for (const candidate of candidates) {
    const progress = Math.hypot(candidate.x - previous.x, candidate.z - previous.z)
    const score = Math.hypot(target.x - candidate.x, target.z - candidate.z) - progress * 0.35
    if (score < bestScore) {
      best = candidate
      bestScore = score
    }
  }
  agent.blockedContacts = (agent.blockedContacts || 0) + 1
  if (best === previous) agent.heading += 0.18
  else if (collided) agent.heading += Math.sin(agent.id.length + nowMs() * 0.001) * 0.08
  return best
}

function moveAgentToward(agent, target, delta, speed, cityOrRoads) {
  const city = Array.isArray(cityOrRoads) ? null : cityOrRoads
  const roads = Array.isArray(cityOrRoads) ? cityOrRoads : cityOrRoads?.roads
  const safeTarget = roads?.length ? pedestrianSafeTarget(target, agent.pos, roads) : target
  const waypoint = roads?.length ? currentWalkWaypoint(agent, safeTarget, roads) : safeTarget
  if (roads?.length && waypoint.routeMode === 'crosswalk-crossing') {
    const crossingRoad = roadForWaypoint(waypoint, roads)
    const store = useCityStore.getState()
    const signal = pedestrianSignalForCrossing(crossingRoad, store.timeMinutes, waypoint, city?.mobilitySystem || store.city?.mobilitySystem)
    const gap = signal.requiresGap ? crossingVehicleGapStatus(crossingRoad, waypoint, store) : { clear: true }
    const alreadyInRoad = pedestrianInsideCrosswalkRoad(agent, crossingRoad)
    const corridor = crossingRoad ? crosswalkCorridorAt(agent.pos.x, agent.pos.z, crossingRoad, roads, waypoint.crosswalk) : null
    if ((!signal.walk || !gap.clear) && !alreadyInRoad) {
      agent.crosswalkWaitTimer = (agent.crosswalkWaitTimer || 0) + delta
      agent.activity = signal.requiresGap ? 'waiting for traffic gap' : 'waiting for walk signal'
      agent.currentIntent = signal.requiresGap
        ? `waiting at ${crossingRoad?.name || 'crosswalk'} for a ${gap.minimumGapSeconds || signal.minimumGapSeconds || 4.5}s safe vehicle gap`
        : `waiting at ${crossingRoad?.name || 'crosswalk'} while traffic has ${signal.vehicleSignal}`
      agent.walkPlan = {
        ...(agent.walkPlan || {}),
        mode: 'crosswalk-waiting',
        crosswalkWaiting: true,
        crosswalkSignal: gap.clear === false ? 'waiting for safe gap' : signal.label,
        crosswalkVehicleSignal: gap.clear === false ? 'approaching vehicle' : signal.vehicleSignal,
        crosswalkPhaseId: signal.phaseId,
        crosswalkNoStart: signal.noStart || gap.clear === false,
        crosswalkCountdown: gap.clear === false ? gap.nearestSeconds : signal.secondsRemaining,
        crosswalkProgram: signal.sourceProgram,
        crosswalkControl: waypoint.crossingControl || signal.crossingControl || null,
        crosswalkPriorityRule: waypoint.crossingPriorityRule || signal.crossingPriorityRule || null,
        crosswalkGapClear: gap.clear ?? null,
        crosswalkGapSeconds: gap.minimumGapSeconds ?? signal.minimumGapSeconds ?? waypoint.crossingGapSeconds ?? null,
        crosswalkNearestVehicleId: gap.nearestVehicleId || null,
        crosswalkLaneHold: false,
        crosswalkCorridorMeters: corridor ? Number((corridor.halfLength * 2).toFixed(1)) : null,
        roadId: crossingRoad?.id || agent.walkPlan?.roadId || null,
        roadName: crossingRoad?.name || agent.walkPlan?.roadName || null,
        roadAxis: crossingRoad?.axis || agent.walkPlan?.roadAxis || null,
        distanceToTarget: pointDistance(agent.pos, safeTarget),
        distanceToWaypoint: pointDistance(agent.pos, waypoint),
      }
      if (agent.crosswalkWaitTimer > 1.4 && (!agent.lastCrosswalkWaitAt || nowMs() - agent.lastCrosswalkWaitAt > 5000)) {
        agent.lastCrosswalkWaitAt = nowMs()
        useCityStore.getState().addCityEvent({
          id: `crosswalk_wait_${agent.id}_${Math.floor(useCityStore.getState().timeMinutes * 10)}`,
          kind: 'crosswalk',
          agentId: agent.id,
          agentName: agent.name,
          placeName: crossingRoad?.name || agent.placeName,
          topic: signal.requiresGap ? 'crossing gap wait' : 'walk signal wait',
          text: signal.requiresGap
            ? `${agent.name} waits at ${crossingRoad?.name || 'a crosswalk'} because a vehicle gap is below ${gap.minimumGapSeconds || signal.minimumGapSeconds || 4.5}s under ${waypoint.crossingControl || 'gap'} rules.`
            : `${agent.name} waits at ${crossingRoad?.name || 'a crosswalk'} because ${signal.phaseId || 'the signal phase'} gives ${signal.vehicleSignal} to vehicle traffic and no pedestrian start.`,
        })
      }
      return Math.hypot(safeTarget.x - agent.pos.x, safeTarget.z - agent.pos.z)
    }
    if (agent.walkPlan) {
      agent.walkPlan.mode = 'crosswalk-crossing'
      agent.walkPlan.crosswalkWaiting = false
      agent.walkPlan.crosswalkLaneHold = false
      agent.walkPlan.crosswalkCorridorMeters = corridor ? Number((corridor.halfLength * 2).toFixed(1)) : agent.walkPlan.crosswalkCorridorMeters ?? null
      agent.walkPlan.crosswalkControl = waypoint.crossingControl || agent.walkPlan.crosswalkControl || corridor?.control || null
    }
  }
  agent.crosswalkWaitTimer = 0
  const dx = waypoint.x - agent.pos.x
  const dz = waypoint.z - agent.pos.z
  const distance = Math.hypot(dx, dz)
  if (distance <= 0.001) return Math.hypot(safeTarget.x - agent.pos.x, safeTarget.z - agent.pos.z)

  const desired = Math.atan2(dx, dz)
  const turn = Math.atan2(Math.sin(desired - agent.heading), Math.cos(desired - agent.heading))
  agent.heading += turn * Math.min(1, delta * 3.5)
  const step = Math.min(distance, speed * delta)
  const previous = { x: agent.pos.x, z: agent.pos.z }
  const next = {
    x: agent.pos.x + Math.sin(agent.heading) * step,
    z: agent.pos.z + Math.cos(agent.heading) * step,
  }
  const safe = resolveAgentMovement(agent, previous, next, waypoint, cityOrRoads)
  agent.pos.x = safe.x
  agent.pos.z = safe.z
  agent.pos.y = terrainHeight(agent.pos.x, agent.pos.z) + 0.95
  if (roads?.length) updateWalkProgress(agent, previous, safe, safeTarget, delta, roads)
  return Math.hypot(safeTarget.x - agent.pos.x, safeTarget.z - agent.pos.z)
}

function advanceTaxi(taxi, delta) {
  const now = performance.now()
  const elapsed = taxi.lastAdvancedAt
    ? Math.min(0.5, Math.max(delta, (now - taxi.lastAdvancedAt) / 1000))
    : delta
  taxi.lastAdvancedAt = now
  taxi.progress = Math.min(taxi.routeMeters, (taxi.progress || 0) + taxi.speed * elapsed)
  const pose = sampleRoute(taxi.path, taxi.progress)
  taxi.pose = { x: pose.x, z: pose.z, heading: pose.heading, yaw: pose.heading, routeCurve: pose.routeCurve || null }
  taxi.routeCurve = pose.routeCurve || null
  return pose
}

function roadLaneOffset(road, direction) {
  const laneOffset = road.width * (road.main ? 0.27 : 0.22)
  return road.axis === 'x' ? direction * laneOffset : -direction * laneOffset
}

function roadLanePoint(road, along, direction) {
  const lane = roadLaneOffset(road, direction)
  if (road.axis === 'x') return { x: Math.max(road.from, Math.min(road.to, along)), z: road.z + lane }
  return { x: road.x + lane, z: Math.max(road.from, Math.min(road.to, along)) }
}

function roadAlongFromPoint(road, point) {
  return road.axis === 'x' ? point.x : point.z
}

function tValueForRoadAlong(road, direction, along) {
  const span = Math.max(1, road.to - road.from)
  const normalized = clampValue((along - road.from) / span, 0, 1)
  return direction > 0 ? normalized : 1 - normalized
}

function vehicleDirectionVector(road, direction) {
  if (road.axis === 'x') return { x: direction > 0 ? 1 : -1, z: 0 }
  return { x: 0, z: direction > 0 ? 1 : -1 }
}

function turnVectorForIntent(vector, intent) {
  if (intent === 'right') return { x: vector.z, z: -vector.x }
  if (intent === 'left') return { x: -vector.z, z: vector.x }
  return vector
}

function directionForRoadVector(road, vector) {
  if (road.axis === 'x') return vector.x >= 0 ? 1 : -1
  return vector.z >= 0 ? 1 : -1
}

function cubicPoint(a, b, c, d, t) {
  const u = 1 - t
  const uu = u * u
  const tt = t * t
  return {
    x: a.x * uu * u + b.x * 3 * uu * t + c.x * 3 * u * tt + d.x * tt * t,
    z: a.z * uu * u + b.z * 3 * uu * t + c.z * 3 * u * tt + d.z * tt * t,
  }
}

function cubicDerivative(a, b, c, d, t) {
  const u = 1 - t
  return {
    x: 3 * u * u * (b.x - a.x) + 6 * u * t * (c.x - b.x) + 3 * t * t * (d.x - c.x),
    z: 3 * u * u * (b.z - a.z) + 6 * u * t * (c.z - b.z) + 3 * t * t * (d.z - c.z),
  }
}

function estimateCubicLength(a, b, c, d) {
  let length = 0
  let previous = a
  for (let i = 1; i <= 12; i += 1) {
    const point = cubicPoint(a, b, c, d, i / 12)
    length += Math.hypot(point.x - previous.x, point.z - previous.z)
    previous = point
  }
  return Math.max(1, length)
}

function applyVehicleTurnIntent(car, intent, road = car.road) {
  car.turnIntent = intent
  car.turnLaneRule = intent === 'straight'
    ? 'through-lane'
    : intent === 'right'
      ? 'right-turn-yield-area'
      : 'left-turn-pocket-before-stop-bar'
  car.turnSignalDistanceMeters = road?.main ? 52 : 34
  car.plannedTurnSignalSide = intent === 'left' ? 'left-side-turn' : intent === 'right' ? 'right-side-turn' : null
}

function nextProceduralTurnIntent(car) {
  const options = ['straight', 'straight', 'straight', 'right', 'left', 'straight', 'right']
  const index = hashValue(`${car.id}:${car.turnsCompleted || 0}:${car.road?.id || ''}`) % options.length
  return options[index]
}

function vehicleTurnArcPose(car) {
  const arc = car.turnArc
  if (!arc) return null
  const t = clampValue((arc.progress || 0) / Math.max(1, arc.length || 1), 0, 1)
  const point = cubicPoint(arc.start, arc.control1, arc.control2, arc.end, t)
  const derivative = cubicDerivative(arc.start, arc.control1, arc.control2, arc.end, t)
  const heading = Math.hypot(derivative.x, derivative.z) > 0.001
    ? Math.atan2(derivative.x, derivative.z)
    : arc.toHeading
  return {
    x: point.x,
    z: point.z,
    yaw: heading,
    heading,
    road: t < 0.55 ? arc.fromRoad : arc.toRoad,
    direction: t < 0.55 ? arc.fromDirection : arc.toDirection,
    turnArc: true,
    turnArcProgress: t,
    turnArcId: arc.id,
  }
}

function beginVehicleTurnArc(car, state, turnContext) {
  if (!turnContext?.crossRoad || !turnContext.intersectionCenter || car.turnArc) return null
  const fromVector = vehicleDirectionVector(state.road, state.direction)
  const toVector = turnVectorForIntent(fromVector, turnContext.direction)
  const toRoad = turnContext.crossRoad
  const toDirection = directionForRoadVector(toRoad, toVector)
  const exitDistance = Math.max(18, Math.min(34, state.road.width * 1.1 + toRoad.width * 0.9))
  const endAlong = toRoad.axis === 'x'
    ? turnContext.intersectionCenter.x + toDirection * exitDistance
    : turnContext.intersectionCenter.z + toDirection * exitDistance
  const start = { x: state.pose.x, z: state.pose.z }
  const end = roadLanePoint(toRoad, endAlong, toDirection)
  const radius = Math.max(12, Math.min(28, exitDistance * 0.78))
  const control1 = {
    x: start.x + fromVector.x * radius,
    z: start.z + fromVector.z * radius,
  }
  const control2 = {
    x: end.x - toVector.x * radius,
    z: end.z - toVector.z * radius,
  }
  const length = estimateCubicLength(start, control1, control2, end)
  car.turnArc = {
    id: `${car.id}_${Date.now()}`,
    intent: turnContext.direction,
    fromRoad: state.road,
    fromRoadName: state.road.name,
    fromDirection: state.direction,
    toRoad,
    toRoadName: toRoad.name,
    toDirection,
    start,
    end,
    control1,
    control2,
    length,
    progress: 0,
    radius,
    source: 'lane-level cubic Bezier steering arc from turnIntent and right-hand lane model',
    toHeading: Math.atan2(toVector.x, toVector.z),
  }
  return car.turnArc
}

function finishVehicleTurnArc(car) {
  const arc = car.turnArc
  if (!arc) return
  car.road = arc.toRoad
  car.direction = arc.toDirection
  car.lane = roadLaneOffset(arc.toRoad, arc.toDirection)
  car.t = tValueForRoadAlong(arc.toRoad, arc.toDirection, roadAlongFromPoint(arc.toRoad, arc.end))
  car.activeRoad = null
  car.activeDirection = null
  car.turnsCompleted = (car.turnsCompleted || 0) + 1
  car.lastTurnArc = {
    id: arc.id,
    intent: arc.intent,
    fromRoadName: arc.fromRoadName,
    toRoadName: arc.toRoadName,
    radius: arc.radius,
    length: arc.length,
    source: arc.source,
    completedAt: Date.now(),
  }
  car.turnArc = null
  applyVehicleTurnIntent(car, nextProceduralTurnIntent(car), car.road)
}

function advanceVehicleTurnArc(car, distance) {
  if (!car.turnArc) return false
  car.turnArc.progress = (car.turnArc.progress || 0) + Math.max(0, distance)
  if (car.turnArc.progress >= car.turnArc.length) finishVehicleTurnArc(car)
  return true
}

function shouldBeginVehicleTurnArc(state, turnContext, signalStop, turnControl) {
  if (!turnContext?.active || turnContext.direction === 'straight') return false
  if (state.car.kind === 'taxi' || state.car.turnArc) return false
  if (signalStop || turnControl?.mustYield) return false
  const distance = turnContext.distanceToDecision
  return typeof distance === 'number' && distance <= Math.max(5.5, Math.min(10, state.dim.length + 5.5))
}

function taxiLoopForCar(car, roads = [], index = 0) {
  const vertical = roads.filter(road => road.axis === 'z' && road.main).sort((a, b) => a.x - b.x)
  const horizontal = roads.filter(road => road.axis === 'x' && road.main).sort((a, b) => a.z - b.z)
  if (vertical.length < 2 || horizontal.length < 2) return null

  const maxRing = Math.max(1, Math.min(4, Math.floor(Math.min(vertical.length, horizontal.length) / 2) - 1))
  const ring = Math.min(maxRing, 1 + (hashValue(car.id || index) % maxRing))
  const west = vertical[ring]
  const east = vertical[vertical.length - 1 - ring]
  const south = horizontal[ring]
  const north = horizontal[horizontal.length - 1 - ring]
  if (!west || !east || !south || !north || west.x >= east.x || south.z >= north.z) return null

  const southStart = roadLanePoint(south, west.x, 1)
  const southEnd = roadLanePoint(south, east.x, 1)
  const eastStart = roadLanePoint(east, south.z, 1)
  const eastEnd = roadLanePoint(east, north.z, 1)
  const northStart = roadLanePoint(north, east.x, -1)
  const northEnd = roadLanePoint(north, west.x, -1)
  const westStart = roadLanePoint(west, north.z, -1)
  const westEnd = roadLanePoint(west, south.z, -1)
  const rawPoints = [southStart, southEnd, eastStart, eastEnd, northStart, northEnd, westStart, westEnd, southStart]
  const points = smoothRouteCorners(rawPoints, 19)
  const smoothing = routeCurveMetadata(points, rawPoints.length)
  return {
    points,
    routeMeters: routeDistance(points),
    ring,
    smoothing,
    roads: [south, south, east, east, north, north, west, west],
    directions: [1, 1, 1, 1, -1, -1, -1, -1],
    roadNames: [south.name, east.name, north.name, west.name].filter(Boolean),
  }
}

function roadForTaxiPose(pose, roads = [], fallback = null) {
  if (!pose || !roads.length) return fallback
  const heading = pose.heading ?? pose.yaw ?? 0
  const preferredAxis = Math.abs(Math.sin(heading)) >= Math.abs(Math.cos(heading)) ? 'x' : 'z'
  let best = null
  let bestScore = Infinity
  for (const road of roads) {
    const along = road.axis === 'x' ? pose.x : pose.z
    if (along < road.from - 6 || along > road.to + 6) continue
    const offset = road.axis === 'x' ? Math.abs(pose.z - road.z) : Math.abs(pose.x - road.x)
    const axisPenalty = road.axis === preferredAxis ? 0 : 5.5
    const score = offset + axisPenalty
    if (score < bestScore) {
      best = road
      bestScore = score
    }
  }
  return best || fallback
}

function taxiDirectionForPose(road, pose, fallback = 1) {
  if (!road || !pose) return fallback
  const heading = pose.heading ?? pose.yaw ?? 0
  if (road.axis === 'x') return Math.sin(heading) >= 0 ? 1 : -1
  return Math.cos(heading) >= 0 ? 1 : -1
}

function ensureTaxiCruise(car, roads = [], index = 0) {
  if (car.kind !== 'taxi') return null
  if (!car.cruiseLoop) {
    const loop = taxiLoopForCar(car, roads, index)
    if (loop?.points?.length >= 2) {
      car.cruiseLoop = loop
      car.cruisePath = loop.points
      car.cruiseMeters = loop.routeMeters
      car.cruiseProgress = (car.t || 0) * loop.routeMeters
      car.cruiseRouteMode = 'city-ring-loop'
      car.cruiseRoadNames = loop.roadNames
      car.cruiseRouteSmoothing = loop.smoothing
    }
  }
  return car.cruiseLoop || null
}

function taxiCruisePose(car, roads = [], index = 0) {
  const loop = ensureTaxiCruise(car, roads, index)
  if (!loop?.points?.length || !car.cruiseMeters) return null
  const pose = sampleRoute(loop.points, ((car.cruiseProgress || 0) % car.cruiseMeters + car.cruiseMeters) % car.cruiseMeters)
  const segment = Math.max(0, Math.min(loop.roads.length - 1, pose.segmentIndex || 0))
  car.activeRoad = roadForTaxiPose(pose, roads, loop.roads[segment] || car.road)
  car.activeDirection = taxiDirectionForPose(car.activeRoad, pose, loop.directions[segment] || car.direction)
  return { x: pose.x, z: pose.z, yaw: pose.heading, heading: pose.heading, road: car.activeRoad, direction: car.activeDirection, routeCurve: pose.routeCurve || null }
}

function taxiPoseForCar(car, roads = [], index = 0) {
  return car.kind === 'taxi'
    ? taxiCruisePose(car, roads, index) || trafficPose(car)
    : trafficPose(car)
}

function assignedTaxiPose(car, store) {
  if (!car.assignment) return null
  const missionTaxi = store.mission?.taxi?.fleetCarId === car.id ? store.mission.taxi.pose : null
  const rideTaxi = store.ride?.taxiId === car.id ? store.ride.taxiPose : null
  const npcTaxi = car.npcTaxi?.pose || null
  const pose = rideTaxi || missionTaxi || npcTaxi
  return pose ? { x: pose.x, z: pose.z, yaw: pose.heading ?? pose.yaw ?? 0, heading: pose.heading ?? pose.yaw ?? 0, routeCurve: pose.routeCurve || null } : null
}

function nearestAvailableTaxi(pickup, cars = [], roads = [], maxDistance = Infinity) {
  let best = null
  let bestDistance = Infinity
  const pickupStop = taxiStopForPickup(pickup, roads)
  cars.forEach((car, index) => {
    if (car.kind !== 'taxi' || car.assignment) return
    const pose = taxiPoseForCar(car, roads, index)
    if (!pose) return
    const directDistance = Math.hypot(pose.x - pickupStop.x, pose.z - pickupStop.z)
    const route = buildTaxiRoute(pose, pickupStop, roads)
    const distance = route.routeMeters || directDistance
    if (distance < bestDistance && directDistance <= maxDistance) {
      best = { car, pose, route, distance, directDistance }
      bestDistance = distance
    }
  })
  return best
}

function releaseFleetTaxi(taxi, city, dropoff) {
  if (!taxi?.fleetCarId) return
  const car = city.cars?.find(item => item.id === taxi.fleetCarId)
  if (!car) return
  car.assignment = null
  car.assignmentTaxiId = null
  if (dropoff && car.cruiseMeters) {
    const pose = taxiCruisePose(car, city.roads || [], city.cars.indexOf(car))
    if (pose) car.cruiseProgress = (car.cruiseProgress || 0) + Math.hypot(dropoff.x - pose.x, dropoff.z - pose.z)
  }
}

function startTaxiRideFromMission(mission, store, roads) {
  const taxi = mission.taxi
  const destination = mission.destination
  if (!taxi || !destination) {
    store.setPulse('Choose a taxi destination first, then press F to board.')
    return false
  }

  const passengerPickup = taxi.passengerPickup || mission.pickup || nearestRoadPickup(store.player || destination, roads)
  const pickupStop = taxi.pickupStop || taxiStopForPickup(passengerPickup, roads)
  const fallbackDropoff = mission.dropoff || taxi.dropoff || nearestRoadPickup(destination, roads)
  const dropoffStop = taxi.dropoffStop || taxiStopForPickup(fallbackDropoff, roads)
  const route = taxi.destinationPath?.length >= 2
    ? {
        points: taxi.destinationPath,
        routeMeters: taxi.destinationMeters,
        roadNames: taxi.routeNames,
        smoothing: taxi.destinationSmoothing || routeCurveMetadata(taxi.destinationPath, taxi.destinationRawPointCount || taxi.destinationPath.length),
      }
    : buildTaxiRoute(pickupStop, dropoffStop, roads)
  const routeMeters = Math.max(1, route.routeMeters || 0)
  const rideSpeed = TAXI_RIDE_SPEED
  mission.phase = 'taxi_ride'
  taxi.phase = 'ride'
  taxi.path = route.points
  taxi.routeMeters = routeMeters
  taxi.progress = 0
  taxi.routeNames = route.roadNames || taxi.routeNames || []
  taxi.routeSmoothing = route.smoothing || taxi.routeSmoothing || null
  store.updateMission({
    phase: 'taxi_ride',
    route: route.points,
    taxi,
    boardingRequested: true,
    summary: `Taxi to ${destination.name} via ${taxi.routeNames?.slice(0, 2).join(' / ') || 'city streets'}.`,
  })
  store.startRide({
    from: { x: pickupStop.x, z: pickupStop.z },
    to: { x: dropoffStop.x, z: dropoffStop.z },
    pickupPoint: { x: passengerPickup.x, z: passengerPickup.z },
    exitPoint: { x: fallbackDropoff.x, z: fallbackDropoff.z },
    path: route.points,
    routeMeters,
    routeNames: taxi.routeNames || [],
    routeSmoothing: route.smoothing || taxi.routeSmoothing || null,
    duration: Math.min(TAXI_MAX_RIDE_SECONDS, Math.max(TAXI_MIN_RIDE_SECONDS, routeMeters / rideSpeed)),
    label: mission.agentName
      ? `${mission.agentName} and you are taking a taxi to ${destination.name}${destination.address ? `, ${destination.address}` : ''}.`
      : `You are taking a taxi to ${destination.name}${destination.address ? `, ${destination.address}` : ''}.`,
    destinationName: destination.name,
    taxiId: taxi.fleetCarId || taxi.id,
    taxiSource: taxi.source,
  })
  return true
}

function attachTaxiDestination(mission, destination, roads, store) {
  if (!mission?.taxi || !destination) return null
  const dropoff = nearestRoadPickup(destination, roads)
  const pickupStop = mission.taxi.pickupStop || taxiStopForPickup(mission.pickup, roads)
  const dropoffStop = taxiStopForPickup(dropoff, roads)
  const routeToDestination = buildTaxiRoute(pickupStop, dropoffStop, roads)
  mission.destination = destination
  mission.dropoff = dropoff
  mission.route = routeToDestination.points
  mission.taxi.dropoff = dropoff
  mission.taxi.dropoffStop = dropoffStop
  mission.taxi.destinationPath = routeToDestination.points
  mission.taxi.destinationMeters = routeToDestination.routeMeters
  mission.taxi.directMeters = routeToDestination.directMeters
  mission.taxi.routeNames = routeToDestination.roadNames
  mission.taxi.destinationSmoothing = routeToDestination.smoothing
  mission.taxi.destinationRawPointCount = routeToDestination.smoothing?.originalPointCount || routeToDestination.points.length
  store.updateMission({
    destination,
    dropoff,
    route: routeToDestination.points,
    taxi: mission.taxi,
    summary: `Destination set to ${destination.name}. Press F when the taxi is at the curb.`,
  })
  return dropoff
}

function directTaxiChannelLabel(mission) {
  if (mission?.channelLabel) return mission.channelLabel
  if (mission?.requestChannel === 'map_place_card') return 'Map place taxi'
  if (mission?.requestChannel === 'realphone_message') return 'RealPhone message taxi'
  return 'RealPhone Taxi'
}

function beginTaxiDispatch(agent, mission, store, cityOrRoads) {
  const roads = Array.isArray(cityOrRoads) ? cityOrRoads : cityOrRoads.roads || []
  const cars = Array.isArray(cityOrRoads) ? [] : cityOrRoads.cars || []
  const pickup = mission.pickup
  const pickupStop = taxiStopForPickup(pickup, roads)
  const dropoff = mission.destination ? nearestRoadPickup(mission.destination, roads) : null
  const dropoffStop = dropoff ? taxiStopForPickup(dropoff, roads) : null
  const preferred = mission.preferredTaxiId
    ? cars
      .map((car, index) => {
        const pose = taxiPoseForCar(car, roads, index)
        const directDistance = pose ? Math.hypot(pose.x - pickupStop.x, pose.z - pickupStop.z) : Infinity
        const route = pose ? buildTaxiRoute(pose, pickupStop, roads) : null
        return {
          car,
          pose,
          route,
          distance: route ? route.routeMeters || directDistance : Infinity,
          directDistance,
        }
      })
      .find(item => item.car.id === mission.preferredTaxiId && item.car.kind === 'taxi' && !item.car.assignment && item.directDistance <= (mission.maxDispatchDistance ?? Infinity))
    : null
  const fleetTaxi = preferred || nearestAvailableTaxi(pickup, cars, roads, mission.maxDispatchDistance ?? Infinity)
  if (!fleetTaxi && mission.allowSpawnTaxi === false) {
    store.setPulse(`No passing taxi is close enough to hail. Move nearer to traffic or use the phone taxi app.`)
    return false
  }
  const spawn = fleetTaxi?.pose || taxiSpawnForPickup(pickupStop, roads)
  const routeToPickup = fleetTaxi?.route || buildTaxiRoute(spawn, pickupStop, roads)
  const routeToDestination = dropoffStop ? buildTaxiRoute(pickupStop, dropoffStop, roads) : { points: [], routeMeters: 0, directMeters: 0, roadNames: [] }
  const initialProgress = fleetTaxi ? Math.max(0, routeToPickup.routeMeters - 620) : 0
  const firstPose = sampleRoute(routeToPickup.points, initialProgress)
  const taxi = {
    id: `taxi_${mission.id}`,
    fleetCarId: fleetTaxi?.car.id || null,
    source: fleetTaxi ? 'fleet' : 'spawned',
    driverName: fleetTaxi?.car.driverName || 'Taxi driver',
    dispatchDistanceFromCruise: fleetTaxi?.distance || null,
    phase: 'driving_to_pickup',
    path: routeToPickup.points,
    destinationPath: routeToDestination.points,
    routeMeters: routeToPickup.routeMeters,
    destinationMeters: routeToDestination.routeMeters,
    directMeters: routeToDestination.directMeters,
    routeSmoothing: routeToPickup.smoothing,
    destinationSmoothing: routeToDestination.smoothing,
    destinationRawPointCount: routeToDestination.smoothing?.originalPointCount || routeToDestination.points.length,
    progress: initialProgress,
    initialProgress,
    approachMetersRemaining: Math.max(0, routeToPickup.routeMeters - initialProgress),
    speed: TAXI_DISPATCH_SPEED,
    pickup,
    passengerPickup: pickup,
    pickupStop,
    dropoff,
    dropoffStop,
    routeNames: routeToDestination.roadNames,
    pose: { x: firstPose.x, z: firstPose.z, heading: firstPose.heading, yaw: firstPose.heading, routeCurve: firstPose.routeCurve || null },
    routeCurve: firstPose.routeCurve || null,
    requestedAt: performance.now(),
  }

  if (fleetTaxi?.car) {
    fleetTaxi.car.assignment = mission.id
    fleetTaxi.car.assignmentTaxiId = taxi.id
  }

  mission.phase = 'taxi_dispatch'
  mission.taxi = taxi
  mission.dropoff = dropoff
  mission.route = routeToDestination.points
  mission.awaitingBoardKey = true
  const directPlayerTaxi = mission.source === 'player_taxi' && !agent
  const directChannel = directTaxiChannelLabel(mission)
  const dispatchSummary = directPlayerTaxi
    ? `${directChannel} dispatched ${taxi.driverName}'s cruising cab directly. It is driving to your curb on ${routeToPickup.roadNames[0] || pickup.roadName || 'the road'}.`
    : `${agent?.name || 'You'} ${fleetTaxi ? `hailed ${taxi.driverName}'s passing taxi` : 'called a taxi'}. It is driving to the curb on ${routeToPickup.roadNames[0] || pickup.roadName || 'the road'}.`
  store.updateMission({
    phase: 'taxi_dispatch',
    pickup,
    dropoff,
    route: routeToDestination.points,
    taxi,
    awaitingBoardKey: true,
    summary: dispatchSummary,
  })
  if (agent) {
    store.showDialogue({
      speaker: agent.name,
      role: agent.job,
      text: styleNpcSpeech(agent, `I called a passing taxi. We wait at the curb first, then press F to board for ${mission.destination?.name || 'the destination'}.`),
      agent: agent.snapshot(),
    })
  }
  return true
}

function activeNpcTaxiCount(cars = []) {
  return cars.filter(car => String(car.assignment || '').startsWith('npc_taxi_')).length
}

function shouldUseAutonomousTaxi(agent, target, city) {
  if (!target || agent.mission || agent.selfTaxi || agent.taxiCooldown > 0) return false
  if (activeNpcTaxiCount(city.cars || []) >= NPC_TAXI_MAX_ACTIVE) return false
  const distance = Math.hypot(target.x - agent.pos.x, target.z - agent.pos.z)
  if (distance < NPC_TAXI_MIN_DISTANCE) return false
  if (/resting|break|dwelling|available/i.test(target.activity || agent.activity || '')) return false
  const longTripRoles = new Set(['banker', 'doctor', 'teacher', 'courier', 'barista', 'engineer', 'student', 'shopkeeper'])
  return longTripRoles.has(agent.role) || distance > NPC_TAXI_MIN_DISTANCE * 1.35
}

function releaseAutonomousNpcTaxi(agent, city, dropoff) {
  const taxi = agent.selfTaxi
  if (!taxi) return
  const car = city.cars?.find(item => item.assignmentTaxiId === taxi.id || item.npcTaxi?.id === taxi.id)
  if (car) {
    car.assignment = null
    car.assignmentTaxiId = null
    car.npcTaxi = null
    if (dropoff && car.cruiseMeters) {
      const pose = taxiCruisePose(car, city.roads || [], city.cars.indexOf(car))
      if (pose) car.cruiseProgress = (car.cruiseProgress || 0) + Math.hypot(dropoff.x - pose.x, dropoff.z - pose.z)
    }
  }
  agent.selfTaxi = null
  agent.boardingTaxi = null
  agent.taxiCooldown = 55 + (hashValue(agent.id) % 35)
}

function startAutonomousNpcTaxi(agent, target, city) {
  const roads = city.roads || []
  const cars = city.cars || []
  if (!roads.length || !cars.length) return false
  const pickup = nearestRoadPickup(agent.pos, roads)
  const pickupStop = taxiStopForPickup(pickup, roads)
  const dropoff = nearestRoadPickup(target, roads)
  const dropoffStop = taxiStopForPickup(dropoff, roads)
  const fleetTaxi = nearestAvailableTaxi(pickup, cars, roads, Infinity)
  if (!fleetTaxi) return false

  const routeToPickup = fleetTaxi.route || buildTaxiRoute(fleetTaxi.pose, pickupStop, roads)
  const routeToDestination = buildTaxiRoute(pickupStop, dropoffStop, roads)
  if (routeToDestination.routeMeters < NPC_TAXI_MIN_DISTANCE * 0.45) return false

  const initialProgress = Math.max(0, routeToPickup.routeMeters - 520)
  const firstPose = sampleRoute(routeToPickup.points, initialProgress)
  const taxi = {
    id: `npc_taxi_${agent.id}_${Math.round(performance.now())}`,
    fleetCarId: fleetTaxi.car.id,
    source: 'fleet',
    driverName: fleetTaxi.car.driverName,
    phase: 'dispatch',
    path: routeToPickup.points,
    destinationPath: routeToDestination.points,
    routeMeters: routeToPickup.routeMeters,
    destinationMeters: routeToDestination.routeMeters,
    directMeters: routeToDestination.directMeters,
    routeSmoothing: routeToPickup.smoothing,
    destinationSmoothing: routeToDestination.smoothing,
    destinationRawPointCount: routeToDestination.smoothing?.originalPointCount || routeToDestination.points.length,
    progress: initialProgress,
    initialProgress,
    speed: NPC_TAXI_DISPATCH_SPEED,
    pickup,
    pickupStop,
    passengerPickup: pickup,
    dropoff,
    dropoffStop,
    targetName: target.name,
    routeNames: routeToDestination.roadNames,
    pose: { x: firstPose.x, z: firstPose.z, heading: firstPose.heading, yaw: firstPose.heading, routeCurve: firstPose.routeCurve || null },
    routeCurve: firstPose.routeCurve || null,
    requestedAt: performance.now(),
  }

  fleetTaxi.car.assignment = taxi.id
  fleetTaxi.car.assignmentTaxiId = taxi.id
  fleetTaxi.car.npcTaxi = taxi
  agent.selfTaxi = taxi
  agent.walkRoute = null
  agent.walkPlan = null
  agent.routeStatus = `${agent.name} called ${taxi.driverName}'s taxi for ${target.name}`
  agent.currentIntent = `taking a taxi to ${target.name}`
  agent.remember('mobility', `I called ${taxi.driverName}'s taxi to reach ${target.name}.`, agent.placeName, 0.68)

  useCityStore.getState().addCityEvent({
    id: `mobility_${taxi.id}`,
    kind: 'mobility',
    agentId: agent.id,
    agentName: agent.name,
    placeName: agent.placeName,
    topic: 'autonomous taxi commute',
    text: `${agent.name} books ${taxi.driverName}'s taxi for ${target.name} instead of walking ${Math.round(routeToDestination.routeMeters)}m.`,
  })
  return true
}

function updateAutonomousNpcTaxi(agent, target, delta, city) {
  const taxi = agent.selfTaxi
  if (!taxi) return false
  const car = city.cars?.find(item => item.assignmentTaxiId === taxi.id)
  if (!car) {
    agent.selfTaxi = null
    return false
  }
  car.npcTaxi = taxi

  if (taxi.phase === 'dispatch') {
    agent.activity = 'waiting for self-called taxi'
    agent.placeName = taxi.pickup.roadName || agent.placeName
    agent.currentIntent = `waiting at the curb for ${taxi.driverName}'s taxi to ${target.name}`
    const curbDistance = Math.hypot(agent.pos.x - taxi.passengerPickup.x, agent.pos.z - taxi.passengerPickup.z)
    if (curbDistance > 1.1) moveAgentToward(agent, taxi.passengerPickup, delta, 1.42 * agent.pace, city)
    advanceTaxi(taxi, delta)
    if (taxi.progress >= taxi.routeMeters - 0.2) {
      const pose = sampleRoute(taxi.path, taxi.routeMeters)
      taxi.progress = taxi.routeMeters
      taxi.pose = { x: pose.x, z: pose.z, heading: pose.heading, yaw: pose.heading, routeCurve: pose.routeCurve || null }
      taxi.routeCurve = pose.routeCurve || null
      taxi.phase = 'boarding'
      taxi.boardingStartedAt = performance.now()
      agent.boardingTaxi = { missionId: taxi.id, x: agent.pos.x, z: agent.pos.z }
      agent.remember('mobility', `${taxi.driverName}'s taxi arrived at the curb.`, agent.placeName, 0.62)
    }
    return true
  }

  if (taxi.phase === 'boarding') {
    agent.activity = 'boarding self-called taxi'
    const elapsed = (performance.now() - (taxi.boardingStartedAt || performance.now())) / (TAXI_BOARDING_SECONDS * 1000)
    const t = smoothstep(clampValue(elapsed, 0, 1))
    const door = taxiPassengerDoorPoint(taxi, 'agent')
    const start = agent.boardingTaxi || { x: agent.pos.x, z: agent.pos.z }
    agent.pos.x = start.x + (door.x - start.x) * t
    agent.pos.z = start.z + (door.z - start.z) * t
    agent.pos.y = terrainHeight(agent.pos.x, agent.pos.z) + 0.95
    agent.heading = taxi.pose.heading ?? door.heading ?? agent.heading
    if (elapsed >= 1) {
      taxi.phase = 'ride'
      taxi.path = taxi.destinationPath
      taxi.routeMeters = taxi.destinationMeters
      taxi.routeSmoothing = taxi.destinationSmoothing || routeCurveMetadata(taxi.destinationPath, taxi.destinationRawPointCount || taxi.destinationPath.length)
      taxi.progress = 0
      taxi.speed = NPC_TAXI_RIDE_SPEED
      agent.boardingTaxi = null
      useCityStore.getState().addCityEvent({
        id: `mobility_board_${taxi.id}`,
        kind: 'mobility',
        agentId: agent.id,
        agentName: agent.name,
        placeName: agent.placeName,
        topic: 'taxi boarding',
        text: `${agent.name} gets into ${taxi.driverName}'s taxi and heads toward ${target.name}.`,
      })
    }
    return true
  }

  if (taxi.phase === 'ride') {
    agent.activity = 'riding self-called taxi'
    agent.placeName = taxi.targetName || target.name
    agent.currentIntent = `riding through traffic to ${target.name}`
    advanceTaxi(taxi, delta)
    const seat = taxiPassengerDoorPoint({ pose: taxi.pose, passengerPickup: taxi.passengerPickup }, 'inside')
    agent.pos.x = seat.x
    agent.pos.z = seat.z
    agent.pos.y = terrainHeight(agent.pos.x, agent.pos.z) + 0.95
    agent.heading = taxi.pose.heading
    if (taxi.progress >= taxi.routeMeters - 0.2) {
      const exit = taxi.dropoff || target
      agent.pos.set(exit.x, terrainHeight(exit.x, exit.z) + 0.95, exit.z)
      agent.heading = taxi.pose.heading
      agent.remember('mobility', `I arrived by taxi at ${target.name}.`, target.name, 0.72)
      useCityStore.getState().addCityEvent({
        id: `mobility_arrive_${taxi.id}`,
        kind: 'mobility',
        agentId: agent.id,
        agentName: agent.name,
        placeName: target.name,
        topic: 'taxi arrival',
        text: `${agent.name} pays ${taxi.driverName} and continues from the curb toward ${target.name}.`,
      })
      releaseAutonomousNpcTaxi(agent, city, taxi.dropoff)
      agent.walkRoute = null
      agent.routeStatus = `taxi dropoff complete near ${target.name}`
    }
    return true
  }

  releaseAutonomousNpcTaxi(agent, city, taxi.dropoff)
  return false
}

class Agent {
  constructor(data) {
    Object.assign(this, data)
    const autonomy = data.autonomy || {}
    this.pos = new THREE.Vector3(data.home.x, data.home.y + 0.95, data.home.z)
    this.heading = Math.random() * Math.PI * 2
    this.activity = 'starting day'
    this.placeName = data.home.name
    this.autonomy = autonomy
    this.needs = {
      energy: autonomy.needProfile?.energy ?? 0.72,
      hunger: autonomy.needProfile?.hunger ?? 0.24,
      social: autonomy.needProfile?.social ?? 0.5,
      urgency: autonomy.needProfile?.urgency ?? 0.36,
    }
    this.currentIntent = autonomy.dailyGoal ? `Today: ${autonomy.dailyGoal}` : 'following schedule'
    this.memories = [{
      kind: 'goal',
      text: this.currentIntent,
      placeName: data.home.name,
      weight: 0.55,
    }]
    this.relationships = {}
    this.relationshipCount = 0
    this.lastInteraction = null
    this.cognition = buildAgentCognition(this, {
      trigger: 'spawn',
      target: data.home,
      activity: this.activity,
      placeName: this.placeName,
    })
    this.cognitionClock = 1.5 + (hashValue(data.id) % 30) / 10
    this.lastReflectionText = this.cognition.reflection?.text || ''
    this.lastReflectionAt = 0
    this.talkTimer = 0
    this.socialCooldown = 4 + Math.random() * 11
    this.playerCooldown = 0
    this.glanceCooldown = 1 + Math.random() * 5
    this.socialReaction = null
    this.playerDistance = null
    this.facingPlayerAngle = null
    this.talkPartnerId = null
    this.talkPartnerName = null
    this.talkTopicLabel = null
    this.talkLine = null
    this.talkSource = null
    this.talkStartedAt = 0
    this.visualGesture = null
    this.renderFacingPartner = false
    this.facingPartnerAngle = null
    this.debugSocialConversation = false
    this.mission = null
    this.bumpVelocity = new THREE.Vector2()
    this.bumpTimer = 0
    this.fallTimer = 0
    this.walkRoute = null
    this.walkPlan = null
    this.selfTaxi = null
    this.taxiCooldown = 0
    this.needErrand = null
    this.needErrandCooldown = NEED_ERRAND_MIN_SECONDS + (hashValue(data.id) % 16)
    this.llmAutonomy = null
    this.lastLlmConversation = null
    this.crosswalkWaitTimer = 0
    this.lastCrosswalkWaitAt = 0
    this.stuckTimer = 0
    this.lastRouteDistance = null
    this.blockedContacts = 0
    this.routeStatus = 'scheduled route pending'
  }

  refreshCognition(context = {}) {
    this.cognition = buildAgentCognition(this, context)
    const reflection = this.cognition.reflection
    const now = performance.now()
    if (
      reflection?.text &&
      reflection.text !== this.lastReflectionText &&
      reflection.importance >= 0.68 &&
      now - (this.lastReflectionAt || 0) > 16000
    ) {
      this.lastReflectionText = reflection.text
      this.lastReflectionAt = now
      this.remember('reflection', reflection.text, this.placeName, reflection.importance)
    }
    return this.cognition
  }

  update(delta, timeMinutes, places, city) {
    const roads = city.roads || city
    this.socialCooldown = Math.max(0, this.socialCooldown - delta)
    this.playerCooldown = Math.max(0, this.playerCooldown - delta)
    this.glanceCooldown = Math.max(0, this.glanceCooldown - delta)
    this.taxiCooldown = Math.max(0, this.taxiCooldown - delta)
    this.needErrandCooldown = Math.max(0, this.needErrandCooldown - delta)
    this.updateNeeds(delta)
    if (this.fallTimer > 0) {
      this.fallTimer = Math.max(0, this.fallTimer - delta)
      this.applyBump(delta * 0.42, city)
      this.activity = this.fallTimer > 0.25 ? 'knocked down' : 'getting back up'
      return 'fallen'
    }
    if (this.bumpTimer > 0) {
      this.bumpTimer = Math.max(0, this.bumpTimer - delta)
      this.applyBump(delta, city)
      this.activity = 'stumbling after contact'
      return 'stumbling'
    }
    if (this.talkTimer > 0 && !this.mission) {
      this.talkTimer -= delta
      return 'talking'
    }
    if (this.talkTimer > 0) this.talkTimer -= delta
    if (this.talkTimer <= 0 && !this.mission) {
      this.talkPartnerId = null
      this.talkPartnerName = null
      this.talkTopicLabel = null
      this.talkLine = null
      this.talkSource = null
      this.visualGesture = null
      this.renderFacingPartner = false
      this.facingPartnerAngle = null
      this.debugSocialConversation = false
    }

    if (this.mission) return this.updateMission(delta, city)

    this.cognitionClock = Math.max(0, (this.cognitionClock || 0) - delta)
    const scheduledTarget = targetFor(this, places, timeMinutes, roads)
    if (this.cognitionClock <= 0) {
      this.refreshCognition({
        trigger: 'routine-tick',
        timeMinutes,
        target: scheduledTarget,
        activity: this.activity,
        placeName: this.placeName,
      })
      this.cognitionClock = 3.2 + (hashValue(`${this.id}_${Math.floor(timeMinutes)}`) % 32) / 10
    }

    this.updateNeedErrand(timeMinutes, places, roads, scheduledTarget)
    const sharedMobilityState = this.updateSharedMobilityTrip(delta, timeMinutes, places, city)
    if (sharedMobilityState) return sharedMobilityState
    const target = targetFor(this, places, timeMinutes, roads)
    if (this.selfTaxi) {
      updateAutonomousNpcTaxi(this, target, delta, city)
      return this.selfTaxi ? this.selfTaxi.phase : 'walking'
    }
    if (shouldUseAutonomousTaxi(this, target, city) && startAutonomousNpcTaxi(this, target, city)) {
      updateAutonomousNpcTaxi(this, target, delta, city)
      return 'taxi'
    }

    this.activity = target.activity
    this.placeName = target.name
    this.currentIntent = this.routeStatus && this.stuckTimer > 0
      ? this.routeStatus
      : this.intentFor(target, timeMinutes)

    const distance = Math.hypot(target.x - this.pos.x, target.z - this.pos.z)
    const sharedMobilityPhase = this.needErrand?.sharedMobilityTrip?.phase || null
    const finalNeedTargetReached = this.needErrand &&
      (!sharedMobilityPhase || sharedMobilityPhase === 'walking-to-destination') &&
      distance < 4.2
    if (finalNeedTargetReached) this.applyNeedErrandRelief(delta)
    if (distance > 2.2) {
      const ridingSharedMobility = sharedMobilityPhase === 'riding-to-return-dock'
      const mobilityMultiplier = ridingSharedMobility && this.needErrand?.mobilityMode === 'shared-scooter'
        ? 2.25
        : ridingSharedMobility && this.needErrand?.mobilityMode === 'shared-bike'
          ? 1.95
          : 1
      const speed = (this.activity === 'commuting' ? 1.65 : 1.05) * this.pace * mobilityMultiplier
      moveAgentToward(this, target, delta, speed, city)
      return 'walking'
    }

    this.heading += Math.sin(timeMinutes * 0.02 + this.id.length) * delta * 0.2
    this.walkRoute = null
    this.walkPlan = {
      mode: 'dwelling',
      targetName: target.name,
      waypointName: target.name,
      waypoint: { x: target.x, z: target.z },
      distanceToTarget: distance,
      distanceToWaypoint: distance,
      stableRoute: true,
    }
    this.routeStatus = 'at scheduled destination'
    return 'dwelling'
  }

  startNeedErrand(profile, places, timeMinutes, forced = false, cognition = null) {
    const place = chooseNeedErrandPlace(this, places, profile)
    if (!place) return false
    const cognitiveReason = cognition?.selectedPolicy?.reason || `${profile.reason} need crossed the routine threshold`
    this.needErrand = {
      id: `${this.id}_${profile.reason}_${Math.floor(timeMinutes)}`,
      reason: profile.reason,
      label: profile.label,
      activity: profile.activity,
      targetId: place.id,
      targetName: place.name,
      startedAt: timeMinutes,
      durationMinutes: forced ? NEED_ERRAND_DURATION_MINUTES + 10 : NEED_ERRAND_DURATION_MINUTES + (hashValue(`${this.id}_${profile.reason}`) % 10),
      forced,
      cognitiveReason,
      cognitionPolicy: cognition?.selectedPolicy?.id || 'need-detour',
    }
    this.walkRoute = null
    this.walkPlan = null
    this.routeStatus = `need detour: ${profile.label} at ${place.name}`
    this.currentIntent = `${profile.label} at ${place.name} because ${strongestNeedPhrase(this)}`
    this.remember('need', `${profile.memory} Detouring to ${place.name}. Reason: ${cognitiveReason}.`, this.placeName, 0.82)
    useCityStore.getState().addCityEvent({
      id: `need_errand_${this.needErrand.id}_${Date.now()}`,
      kind: 'need',
      agentId: this.id,
      agentName: this.name,
      placeName: place.name,
      topic: profile.label,
      text: `${this.name} changes course for a ${profile.label} at ${place.name} after memory/reflection utility scoring instead of blindly following the schedule.`,
    })
    return true
  }

  startLlmDirectedErrand(place, detail = {}, timeMinutes = 0) {
    if (!place?.id) return false
    const label = detail.label || detail.actionLabel || 'local LLM errand'
    this.needErrand = {
      id: `${this.id}_llm_${place.id}_${Math.floor(timeMinutes)}`,
      reason: 'local-llm',
      label,
      activity: detail.activity || `going to ${place.name}`,
      targetId: place.id,
      targetName: place.name,
      startedAt: timeMinutes,
      durationMinutes: 14 + (hashValue(`${this.id}_${place.id}`) % 14),
      forced: true,
      cognitiveReason: detail.reason || detail.thought || 'local LLM selected this executable city action',
      cognitionPolicy: 'local-llm-autonomy',
      mobilityMode: detail.mobilityMode || 'walk',
      mobilitySource: detail.mobilitySource || null,
      mobilityDockName: detail.mobilityDockName || null,
      sharedMobilityTrip: detail.sharedMobilityTrip || null,
    }
    this.walkRoute = null
    this.walkPlan = null
    this.selfTaxi = null
    this.boardingTaxi = null
    this.routeStatus = detail.mobilityMode
      ? `local LLM directed ${detail.mobilityMode} route to ${place.name}`
      : `local LLM directed errand to ${place.name}`
    this.currentIntent = `${label} at ${place.name}`
    this.remember('llm-action', `${detail.thought || this.currentIntent} Target: ${place.name}.${detail.mobilityMode ? ` Mode: ${detail.mobilityMode}.` : ''}`, this.placeName, 0.82)
    useCityStore.getState().addCityEvent({
      id: `llm_errand_${this.id}_${place.id}_${Date.now()}`,
      kind: 'llm',
      agentId: this.id,
      agentName: this.name,
      placeName: place.name,
      topic: 'npc autonomy action',
      text: `${this.name} turns a local-LLM decision into a real route toward ${place.name}.`,
    })
    return true
  }

  updateNeedErrand(timeMinutes, places, roads = [], currentTarget = null) {
    if (this.needErrand) {
      if (this.selfTaxi) return
      const sharedTrip = this.needErrand.sharedMobilityTrip
      if (sharedTrip && isSharedMobilityMode(this.needErrand.mobilityMode) && sharedTrip.phase !== 'walking-to-destination') {
        this.currentIntent = `${this.needErrand.label} at ${this.needErrand.targetName}; ${sharedTrip.phase.replaceAll('-', ' ')}`
        return
      }
      const remaining = errandMinutesRemaining(this.needErrand, timeMinutes)
      if (remaining > 0) {
        this.currentIntent = `${this.needErrand.label} at ${this.needErrand.targetName}; ${Math.ceil(remaining)} city min before returning to schedule`
        return
      }
      const completed = this.needErrand
      this.remember('need', `Finished ${completed.label} at ${completed.targetName} and returning to my schedule.`, completed.targetName, 0.7)
      useCityStore.getState().addCityEvent({
        id: `need_errand_done_${completed.id}_${Date.now()}`,
        kind: 'need',
        agentId: this.id,
        agentName: this.name,
        placeName: completed.targetName,
        topic: completed.label,
        text: `${this.name} finishes a ${completed.label} at ${completed.targetName} and returns to the daily route.`,
      })
      this.needErrand = null
      this.needErrandCooldown = 42 + (hashValue(`${this.id}_cooldown_${Math.floor(timeMinutes)}`) % 38)
      this.walkRoute = null
      this.walkPlan = null
      return
    }

    if (this.needErrandCooldown > 0 || this.selfTaxi || this.talkTimer > 0) return
    const profile = needErrandProfile(this)
    if (!profile) return
    const cognition = this.refreshCognition({
      trigger: 'need-check',
      timeMinutes,
      target: currentTarget || targetFor(this, places, timeMinutes, roads),
      profile,
      activity: this.activity,
      placeName: this.placeName,
    })
    if (!shouldStartNeedErrandFromCognition(this, profile, cognition)) return
    this.startNeedErrand(profile, places, timeMinutes, false, cognition)
  }

  applyNeedErrandRelief(delta) {
    if (!this.needErrand) return
    if (this.needErrand.reason === 'hunger') {
      this.needs.hunger = clampValue(this.needs.hunger - 0.018 * delta, 0, 1)
      this.needs.energy = clampValue(this.needs.energy + 0.003 * delta, 0, 1)
    } else if (this.needErrand.reason === 'energy') {
      this.needs.energy = clampValue(this.needs.energy + 0.018 * delta, 0, 1)
      this.needs.urgency = clampValue(this.needs.urgency - 0.006 * delta, 0, 1)
    } else if (this.needErrand.reason === 'social') {
      this.needs.social = clampValue(this.needs.social + 0.017 * delta, 0, 1)
    }
  }

  updateSharedMobilityTrip(delta, timeMinutes, places, city) {
    const trip = this.needErrand?.sharedMobilityTrip
    if (!trip || !isSharedMobilityMode(this.needErrand?.mobilityMode)) return null
    const store = useCityStore.getState()
    const now = performance.now()
    const pickupTarget = sharedMobilityTripPoint(trip, 'pickup', `walking to ${trip.mode} dock`)
    const returnTarget = sharedMobilityTripPoint(trip, 'return', `${trip.mode} return dock`)

    if (trip.phase === 'walking-to-dock' && pickupTarget) {
      const distance = Math.hypot(this.pos.x - pickupTarget.x, this.pos.z - pickupTarget.z)
      this.routeStatus = `walking to ${trip.pickupStationName} to unlock ${trip.mode}`
      if (distance < 2.6) {
        trip.phase = 'pickup'
        trip.phaseStartedAt = now
        trip.pickupAnimationProgress = 0
        this.walkRoute = null
        this.walkPlan = {
          mode: 'gbfs-pickup',
          targetName: trip.pickupStationName,
          waypointName: pickupTarget.name,
          stableRoute: true,
          routePoints: 1,
        }
        store.addCityEvent({
          id: `gbfs_pickup_${trip.id}_${Date.now()}`,
          kind: 'mobility',
          agentId: this.id,
          agentName: this.name,
          placeName: trip.pickupStationName,
          topic: `${trip.mode}-pickup`,
          text: `${this.name} starts unlocking a ${trip.mode} at ${trip.pickupStationName}; pickup inventory has already been decremented.`,
        })
        return 'unlocking-shared-mobility'
      }
      return null
    }

    if (trip.phase === 'pickup') {
      const elapsed = (now - (trip.phaseStartedAt || now)) / Math.max(1, (trip.pickupAnimationSeconds || 2.2) * 1000)
      trip.pickupAnimationProgress = Number(clampValue(elapsed, 0, 1).toFixed(3))
      this.activity = `unlocking ${trip.mode}`
      this.currentIntent = `unlocking ${trip.mode} at ${trip.pickupStationName}`
      this.routeStatus = `unlocking ${trip.mode}: ${Math.round(trip.pickupAnimationProgress * 100)}%`
      if (pickupTarget) {
        this.pos.x += (pickupTarget.x - this.pos.x) * Math.min(1, delta * 4)
        this.pos.z += (pickupTarget.z - this.pos.z) * Math.min(1, delta * 4)
        this.pos.y = terrainHeight(this.pos.x, this.pos.z) + 0.95
      }
      if (trip.pickupAnimationProgress >= 1) {
        trip.phase = 'riding-to-return-dock'
        trip.phaseStartedAt = now
        this.walkRoute = null
        this.walkPlan = null
        this.routeStatus = `riding ${trip.mode} to ${trip.returnStationName}`
        store.addCityEvent({
          id: `gbfs_ride_${trip.id}_${Date.now()}`,
          kind: 'mobility',
          agentId: this.id,
          agentName: this.name,
          placeName: trip.pickupStationName,
          topic: `${trip.mode}-ride-start`,
          text: `${this.name} leaves ${trip.pickupStationName} on a ${trip.mode}; ${trip.returnStationName} keeps a reserved return slot.`,
        })
        return null
      }
      return 'unlocking-shared-mobility'
    }

    if (trip.phase === 'riding-to-return-dock' && returnTarget) {
      const distance = Math.hypot(this.pos.x - returnTarget.x, this.pos.z - returnTarget.z)
      this.routeStatus = `riding ${trip.mode} to reserved return dock at ${trip.returnStationName}`
      if (distance < 2.8) {
        trip.phase = 'return'
        trip.phaseStartedAt = now
        trip.returnAnimationProgress = 0
        this.walkRoute = null
        this.walkPlan = {
          mode: 'gbfs-return',
          targetName: trip.returnStationName,
          waypointName: returnTarget.name,
          stableRoute: true,
          routePoints: 1,
        }
        store.addCityEvent({
          id: `gbfs_return_start_${trip.id}_${Date.now()}`,
          kind: 'mobility',
          agentId: this.id,
          agentName: this.name,
          placeName: trip.returnStationName,
          topic: `${trip.mode}-return-start`,
          text: `${this.name} reaches ${trip.returnStationName} and starts returning the ${trip.mode} into the reserved slot.`,
        })
        return 'returning-shared-mobility'
      }
      return null
    }

    if (trip.phase === 'return') {
      const elapsed = (now - (trip.phaseStartedAt || now)) / Math.max(1, (trip.returnAnimationSeconds || 2) * 1000)
      trip.returnAnimationProgress = Number(clampValue(elapsed, 0, 1).toFixed(3))
      this.activity = `returning ${trip.mode}`
      this.currentIntent = `returning ${trip.mode} at ${trip.returnStationName}`
      this.routeStatus = `returning ${trip.mode}: ${Math.round(trip.returnAnimationProgress * 100)}%`
      if (returnTarget) {
        this.pos.x += (returnTarget.x - this.pos.x) * Math.min(1, delta * 4)
        this.pos.z += (returnTarget.z - this.pos.z) * Math.min(1, delta * 4)
        this.pos.y = terrainHeight(this.pos.x, this.pos.z) + 0.95
      }
      if (trip.returnAnimationProgress >= 1) {
        finishSharedMobilityReturn(this, trip, city)
        trip.phase = 'walking-to-destination'
        trip.phaseStartedAt = now
        this.walkRoute = null
        this.walkPlan = null
        const place = places.get(this.needErrand.targetId)
        this.routeStatus = `returned ${trip.mode}; walking from ${trip.returnStationName} to ${place?.name || this.needErrand.targetName}`
      }
      return 'returning-shared-mobility'
    }

    return null
  }

  updateMission(delta, city) {
    const roads = city.roads || city
    const store = useCityStore.getState()
    const mission = this.mission
    const destination = mission.destination
    this.placeName = destination.name
    this.currentIntent = `helping the player reach ${destination.name}`

    if (mission.mode === 'taxi') {
      if (mission.phase === 'to_pickup') {
        this.activity = 'walking to taxi pickup'
        const distance = moveAgentToward(this, mission.pickup, delta, 1.9 * this.pace, city)
        if (distance < 2.6) {
          beginTaxiDispatch(this, mission, store, city)
          return 'talking'
          mission.phase = 'taxi_boarding'
          mission.boardingAt = performance.now()
          store.updateMission({ phase: 'taxi_boarding', summary: `${this.name} is hailing a taxi at the curb.` })
          store.showDialogue({
            speaker: this.name,
            role: this.job,
            text: styleNpcSpeech(this, '여기서 택시를 잡을게요. 바로 같이 타고 제 일터로 이동하죠.'),
            agent: this.snapshot(),
          })
        }
        return 'walking'
      }

      if (mission.phase === 'taxi_dispatch') {
        this.activity = 'waiting for taxi'
        const curbDistance = Math.hypot(this.pos.x - mission.pickup.x, this.pos.z - mission.pickup.z)
        if (curbDistance > 2.2) moveAgentToward(this, mission.pickup, delta, 1.6 * this.pace, city)

        const taxi = mission.taxi
        if (taxi) {
          advanceTaxi(taxi, delta)
          if (taxi.progress >= taxi.routeMeters - 0.2) {
            const stopPose = sampleRoute(taxi.path, taxi.routeMeters)
            taxi.phase = 'waiting_at_pickup'
            taxi.progress = taxi.routeMeters
            taxi.pose = { x: stopPose.x, z: stopPose.z, heading: stopPose.heading, yaw: stopPose.heading, routeCurve: stopPose.routeCurve || null }
            taxi.routeCurve = stopPose.routeCurve || null
            mission.phase = 'taxi_waiting'
            mission.boardingAt = performance.now()
            store.updateMission({
              phase: 'taxi_waiting',
              taxi,
              summary: `Taxi arrived at ${mission.pickup.roadName || mission.pickup.name || 'the curb'}. Press F to board.`,
            })
            store.showDialogue({
              speaker: this.name,
              role: this.job,
              text: styleNpcSpeech(this, 'The taxi is here. Press F when you are ready to get in.'),
              agent: this.snapshot(),
            })
          }
        }
        return 'talking'
      }

      if (mission.phase === 'taxi_waiting') {
        this.activity = 'waiting by taxi door'
        const taxi = mission.taxi
        const curb = taxi?.passengerPickup || mission.pickup
        if (curb) {
          const distance = Math.hypot(this.pos.x - curb.x, this.pos.z - curb.z)
          if (distance > 0.9) moveAgentToward(this, curb, delta, 1.35 * this.pace, city)
          this.heading = taxi?.pose?.heading ?? this.heading
        }

        if (taxi && mission.boardingRequested) {
          mission.phase = 'taxi_boarding'
          mission.boardingStartedAt = performance.now()
          this.boardingTaxi = null
          store.updateMission({
            phase: 'taxi_boarding',
            taxi,
            boardingStartedAt: mission.boardingStartedAt,
            summary: `${this.name} and you are getting into the taxi from the curb side.`,
          })
        }

        return 'talking'
      }

      if (mission.phase === 'taxi_boarding') {
        this.activity = 'stepping into taxi'
        const taxi = mission.taxi
        if (taxi?.pose) {
          if (!this.boardingTaxi || this.boardingTaxi.missionId !== mission.id) {
            this.boardingTaxi = {
              missionId: mission.id,
              x: this.pos.x,
              z: this.pos.z,
            }
          }
          const elapsed = (performance.now() - (mission.boardingStartedAt || performance.now())) / (TAXI_BOARDING_SECONDS * 1000)
          const t = smoothstep(clampValue(elapsed, 0, 1))
          const door = taxiPassengerDoorPoint(taxi, 'agent')
          const start = this.boardingTaxi
          this.pos.x = start.x + (door.x - start.x) * t
          this.pos.z = start.z + (door.z - start.z) * t
          this.pos.y = terrainHeight(this.pos.x, this.pos.z) + 0.95
          this.heading = taxi.pose.heading ?? door.heading ?? this.heading
          if (elapsed >= 1 && mission.boardingRequested) {
            this.boardingTaxi = null
            startTaxiRideFromMission(mission, store, roads)
          }
        }
        return 'boarding'
      }

      if (mission.phase === 'taxi_ride') {
        this.activity = 'riding with player'
        const ride = store.ride
        if (ride) {
          if (ride.path?.length >= 2) {
            const progress = Math.min(
              ride.routeMeters || 1,
              ((performance.now() - ride.startedAt) / (ride.duration * 1000)) * (ride.routeMeters || 1),
            )
            const pose = sampleRoute(ride.path, progress)
            const seat = taxiPassengerDoorPoint({ pose, passengerPickup: mission.pickup }, 'inside')
            this.pos.x = seat.x
            this.pos.z = seat.z
            this.pos.y = terrainHeight(this.pos.x, this.pos.z) + 0.95
            this.heading = pose.heading
            return 'riding'
          }
          const t = Math.min(1, (performance.now() - ride.startedAt) / (ride.duration * 1000))
          const eased = smoothstep(t)
          this.pos.x = ride.from.x + (ride.to.x - ride.from.x) * eased + 1.2
          this.pos.z = ride.from.z + (ride.to.z - ride.from.z) * eased - 1.2
          this.pos.y = terrainHeight(this.pos.x, this.pos.z) + 0.95
          this.heading = Math.atan2(ride.to.x - ride.from.x, ride.to.z - ride.from.z)
          return 'riding'
        }
        const dropoff = mission.dropoff || nearestRoadPickup(destination, roads)
        this.pos.set(dropoff.x + 1.4, terrainHeight(dropoff.x, dropoff.z) + 0.95, dropoff.z + 1.4)
        releaseFleetTaxi(mission.taxi, city, dropoff)
        store.finishMission(`${this.name} brought you to ${destination.name}.`)
        store.showDialogue({
          speaker: this.name,
          role: this.job,
          text: styleNpcSpeech(this, `도착했어요. 여기가 ${destination.name}입니다. 안으로 들어가려면 제가 먼저 안내할게요.`),
          agent: this.snapshot(),
        })
        this.mission = null
        this.debugSpeedScale = 1
        return 'dwelling'
      }
    }

    this.activity = 'guiding player'
    const distance = moveAgentToward(this, destination, delta, 1.72 * this.pace * (this.debugSpeedScale || 1), city)
    const arrivalRadius = destination.entryRule === 'road-sidewalk-access' ? 9.5 : 4.2
    if (distance < arrivalRadius) {
      this.pos.set(destination.x + 2.2, terrainHeight(destination.x, destination.z) + 0.95, destination.z + 2.2)
      store.finishMission(`${this.name} guided you to ${destination.name}.`)
      store.showDialogue({
        speaker: this.name,
        role: this.job,
        text: styleNpcSpeech(this, `도착했어요. 여기가 ${destination.name}입니다. 제가 일하는 곳이에요.`),
        agent: this.snapshot(),
      })
      this.mission = null
      this.debugSpeedScale = 1
      return 'dwelling'
    }
    return 'walking'
  }

  updateNeeds(delta) {
    const walking = /walking|commuting|guiding|pickup/.test(this.activity)
    const resting = /resting|home|break|dwelling/.test(this.activity)
    const working = /shift|class|working|customers|rush/.test(this.activity)
    this.needs.energy = clampValue(this.needs.energy + (resting ? 0.004 : walking ? -0.0045 : working ? -0.0025 : -0.001) * delta, 0, 1)
    this.needs.hunger = clampValue(this.needs.hunger + (/cafe|break|home/.test(this.placeName?.toLowerCase?.() || '') ? -0.006 : 0.0022) * delta, 0, 1)
    this.needs.social = clampValue(this.needs.social - (working ? 0.0016 : 0.0009) * delta, 0, 1)
    this.needs.urgency = clampValue(this.needs.urgency + (walking ? -0.003 : working ? 0.0012 : -0.0008) * delta, 0, 1)
  }

  intentFor(target, timeMinutes) {
    if (this.needs.hunger > 0.78) return `looking for food after ${target.activity}`
    if (this.needs.energy < 0.28) return `saving energy while ${target.activity}`
    if (this.needs.social < 0.22) return `hoping to talk with someone near ${target.name}`
    if (target.activity === 'commuting') return `commuting toward ${target.name}`
    if (target.activity === 'class') return `getting through class at ${target.name}`
    if (target.activity === 'working' || target.activity === 'on shift') return `working toward: ${this.autonomy?.dailyGoal || 'today schedule'}`
    if (timeMinutes > 18 * 60) return `wrapping up: ${this.autonomy?.dailyGoal || 'evening routine'}`
    return this.autonomy?.dailyGoal ? `today goal: ${this.autonomy.dailyGoal}` : `following ${target.activity}`
  }

  remember(kind, text, placeName = this.placeName, weight = 0.5) {
    if (!text) return
    this.memories = [
      { kind, text: String(text).slice(0, 150), placeName, weight, time: performance.now() },
      ...this.memories.filter(memory => memory.text !== text),
    ].slice(0, 7)
  }

  applyBump(delta, cityOrRoads) {
    if (this.bumpVelocity.lengthSq() < 0.002) return
    const previous = { x: this.pos.x, z: this.pos.z }
    const next = {
      x: this.pos.x + this.bumpVelocity.x * delta,
      z: this.pos.z + this.bumpVelocity.y * delta,
    }
    const safe = resolveAgentMovement(this, previous, next, next, cityOrRoads)
    this.pos.x = safe.x
    this.pos.z = safe.z
    this.pos.y = terrainHeight(this.pos.x, this.pos.z) + 0.95
    this.bumpVelocity.multiplyScalar(Math.exp(-delta * 4.5))
  }

  bumpFrom(sourceX, sourceZ, impulse = 0.7) {
    const dx = this.pos.x - sourceX
    const dz = this.pos.z - sourceZ
    const distance = Math.hypot(dx, dz)
    const nx = distance > 0.001 ? dx / distance : Math.sin(hashValue(this.id) * 0.1)
    const nz = distance > 0.001 ? dz / distance : Math.cos(hashValue(this.id) * 0.1)
    const force = 2.3 + impulse * 3.2
    this.bumpVelocity.x += nx * force
    this.bumpVelocity.y += nz * force
    this.bumpTimer = Math.max(this.bumpTimer, 0.42 + impulse * 0.18)
    if (impulse > 1.02) this.fallTimer = Math.max(this.fallTimer, 1.05 + Math.min(0.65, impulse * 0.28))
    this.remember('collision', `I was bumped near ${this.placeName}.`, this.placeName, 0.72)
    this.talk(0.85)
  }

  talk(seconds = 6, partner = null, topic = null, timeMinutes = 0) {
    this.talkTimer = seconds
    this.socialCooldown = 20 + Math.random() * 20
    this.needs.social = clampValue(this.needs.social + 0.12, 0, 1)
    this.talkStartedAt = performance.now()
    this.visualGesture = socialGestureKind(this)
    this.talkPartnerId = partner?.id || null
    this.talkPartnerName = partner?.name || null
    this.talkTopicLabel = topic?.label || (partner ? 'sidewalk conversation' : 'player interaction')
    this.talkLine = null
    this.talkSource = null
    if (partner) {
      const conversation = topic || conversationTopicFor(this, partner, timeMinutes)
      this.talkTopicLabel = conversation.label
      this.talkSource = conversation.source || 'simulated-social'
      this.talkLine = conversation.lineFor?.(this, partner) || conversation.lines?.[this.id] || null
      const existing = this.relationships[partner.id] || {
        agentId: partner.id,
        name: partner.name,
        job: partner.job,
        trust: 0.28 + (hashValue(`${this.id}_${partner.id}`) % 18) / 100,
        talks: 0,
        firstMetAt: performance.now(),
      }
      const delta = relationshipDeltaFor(this, partner, conversation)
      const nextTrust = clampValue(existing.trust + delta, 0, 1)
      const next = {
        ...existing,
        trust: nextTrust,
        talks: existing.talks + 1,
        lastTopic: conversation.label,
        lastTopicId: conversation.id,
        lastPlaceName: this.placeName,
        lastSpokenAt: performance.now(),
      }
      this.relationships = { ...this.relationships, [partner.id]: next }
      this.relationshipCount = Object.keys(this.relationships).length
      this.lastInteraction = {
        partnerId: partner.id,
        partnerName: partner.name,
        partnerJob: partner.job,
        topicId: conversation.id,
        topic: conversation.label,
        line: this.talkLine,
        source: this.talkSource,
        placeName: this.placeName,
        trust: Number(next.trust.toFixed(2)),
        delta: Number(delta.toFixed(3)),
        talks: next.talks,
        at: performance.now(),
      }
      const llmBackedSocial = /^local-llm-social/.test(conversation.source || '')
      if (llmBackedSocial) {
        this.lastLlmConversation = {
          partnerId: partner.id,
          partnerName: partner.name,
          topicId: conversation.id,
          topic: conversation.label,
          line: this.talkLine,
          source: conversation.source,
          latencyMs: conversation.llmLatencyMs ?? null,
          at: performance.now(),
        }
      }
      this.currentIntent = `talking with ${partner.name} about ${conversation.label}`
      this.remember(llmBackedSocial ? 'llm-social' : 'social', conversation.memoryFor(this, partner), this.placeName, 0.66 + delta)
      this.refreshCognition({
        trigger: 'conversation',
        timeMinutes,
        partner,
        topic: conversation,
        activity: this.activity,
        placeName: this.placeName,
        nearbyAgents: 1,
      })
    }
  }

  snapshot(places) {
    const work = places?.get(this.workId)
    const third = places?.get(this.thirdId)
    return {
      id: this.id,
      name: this.name,
      age: this.age,
      gender: this.gender,
      job: this.job,
      role: this.role,
      personality: this.personality,
      speechStyle: this.speechStyle,
      voice: this.voice,
      gestureStyle: this.gestureStyle,
      personaSignature: this.personaSignature,
      appearance: this.appearance,
      styleBrief: this.styleBrief,
      autonomy: this.autonomy,
      cognition: this.cognition ? {
        architectureId: this.cognition.architecture?.id,
        selectedPolicy: this.cognition.selectedPolicy,
        reflection: this.cognition.reflection,
        retrievedMemories: this.cognition.retrievedMemories,
        utilityScores: this.cognition.utilityScores?.slice(0, 5),
        executionContract: this.cognition.executionContract,
      } : null,
      needs: this.needs,
      memories: this.memories,
      relationships: Object.values(this.relationships).slice(0, 5),
      relationshipCount: this.relationshipCount,
      lastInteraction: this.lastInteraction,
      currentIntent: this.currentIntent,
      llmAutonomy: this.llmAutonomy,
      activity: this.activity,
      placeName: this.placeName,
      socialReaction: this.socialReaction,
      playerDistance: this.playerDistance,
      facingPlayerAngle: this.facingPlayerAngle,
      talkPartnerId: this.talkPartnerId,
      talkPartnerName: this.talkPartnerName,
      talkTopicLabel: this.talkTopicLabel,
      talkLine: this.talkLine,
      talkSource: this.talkSource,
      lastLlmConversation: this.lastLlmConversation,
      visualGesture: this.visualGesture,
      renderFacingPartner: this.renderFacingPartner,
      facingPartnerAngle: this.facingPartnerAngle,
      workId: this.workId,
      workName: work?.name,
      workAddress: work?.address,
      thirdId: this.thirdId,
      thirdName: third?.name,
      thirdAddress: third?.address,
      homeAddress: this.home?.address,
      x: this.pos.x,
      z: this.pos.z,
      needErrand: this.needErrand ? {
        id: this.needErrand.id,
        reason: this.needErrand.reason,
        label: this.needErrand.label,
        targetName: this.needErrand.targetName,
        activity: this.needErrand.activity,
        cognitiveReason: this.needErrand.cognitiveReason,
        cognitionPolicy: this.needErrand.cognitionPolicy,
        mobilityMode: this.needErrand.mobilityMode || null,
        mobilitySource: this.needErrand.mobilitySource || null,
        mobilityDockName: this.needErrand.mobilityDockName || null,
        sharedMobilityTrip: this.needErrand.sharedMobilityTrip ? {
          id: this.needErrand.sharedMobilityTrip.id,
          mode: this.needErrand.sharedMobilityTrip.mode,
          phase: this.needErrand.sharedMobilityTrip.phase,
          pickupStationName: this.needErrand.sharedMobilityTrip.pickupStationName,
          returnStationName: this.needErrand.sharedMobilityTrip.returnStationName,
          returnSlotReserved: this.needErrand.sharedMobilityTrip.returnSlotReserved,
          pickupInventoryAfter: this.needErrand.sharedMobilityTrip.pickupInventoryAfter,
          returnInventoryAfter: this.needErrand.sharedMobilityTrip.returnInventoryAfter,
        } : null,
        remainingMinutes: errandMinutesRemaining(this.needErrand, useCityStore.getState().timeMinutes),
      } : null,
      mission: this.mission ? { mode: this.mission.mode, phase: this.mission.phase } : null,
      selfTaxi: this.selfTaxi ? {
        id: this.selfTaxi.id,
        phase: this.selfTaxi.phase,
        driverName: this.selfTaxi.driverName,
        targetName: this.selfTaxi.targetName,
      } : null,
    }
  }
}

function resolveAutonomyTargetPlace(result, places, scheduledTarget = null) {
  const list = [...(places?.values?.() || [])]
  if (result?.targetPlaceId) {
    const byId = places.get(result.targetPlaceId) || list.find(place => place.id === result.targetPlaceId)
    if (byId) return byId
  }
  if (result?.targetPlaceName) {
    const name = String(result.targetPlaceName).toLowerCase()
    const byName = list.find(place => String(place.name || '').toLowerCase().includes(name) || name.includes(String(place.name || '').toLowerCase()))
    if (byName) return byName
  }
  if (result?.targetKind) {
    const byKind = list.find(place => place.kind === result.targetKind)
    if (byKind) return byKind
  }
  if (scheduledTarget?.id) return places.get(scheduledTarget.id) || null
  return null
}

function nearestConversationPartner(agent, agents) {
  return agents
    .filter(item => item && item !== agent && !item.mission && !item.selfTaxi && item.talkTimer <= 0 && item.fallTimer <= 0)
    .map(item => ({ item, distance: agent.pos.distanceTo(item.pos) }))
    .filter(({ distance }) => distance <= 8.5)
    .sort((a, b) => a.distance - b.distance)[0]?.item || null
}

function nearestByDistance(items = [], x = 0, z = 0, filter = null) {
  return items
    .filter(item => !filter || filter(item))
    .map(item => ({
      item,
      distanceMeters: Math.hypot((item.x || 0) - x, (item.z || 0) - z),
    }))
    .sort((a, b) => a.distanceMeters - b.distanceMeters)[0] || null
}

function timeWindowActive(timeMinutes = 0, windowText = '') {
  const match = String(windowText).match(/(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})/)
  if (!match) return false
  const start = Number(match[1]) * 60 + Number(match[2])
  const end = Number(match[3]) * 60 + Number(match[4])
  const minute = ((timeMinutes % 1440) + 1440) % 1440
  return start <= end ? minute >= start && minute <= end : minute >= start || minute <= end
}

function roadDistanceToPoint(road, x, z) {
  if (!road) return Infinity
  if (road.axis === 'x') {
    const clampedX = clampValue(x, road.from, road.to)
    return Math.hypot(x - clampedX, z - road.z)
  }
  const clampedZ = clampValue(z, road.from, road.to)
  return Math.hypot(x - road.x, z - clampedZ)
}

function mobilityContextForAgent(agent, city, scheduledTarget, timeMinutes) {
  const mobility = city.mobilitySystem || {}
  const stations = mobility.gbfs?.stations || []
  const curbZones = mobility.smartCity?.curbZones || []
  const flows = mobility.smartCity?.trafficFlowObserved || []
  const geofences = mobility.gbfs?.geofencingZones || []
  const x = agent?.pos?.x || 0
  const z = agent?.pos?.z || 0
  const nearestDock = nearestByDistance(stations, x, z, station => station.status === 'active') || null
  const nearestCurbZone = nearestByDistance(curbZones, x, z) || null
  const nearestRoad = (city.roads || [])
    .map(road => ({ road, distance: roadDistanceToPoint(road, x, z) }))
    .sort((a, b) => a.distance - b.distance)[0]?.road || null
  const trafficFlow = flows.find(flow => flow.roadId === nearestRoad?.id) || flows[0] || null
  const geofence = geofences
    .map(zone => ({
      zone,
      distance: Math.hypot((zone.center?.x || 0) - x, (zone.center?.z || 0) - z),
    }))
    .filter(({ zone, distance }) => distance <= (zone.radius || 0))
    .sort((a, b) => a.distance - b.distance)[0]?.zone || null
  const activeDisruption = (mobility.gatsim?.disruptionEvents || [])
    .find(event => timeWindowActive(timeMinutes, event.timeWindow) || event.affectedPlace === scheduledTarget?.id) || null

  return {
    standard: 'GBFS + SmartCities + GATSim',
    nearestDock: nearestDock ? {
      id: nearestDock.item.id,
      name: nearestDock.item.name,
      roadName: nearestDock.item.roadName,
      distanceMeters: Number(nearestDock.distanceMeters.toFixed(1)),
      numBikesAvailable: nearestDock.item.numBikesAvailable,
      numScootersAvailable: nearestDock.item.numScootersAvailable,
      numDocksAvailable: nearestDock.item.numDocksAvailable,
      parkingRule: nearestDock.item.parkingRule,
    } : null,
    nearestCurbZone: nearestCurbZone ? {
      id: nearestCurbZone.item.id,
      purpose: nearestCurbZone.item.purpose,
      roadName: nearestCurbZone.item.roadName,
      distanceMeters: Number(nearestCurbZone.distanceMeters.toFixed(1)),
      enforcement: nearestCurbZone.item.enforcement,
    } : null,
    trafficFlow: trafficFlow ? {
      roadId: trafficFlow.roadId,
      roadName: trafficFlow.roadName,
      congestionLevel: trafficFlow.congestionLevel,
      averageVehicleSpeedKph: trafficFlow.averageVehicleSpeedKph,
      intensity: trafficFlow.intensity,
    } : null,
    geofence: geofence ? {
      id: geofence.id,
      rideAllowed: geofence.rideAllowed,
      parkingAllowed: geofence.parkingAllowed,
      maxSpeedKph: geofence.maxSpeedKph,
      rule: geofence.rule,
    } : null,
    activeDisruption: activeDisruption ? {
      id: activeDisruption.id,
      timeWindow: activeDisruption.timeWindow,
      affectedPlace: activeDisruption.affectedPlace,
      policy: activeDisruption.policy,
    } : null,
  }
}

function stationInventorySnapshot(station) {
  if (!station) return null
  return {
    bikes: station.numBikesAvailable || 0,
    scooters: station.numScootersAvailable || 0,
    docks: station.numDocksAvailable || 0,
  }
}

function syncGbfsStationStatus(city, station) {
  const status = city?.mobilitySystem?.gbfs?.stationStatus?.find(item => item.stationId === station?.id)
  if (!status || !station) return
  status.numBikesAvailable = station.numBikesAvailable || 0
  status.numScootersAvailable = station.numScootersAvailable || 0
  status.numDocksAvailable = station.numDocksAvailable || 0
  status.lastReportedRuntimeMutation = Date.now()
}

function stationPoint(station, label = 'GBFS dock') {
  if (!station) return null
  return {
    x: station.x,
    z: station.z,
    y: terrainHeight(station.x, station.z),
    name: label,
    roadId: station.roadId,
    roadName: station.roadName,
    roadAxis: station.roadAxis || null,
  }
}

function reserveSharedMobilityTrip(agent, mobilityMode, city, targetPlace, mobilityContext = {}) {
  const stations = city?.mobilitySystem?.gbfs?.stations || []
  if (!isSharedMobilityMode(mobilityMode) || !stations.length || !targetPlace) return null
  const vehicleField = mobilityMode === 'shared-scooter' ? 'numScootersAvailable' : 'numBikesAvailable'
  const pickup = stations.find(station => station.id === mobilityContext.nearestDock?.id) ||
    stations.find(station => station.name === mobilityContext.nearestDock?.name) ||
    nearestByDistance(stations, agent.pos.x, agent.pos.z, station => (station[vehicleField] || 0) > 0)?.item ||
    null
  if (!pickup || (pickup[vehicleField] || 0) <= 0) return null

  const returnStation = nearestByDistance(stations, targetPlace.x, targetPlace.z, station => (station.numDocksAvailable || 0) > 0)?.item || pickup
  const pickupBefore = stationInventorySnapshot(pickup)
  const returnBefore = stationInventorySnapshot(returnStation)
  pickup[vehicleField] = Math.max(0, (pickup[vehicleField] || 0) - 1)
  pickup.numDocksAvailable = Math.min(pickup.capacity || 99, (pickup.numDocksAvailable || 0) + 1)
  const returnSlotReserved = (returnStation.numDocksAvailable || 0) > 0
  if (returnSlotReserved) returnStation.numDocksAvailable = Math.max(0, (returnStation.numDocksAvailable || 0) - 1)
  syncGbfsStationStatus(city, pickup)
  if (returnStation !== pickup) syncGbfsStationStatus(city, returnStation)

  const now = performance.now()
  const trip = {
    id: `${mobilityMode}_${agent.id}_${Date.now()}`,
    mode: mobilityMode,
    vehicleType: mobilityMode === 'shared-scooter' ? 'e_scooter' : 'pedal_bike',
    phase: 'walking-to-dock',
    phaseStartedAt: now,
    pickupStationId: pickup.id,
    pickupStationName: pickup.name,
    returnStationId: returnStation.id,
    returnStationName: returnStation.name,
    pickup: stationPoint(pickup, `${pickup.name} pickup dock`),
    return: stationPoint(returnStation, `${returnStation.name} return dock`),
    pickupInventoryBefore: pickupBefore,
    pickupInventoryAfter: stationInventorySnapshot(pickup),
    returnInventoryBefore: returnBefore,
    returnInventoryAfter: null,
    returnSlotReserved,
    inventorySource: 'GBFS station_status runtime mutation',
    pickupAnimationSeconds: 2.2,
    returnAnimationSeconds: 2.0,
    pickupAnimationProgress: 0,
    returnAnimationProgress: 0,
  }

  useCityStore.getState().addCityEvent({
    id: `gbfs_reserve_${trip.id}`,
    kind: 'mobility',
    agentId: agent.id,
    agentName: agent.name,
    placeName: pickup.name,
    topic: `${mobilityMode}-reservation`,
    text: `${agent.name} reserves a ${mobilityMode} at ${pickup.name}; ${returnStation.name} holds a return slot from GBFS station_status.`,
  })
  return trip
}

function finishSharedMobilityReturn(agent, trip, city) {
  const stations = city?.mobilitySystem?.gbfs?.stations || []
  const returnStation = stations.find(station => station.id === trip?.returnStationId)
  if (!returnStation || !trip) return
  if (trip.mode === 'shared-scooter') returnStation.numScootersAvailable = (returnStation.numScootersAvailable || 0) + 1
  else returnStation.numBikesAvailable = (returnStation.numBikesAvailable || 0) + 1
  returnStation.numDocksAvailable = Math.max(0, returnStation.numDocksAvailable || 0)
  trip.returnInventoryAfter = stationInventorySnapshot(returnStation)
  trip.returnedAt = Date.now()
  syncGbfsStationStatus(city, returnStation)
  useCityStore.getState().addCityEvent({
    id: `gbfs_return_${trip.id}_${Date.now()}`,
    kind: 'mobility',
    agentId: agent.id,
    agentName: agent.name,
    placeName: returnStation.name,
    topic: `${trip.mode}-return`,
    text: `${agent.name} returns the ${trip.mode} at ${returnStation.name}; GBFS station_status inventory updates in real time.`,
  })
}

function executeAutonomyAction(agent, result, context) {
  const { agents, city, places, scheduledTarget, store, timeMinutes, reason } = context
  const action = result?.action || 'continue_schedule'
  const targetPlace = resolveAutonomyTargetPlace(result, places, scheduledTarget)
  let executed = false
  let outcome = 'observed'
  let targetName = targetPlace?.name || scheduledTarget?.name || result?.targetPlaceName || ''

  if (!result?.ok || agent.mission || agent.selfTaxi || agent.fallTimer > 0) {
    outcome = result?.ok ? 'busy' : 'llm-fallback-only'
  } else if (action === 'start_need_errand') {
    const profile = needErrandProfile(agent)
    if (profile && agent.startNeedErrand(profile, places, timeMinutes, true, agent.cognition)) {
      executed = true
      outcome = 'need-errand'
      targetName = agent.needErrand?.targetName || targetName
    } else if (targetPlace && agent.startLlmDirectedErrand(targetPlace, {
      label: 'LLM errand',
      activity: `checking ${targetPlace.name}`,
      thought: result.text,
      reason: result.reason,
    }, timeMinutes)) {
      executed = true
      outcome = 'directed-errand'
    } else {
      outcome = 'no-errand-target'
    }
  } else if (action === 'visit_place') {
    if (targetPlace && agent.startLlmDirectedErrand(targetPlace, {
      label: 'LLM place visit',
      activity: `visiting ${targetPlace.name}`,
      thought: result.text,
      reason: result.reason,
    }, timeMinutes)) {
      executed = true
      outcome = 'directed-place-route'
    } else {
      outcome = 'no-place-target'
    }
  } else if (action === 'social_check_in') {
    const partner = nearestConversationPartner(agent, agents)
    if (partner) {
      const topic = conversationTopicFor(agent, partner, timeMinutes)
      agent.talk(7.5, partner, topic, timeMinutes)
      partner.talk(7.5, agent, topic, timeMinutes)
      store.addCityEvent(conversationEventFor(agent, partner, topic, timeMinutes, `llm_social_${Date.now()}`))
      executed = true
      outcome = `talking-with-${partner.name}`
      targetName = partner.name
    } else {
      agent.talkTimer = Math.max(agent.talkTimer, 2.5)
      agent.routeStatus = 'local LLM wanted a social check-in but no partner was close'
      outcome = 'no-nearby-partner'
    }
  } else if (action === 'hail_taxi') {
    const taxiTarget = targetPlace ? scheduleTargetForPlace(targetPlace, agent.offset, city.roads) : scheduledTarget
    if (taxiTarget && startAutonomousNpcTaxi(agent, taxiTarget, city)) {
      executed = true
      outcome = 'self-called-taxi'
      targetName = taxiTarget.name
    } else {
      outcome = 'taxi-unavailable-or-too-close'
    }
  } else if (action === 'use_shared_bike' || action === 'use_shared_scooter') {
    const mobilityMode = action === 'use_shared_scooter' ? 'shared-scooter' : 'shared-bike'
    const dockName = result?.mobilityContext?.nearestDock?.name || 'nearby GBFS dock'
    const sharedMobilityTrip = reserveSharedMobilityTrip(agent, mobilityMode, city, targetPlace, result?.mobilityContext || {})
    if (targetPlace && sharedMobilityTrip && agent.startLlmDirectedErrand(targetPlace, {
      label: mobilityMode === 'shared-scooter' ? 'GBFS scooter trip' : 'GBFS bike trip',
      activity: `${mobilityMode} ride to ${targetPlace.name}`,
      thought: result.text,
      reason: result.reason,
      mobilityMode,
      mobilitySource: result.mobilitySource || 'GBFS station_status + SmartCities geofence',
      mobilityDockName: dockName,
      sharedMobilityTrip,
    }, timeMinutes)) {
      executed = true
      outcome = mobilityMode === 'shared-scooter' ? 'gbfs-scooter-route' : 'gbfs-bike-route'
      targetName = targetPlace.name
      store.addCityEvent({
        id: `llm_micromobility_${agent.id}_${Date.now()}`,
        kind: 'mobility',
        agentId: agent.id,
        agentName: agent.name,
        placeName: targetPlace.name,
        topic: mobilityMode,
        text: `${agent.name} chooses a ${mobilityMode} from ${dockName} using GBFS availability and SmartCities geofence rules.`,
      })
    } else {
      outcome = 'shared-mobility-target-unavailable'
    }
  } else if (action === 'replan_route') {
    agent.walkRoute = null
    agent.walkPlan = null
    agent.blockedContacts = 0
    agent.stuckTimer = 0
    agent.routeStatus = `local LLM requested route repair toward ${targetName || 'schedule'}`
    agent.remember('llm-action', agent.routeStatus, agent.placeName, 0.62)
    executed = true
    outcome = 'route-repair'
  } else if (action === 'pause_observe') {
    agent.talkTimer = Math.max(agent.talkTimer, 2.4)
    agent.routeStatus = 'local LLM paused to observe street context'
    executed = true
    outcome = 'pause-observe'
  } else {
    outcome = 'continue-schedule'
  }

  const execution = {
    action,
    executed,
    outcome,
    targetPlaceId: targetPlace?.id || result?.targetPlaceId || '',
    targetName,
    reason: result?.reason || reason,
    mobilityMode: result?.mobilityMode || (action === 'use_shared_bike' ? 'shared-bike' : action === 'use_shared_scooter' ? 'shared-scooter' : null),
    mobilitySource: result?.mobilitySource || (action === 'use_shared_bike' || action === 'use_shared_scooter' ? 'GBFS station_status + SmartCities geofence' : null),
    createdAt: Date.now(),
  }
  agent.llmAutonomy = {
    ...(agent.llmAutonomy || {}),
    action,
    targetPlaceId: execution.targetPlaceId,
    targetName,
    execution,
  }
  if (executed && !['need-errand', 'directed-errand', 'directed-place-route', 'self-called-taxi', 'gbfs-bike-route', 'gbfs-scooter-route'].includes(outcome)) {
    store.addCityEvent({
      id: `llm_action_${agent.id}_${Date.now()}`,
      kind: 'llm',
      agentId: agent.id,
      agentName: agent.name,
      placeName: agent.placeName,
      topic: 'npc autonomy action',
      text: `${agent.name} executes local-LLM action ${action}: ${outcome}.`,
    })
  }
  return execution
}

function autonomyEventFor(agent, timeMinutes) {
  const need = agent.needs || {}
  const route = agent.walkPlan?.mode && agent.walkPlan.mode !== 'direct'
    ? ` via ${agent.walkPlan.mode.replace('-', ' ')}`
    : ''
  const needText = need.hunger > 0.82
    ? 'is getting hungry'
    : need.energy < 0.24
      ? 'is visibly tired'
      : need.social < 0.2
        ? 'is looking for someone to talk to'
        : null
  const text = needText
    ? `${agent.name} ${needText} while ${agent.activity} near ${agent.placeName}.`
    : `${agent.name} is ${agent.activity} near ${agent.placeName}${route}; ${agent.currentIntent}.`
  return {
    id: `${agent.id}_${Math.floor(timeMinutes)}_${hashValue(text)}`,
    kind: needText ? 'need' : agent.walkPlan?.mode === 'crosswalk-crossing' ? 'crosswalk' : 'routine',
    agentId: agent.id,
    agentName: agent.name,
    placeName: agent.placeName,
    text,
  }
}

function strongestNeedPhrase(agent) {
  const needs = agent.needs || {}
  if (needs.hunger > 0.76) return 'finding food soon'
  if (needs.energy < 0.3) return 'saving energy'
  if (needs.social < 0.34) return 'catching up with someone'
  if (needs.urgency > 0.72) return 'keeping an urgent schedule'
  return agent.activity || 'staying on schedule'
}

function shortIntent(agent) {
  return String(agent.currentIntent || agent.autonomy?.dailyGoal || agent.activity || 'today routine')
    .replace(/^today:\s*/i, '')
    .replace(/^today goal:\s*/i, '')
    .slice(0, 72)
}

function conversationTopicFor(a, b, timeMinutes = 0) {
  const place = a.placeName || b.placeName || 'the block'
  const roadName = a.walkPlan?.roadName || b.walkPlan?.roadName || a.home?.roadName || b.home?.roadName || 'the nearest sidewalk'
  const targetA = a.walkPlan?.targetName || a.placeName || a.home?.name || 'the next stop'
  const targetB = b.walkPlan?.targetName || b.placeName || b.home?.name || 'the next stop'
  const hour = formatTime(timeMinutes || 0)
  const topics = [
    {
      id: 'schedule',
      label: `${hour} schedule around ${place}`,
      event: `${a.name} and ${b.name} compare schedules near ${place}; ${a.name} adjusts their next stop after hearing about ${targetB}.`,
      memoryFor: (self, partner) => `Talked with ${partner.name} about the ${hour} schedule and ${shortIntent(partner)}.`,
    },
    {
      id: 'route',
      label: `safe sidewalk route on ${roadName}`,
      event: `${a.name} and ${b.name} discuss the sidewalk route on ${roadName}; both keep to the curb rules before moving on.`,
      memoryFor: (self, partner) => `Checked the safer walking route on ${roadName} with ${partner.name}.`,
    },
    {
      id: 'neighborhood',
      label: `${place} street conditions`,
      event: `${a.name} and ${b.name} trade notes on traffic and crossings near ${place}.`,
      memoryFor: (self, partner) => `Noted ${place} street conditions after talking with ${partner.name}.`,
    },
    {
      id: 'needs',
      label: `${strongestNeedPhrase(a)} and ${strongestNeedPhrase(b)}`,
      event: `${a.name} notices ${b.name} is ${strongestNeedPhrase(b)}; they pause briefly near ${place}.`,
      memoryFor: (self, partner) => `Learned ${partner.name} is ${strongestNeedPhrase(partner)} near ${place}.`,
    },
    {
      id: 'work',
      label: `${a.job} work and ${b.job} work`,
      event: `${a.name} and ${b.name} talk about work routines near ${place}; the exchange changes how they remember each other.`,
      memoryFor: (self, partner) => `Talked with ${partner.name} about ${partner.job} work and ${shortIntent(self)}.`,
    },
  ]

  if (a.workId && a.workId === b.workId) {
    topics.unshift({
      id: 'same-workplace',
      label: `${a.workName || a.placeName || 'shared workplace'} coordination`,
      event: `${a.name} and ${b.name} coordinate a shared workplace errand near ${place}.`,
      memoryFor: (self, partner) => `Coordinated workplace timing with ${partner.name}.`,
    })
  }

  if (targetA === targetB && targetA) {
    topics.unshift({
      id: 'shared-destination',
      label: `shared destination ${targetA}`,
      event: `${a.name} and ${b.name} realize they are both heading toward ${targetA} and agree on a calmer route.`,
      memoryFor: (self, partner) => `Found out ${partner.name} is also heading toward ${targetA}.`,
    })
  }

  const index = hashValue(`${a.id}_${b.id}_${Math.floor((timeMinutes || 0) / 8)}_${place}`) % topics.length
  return topics[index]
}

function llmConversationTopicFor(a, b, fallbackTopic, result) {
  const generated = result?.topic || {}
  const lineA = generated.lineA || null
  const lineB = generated.lineB || null
  const fallbackMemory = (self, partner) => typeof fallbackTopic?.memoryFor === 'function'
    ? fallbackTopic.memoryFor(self, partner)
    : `Talked with ${partner?.name || 'a neighbor'} about ${fallbackTopic?.label || 'the block'}.`
  const id = generated.id || fallbackTopic?.id || 'llm-social'

  return {
    id,
    label: generated.label || fallbackTopic?.label || 'local LLM sidewalk conversation',
    event: generated.event || fallbackTopic?.event || `${a.name} and ${b.name} have a short local-LLM conversation on the sidewalk.`,
    source: result?.source || 'fallback:local-llm-social',
    llmLatencyMs: result?.latencyMs ?? null,
    llm: result?.llm || null,
    lines: {
      [a.id]: lineA,
      [b.id]: lineB,
    },
    lineFor: self => self?.id === a.id ? lineA : self?.id === b.id ? lineB : null,
    memoryFor: (self, partner) => {
      if (self?.id === a.id) return generated.memoryA || fallbackMemory(self, partner)
      if (self?.id === b.id) return generated.memoryB || fallbackMemory(self, partner)
      return fallbackMemory(self, partner)
    },
  }
}

function relationshipDeltaFor(a, b, topic) {
  const styleMatch = a.autonomy?.relationshipStyle && a.autonomy.relationshipStyle === b.autonomy?.relationshipStyle ? 0.012 : 0
  const sharedPlace = a.placeName && a.placeName === b.placeName ? 0.014 : 0
  const sharedWork = a.workId && a.workId === b.workId ? 0.018 : 0
  const socialNeed = a.needs?.social < 0.36 ? 0.016 : 0.006
  const practicalTopic = ['route', 'same-workplace', 'shared-destination'].includes(topic?.id) ? 0.012 : 0
  return clampValue(0.024 + styleMatch + sharedPlace + sharedWork + socialNeed + practicalTopic, 0.018, 0.084)
}

function conversationEventFor(a, b, topic, timeMinutes, prefix = 'talk') {
  const interaction = a.lastInteraction?.partnerId === b.id ? a.lastInteraction : null
  const lineA = topic.lineFor?.(a, b) || topic.lines?.[a.id] || null
  const lineB = topic.lineFor?.(b, a) || topic.lines?.[b.id] || null
  const text = lineA && lineB
    ? `${topic.event} ${a.name}: "${lineA}" ${b.name}: "${lineB}"`
    : topic.event
  return {
    id: `${prefix}_${a.id}_${b.id}_${topic.id || 'conversation'}_${Math.floor((timeMinutes || 0) * 10)}`,
    kind: 'conversation',
    agentId: a.id,
    agentName: a.name,
    partnerId: b.id,
    partnerName: b.name,
    placeName: a.placeName,
    topic: topic.label,
    source: topic.source || 'simulated-social',
    lineA,
    lineB,
    llmLatencyMs: topic.llmLatencyMs ?? null,
    relationshipTrust: interaction?.trust ?? null,
    relationshipDelta: interaction?.delta ?? null,
    text: String(text || '').slice(0, 260),
  }
}

function nearestRoadPickup(pos, roads) {
  let best = null
  let bestDistance = Infinity
  for (const road of roads) {
    const half = road.width * 0.58
    let x
    let z
    if (road.axis === 'x') {
      x = Math.max(road.from, Math.min(road.to, pos.x))
      const side = pos.z >= road.z ? 1 : -1
      z = road.z + side * half
      const laneDirection = side
      const vehicleStop = roadLanePoint(road, x, laneDirection)
      const distance = Math.hypot(pos.x - x, pos.z - z)
      if (distance < bestDistance) {
        bestDistance = distance
        best = {
          x,
          z,
          y: terrainHeight(x, z),
          name: `${road.name} curb`,
          roadName: road.name,
          roadId: road.id,
          roadAxis: road.axis,
          curbSide: side,
          laneDirection,
          vehicleStop: { ...vehicleStop, y: terrainHeight(vehicleStop.x, vehicleStop.z), name: `${road.name} curb lane`, roadName: road.name, roadId: road.id, roadAxis: road.axis, curbSide: side, laneDirection },
        }
      }
      continue
    } else {
      const side = pos.x >= road.x ? 1 : -1
      x = road.x + side * half
      z = Math.max(road.from, Math.min(road.to, pos.z))
      const laneDirection = -side
      const vehicleStop = roadLanePoint(road, z, laneDirection)
      const distance = Math.hypot(pos.x - x, pos.z - z)
      if (distance < bestDistance) {
        bestDistance = distance
        best = {
          x,
          z,
          y: terrainHeight(x, z),
          name: `${road.name} curb`,
          roadName: road.name,
          roadId: road.id,
          roadAxis: road.axis,
          curbSide: side,
          laneDirection,
          vehicleStop: { ...vehicleStop, y: terrainHeight(vehicleStop.x, vehicleStop.z), name: `${road.name} curb lane`, roadName: road.name, roadId: road.id, roadAxis: road.axis, curbSide: side, laneDirection },
        }
      }
    }
  }
  return best || { x: pos.x + 4, z: pos.z + 4, y: terrainHeight(pos.x + 4, pos.z + 4), name: 'curbside' }
}

function taxiStopForPickup(pickup, roads = []) {
  if (!pickup) return null
  if (pickup.vehicleStop) return { ...pickup.vehicleStop, passengerCurb: { x: pickup.x, z: pickup.z } }
  const curb = nearestRoadPickup(pickup, roads)
  return curb.vehicleStop ? { ...curb.vehicleStop, passengerCurb: { x: curb.x, z: curb.z } } : curb
}

function normalizeRouteText(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9가-힣]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function placeMatchesText(place, text) {
  return includesPlaceCandidate(text, [place.id, place.name, place.kind, place.address, place.roadName, place.district, place.buildingType])
}

function routePlacesForRequest(request, city, player) {
  const landmarks = city.landmarks || []
  const addresses = city.addressBook || []
  const explicitAddresses = addresses.filter(place => placeMatchesText(place, request)).slice(0, 36)
  const nearbyAddresses = [...addresses]
    .sort((a, b) => Math.hypot(a.x - player.x, a.z - player.z) - Math.hypot(b.x - player.x, b.z - player.z))
    .slice(0, 18)
  const merged = new Map()

  for (const place of [...explicitAddresses, ...landmarks, ...nearbyAddresses]) {
    merged.set(place.id, {
      id: place.id,
      name: place.name,
      kind: place.kind,
      address: place.address,
      roadName: place.roadName,
      district: place.district,
      buildingType: place.buildingType,
      x: place.x,
      z: place.z,
    })
  }

  return [...merged.values()]
}

function destinationFromPlan(plan, agent, places, request = '', destinations = places) {
  if (plan.destination === 'named_place') {
    const placeList = [...destinations.values()]
    const targetId = typeof plan.targetPlaceId === 'string' ? plan.targetPlaceId : ''
    const targetName = typeof plan.targetPlaceName === 'string' ? plan.targetPlaceName : ''
    const byId = targetId ? (destinations.get(targetId) || places.get(targetId)) : null
    if (byId) return byId

    if (targetName) {
      const normalizedName = normalizeRouteText(targetName)
      const byName = placeList.find(place => [place.id, place.name, place.kind, place.address, place.roadName, place.district, place.buildingType].some(value => {
        const normalizedValue = normalizeRouteText(value)
        return normalizedValue && (normalizedValue.includes(normalizedName) || normalizedName.includes(normalizedValue))
      }))
      if (byName) return byName
    }

    const byRequest = matchRequestedPlace(request, placeList)
    if (byRequest) return byRequest
  }
  if (plan.destination === 'home') return { ...agent.home, name: agent.home.name || 'home' }
  if (plan.destination === 'third') {
    const third = places.get(agent.thirdId)
    if (third) return third
  }
  const work = places.get(agent.workId)
  return work || [...places.values()][0]
}

function setLocalPart(mesh, index, dummy, base, yaw, local, scale, rotX = 0, rotZ = 0) {
  const cos = Math.cos(yaw)
  const sin = Math.sin(yaw)
  dummy.position.set(
    base.x + local[0] * cos + local[2] * sin,
    base.y + local[1],
    base.z - local[0] * sin + local[2] * cos,
  )
  dummy.rotation.set(rotX, yaw, rotZ)
  dummy.scale.set(scale[0], scale[1], scale[2])
  dummy.updateMatrix()
  mesh.setMatrixAt(index, dummy.matrix)
}

// ---------------------------------------------------------------------------
// Humanoid v2 — articulated procedural rig helpers (owned by Actors.jsx).
// The crowd is drawn with shared instanced meshes and no per-agent Object3D
// hierarchy, so limb bending is done with hand-rolled forward kinematics:
// joint positions are computed in the agent's local frame, converted to world
// with the heading yaw, and each bone is drawn as a capsule stretched between
// two joints. All scratch math reuses the module-level temporaries below so the
// per-frame loop performs zero heap allocation for the near-agent articulation.
// ---------------------------------------------------------------------------
const _UP = new THREE.Vector3(0, 1, 0)
const _XA = new THREE.Vector3(1, 0, 0)
const _ZA = new THREE.Vector3(0, 0, 1)
const _segDir = new THREE.Vector3()
const _segQuat = new THREE.Quaternion()
const _boneV = new THREE.Vector3()
const _jointA = new THREE.Vector3()
const _jointB = new THREE.Vector3()
const _jointC = new THREE.Vector3()
const NPC_BASE_SCRATCH = { x: 0, y: 0, z: 0 }
const NPC_ZERO = [0, 0, 0]
const NPC_HIDE = [0.0001, 0.0001, 0.0001]
const NPC_NEAR_DIST = 90 // full articulation only within this radius of the player/camera
const NPC_RUN_SPEED = 2.4 // world units / second above which the walk gait becomes a run
const NPC_GAIT_STRIDE_RATE = 3.4 // radians of gait phase advanced per world unit travelled (anti-skate)
const NPC_ACTION_BLEND = 0.25 // seconds to ease an action pose in and back out
const NPC_ACTION_SCRATCH = {
  rootDrop: 0, lean: 0, leanZ: 0,
  thighL: 0, thighR: 0, kneeL: 0, kneeR: 0,
  shL: 0, shR: 0, latL: 0, latR: 0, elbL: 0, elbR: 0,
}

// Convert a point in the agent's local frame (x=right, y=up, z=forward) into
// world space given the heading cos/sin, writing into `out` (reused vector).
function localWorld(base, cos, sin, lx, ly, lz, out) {
  out.set(base.x + lx * cos + lz * sin, base.y + ly, base.z - lx * sin + lz * cos)
}

// Draw a capsule bone spanning world-space joints a -> b. The limb capsule
// geometry is capsuleGeometry([1, 2, ...]) whose tip-to-tip length is 4, so
// scaling Y by len*0.25 makes the drawn segment exactly `len` long.
function setBone(mesh, index, dummy, a, b, radius) {
  _segDir.set(b.x - a.x, b.y - a.y, b.z - a.z)
  const len = _segDir.length() || 0.0001
  _segDir.multiplyScalar(1 / len)
  _segQuat.setFromUnitVectors(_UP, _segDir)
  dummy.position.set((a.x + b.x) * 0.5, (a.y + b.y) * 0.5, (a.z + b.z) * 0.5)
  dummy.quaternion.copy(_segQuat)
  dummy.scale.set(radius, len * 0.25, radius)
  dummy.updateMatrix()
  mesh.setMatrixAt(index, dummy.matrix)
}

// Fill `out` with target joint angles for a capability-animation id. Angle
// convention (radians): thigh/shoulder pitch positive swings the limb forward,
// knee/elbow bend positive folds the lower segment, lat positive abducts the
// arm outward, lean positive tips the torso forward, rootDrop lowers the hips.
// `t` is elapsed seconds since the action started, `dur` its length, `h` height.
function actionPose(out, rawId, t, dur, h) {
  const id = String(rawId || '').toLowerCase()
  const has = s => id.indexOf(s) >= 0
  // neutral standing defaults; every family overrides a subset of these
  out.rootDrop = 0; out.lean = 0; out.leanZ = 0
  out.thighL = 0.05; out.thighR = 0.05; out.kneeL = 0.12; out.kneeR = 0.12
  out.shL = 0.12; out.shR = 0.12; out.latL = 0.05; out.latR = 0.05
  out.elbL = 0.30; out.elbR = 0.30
  if (has('sit')) {
    out.rootDrop = 0.34 * h; out.thighL = out.thighR = 1.45; out.kneeL = out.kneeR = 1.5
    out.lean = 0.06; out.shL = out.shR = 0.35; out.elbL = out.elbR = 0.55; out.latL = out.latR = 0.08
  } else if (has('lie') || has('sleep') || has('rest')) {
    out.rootDrop = 0.55 * h; out.lean = 1.15
    out.thighL = out.thighR = 0.12 + Math.sin(t * 1.4) * 0.02
    out.kneeL = out.kneeR = 0.18; out.shL = out.shR = 0.1; out.elbL = out.elbR = 0.22
  } else if (has('crouch')) {
    out.rootDrop = 0.34 * h; out.thighL = out.thighR = 1.25; out.kneeL = out.kneeR = 1.5
    out.lean = 0.28; out.shL = out.shR = 0.4; out.elbL = out.elbR = 0.7
  } else if (has('pickup') || has('pick') || has('putdown') || has('put') || has('grab') || has('lift')) {
    const c = 0.5 - 0.5 * Math.cos(Math.min(1, t / Math.max(0.4, dur * 0.5)) * Math.PI)
    out.lean = 0.5 + c * 0.4; out.thighL = out.thighR = 0.35 + c * 0.25; out.kneeL = out.kneeR = 0.4 + c * 0.5
    out.shL = out.shR = 0.7 + c * 0.5; out.elbL = out.elbR = 0.35 - c * 0.15
  } else if (has('carry') || has('hold')) {
    out.shL = out.shR = 0.85; out.elbL = out.elbR = 1.55; out.latL = out.latR = 0.14; out.thighL = out.thighR = 0.08
  } else if (has('throw')) {
    const p = Math.min(1, t / Math.max(0.3, dur))
    const wind = p < 0.45 ? p / 0.45 : 1 - (p - 0.45) / 0.55
    out.shR = -0.5 + (1 - wind) * 2.2; out.elbR = 1.5 - (1 - wind) * 1.2; out.leanZ = -0.15 * wind
    out.shL = 0.4; out.elbL = 0.8; out.lean = 0.1
  } else if (has('pour')) {
    out.shR = 1.0; out.elbR = 1.1; out.latR = 0.2; out.leanZ = 0.25 + Math.sin(t * 2) * 0.12
    out.shL = 0.3; out.elbL = 0.9
  } else if (has('press') || has('poke') || has('push') || has('button')) {
    const L = 0.5 + 0.5 * Math.sin(t * 4)
    out.shR = 1.1; out.elbR = 0.9 - L * 0.6; out.lean = 0.08
  } else if (has('give') || has('offer')) {
    out.shL = out.shR = 1.05; out.elbL = out.elbR = 0.5; out.latL = out.latR = 0.12; out.lean = 0.12
  } else if (has('eat') || has('drink') || has('bite') || has('sip')) {
    const L = 0.5 + 0.5 * Math.sin(t * 2.4)
    out.shR = 0.8 + L * 0.15; out.elbR = 1.4 + L * 0.8; out.shL = 0.2; out.elbL = 0.5
  } else if (has('cook') || has('work') || has('repair') || has('build') || has('clean') || has('wash') || has('fix') || has('craft') || has('mix') || has('stir') || has('scrub')) {
    const L = Math.sin(t * 3.4)
    out.lean = 0.24; out.shL = 0.75 + L * 0.2; out.shR = 0.75 - L * 0.2
    out.elbL = 1.1 + L * 0.3; out.elbR = 1.1 - L * 0.3; out.latL = out.latR = 0.08
  } else if (has('wave') || has('hello') || has('greet')) {
    const L = Math.sin(t * 6)
    out.shR = 2.35; out.latR = 0.35 + L * 0.05; out.elbR = 0.3 + (L * 0.5 + 0.5) * 0.5; out.shL = 0.12; out.elbL = 0.3
  } else if (has('talk') || has('speak') || has('chat') || has('explain') || has('discuss')) {
    const L = Math.sin(t * 3)
    out.shR = 0.45 + L * 0.18; out.elbR = 1.0 + L * 0.2; out.shL = 0.32 - L * 0.12; out.elbL = 0.9; out.lean = 0.03
  } else if (has('phone') || has('call')) {
    out.shR = 1.35; out.latR = 0.28; out.elbR = 2.45; out.shL = 0.14; out.elbL = 0.35
  } else if (has('help') || has('comfort') || has('support') || has('care')) {
    out.lean = 0.3; out.shR = 1.0; out.elbR = 0.45; out.latR = 0.18; out.shL = 0.5; out.elbL = 0.7
  } else if (has('transact') || has('vote') || has('pay') || has('buy') || has('sell') || has('tap')) {
    const L = 0.5 + 0.5 * Math.sin(t * 2)
    out.shR = 1.15; out.elbR = 0.3 + L * 0.15; out.lean = 0.05
  } else if (has('dance')) {
    const L = Math.sin(t * 4)
    const L2 = Math.sin(t * 4 + Math.PI / 2)
    out.shR = 1.2 + L * 0.8; out.shL = 1.2 - L * 0.8; out.elbR = 1.0; out.elbL = 1.0
    out.latR = 0.5; out.latL = 0.5; out.leanZ = L * 0.18
    out.thighR = 0.1 + Math.max(0, L2) * 0.4; out.thighL = 0.1 + Math.max(0, -L2) * 0.4
    out.kneeR = 0.2 + Math.max(0, L2) * 0.5; out.kneeL = 0.2 + Math.max(0, -L2) * 0.5
    out.rootDrop = (0.5 + 0.5 * Math.sin(t * 8)) * 0.05 * h
  } else if (has('laugh') || has('giggle')) {
    const L = Math.sin(t * 9)
    out.lean = 0.22 + L * 0.08; out.shL = out.shR = 0.5; out.elbL = out.elbR = 1.3; out.leanZ = L * 0.04
  } else if (has('exercise') || has('squat') || has('workout')) {
    const c = 0.5 - 0.5 * Math.cos(t * 3)
    out.rootDrop = c * 0.32 * h; out.thighL = out.thighR = c * 1.3; out.kneeL = out.kneeR = c * 1.5
    out.shL = out.shR = 1.4; out.elbL = out.elbR = 0.2
  } else if (has('climb') || has('ladder') || has('stairs')) {
    const L = Math.sin(t * 3)
    out.thighR = 0.3 + Math.max(0, L) * 1.0; out.thighL = 0.3 + Math.max(0, -L) * 1.0
    out.kneeR = 0.4 + Math.max(0, L) * 1.1; out.kneeL = 0.4 + Math.max(0, -L) * 1.1
    out.shR = 1.6 + Math.max(0, -L) * 0.9; out.shL = 1.6 + Math.max(0, L) * 0.9
    out.elbR = 0.6; out.elbL = 0.6; out.latR = 0.15; out.latL = 0.15; out.lean = 0.15
  } else if (has('jump') || has('leap') || has('hop')) {
    const p = Math.min(1, t / Math.max(0.5, dur))
    let drop = 0; let thigh = 0.1; let knee = 0.15; let sh = 0.4
    if (p < 0.25) { const k = p / 0.25; drop = k * 0.3 * h; thigh = k * 1.1; knee = k * 1.4; sh = 0.4 + k * 0.3 }
    else if (p < 0.5) { const k = (p - 0.25) / 0.25; drop = (1 - k) * 0.3 * h - k * 0.12 * h; thigh = 1.1 * (1 - k); knee = 1.4 * (1 - k); sh = 0.7 + k * 1.6 }
    else if (p < 0.75) { drop = -0.12 * h; thigh = 0.1; knee = 0.15; sh = 2.3 }
    else { const k = (p - 0.75) / 0.25; drop = (1 - k) * (-0.12 * h) + k * 0.06 * h; thigh = 0.1 + k * 0.4; knee = 0.15 + k * 0.6; sh = 2.3 - k * 1.9 }
    out.rootDrop = drop; out.thighL = out.thighR = thigh; out.kneeL = out.kneeR = knee
    out.shL = out.shR = sh; out.elbL = out.elbR = 0.2
  } else {
    // emote / shrug / unknown id -> gentle two-handed shrug
    const L = Math.sin(t * 2)
    out.shL = out.shR = 0.25 + Math.max(0, L) * 0.15; out.latL = out.latR = 0.25
    out.elbL = out.elbR = 1.35; out.lean = L * 0.03
  }
}

function hashValue(value) {
  let hash = 0
  const text = String(value || '')
  for (let i = 0; i < text.length; i += 1) hash = (hash * 31 + text.charCodeAt(i)) >>> 0
  return hash
}

function skinTone(agent) {
  if (agent.appearance?.skinColor) return agent.appearance.skinColor
  const tones = ['#f0c49b', '#d8a17d', '#b98262', '#efd2b3', '#9f6a4f']
  return tones[hashValue(agent.id) % tones.length]
}

function hairTone(agent) {
  if (agent.appearance?.hairColor) return agent.appearance.hairColor
  const tones = ['#17100b', '#2b1b12', '#4b3527', '#111318', '#6b5949']
  return tones[hashValue(`${agent.id}_hair`) % tones.length]
}

// ATANOR ambassadors wear a signature look so the player can spot them instantly: bright ATANOR
// teal top + sleeves + accent, a light jacket to make the teal read, so they glow out of the crowd
// whose outfits are muted procedural hues. Everyone else keeps their generated appearance.
const ATANOR_LOOK = {
  topColor: '#00e5c0', jacketColor: '#0b3b34', pantsColor: '#0d2b28',
  shoeColor: '#052420', accessoryColor: '#7cffe6',
}

function agentLook(agent) {
  if (agent.brain === 'atanor') {
    return { ...(agent.appearance || {}), ...ATANOR_LOOK }
  }
  return agent.appearance || {
    heightScale: 1,
    shoulderScale: 1,
    bodyScale: 1,
    legScale: 1,
    headScale: 1,
    walkStyle: { id: 'default', cadence: 1, stride: 1, armSwing: 1, speed: 1 },
    bodyArchetype: 'average_relaxed',
    outfitPattern: 'solid',
    outerwear: 'overshirt',
    accessory: 'none',
    glassesStyle: 'none',
    scarfStyle: 'none',
    hairStyle: 'short',
    hatStyle: 'none',
    bagStyle: 'backpack',
    bottomStyle: 'pants',
    topColor: agent.color || '#2f6f9f',
    jacketColor: '#d9e2ea',
    pantsColor: '#1f2937',
    shoeColor: '#10151c',
    accessoryColor: '#473120',
  }
}

function socialGestureKind(agent) {
  const text = String(agent.gestureStyle || agent.speechStyle?.gesture || '').toLowerCase()
  if (text.includes('phone')) return 'checks-phone'
  if (text.includes('point')) return 'points-while-speaking'
  if (text.includes('wave')) return 'small-wave'
  if (text.includes('bag')) return 'adjusts-bag-strap'
  if (text.includes('fold')) return 'folds-arms'
  if (text.includes('bow')) return 'formal-bow'
  if (text.includes('look')) return 'looks-around'
  if (text.includes('pocket')) return 'hands-in-pockets'
  return 'quick-nod'
}

function trafficPose(car, tValue = car.t) {
  const arcPose = vehicleTurnArcPose(car)
  if (arcPose) return arcPose
  const t = car.direction > 0 ? tValue : 1 - tValue
  const span = car.road.to - car.road.from
  if (car.road.axis === 'x') {
    return {
      x: car.road.from + span * t,
      z: car.road.z + car.lane,
      yaw: car.direction > 0 ? Math.PI / 2 : -Math.PI / 2,
    }
  }
  return {
    x: car.road.x + car.lane,
    z: car.road.from + span * t,
    yaw: car.direction > 0 ? 0 : Math.PI,
  }
}

function shouldYieldToPedestrian(car, pose, pedestrians) {
  for (const pedestrian of pedestrians) {
    if (car.road.axis === 'x') {
      const lateral = Math.abs(pedestrian.z - car.road.z)
      const ahead = car.direction > 0 ? pedestrian.x - pose.x : pose.x - pedestrian.x
      if (lateral < car.road.width * 0.72 && ahead > -5 && ahead < 26) return pedestrian
    } else {
      const lateral = Math.abs(pedestrian.x - car.road.x)
      const ahead = car.direction > 0 ? pedestrian.z - pose.z : pose.z - pedestrian.z
      if (lateral < car.road.width * 0.72 && ahead > -5 && ahead < 26) return pedestrian
    }
  }
  return null
}

function upcomingIntersectionForCar(car, pose, roads) {
  const crossRoads = roads.filter(road => road.axis !== car.road.axis && road.main)
  let nearest = null
  for (const cross of crossRoads) {
    if (car.road.axis === 'x') {
      if (cross.x < car.road.from || cross.x > car.road.to) continue
      const stopLine = cross.x - car.direction * cross.width * 0.92
      const distance = car.direction > 0 ? stopLine - pose.x : pose.x - stopLine
      if (distance > 0 && (!nearest || distance < nearest.distance)) {
        nearest = {
          crossRoad: cross,
          distance,
          stopLine,
          intersectionAlong: cross.x,
          center: { x: cross.x, z: car.road.z },
        }
      }
    } else {
      if (cross.z < car.road.from || cross.z > car.road.to) continue
      const stopLine = cross.z - car.direction * cross.width * 0.92
      const distance = car.direction > 0 ? stopLine - pose.z : pose.z - stopLine
      if (distance > 0 && (!nearest || distance < nearest.distance)) {
        nearest = {
          crossRoad: cross,
          distance,
          stopLine,
          intersectionAlong: cross.z,
          center: { x: car.road.x, z: cross.z },
        }
      }
    }
  }
  return nearest
}

function distanceToSignalStop(car, pose, roads) {
  return upcomingIntersectionForCar(car, pose, roads)?.distance ?? Infinity
}

function shouldStopForSignal(car, pose, roads, timeMinutes, mobilitySystem = null) {
  const movement = car.turnIntent === 'left' ? 'left' : car.turnIntent === 'right' ? 'right' : 'through'
  const movementSignal = trafficSignalForMovement(car.road.axis, movement, timeMinutes, mobilitySystem)
  const signal = movementSignal.signal || trafficSignalForAxis(car.road.axis, timeMinutes, mobilitySystem)
  const phase = trafficPhaseAt(timeMinutes, mobilitySystem)
  if (signal === 'green') return null
  const stopDistance = distanceToSignalStop(car, pose, roads)
  if (signal === 'yellow') {
    if (stopDistance > 10 && stopDistance < 34) return { signal, stopDistance, phase: phase.kind, rule: 'yellow-far-decelerate', movementSignal }
    return null
  }
  if (stopDistance > 1.6 && stopDistance < 36) {
    return {
      signal: phase.kind === 'all-red' ? 'all-red' : signal,
      stopDistance,
      phase: phase.kind,
      rule: phase.kind === 'all-red' ? 'all-red-clearance-stop' : 'red-stop-at-stop-bar',
      movementSignal,
    }
  }
  return null
}

function trafficStateForCar(car, roads, index, store) {
  if (car.kind === 'taxi') ensureTaxiCruise(car, roads, index)
  const dim = car.dimensions || { width: 2.05, height: 0.72, length: 4.35, cabinLength: 1.82, cabinHeight: 0.58 }
  const assignedPose = assignedTaxiPose(car, store)
  const pose = assignedPose || taxiPoseForCar(car, roads, index)
  const road = pose.road || car.activeRoad || car.road
  const direction = pose.direction ?? car.activeDirection ?? car.direction
  const laneOffset = road.axis === 'x' ? pose.z - road.z : pose.x - road.x
  const along = road.axis === 'x'
    ? clampValue(pose.x, road.from, road.to)
    : clampValue(pose.z, road.from, road.to)
  return {
    car,
    index,
    dim,
    assignedPose,
    pose,
    trafficCar: { ...car, road, direction },
    road,
    direction,
    along,
    laneOffset,
    laneKey: `${road.id}:${direction}:${laneOffset.toFixed(1)}`,
  }
}

function frontVehicleFor(state, trafficStates) {
  if (state.assignedPose) return null
  const span = Math.max(1, state.road.to - state.road.from)
  let best = null
  for (const other of trafficStates) {
    if (!other || other.index === state.index || other.assignedPose) continue
    if (other.laneKey !== state.laneKey) continue
    let distance = state.direction > 0
      ? other.along - state.along
      : state.along - other.along
    if (distance <= -2) distance += span
    if (distance <= 0.8 || distance > 140) continue
    if (!best || distance < best.distance) best = { state: other, distance }
  }
  if (!best) return null

  const temperamentGap = {
    careful: 18,
    patient: 16,
    calm: 14,
    hurried: 11,
  }[state.car.driverTemperament] || 14
  const desiredGap = temperamentGap + state.dim.length * 0.8 + Math.min(13, state.car.speed * 0.72)
  const cautionGap = desiredGap + 18
  if (best.distance >= cautionGap) {
    return {
      vehicleId: best.state.car.id,
      driverName: best.state.car.driverName,
      distance: Number(best.distance.toFixed(2)),
      desiredGap: Number(desiredGap.toFixed(2)),
      intensity: 0,
    }
  }

  const intensity = best.distance <= desiredGap
    ? clampValue(0.58 + (desiredGap - best.distance) / Math.max(1, desiredGap), 0.58, 1)
    : clampValue(((cautionGap - best.distance) / Math.max(1, cautionGap - desiredGap)) * 0.42, 0.04, 0.42)

  return {
    vehicleId: best.state.car.id,
    driverName: best.state.car.driverName,
    distance: Number(best.distance.toFixed(2)),
    desiredGap: Number(desiredGap.toFixed(2)),
    intensity,
  }
}

function distanceToIntersectionAlong(state, intersectionAlong) {
  return state.direction > 0
    ? intersectionAlong - state.along
    : state.along - intersectionAlong
}

function pointInVehicleBody(pose, dim, point, padding = 0.72) {
  const dx = point.x - pose.x
  const dz = point.z - pose.z
  const cos = Math.cos(pose.yaw)
  const sin = Math.sin(pose.yaw)
  const localX = dx * cos - dz * sin
  const localZ = dx * sin + dz * cos
  return Math.abs(localX) < dim.width / 2 + padding && Math.abs(localZ) < dim.length / 2 + padding
}

function turnContextForCar(state, roads = []) {
  const intent = state.car.turnIntent || 'straight'
  if (state.car.turnArc) {
    const arc = state.car.turnArc
    return {
      intent: arc.intent,
      direction: arc.intent,
      active: true,
      arcActive: true,
      distanceToDecision: Number(Math.max(0, (arc.length || 0) - (arc.progress || 0)).toFixed(2)),
      intersectionRoadId: arc.toRoad?.id || null,
      intersectionRoadName: arc.toRoadName || null,
      intersectionAlong: roadAlongFromPoint(arc.toRoad, arc.end),
      intersectionCenter: null,
      crossRoad: arc.toRoad,
      laneRule: state.car.turnLaneRule || 'lane-level-steering-arc',
      turnSignalDistanceMeters: state.car.turnSignalDistanceMeters || state.road.laneModel?.turnSignalDistanceMeters || 42,
      turnPocketLengthMeters: state.road.laneModel?.turnPocketLengthMeters || null,
      plannedSignalSide: state.car.plannedTurnSignalSide || null,
      source: arc.source,
    }
  }
  const turnSignalDistance = state.car.turnSignalDistanceMeters || state.road.laneModel?.turnSignalDistanceMeters || 42
  const upcoming = upcomingIntersectionForCar(state.trafficCar, state.pose, roads)
  const stopDistance = upcoming?.distance ?? Infinity
  const active = intent !== 'straight' && Number.isFinite(stopDistance) && stopDistance > 0 && stopDistance <= turnSignalDistance
  return {
    intent,
    direction: intent,
    active,
    distanceToDecision: Number.isFinite(stopDistance) ? Number(stopDistance.toFixed(2)) : null,
    intersectionRoadId: upcoming?.crossRoad?.id || null,
    intersectionRoadName: upcoming?.crossRoad?.name || null,
    intersectionAlong: upcoming?.intersectionAlong ?? null,
    intersectionCenter: upcoming?.center || null,
    crossRoad: upcoming?.crossRoad || null,
    laneRule: state.car.turnLaneRule || state.road.laneModel?.turnLanePolicy || 'through-lane',
    turnSignalDistanceMeters: turnSignalDistance,
    turnPocketLengthMeters: state.road.laneModel?.turnPocketLengthMeters || null,
    plannedSignalSide: state.car.plannedTurnSignalSide || null,
    source: 'procedural turn intention + right-hand lane policy',
  }
}

function pedestrianInTurnConflictZone(state, turnContext, pedestrians) {
  if (!turnContext?.intersectionCenter || !turnContext.crossRoad) return null
  const roadHalf = state.road.width / 2
  const crossHalf = turnContext.crossRoad.width / 2
  const boxX = state.road.axis === 'x' ? crossHalf + 9 : roadHalf + 9
  const boxZ = state.road.axis === 'x' ? roadHalf + 9 : crossHalf + 9
  for (const pedestrian of pedestrians) {
    if (!pedestrian || /taxi|riding|boarding/i.test(pedestrian.state || '')) continue
    const dx = Math.abs(pedestrian.x - turnContext.intersectionCenter.x)
    const dz = Math.abs(pedestrian.z - turnContext.intersectionCenter.z)
    if (dx <= boxX && dz <= boxZ) return pedestrian
  }
  return null
}

function oncomingVehicleForTurn(state, turnContext, trafficStates) {
  if (turnContext?.direction !== 'left' || typeof turnContext.intersectionAlong !== 'number') return null
  let nearest = null
  for (const other of trafficStates) {
    if (!other || other.index === state.index || other.assignedPose) continue
    if (other.road.id !== state.road.id || other.direction === state.direction) continue
    const distance = distanceToIntersectionAlong(other, turnContext.intersectionAlong)
    if (distance < -6 || distance > 52) continue
    if (!nearest || distance < nearest.distance) nearest = { state: other, distance }
  }
  return nearest
}

function crossingVehicleForTurn(state, turnContext, trafficStates) {
  if (!turnContext?.crossRoad || !turnContext.intersectionCenter) return null
  let nearest = null
  for (const other of trafficStates) {
    if (!other || other.index === state.index || other.assignedPose) continue
    if (other.road.id !== turnContext.crossRoad.id) continue
    const distance = Math.hypot(other.pose.x - turnContext.intersectionCenter.x, other.pose.z - turnContext.intersectionCenter.z)
    if (distance > 30) continue
    if (!nearest || distance < nearest.distance) nearest = { state: other, distance }
  }
  return nearest
}

function turnControlForCar(state, turnContext, trafficStates, pedestrians, phase = null) {
  if (!turnContext?.active || turnContext.direction === 'straight') return null
  if (turnContext.arcActive) {
    return {
      type: 'lane-level-steering-arc',
      reason: null,
      intensity: 0.18,
      mustYield: false,
      targetId: null,
      targetName: null,
      distance: turnContext.distanceToDecision,
      priorityRule: 'vehicle body follows a curved lane-level steering arc through the intersection',
      policy: 'turning vehicle has already accepted the conflict gap and is completing the lane-change arc',
      source: turnContext.source,
    }
  }
  const distance = typeof turnContext.distanceToDecision === 'number' ? turnContext.distanceToDecision : turnContext.turnSignalDistanceMeters
  const signalDistance = Math.max(1, turnContext.turnSignalDistanceMeters || 42)
  const approachProgress = clampValue(1 - distance / signalDistance, 0, 1)
  const baseIntensity = turnContext.direction === 'left'
    ? 0.14 + approachProgress * 0.26
    : 0.1 + approachProgress * 0.22
  const policy = turnContext.direction === 'left'
    ? 'SUMO green-minor style left turn: slow in the marked pocket and accept a safe oncoming gap before crossing'
    : 'right-turn-yield area: slow before the turn, yield to pedestrians in the corner crosswalk, then merge into the curb lane'
  const protectedLeftTurn = turnContext.direction === 'left' && phase?.leftTurnProtected && phase?.activeAxis === state.road.axis

  const pedestrian = pedestrianInTurnConflictZone(state, turnContext, pedestrians)
  if (pedestrian) {
    return {
      type: 'crosswalk-yield',
      reason: 'turn-pedestrian-yield',
      intensity: 0.88,
      mustYield: true,
      targetId: pedestrian.id || 'player',
      targetName: pedestrian.name || (pedestrian.player ? 'player' : 'pedestrian'),
      distance: Number(Math.hypot(pedestrian.x - state.pose.x, pedestrian.z - state.pose.z).toFixed(2)),
      priorityRule: 'pedestrian has priority in marked crossing / turn conflict box',
      policy,
      source: 'SUMO pedestrian crossing + GATSim gap acceptance',
    }
  }

  if (protectedLeftTurn) {
    return {
      type: 'protected-left-turn-window',
      reason: 'protected-left-turn-slowdown',
      intensity: Number(Math.max(0.12, baseIntensity * 0.62).toFixed(3)),
      mustYield: false,
      targetId: null,
      targetName: null,
      distance: Number(distance.toFixed(2)),
      priorityRule: 'SUMO G protected-left window gives the left-turn pocket priority over oncoming through links',
      policy: 'the late green window disables pedestrian starts and upgrades the left turn from permissive g to protected G',
      source: 'Eclipse SUMO Traffic_Lights g/G priority relationship',
    }
  }

  const oncoming = oncomingVehicleForTurn(state, turnContext, trafficStates)
  if (oncoming) {
    return {
      type: 'left-turn-oncoming-gap',
      reason: 'left-turn-gap-yield',
      intensity: clampValue(0.46 + (52 - oncoming.distance) / 90, 0.46, 0.82),
      mustYield: true,
      targetId: oncoming.state.car.id,
      targetName: oncoming.state.car.driverName,
      distance: Number(oncoming.distance.toFixed(2)),
      priorityRule: 'left-turning vehicle yields to oncoming through traffic before crossing its path',
      policy,
      source: 'SUMO green-minor left-turn conflict + GATSim gap acceptance',
    }
  }

  const crossing = crossingVehicleForTurn(state, turnContext, trafficStates)
  if (crossing && turnContext.direction === 'right') {
    return {
      type: 'right-turn-cross-traffic-check',
      reason: 'right-turn-gap-yield',
      intensity: clampValue(0.34 + (30 - crossing.distance) / 80, 0.34, 0.68),
      mustYield: true,
      targetId: crossing.state.car.id,
      targetName: crossing.state.car.driverName,
      distance: Number(crossing.distance.toFixed(2)),
      priorityRule: 'right-turning vehicle checks the receiving lane and yields before merging',
      policy,
      source: 'GATSim receiving-lane conflict check',
    }
  }

  return {
    type: turnContext.direction === 'left' ? 'left-turn-pocket-slowdown' : 'right-turn-yield-slowdown',
    reason: turnContext.direction === 'left' ? 'left-turn-pocket-slowdown' : 'right-turn-yield-slowdown',
    intensity: Number(baseIntensity.toFixed(3)),
    mustYield: false,
    targetId: null,
    targetName: null,
    distance: Number(distance.toFixed(2)),
    priorityRule: turnContext.direction === 'left'
      ? 'left-turning vehicle slows differently from through traffic before gap acceptance'
      : 'right-turning vehicle slows differently from through traffic before crosswalk/merge check',
    policy,
    source: 'laneModel turnLanePolicy + vehicle turnIntent',
  }
}

function vehicleSignalIntent(brakingReason, car, assignedPose, turnContext = null) {
  if (assignedPose && car.assignment) return 'service-pull-over'
  if (brakingReason === 'player-yield' || brakingReason === 'pedestrian-yield') return 'yield-hazard'
  if (brakingReason === 'player-contact') return 'collision-brake'
  if (turnContext?.active && turnContext.direction === 'left') return 'turn-left'
  if (turnContext?.active && turnContext.direction === 'right') return 'turn-right'
  if (brakingReason?.includes('signal')) return 'red-light-stop'
  if (brakingReason === 'following-vehicle') return 'following-gap'
  return null
}

function vehicleSignalSide(signalIntent) {
  if (!signalIntent) return null
  if (signalIntent === 'service-pull-over') return 'right-side-pull-over'
  if (signalIntent === 'turn-left') return 'left-side-turn'
  if (signalIntent === 'turn-right') return 'right-side-turn'
  if (signalIntent === 'red-light-stop' || signalIntent === 'following-gap') return 'rear-caution'
  return 'hazard-all'
}

function signalCornerActive(signalSide, corner) {
  if (!signalSide) return false
  if (signalSide === 'hazard-all') return true
  if (signalSide === 'right-side-pull-over') return corner === 'front-right' || corner === 'rear-right'
  if (signalSide === 'left-side-turn') return corner === 'front-left' || corner === 'rear-left'
  if (signalSide === 'right-side-turn') return corner === 'front-right' || corner === 'rear-right'
  if (signalSide === 'rear-caution') return corner === 'rear-left' || corner === 'rear-right'
  return false
}

function Traffic({ cars, roads, mobilitySystem }) {
  const bodyRef = useRef()
  const cabinRef = useRef()
  const windshieldRef = useRef()
  const sideWindowRef = useRef()
  const wheelRef = useRef()
  const wheelHubRef = useRef()
  const headlightRef = useRef()
  const tailLightRef = useRef()
  const bumperRef = useRef()
  const grilleRef = useRef()
  const mirrorRef = useRef()
  const licenseRef = useRef()
  const taxiSignRef = useRef()
  const driverRef = useRef()
  const driverTorsoRef = useRef()
  const driverHandRef = useRef()
  const steeringRef = useRef()
  const brakeGlowRef = useRef()
  const signalRef = useRef()
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const color = useMemo(() => new THREE.Color(), [])
  const colorsReady = useRef(false)
  const yieldPulse = useRef(0)
  const vehicleSampleClock = useRef(0)
  const textures = useMemo(() => ({
    paint: makeProceduralTexture('vehicle-paint', { size: 128, seed: 501, repeatX: 1.6, repeatY: 1.2 }),
    glass: makeProceduralTexture('glass-smudge', { size: 128, seed: 502, repeatX: 1.2, repeatY: 1.2 }),
    rubber: makeProceduralTexture('rubber-tread', { size: 128, seed: 503, repeatX: 1.8, repeatY: 1.8 }),
    metal: makeProceduralTexture('brushed-metal', { size: 128, seed: 504, repeatX: 2.2, repeatY: 0.8 }),
    skin: makeProceduralTexture('skin-pores', { size: 128, seed: 505, repeatX: 1.2, repeatY: 1.2 }),
    paper: makeProceduralTexture('paper-plate', { size: 128, seed: 506, repeatX: 1.1, repeatY: 1.1 }),
    fabric: makeProceduralTexture('city-fabric', { size: 128, seed: 507, repeatX: 1.8, repeatY: 1.8 }),
  }), [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.__REALCITY_TRAFFIC_RENDERING__ = {
      vehicleBase: 'procedural-driver-visible-traffic',
      cabinParts: ['driverHead', 'driverTorso', 'driverHands', 'steeringWheel'],
      signalRules: ['hazard-all', 'right-side-pull-over', 'rear-caution', 'left-side-turn', 'right-side-turn'],
      behaviorCues: ['braking-forward-lean', 'checking-curb-mirror', 'hands-on-wheel'],
      vehicleCount: cars.length,
      sumoProgram: mobilitySystem?.standards?.sumo?.reference || 'Eclipse SUMO actuated tlLogic',
      signalActuation: 'actuated TrafficFlowObserved detector pressure changes protected green durations at runtime',
      movementLinkRules: ['SUMO g/G permissive-left-to-protected-left', '6s protected-left-window', 'pedestrian-no-start-during-left-window'],
      turnIntentRendering: 'vehicles expose left/right/straight turn intent and blink amber side signals before intersections',
      turnConflictRules: ['left-turn-pocket-slowdown', 'left-turn-gap-yield', 'protected-left-turn-window', 'right-turn-yield-slowdown', 'turn-pedestrian-yield'],
      turnArcRules: ['lane-level-cubic-bezier-arc', 'road-state-transfer-after-turn', 'post-turn-intent-reselection'],
      taxiRouteSmoothing: 'taxi dispatch, ride, NPC taxi, and cruising loop routes expose Bezier corner smoothing instead of hard 90-degree route corners',
      gbfsStations: mobilitySystem?.gbfs?.stations?.length || 0,
      smartCityCurbZones: mobilitySystem?.smartCity?.curbZones?.length || 0,
      gatsimDisruptions: mobilitySystem?.gatsim?.disruptionEvents?.length || 0,
    }
  }, [cars.length, mobilitySystem])

  useFrame((state, delta) => {
    if (!bodyRef.current || !cabinRef.current || !windshieldRef.current || !sideWindowRef.current || !wheelRef.current || !wheelHubRef.current || !headlightRef.current || !tailLightRef.current || !bumperRef.current || !grilleRef.current || !mirrorRef.current || !licenseRef.current || !taxiSignRef.current || !driverRef.current || !driverTorsoRef.current || !driverHandRef.current || !steeringRef.current || !brakeGlowRef.current || !signalRef.current) return
    const dt = Math.min(delta, 0.05)
    const store = useCityStore.getState()
    const pedestrians = [
      { x: store.player.x, z: store.player.z, player: true },
      ...(store.pedestrianSamples || []),
    ]
    yieldPulse.current = Math.max(0, yieldPulse.current - dt)
    vehicleSampleClock.current += dt
    const vehicleSamples = []

    if (!colorsReady.current) {
      cars.forEach((car, i) => bodyRef.current.setColorAt(i, color.set(car.color)))
      if (bodyRef.current.instanceColor) bodyRef.current.instanceColor.needsUpdate = true
      colorsReady.current = true
    }

    const trafficStates = cars.map((car, index) => trafficStateForCar(car, roads, index, store))

    for (let i = 0; i < cars.length; i += 1) {
      const car = cars[i]
      const trafficState = trafficStates[i]
      const dim = trafficState.dim
      const assignedPose = trafficState.assignedPose
      const currentPose = trafficState.pose
      const trafficCar = trafficState.trafficCar
      const playerContact = pointInVehicleBody(currentPose, dim, store.player, 0.74)
      const hazard = assignedPose ? null : shouldYieldToPedestrian(trafficCar, currentPose, pedestrians)
      const signalStop = assignedPose ? null : shouldStopForSignal(trafficCar, currentPose, roads, store.timeMinutes, mobilitySystem)
      const phase = trafficPhaseAt(store.timeMinutes, mobilitySystem)
      const movement = trafficCar.turnIntent === 'left' ? 'left' : trafficCar.turnIntent === 'right' ? 'right' : 'through'
      const movementSignal = trafficSignalForMovement(trafficState.road.axis, movement, store.timeMinutes, mobilitySystem)
      const follow = assignedPose ? null : frontVehicleFor(trafficState, trafficStates)
      const turnContext = assignedPose ? null : turnContextForCar(trafficState, roads)
      const turnControl = assignedPose ? null : turnControlForCar(trafficState, turnContext, trafficStates, pedestrians, phase)
      const brakingReason = playerContact
        ? 'player-contact'
        : signalStop
          ? `${signalStop.signal}-signal`
          : turnControl?.reason
            ? turnControl.reason
            : hazard
              ? hazard.player ? 'player-yield' : 'pedestrian-yield'
              : follow?.intensity > 0.15
                ? 'following-vehicle'
                : null
      const turnBrakeTarget = turnControl?.intensity || 0
      const shouldBrake = !assignedPose && (!!brakingReason || turnBrakeTarget > 0)
      const signalIntent = vehicleSignalIntent(brakingReason, car, assignedPose, turnContext)
      const signalSide = vehicleSignalSide(signalIntent)
      const signalBlink = !!signalIntent && Math.sin(state.clock.elapsedTime * 8.4 + car.phase) > -0.25
      car.brake = shouldBrake
        ? Math.min(1, Math.max(turnBrakeTarget, (car.brake || 0) + dt * (playerContact || signalStop ? 5.2 : turnControl ? 2.2 + turnControl.intensity * 3.4 : follow ? 2.6 + follow.intensity * 2.8 : car.driverTemperament === 'hurried' ? 2.8 : 4.2)))
        : Math.max(0, (car.brake || 0) - dt * 1.45)
      if (signalStop?.signal === 'red' || signalStop?.signal === 'all-red') {
        const stopHold = clampValue((8 - signalStop.stopDistance) / 6, 0, 1)
        car.brake = Math.max(car.brake || 0, stopHold)
      }
      if (playerContact && yieldPulse.current <= 0) {
        yieldPulse.current = 3.5
        store.setPulse(`${car.kind === 'taxi' ? 'A taxi driver' : 'A driver'} hits the brakes as you crowd the lane.`)
      }
      if (hazard?.player && yieldPulse.current <= 0) {
        yieldPulse.current = 5
        store.setPulse(`${car.kind === 'taxi' ? 'A taxi' : 'A driver'} yields as you step into the lane.`)
      }
      if (signalStop && yieldPulse.current <= 0) {
        yieldPulse.current = 4
        store.setPulse(`${car.kind === 'taxi' ? 'A taxi' : 'Traffic'} stops at the bar for ${signalStop.signal} on ${car.road.name}.`)
      }
      if (turnControl?.mustYield && yieldPulse.current <= 0) {
        yieldPulse.current = 4.5
        store.setPulse(`${car.driverName} yields before a ${turnContext.direction} turn for ${turnControl.targetName || 'the conflict gap'}.`)
      }
      if (follow && follow.distance < follow.desiredGap * 0.62 && yieldPulse.current <= 0) {
        yieldPulse.current = 4.5
        store.setPulse(`${car.driverName} eases off behind ${follow.driverName || 'the car ahead'} to keep the lane gap.`)
      }
      const wave = 0.82 + Math.sin(state.clock.elapsedTime * 0.23 + car.phase) * 0.18
      const followFactor = follow ? clampValue(1 - follow.intensity * (car.driverTemperament === 'hurried' ? 0.52 : 0.68), 0.18, 1) : 1
      const speedFactor = Math.max(0, (1 - car.brake * 0.98) * followFactor)
      const travelDistance = car.speed * wave * speedFactor * dt
      if (!assignedPose) {
        if (car.turnArc) {
          advanceVehicleTurnArc(car, travelDistance)
        } else if (shouldBeginVehicleTurnArc(trafficState, turnContext, signalStop, turnControl)) {
          beginVehicleTurnArc(car, trafficState, turnContext)
          advanceVehicleTurnArc(car, travelDistance)
        } else if (car.kind === 'taxi' && car.cruisePath?.length >= 2 && car.cruiseMeters > 0) {
          car.cruiseProgress = ((car.cruiseProgress || 0) + travelDistance) % car.cruiseMeters
        } else {
          car.t = (car.t + travelDistance / Math.max(1, car.road.to - car.road.from)) % 1
        }
      }
      const finalPose = assignedPose || taxiPoseForCar(car, roads, i)
      const { x, z, yaw } = finalPose
      const activeArc = car.turnArc || null
      const recentArc = !activeArc && car.lastTurnArc && Date.now() - car.lastTurnArc.completedAt < 12000 ? car.lastTurnArc : null
      const arcTelemetry = activeArc || recentArc
      const assignedTaxiSmoothing = car.assignment
        ? (store.ride?.taxiId === car.id ? store.ride?.routeSmoothing : store.mission?.taxi?.routeSmoothing)
        : null
      const taxiRouteSmoothing = car.kind === 'taxi'
        ? (assignedTaxiSmoothing || car.npcTaxi?.routeSmoothing || car.cruiseRouteSmoothing || null)
        : null
      const taxiRouteCurve = car.kind === 'taxi'
        ? (finalPose.routeCurve || assignedPose?.routeCurve || car.npcTaxi?.routeCurve || null)
        : null

      vehicleSamples.push({
        id: car.id,
        kind: car.kind,
        bodyStyle: car.bodyStyle,
        driverName: car.driverName,
        driverTemperament: car.driverTemperament,
        routeMode: car.kind === 'taxi'
          ? (car.npcTaxi ? 'npc-autonomous-taxi' : car.assignment ? 'assigned-dispatch' : car.cruiseRouteMode || 'single-road')
          : 'traffic-lane',
        assignment: car.assignment || null,
        npcPassenger: car.npcTaxi?.id || null,
        npcTaxiPhase: car.npcTaxi?.phase || null,
        npcTaxiTarget: car.npcTaxi?.targetName || null,
        cruiseRoutePoints: car.cruisePath?.length || 0,
        taxiRouteSmoothingModel: taxiRouteSmoothing?.model || null,
        taxiRouteSmoothingSource: taxiRouteSmoothing?.source || null,
        taxiRouteSmoothedPointCount: taxiRouteSmoothing?.smoothedPointCount || car.cruisePath?.length || 0,
        taxiRouteCurveSamples: taxiRouteSmoothing?.curveSamples || 0,
        taxiRouteCurvedCorners: taxiRouteSmoothing?.curvedCorners || 0,
        taxiRouteMaxHeadingDelta: taxiRouteSmoothing?.maxHeadingDelta ?? null,
        taxiRouteCurveActive: !!taxiRouteCurve,
        taxiRouteCurveModel: taxiRouteCurve?.model || null,
        taxiRouteCurveRadius: taxiRouteCurve?.radius || null,
        taxiRouteCurveT: taxiRouteCurve?.t ?? null,
        activeRoadName: trafficState.road.name,
        laneKey: trafficState.laneKey,
        laneRule: trafficState.road.laneModel?.rule || car.laneRule,
        turnIntent: turnContext?.intent || car.turnIntent || 'straight',
        turnLaneRule: turnContext?.laneRule || car.turnLaneRule || null,
        turnSignalDistanceMeters: turnContext?.turnSignalDistanceMeters || car.turnSignalDistanceMeters || trafficState.road.laneModel?.turnSignalDistanceMeters || null,
        turnDecisionDistance: turnContext?.distanceToDecision ?? null,
        turnSignalActive: !!turnContext?.active,
        turnPocketLengthMeters: turnContext?.turnPocketLengthMeters || trafficState.road.laneModel?.turnPocketLengthMeters || null,
        plannedTurnSignalSide: turnContext?.plannedSignalSide || car.plannedTurnSignalSide || null,
        turnTelemetrySource: turnContext?.source || 'procedural turn intention',
        turnIntersectionRoadName: turnContext?.intersectionRoadName || null,
        turnConflictKind: turnControl?.type || (turnContext?.active ? 'turn-approach-clear' : null),
        turnCautionIntensity: Number((turnControl?.intensity || 0).toFixed(3)),
        turnYieldRequired: !!turnControl?.mustYield,
        turnConflictTargetId: turnControl?.targetId || null,
        turnConflictTargetName: turnControl?.targetName || null,
        turnConflictDistance: turnControl?.distance ?? null,
        turnPriorityRule: turnControl?.priorityRule || (turnContext?.intent === 'straight'
          ? 'through vehicles follow the protected signal link and same-lane gap rule'
          : 'turning vehicle checks marked pocket/yield area before entering the conflict box'),
        turnConflictPolicy: turnControl?.policy || (turnContext?.intent === 'straight'
          ? 'SUMO protected through movement when the axis is green; otherwise stop at the bar'
          : 'turning vehicles use laneModel turnLanePolicy, SUMO conflict priority, and GATSim gap acceptance'),
        turnConflictTelemetrySource: turnControl?.source || 'SUMO/GATSim turn conflict policy metadata',
        turnArcActive: !!activeArc || !!finalPose.turnArc,
        turnArcRecentlyCompleted: !!recentArc,
        turnArcProgress: activeArc
          ? Number(clampValue((activeArc.progress || 0) / Math.max(1, activeArc.length || 1), 0, 1).toFixed(3))
          : recentArc
            ? 1
            : null,
        turnArcFromRoadName: arcTelemetry?.fromRoadName || null,
        turnArcToRoadName: arcTelemetry?.toRoadName || null,
        turnArcRadiusMeters: arcTelemetry?.radius ? Number(arcTelemetry.radius.toFixed(2)) : null,
        turnArcLengthMeters: arcTelemetry?.length ? Number(arcTelemetry.length.toFixed(2)) : null,
        turnArcSteering: arcTelemetry ? 'lane-level-cubic-bezier-steering-arc' : null,
        turnArcTelemetrySource: arcTelemetry?.source || null,
        brakingReason,
        signalPhase: signalStop?.phase || phase.kind,
        signalPhaseId: phase.id,
        signalModel: phase.signalModel || 'SUMO-inspired static tlLogic',
        signalPhasePurpose: phase.movementPriority || phase.kind,
        actuatedGreenSeconds: phase.actuationPolicy?.mode === 'actuated-detector-pressure' ? phase.duration : null,
        detectorPressure: phase.detectorPressure || null,
        signalCycleSeconds: Number((phase.cycleSeconds || 0).toFixed(2)),
        sumoState: phase.sumoState,
        sumoVehicleLinkState: phase.vehicleLinks?.[trafficState.road.axis] || 'r',
        sumoVehicleMovement: movementSignal.movement,
        sumoVehicleMovementLinkState: movementSignal.linkState,
        sumoTurnPriority: movementSignal.priority,
        protectedLeftTurnWindow: !!phase.leftTurnProtected,
        protectedLeftTurnAxis: phase.protectedLeftTurnAxis || null,
        leftTurnWindowSeconds: phase.leftTurnWindowSeconds || 0,
        sumoPedestrianLinks: phase.pedestrianLinks || null,
        noPedestrianStart: !!phase.noPedestrianStart,
        stopBarDistance: signalStop?.stopDistance ? Number(signalStop.stopDistance.toFixed(2)) : null,
        signalStopRule: signalStop?.rule || null,
        rightOfWay: movementSignal.priority || (phase.kind === 'green' && phase.activeAxis === trafficState.road.axis ? 'protected-vehicle-link' : 'yield-or-stop'),
        yellowDecision: signalStop?.rule === 'yellow-far-decelerate' ? 'decelerate-before-stop-bar' : phase.kind === 'yellow' ? 'clear-if-close' : null,
        smartCityCurbRule: mobilitySystem?.smartCity?.curbZones?.length ? 'stop, taxi, load, and park only in marked curb zones' : null,
        gbfsNearbyDockCount: mobilitySystem?.gbfs?.stations?.length || 0,
        gatsimDecisionSignals: mobilitySystem?.gatsim?.agentDecisionSignals?.slice(0, 5) || [],
        signalIntent,
        signalSide,
        signalBlink,
        signalLampCount: signalBlink && signalSide === 'hazard-all' ? 4 : signalBlink && signalSide ? 2 : 0,
        visualSafetyCue: brakingReason ? 'brake-lights-and-driver-yield' : signalIntent ? 'amber-caution-signal' : null,
        brakeLightIntensity: Number(clampValue(car.brake || 0, 0, 1).toFixed(3)),
        driverCabinCue: 'visible-driver-hands-wheel',
        driverPose: brakingReason
          ? 'braking-forward-lean'
          : signalIntent === 'service-pull-over'
            ? 'checking-curb-mirror'
            : 'hands-on-wheel',
        driverReaction: brakingReason
          ? `${car.driverName} reacts to ${brakingReason.replaceAll('-', ' ')}`
          : signalIntent
            ? `${car.driverName} signals ${signalIntent.replaceAll('-', ' ')}`
            : null,
        followingVehicleId: follow?.vehicleId || null,
        followDistance: follow?.distance ?? null,
        desiredGap: follow?.desiredGap ?? null,
        x,
        z,
        yaw,
        width: dim.width,
        length: dim.length,
        speed: Number((car.speed * speedFactor).toFixed(3)),
        brake: Number((car.brake || 0).toFixed(3)),
      })

      const y = terrainHeight(x, z) + 0.55
      const base = { x, y, z }
      const front = dim.length / 2
      const rear = -dim.length / 2
      const wheelX = dim.width * 0.55
      const wheelZ = dim.length * 0.34
      const cabinZ = car.bodyStyle === 'van' || car.bodyStyle === 'minivan' ? -0.18 : car.bodyStyle === 'coupe' ? -0.34 : -0.12
      setLocalPart(bodyRef.current, i, dummy, base, yaw, [0, 0, 0], [dim.width, dim.height, dim.length])
      setLocalPart(cabinRef.current, i, dummy, base, yaw, [0, dim.height * 0.76, cabinZ], [dim.width * 0.72, dim.cabinHeight, dim.cabinLength])
      setLocalPart(windshieldRef.current, i * 2, dummy, base, yaw, [0, dim.height + dim.cabinHeight * 0.2, cabinZ + dim.cabinLength * 0.52], [dim.width * 0.56, dim.cabinHeight * 0.46, 0.04], -0.22)
      setLocalPart(windshieldRef.current, i * 2 + 1, dummy, base, yaw, [0, dim.height + dim.cabinHeight * 0.18, cabinZ - dim.cabinLength * 0.52], [dim.width * 0.5, dim.cabinHeight * 0.42, 0.04], 0.18)
      setLocalPart(sideWindowRef.current, i * 2, dummy, base, yaw, [-dim.width * 0.38, dim.height + dim.cabinHeight * 0.18, cabinZ], [0.045, dim.cabinHeight * 0.52, dim.cabinLength * 0.58])
      setLocalPart(sideWindowRef.current, i * 2 + 1, dummy, base, yaw, [dim.width * 0.38, dim.height + dim.cabinHeight * 0.18, cabinZ], [0.045, dim.cabinHeight * 0.52, dim.cabinLength * 0.58])
      const driverLean = clampValue(car.brake || 0, 0, 1) * 0.06
      const mirrorCheck = signalIntent === 'service-pull-over' ? 0.045 : 0
      const handPulse = signalBlink ? Math.sin(state.clock.elapsedTime * 12 + car.phase) * 0.012 : 0
      setLocalPart(driverTorsoRef.current, i, dummy, base, yaw, [-dim.width * 0.16 + mirrorCheck, dim.height + dim.cabinHeight * 0.26, cabinZ + 0.04 + driverLean], [0.18, 0.22, 0.14], car.brake * 0.12, 0)
      setLocalPart(driverRef.current, i, dummy, base, yaw, [-dim.width * 0.16 + mirrorCheck, dim.height + dim.cabinHeight * 0.55, cabinZ + 0.1 + driverLean], [0.16, 0.18, 0.16], car.brake * 0.08, signalIntent === 'service-pull-over' ? -0.1 : 0)
      setLocalPart(steeringRef.current, i, dummy, base, yaw, [-dim.width * 0.14, dim.height + dim.cabinHeight * 0.33, cabinZ + dim.cabinLength * 0.35], [0.14, 0.14, 0.018], Math.PI / 2, 0)
      setLocalPart(driverHandRef.current, i * 2, dummy, base, yaw, [-dim.width * 0.22, dim.height + dim.cabinHeight * 0.35 + handPulse, cabinZ + dim.cabinLength * 0.35], [0.045, 0.045, 0.045])
      setLocalPart(driverHandRef.current, i * 2 + 1, dummy, base, yaw, [-dim.width * 0.06, dim.height + dim.cabinHeight * 0.35 - handPulse, cabinZ + dim.cabinLength * 0.35], [0.045, 0.045, 0.045])
      setLocalPart(wheelRef.current, i * 4, dummy, base, yaw, [-wheelX, -0.34, wheelZ], [0.36, 0.22, 0.36], 0, Math.PI / 2)
      setLocalPart(wheelRef.current, i * 4 + 1, dummy, base, yaw, [wheelX, -0.34, wheelZ], [0.36, 0.22, 0.36], 0, Math.PI / 2)
      setLocalPart(wheelRef.current, i * 4 + 2, dummy, base, yaw, [-wheelX, -0.34, -wheelZ], [0.36, 0.22, 0.36], 0, Math.PI / 2)
      setLocalPart(wheelRef.current, i * 4 + 3, dummy, base, yaw, [wheelX, -0.34, -wheelZ], [0.36, 0.22, 0.36], 0, Math.PI / 2)
      setLocalPart(wheelHubRef.current, i * 4, dummy, base, yaw, [-wheelX - 0.012, -0.34, wheelZ], [0.19, 0.035, 0.19], 0, Math.PI / 2)
      setLocalPart(wheelHubRef.current, i * 4 + 1, dummy, base, yaw, [wheelX + 0.012, -0.34, wheelZ], [0.19, 0.035, 0.19], 0, Math.PI / 2)
      setLocalPart(wheelHubRef.current, i * 4 + 2, dummy, base, yaw, [-wheelX - 0.012, -0.34, -wheelZ], [0.19, 0.035, 0.19], 0, Math.PI / 2)
      setLocalPart(wheelHubRef.current, i * 4 + 3, dummy, base, yaw, [wheelX + 0.012, -0.34, -wheelZ], [0.19, 0.035, 0.19], 0, Math.PI / 2)
      setLocalPart(headlightRef.current, i * 2, dummy, base, yaw, [-dim.width * 0.27, 0.08, front + 0.035], [0.24, 0.14, 0.08])
      setLocalPart(headlightRef.current, i * 2 + 1, dummy, base, yaw, [dim.width * 0.27, 0.08, front + 0.035], [0.24, 0.14, 0.08])
      setLocalPart(tailLightRef.current, i * 2, dummy, base, yaw, [-dim.width * 0.28, 0.05, rear - 0.035], [0.22 + car.brake * 0.18, 0.12 + car.brake * 0.12, 0.08])
      setLocalPart(tailLightRef.current, i * 2 + 1, dummy, base, yaw, [dim.width * 0.28, 0.05, rear - 0.035], [0.22 + car.brake * 0.18, 0.12 + car.brake * 0.12, 0.08])
      setLocalPart(brakeGlowRef.current, i * 2, dummy, base, yaw, [-dim.width * 0.28, 0.08, rear - 0.08], car.brake > 0.04 ? [0.34 + car.brake * 0.34, 0.2 + car.brake * 0.24, 0.035] : [0.001, 0.001, 0.001])
      setLocalPart(brakeGlowRef.current, i * 2 + 1, dummy, base, yaw, [dim.width * 0.28, 0.08, rear - 0.08], car.brake > 0.04 ? [0.34 + car.brake * 0.34, 0.2 + car.brake * 0.24, 0.035] : [0.001, 0.001, 0.001])
      const activeSignalScale = [0.16, 0.11, 0.045]
      const hiddenSignalScale = [0.001, 0.001, 0.001]
      setLocalPart(signalRef.current, i * 4, dummy, base, yaw, [-dim.width * 0.42, 0.1, front + 0.055], signalBlink && signalCornerActive(signalSide, 'front-left') ? activeSignalScale : hiddenSignalScale)
      setLocalPart(signalRef.current, i * 4 + 1, dummy, base, yaw, [dim.width * 0.42, 0.1, front + 0.055], signalBlink && signalCornerActive(signalSide, 'front-right') ? activeSignalScale : hiddenSignalScale)
      setLocalPart(signalRef.current, i * 4 + 2, dummy, base, yaw, [-dim.width * 0.43, 0.1, rear - 0.055], signalBlink && signalCornerActive(signalSide, 'rear-left') ? activeSignalScale : hiddenSignalScale)
      setLocalPart(signalRef.current, i * 4 + 3, dummy, base, yaw, [dim.width * 0.43, 0.1, rear - 0.055], signalBlink && signalCornerActive(signalSide, 'rear-right') ? activeSignalScale : hiddenSignalScale)
      setLocalPart(bumperRef.current, i * 2, dummy, base, yaw, [0, -0.04, front + 0.08], [dim.width * 0.84, 0.16, 0.11])
      setLocalPart(bumperRef.current, i * 2 + 1, dummy, base, yaw, [0, -0.04, rear - 0.08], [dim.width * 0.84, 0.16, 0.11])
      setLocalPart(grilleRef.current, i, dummy, base, yaw, [0, 0.11, front + 0.1], [dim.width * 0.42, 0.16, 0.035])
      setLocalPart(mirrorRef.current, i * 2, dummy, base, yaw, [-dim.width * 0.58, dim.height * 0.72, dim.length * 0.14], [0.075, 0.075, 0.18])
      setLocalPart(mirrorRef.current, i * 2 + 1, dummy, base, yaw, [dim.width * 0.58, dim.height * 0.72, dim.length * 0.14], [0.075, 0.075, 0.18])
      setLocalPart(licenseRef.current, i * 2, dummy, base, yaw, [0, 0.12, front + 0.125], [0.5, 0.13, 0.025])
      setLocalPart(licenseRef.current, i * 2 + 1, dummy, base, yaw, [0, 0.12, rear - 0.125], [0.5, 0.13, 0.025])
      setLocalPart(taxiSignRef.current, i, dummy, base, yaw, [0, dim.height + dim.cabinHeight + 0.05, cabinZ - 0.08], car.kind === 'taxi' ? [0.9, 0.18, 0.45] : [0.001, 0.001, 0.001])
    }

    if (vehicleSampleClock.current > 0.14) {
      vehicleSampleClock.current = 0
      store.setVehicleSamples(vehicleSamples)
    }

    bodyRef.current.instanceMatrix.needsUpdate = true
    cabinRef.current.instanceMatrix.needsUpdate = true
    windshieldRef.current.instanceMatrix.needsUpdate = true
    sideWindowRef.current.instanceMatrix.needsUpdate = true
    driverRef.current.instanceMatrix.needsUpdate = true
    driverTorsoRef.current.instanceMatrix.needsUpdate = true
    driverHandRef.current.instanceMatrix.needsUpdate = true
    steeringRef.current.instanceMatrix.needsUpdate = true
    wheelRef.current.instanceMatrix.needsUpdate = true
    wheelHubRef.current.instanceMatrix.needsUpdate = true
    headlightRef.current.instanceMatrix.needsUpdate = true
    tailLightRef.current.instanceMatrix.needsUpdate = true
    brakeGlowRef.current.instanceMatrix.needsUpdate = true
    signalRef.current.instanceMatrix.needsUpdate = true
    bumperRef.current.instanceMatrix.needsUpdate = true
    grilleRef.current.instanceMatrix.needsUpdate = true
    mirrorRef.current.instanceMatrix.needsUpdate = true
    licenseRef.current.instanceMatrix.needsUpdate = true
    taxiSignRef.current.instanceMatrix.needsUpdate = true
  })

  return (
    <>
      <instancedMesh ref={bodyRef} args={[undefined, undefined, cars.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshPhysicalMaterial map={textures.paint} color="#ffffff" vertexColors roughness={0.24} metalness={0.42} clearcoat={0.7} clearcoatRoughness={0.18} envMapIntensity={1.1} />
      </instancedMesh>
      <instancedMesh ref={cabinRef} args={[undefined, undefined, cars.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshPhysicalMaterial map={textures.glass} color="#111923" roughness={0.08} metalness={0.28} clearcoat={1} clearcoatRoughness={0.05} envMapIntensity={1.45} />
      </instancedMesh>
      <instancedMesh ref={windshieldRef} args={[undefined, undefined, cars.length * 2]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshPhysicalMaterial map={textures.glass} color="#9edcff" roughness={0.035} metalness={0.12} transparent opacity={0.72} clearcoat={1} clearcoatRoughness={0.03} envMapIntensity={1.8} />
      </instancedMesh>
      <instancedMesh ref={sideWindowRef} args={[undefined, undefined, cars.length * 2]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshPhysicalMaterial map={textures.glass} color="#83c7e7" roughness={0.04} metalness={0.16} transparent opacity={0.68} clearcoat={1} envMapIntensity={1.7} />
      </instancedMesh>
      <instancedMesh ref={driverRef} args={[undefined, undefined, cars.length]} castShadow frustumCulled={false}>
        <sphereGeometry args={[1, 14, 10]} />
        <meshStandardMaterial map={textures.skin} color="#d4a17d" roughness={0.7} />
      </instancedMesh>
      <instancedMesh ref={driverTorsoRef} args={[undefined, undefined, cars.length]} castShadow frustumCulled={false}>
        <capsuleGeometry args={[1, 1.3, 6, 10]} />
        <meshStandardMaterial map={textures.fabric} color="#243447" roughness={0.78} metalness={0.04} />
      </instancedMesh>
      <instancedMesh ref={driverHandRef} args={[undefined, undefined, cars.length * 2]} castShadow frustumCulled={false}>
        <sphereGeometry args={[1, 10, 8]} />
        <meshStandardMaterial map={textures.skin} color="#d4a17d" roughness={0.7} />
      </instancedMesh>
      <instancedMesh ref={steeringRef} args={[undefined, undefined, cars.length]} castShadow frustumCulled={false}>
        <torusGeometry args={[1, 0.16, 8, 18]} />
        <meshStandardMaterial map={textures.rubber} color="#10151c" roughness={0.62} metalness={0.16} />
      </instancedMesh>
      <instancedMesh ref={wheelRef} args={[undefined, undefined, cars.length * 4]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 18]} />
        <meshStandardMaterial map={textures.rubber} color="#08090b" roughness={0.56} metalness={0.18} />
      </instancedMesh>
      <instancedMesh ref={wheelHubRef} args={[undefined, undefined, cars.length * 4]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 16]} />
        <meshStandardMaterial map={textures.metal} color="#c8cdd0" roughness={0.24} metalness={0.72} />
      </instancedMesh>
      <instancedMesh ref={headlightRef} args={[undefined, undefined, cars.length * 2]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#fff8df" emissive="#ffe08a" emissiveIntensity={1.45} roughness={0.18} />
      </instancedMesh>
      <instancedMesh ref={tailLightRef} args={[undefined, undefined, cars.length * 2]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#ff2b2b" emissive="#ff1d18" emissiveIntensity={1.2} roughness={0.24} />
      </instancedMesh>
      <instancedMesh ref={brakeGlowRef} args={[undefined, undefined, cars.length * 2]} frustumCulled={false} renderOrder={7}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial color="#ff1d18" transparent opacity={0.58} depthWrite={false} />
      </instancedMesh>
      <instancedMesh ref={signalRef} args={[undefined, undefined, cars.length * 4]} frustumCulled={false} renderOrder={7}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#ffbf3f" emissive="#ffad1f" emissiveIntensity={1.5} roughness={0.18} />
      </instancedMesh>
      <instancedMesh ref={bumperRef} args={[undefined, undefined, cars.length * 2]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.metal} color="#cfd4d8" roughness={0.26} metalness={0.7} />
      </instancedMesh>
      <instancedMesh ref={grilleRef} args={[undefined, undefined, cars.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.metal} color="#15191d" roughness={0.32} metalness={0.42} />
      </instancedMesh>
      <instancedMesh ref={mirrorRef} args={[undefined, undefined, cars.length * 2]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.glass} color="#12171d" roughness={0.18} metalness={0.36} />
      </instancedMesh>
      <instancedMesh ref={licenseRef} args={[undefined, undefined, cars.length * 2]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.paper} color="#f5f1df" roughness={0.42} metalness={0.08} />
      </instancedMesh>
      <instancedMesh ref={taxiSignRef} args={[undefined, undefined, cars.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#fff7b0" emissive="#ffd34d" emissiveIntensity={1.1} roughness={0.22} />
      </instancedMesh>
    </>
  )
}

function activeTaxiRoute(mission, ride, mapRoute = null) {
  if (mission?.phase === 'taxi_dispatch' && mission?.taxi?.path?.length >= 2) return mission.taxi.path
  if (ride?.path?.length >= 2) return ride.path
  if (mission?.phase === 'taxi_waiting' && mission?.taxi?.destinationPath?.length >= 2) return mission.taxi.destinationPath
  if (mission?.route?.length >= 2) return mission.route
  if (mission?.taxi?.destinationPath?.length >= 2) return mission.taxi.destinationPath
  if (mission?.taxi?.path?.length >= 2) return mission.taxi.path
  if (mapRoute?.route?.length >= 2) return mapRoute.route
  return []
}

function TaxiRouteRibbon() {
  const mission = useCityStore(state => state.mission)
  const ride = useCityStore(state => state.ride)
  const mapRoute = useCityStore(state => state.mapRoute)
  const route = activeTaxiRoute(mission, ride, mapRoute)
  const geometry = useMemo(() => {
    if (!route.length) return null
    const points = route.map(point => new THREE.Vector3(point.x, terrainHeight(point.x, point.z) + 0.16, point.z))
    return new THREE.BufferGeometry().setFromPoints(points)
  }, [route, mission?.updatedAt, ride?.updatedAt, mapRoute?.updatedAt])

  if (!geometry) return null
  return (
    <line geometry={geometry} renderOrder={6}>
      <lineBasicMaterial color="#ffd447" transparent opacity={0.94} depthWrite={false} />
    </line>
  )
}

function MissionTaxi() {
  const group = useRef()
  const textures = useMemo(() => ({
    paint: makeProceduralTexture('vehicle-paint', { size: 128, seed: 731, repeatX: 1.6, repeatY: 1.2 }),
    glass: makeProceduralTexture('glass-smudge', { size: 128, seed: 732, repeatX: 1.2, repeatY: 1.2 }),
    rubber: makeProceduralTexture('rubber-tread', { size: 128, seed: 733, repeatX: 1.8, repeatY: 1.8 }),
    metal: makeProceduralTexture('brushed-metal', { size: 128, seed: 734, repeatX: 2.2, repeatY: 0.8 }),
    skin: makeProceduralTexture('skin-pores', { size: 128, seed: 735, repeatX: 1.2, repeatY: 1.2 }),
  }), [])

  useFrame(() => {
    if (!group.current) return
    const store = useCityStore.getState()
    if (store.ride?.taxiSource === 'fleet' || store.mission?.taxi?.source === 'fleet') {
      group.current.visible = false
      return
    }
    const pose = store.ride?.taxiPose || store.mission?.taxi?.pose
    if (!pose) {
      group.current.visible = false
      return
    }
    group.current.visible = true
    group.current.position.set(pose.x, terrainHeight(pose.x, pose.z) + 0.58, pose.z)
    group.current.rotation.y = pose.heading ?? pose.yaw ?? 0
  })

  return (
    <group ref={group} visible={false}>
      <mesh castShadow receiveShadow position={[0, 0, 0]}>
        <boxGeometry args={[2.22, 0.72, 4.75]} />
        <meshPhysicalMaterial map={textures.paint} color="#f6c445" roughness={0.22} metalness={0.42} clearcoat={0.75} clearcoatRoughness={0.15} />
      </mesh>
      <mesh castShadow position={[0, 0.66, -0.18]}>
        <boxGeometry args={[1.55, 0.62, 1.92]} />
        <meshPhysicalMaterial map={textures.glass} color="#17202a" roughness={0.06} metalness={0.24} clearcoat={1} transparent opacity={0.92} />
      </mesh>
      <mesh position={[0, 0.86, 0.86]}>
        <boxGeometry args={[1.18, 0.34, 0.045]} />
        <meshPhysicalMaterial map={textures.glass} color="#9edcff" roughness={0.035} metalness={0.1} transparent opacity={0.72} clearcoat={1} />
      </mesh>
      <mesh position={[0, 0.82, -1.2]}>
        <boxGeometry args={[1.08, 0.3, 0.045]} />
        <meshPhysicalMaterial map={textures.glass} color="#83c7e7" roughness={0.04} metalness={0.16} transparent opacity={0.68} clearcoat={1} />
      </mesh>
      <mesh castShadow position={[-0.36, 1.04, 0.16]}>
        <sphereGeometry args={[0.2, 14, 10]} />
        <meshStandardMaterial map={textures.skin} color="#d4a17d" roughness={0.7} />
      </mesh>
      <mesh castShadow position={[0, 1.22, -0.2]}>
        <boxGeometry args={[0.92, 0.18, 0.44]} />
        <meshStandardMaterial color="#fff7b0" emissive="#ffd34d" emissiveIntensity={1.2} roughness={0.22} />
      </mesh>
      <mesh position={[0, 0.16, 2.44]}>
        <boxGeometry args={[0.78, 0.18, 0.08]} />
        <meshStandardMaterial color="#fff8df" emissive="#ffe08a" emissiveIntensity={1.3} roughness={0.18} />
      </mesh>
      <mesh position={[0, 0.12, -2.44]}>
        <boxGeometry args={[0.86, 0.14, 0.08]} />
        <meshStandardMaterial color="#ff2b2b" emissive="#ff1d18" emissiveIntensity={1.1} roughness={0.24} />
      </mesh>
      {[
        [-1.18, -0.38, 1.48],
        [1.18, -0.38, 1.48],
        [-1.18, -0.38, -1.42],
        [1.18, -0.38, -1.42],
      ].map(([x, y, z]) => (
        <mesh key={`${x}-${z}`} castShadow position={[x, y, z]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.34, 0.34, 0.24, 20]} />
          <meshStandardMaterial map={textures.rubber} color="#08090b" roughness={0.56} metalness={0.18} />
        </mesh>
      ))}
      {[
        [-1.31, -0.38, 1.48],
        [1.31, -0.38, 1.48],
        [-1.31, -0.38, -1.42],
        [1.31, -0.38, -1.42],
      ].map(([x, y, z]) => (
        <mesh key={`hub-${x}-${z}`} position={[x, y, z]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.18, 0.18, 0.035, 16]} />
          <meshStandardMaterial map={textures.metal} color="#c8cdd0" roughness={0.24} metalness={0.72} />
        </mesh>
      ))}
    </group>
  )
}

function PlayerTaxiController({ city }) {
  const completionPulse = useRef(false)

  useFrame((_, delta) => {
    const store = useCityStore.getState()
    const mission = store.mission
    if (!mission || !['player_taxi', 'street_hail'].includes(mission.source)) {
      completionPulse.current = false
      return
    }

    const taxi = mission.taxi
    if (mission.phase === 'taxi_dispatch' && taxi) {
      advanceTaxi(taxi, delta)
      if (taxi.progress >= taxi.routeMeters - 0.2) {
        const stopPose = sampleRoute(taxi.path, taxi.routeMeters)
        taxi.phase = 'waiting_at_pickup'
        taxi.progress = taxi.routeMeters
        taxi.pose = { x: stopPose.x, z: stopPose.z, heading: stopPose.heading, yaw: stopPose.heading, routeCurve: stopPose.routeCurve || null }
        taxi.routeCurve = stopPose.routeCurve || null
        mission.phase = 'taxi_waiting'
        mission.boardingAt = performance.now()
        store.updateMission({
          phase: 'taxi_waiting',
          taxi,
          summary: mission.destination
            ? `Taxi arrived at ${mission.pickup.roadName || mission.pickup.name || 'the curb'}. Press F to board.`
            : `Taxi is waiting at the curb. Choose a destination in RealPhone Taxi, then press F.`,
        })
      }
      return
    }

    if (mission.phase === 'taxi_boarding' && mission.boardingRequested) {
      const elapsed = (performance.now() - (mission.boardingStartedAt || performance.now())) / 1000
      if (elapsed >= TAXI_BOARDING_SECONDS) startTaxiRideFromMission(mission, store, city.roads)
      return
    }

    if (mission.phase === 'taxi_ride' && !store.ride && !completionPulse.current) {
      completionPulse.current = true
      releaseFleetTaxi(mission.taxi, city, mission.dropoff)
      store.finishMission(`Taxi trip complete${mission.destination?.name ? ` at ${mission.destination.name}` : ''}.`)
    }
  })

  useEffect(() => {
    const startPlayerTaxiMission = (target, source = 'player_taxi', requestChannel = 'realphone_taxi', channelLabel = 'RealPhone Taxi') => {
      const store = useCityStore.getState()
      const player = store.player
      const destination = target ? entranceTargetFor(target) : null
      const pickup = nearestRoadPickup(player, city.roads)
      const channel = channelLabel || directTaxiChannelLabel({ requestChannel })
      const mission = {
        id: `${source}_${Date.now()}`,
        mode: 'taxi',
        source,
        requestChannel,
        channelLabel: channel,
        phase: 'taxi_dispatch',
        destination,
        pickup,
        steps: destination
          ? [`${channel} dispatches the nearest cruising taxi`, 'Taxi drives to your curb without NPC relay', 'Press F to board', `Ride to ${destination.name}`]
          : ['Raise your hand at the curb', 'Nearest passing taxi pulls over', 'Choose a destination in RealPhone', 'Press F to board'],
        request: destination ? `Direct ${channel} to ${destination.name}` : 'Street hail passing taxi',
      }
      store.startMission({
        ...mission,
        summary: destination
          ? `${channel} is dispatching the nearest cruising cab directly to ${destination.name}.`
          : 'Hailing the nearest passing taxi.',
      })
      const started = beginTaxiDispatch(null, mission, store, {
        ...city,
        cars: city.cars,
        roads: city.roads,
      })
      if (!started) {
        store.finishMission('Taxi hail cancelled.')
      } else if (destination && requestChannel === 'map_place_card') {
        store.addCityEvent({
          id: `mobility_map_taxi_${Math.round(performance.now())}`,
          kind: 'mobility',
          placeName: destination.name,
          topic: 'map taxi',
          text: `${channel} directly dispatched a cruising cab to ${destination.address || destination.name}; no contact or NPC relay was used.`,
        })
      }
      return started
    }

    const onPlayerTaxiRequest = (event) => {
      const target = event.detail?.target
      if (!target) return
      const store = useCityStore.getState()
      const mission = store.mission
      if (mission?.source === 'street_hail' && mission.taxi && !mission.destination) {
        const destination = entranceTargetFor(target)
        attachTaxiDestination(mission, destination, city.roads, store)
        store.setPulse(`Destination set. Press F when ${mission.taxi.driverName || 'the taxi driver'} reaches the curb.`)
        return
      }
      if (store.ride || mission) {
        store.setPulse('Finish the current plan before calling another taxi.')
        return
      }
      const requestChannel = event.detail?.requestChannel || event.detail?.source || 'realphone_taxi'
      const channelLabel = event.detail?.channelLabel || directTaxiChannelLabel({ requestChannel })
      startPlayerTaxiMission(target, 'player_taxi', requestChannel, channelLabel)
    }

    const onKey = (event) => {
      if (event.target?.closest?.('input, textarea, select, button')) return
      const store = useCityStore.getState()
      if (event.code === 'KeyF') {
        const mission = store.mission
        if (!mission || mission.mode !== 'taxi' || mission.phase !== 'taxi_waiting') return
        if (event.cancelable) event.preventDefault()
        const taxi = mission.taxi
        if (taxi?.pose) {
          const door = taxiPassengerDoorPoint(taxi, 'player')
          const boardingPoints = [door, taxi.passengerPickup, mission.pickup, taxi.pickupStop]
            .filter(point => Number.isFinite(Number(point?.x)) && Number.isFinite(Number(point?.z)))
          const distance = Math.min(...boardingPoints.map(point => Math.hypot(store.player.x - point.x, store.player.z - point.z)))
          if (distance > 26) {
            store.setPulse('Move closer to the taxi door before boarding.')
            return
          }
        }
        if (!mission.destination) {
          store.setPulse('Choose a destination in RealPhone Taxi first.')
          window.dispatchEvent(new CustomEvent('realcity:open-phone', { detail: { tab: 'taxi' } }))
          return
        }
        mission.boardingRequested = true
        mission.phase = 'taxi_boarding'
        mission.boardingStartedAt = performance.now()
        mission.boardingPlayerStart = { x: store.player.x, z: store.player.z }
        store.updateMission({
          phase: 'taxi_boarding',
          boardingRequested: true,
          boardingStartedAt: mission.boardingStartedAt,
          boardingPlayerStart: mission.boardingPlayerStart,
          summary: 'Boarding taxi from the curb side. The driver waits until the doors are clear.',
        })
        window.dispatchEvent(new CustomEvent('realcity:taxi-board-requested', {
          detail: { missionId: mission.id },
        }))
      }

      if (event.code === 'KeyH') {
        if (store.ride || store.mission) return
        if (event.cancelable) event.preventDefault()
        const player = store.player
        const pickup = nearestRoadPickup(player, city.roads)
        const nearbyTaxi = nearestAvailableTaxi(pickup, city.cars, city.roads, TAXI_HAIL_RADIUS)
        if (!nearbyTaxi) {
          store.setPulse('No passing taxi is close enough to hail. Step toward a main road or use RealPhone Taxi.')
          return
        }
        const mission = {
          id: `street_hail_${Date.now()}`,
          mode: 'taxi',
          source: 'street_hail',
          phase: 'taxi_dispatch',
          destination: null,
          pickup,
          preferredTaxiId: nearbyTaxi.car.id,
          maxDispatchDistance: TAXI_HAIL_RADIUS,
          allowSpawnTaxi: false,
          steps: ['Raise hand toward traffic', `${nearbyTaxi.car.driverName} pulls over`, 'Choose destination in RealPhone Taxi', 'Press F to board'],
          request: 'Street hail passing taxi',
        }
        store.startMission({ ...mission, summary: `Hailing ${nearbyTaxi.car.driverName}'s passing taxi.` })
        beginTaxiDispatch(null, mission, store, city)
      }
    }

    window.addEventListener('realcity:player-taxi-request', onPlayerTaxiRequest)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('realcity:player-taxi-request', onPlayerTaxiRequest)
      window.removeEventListener('keydown', onKey)
    }
  }, [city])

  return null
}

function NPCs({ city }) {
  const places = useMemo(() => new Map(city.landmarks.map(place => [place.id, place])), [city.landmarks])
  const destinations = useMemo(() => new Map([...city.landmarks, ...(city.addressBook || [])].map(place => [place.id, place])), [city.landmarks, city.addressBook])
  const agents = useMemo(() => city.npcs.map((npc, i) => {
    const agent = new Agent(npc)
    const target = targetFor(agent, places, useCityStore.getState().timeMinutes, city.roads)
    const spread = 2.4 + (i % 5) * 0.7
    const plazaAgent = i < 10
    const lateTaxiCommuter = i >= 10 && i < 18 && Math.hypot(target.x - agent.home.x, target.z - agent.home.z) > NPC_TAXI_MIN_DISTANCE
    const spawnAnchor = lateTaxiCommuter ? agent.home : target
    const x = plazaAgent
      ? 8 + (i % 5) * 5.5
      : lateTaxiCommuter
        ? agent.home.x + Math.sin(i * 1.73) * spread
        : target.x + Math.sin(i * 2.13) * spread
    const z = plazaAgent
      ? 30 + Math.floor(i / 5) * 20 + Math.sin(i * 1.7) * 2
      : lateTaxiCommuter
        ? agent.home.z + Math.cos(i * 1.61) * spread
        : target.z + Math.cos(i * 1.71) * spread
    const spawn = pedestrianSafeTarget({ x, z, y: terrainHeight(x, z), name: plazaAgent ? 'Central Core plaza' : lateTaxiCommuter ? agent.home.name : target.name }, spawnAnchor, city.roads)
    const outdoorSpawn = pushOutdoorFromSolid(city, spawn.x, spawn.z, 0.92)
    const [safeX, safeZ] = resolveBuildingCollision(city, spawnAnchor.x, spawnAnchor.z, outdoorSpawn.x, outdoorSpawn.z, 0.68)
    agent.pos.set(safeX, terrainHeight(safeX, safeZ) + 0.95, safeZ)
    agent.activity = plazaAgent ? 'available for directions' : target.activity
    agent.placeName = plazaAgent ? 'Central Core plaza' : lateTaxiCommuter ? agent.home.name : target.name
    agent.heading = plazaAgent ? Math.atan2(-x, 40 - z) : Math.atan2(target.x - agent.home.x, target.z - agent.home.z)
    agent.routeStatus = plazaAgent
      ? 'available near the central plaza'
      : lateTaxiCommuter
        ? `late commute from ${agent.home.name} to ${target.name}`
        : `starting from ${target.name}`
    if (lateTaxiCommuter) agent.remember('mobility', `I am late for ${target.name} and should use a taxi.`, agent.home.name, 0.7)
    return agent
  }), [city.npcs, places])
  const agentsById = useMemo(() => new Map(agents.map(agent => [agent.id, agent])), [agents])

  // Publish the LIVE agent instances (the SAME array reference, never a clone) onto
  // the global city handle. window.__REALCITY_CITY__ is the identical object App.jsx
  // passes down as `city`, but it otherwise exposes only the static city.npcs home
  // coordinates; the self-driving engine modules (perception, lifePatterns,
  // populationMix, economy, atanorLink, dialogueEavesdrop) read city.agents for live
  // pos/heading/activity/needs and the current spoken line (agent.talkLine). This
  // fires only when the agents memo rebuilds, so there is no per-frame allocation.
  useEffect(() => {
    if (city) city.agents = agents
    if (typeof window !== 'undefined' && window.__REALCITY_CITY__ && window.__REALCITY_CITY__ !== city) {
      window.__REALCITY_CITY__.agents = agents
    }
  }, [agents, city])

  const hipsRef = useRef()
  const torsoRef = useRef()
  const neckRef = useRef()
  const headRef = useRef()
  const hairBackRef = useRef()
  const faceMarkRef = useRef()
  const cheekRef = useRef()
  const legRef = useRef()
  const armRef = useRef()
  const sleeveRef = useRef()
  const shinRef = useRef()
  const forearmRef = useRef()
  const hairRef = useRef()
  const eyeRef = useRef()
  const pupilRef = useRef()
  const eyelidRef = useRef()
  const browRef = useRef()
  const noseRef = useRef()
  const mouthRef = useRef()
  const shoeRef = useRef()
  const chestRef = useRef()
  const collarRef = useRef()
  const lapelRef = useRef()
  const badgeRef = useRef()
  const beltRef = useRef()
  const cuffRef = useRef()
  const bagRef = useRef()
  const backSeamRef = useRef()
  const shoulderStrapRef = useRef()
  const handRef = useRef()
  const thumbRef = useRef() // v2: mitten thumb nub, one per hand
  const earRef = useRef()
  const hatRef = useRef()
  const skirtRef = useRef()
  const glassesRef = useRef()
  const scarfRef = useRef()
  const speechCueRef = useRef()
  const phoneRef = useRef()
  const gestureCueRef = useRef()
  const mobilityDeckRef = useRef()
  const mobilityWheelRef = useRef()
  const mobilityHandleRef = useRef()
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const color = useMemo(() => new THREE.Color(), [])
  const colorsReady = useRef(false)
  const socialClock = useRef(0)
  const statsClock = useRef(0)
  const nearbyClock = useRef(0)
  const cityEventClock = useRef(0)
  const autonomyLlmClock = useRef(16)
  const autonomyLlmBusy = useRef(false)
  const autonomyLlmLastAgent = useRef(null)
  const socialLlmBusy = useRef(false)
  const busy = useRef(false)
  const requestBusy = useRef(false)
  const clockRef = useRef(0)
  const textures = useMemo(() => ({
    fabric: makeProceduralTexture('city-fabric', { size: 128, seed: 701, repeatX: 2.1, repeatY: 2.1 }),
    skin: makeProceduralTexture('skin-pores', { size: 128, seed: 702, repeatX: 1.4, repeatY: 1.4 }),
    hair: makeProceduralTexture('hair-strands', { size: 128, seed: 703, repeatX: 2.4, repeatY: 1.2 }),
    rubber: makeProceduralTexture('rubber-tread', { size: 128, seed: 704, repeatX: 1.8, repeatY: 1.8 }),
    metal: makeProceduralTexture('brushed-metal', { size: 128, seed: 705, repeatX: 1.8, repeatY: 0.9 }),
    glass: makeProceduralTexture('glass-smudge', { size: 128, seed: 706, repeatX: 1.2, repeatY: 1.2 }),
  }), [])

  // P-avatar-2 capability-animation player. External systems trigger a pose on a
  // specific agent via the 'realcity:avatar-action' window event or the
  // window.__REALCITY_AVATAR__.play() bridge; the per-frame loop reads
  // agent._action and overrides the gait for the action's duration (with a short
  // ease in/out) before returning to normal locomotion.
  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const startAction = (agentId, animation, duration) => {
      let agent = agentsById.get(agentId)
      if (!agent && agentId != null) agent = agents.find(a => a.id === agentId || a.name === agentId)
      if (!agent) return false
      agent._action = { id: String(animation || 'emote'), t0: clockRef.current, dur: Math.max(0.35, Number(duration) || 3) }
      return true
    }
    const onAction = (event) => {
      const detail = event?.detail || {}
      startAction(detail.agentId, detail.animation, detail.duration)
    }
    window.addEventListener('realcity:avatar-action', onAction)
    const api = {
      play: (agentId, animation, duration) => startAction(agentId, animation, duration),
      stop: (agentId) => { const agent = agentsById.get(agentId); if (agent) agent._action = null; return !!agent },
      animations: [
        'sit', 'lie', 'sleep', 'crouch', 'pickup', 'putdown', 'carry', 'throw', 'pour', 'press',
        'give', 'eat', 'drink', 'cook', 'work', 'repair', 'build', 'clean', 'wash', 'wave', 'talk',
        'phone', 'help', 'comfort', 'transact', 'vote', 'dance', 'laugh', 'exercise', 'climb', 'jump', 'emote',
      ],
    }
    window.__REALCITY_AVATAR__ = api
    return () => {
      window.removeEventListener('realcity:avatar-action', onAction)
      if (window.__REALCITY_AVATAR__ === api) delete window.__REALCITY_AVATAR__
    }
  }, [agentsById, agents])

  const runAutonomyLlm = async (agent, reason = 'ambient', options = {}) => {
    if (!agent || autonomyLlmBusy.current || typeof window === 'undefined') return null
    if (window.location.hostname.endsWith('.vercel.app')) return null
    autonomyLlmBusy.current = true
    autonomyLlmLastAgent.current = agent.id
    try {
      const store = useCityStore.getState()
      const scheduledTarget = targetFor(agent, places, store.timeMinutes, city.roads)
      const targetDistance = Math.hypot(scheduledTarget.x - agent.pos.x, scheduledTarget.z - agent.pos.z)
      const mobilityContext = mobilityContextForAgent(agent, city, scheduledTarget, store.timeMinutes)
      const placeCandidates = [...places.values()].slice(0, 12).map(place => ({
        id: place.id,
        name: place.name,
        kind: place.kind,
        address: place.address,
      }))
      const snapshot = agent.snapshot(places)
      const result = await askLocalAutonomy(snapshot, {
        timeLabel: `Day ${store.day}, ${formatTime(store.timeMinutes)}`,
        placeContext: `${agent.placeName || 'street'} / ${reason}`,
        scheduledTargetId: scheduledTarget.id || '',
        scheduledTargetName: scheduledTarget.name || '',
        scheduledTargetKind: scheduledTarget.kind || '',
        targetDistance,
        mobilityContext,
        placeCandidates,
        forceAction: options.forceAction || (reason === 'verification autonomous city life' ? 'visit_place' : undefined),
        forceTargetPlaceId: options.forceTargetPlaceId || (reason === 'verification autonomous city life' ? 'river_cafe' : undefined),
        forceTargetPlaceName: options.forceTargetPlaceName,
        forceTargetKind: options.forceTargetKind,
      })
      const runtime = window.__REALCITY_LLM__ || null
      if (!result?.ok) return result
      const thought = result.text || `${agent.name} keeps following the current routine.`
      const execution = executeAutonomyAction(agent, result, {
        agents,
        city,
        places,
        scheduledTarget,
        store,
        timeMinutes: store.timeMinutes,
        reason,
      })
      agent.currentIntent = thought
      agent.llmAutonomy = {
        ...(agent.llmAutonomy || {}),
        thought,
        source: result.source,
        provider: result.provider,
        model: result.model,
        latencyMs: result.latencyMs,
        reason,
        action: result.action,
        targetPlaceId: result.targetPlaceId || execution.targetPlaceId,
        targetName: result.targetPlaceName || execution.targetName,
        mobilityMode: result.mobilityMode || execution.mobilityMode || null,
        mobilitySource: result.mobilitySource || execution.mobilitySource || null,
        mobilityContext,
        execution,
        parsed: result.parsed,
        createdAt: Date.now(),
      }
      agent.remember('llm-autonomy', `${thought} Action: ${execution.action} -> ${execution.outcome}.`, agent.placeName, 0.76)
      const event = {
        id: `llm_autonomy_${agent.id}_${Date.now()}`,
        kind: 'llm',
        agentId: agent.id,
        agentName: agent.name,
        placeName: agent.placeName,
        topic: 'npc autonomy',
        text: `${agent.name} updates a local-LLM intention: ${thought} (${execution.action}: ${execution.outcome})`.slice(0, 180),
      }
      store.addCityEvent(event)
      const player = store.player || { x: 0, z: 0 }
      if (Math.hypot(agent.pos.x - player.x, agent.pos.z - player.z) < 55) store.setPulse(event.text)
      window.__REALCITY_LLM_AUTONOMY__ = {
        agentId: agent.id,
        agentName: agent.name,
        reason,
        thought,
        source: result.source,
        provider: result.provider,
        model: result.model,
        latencyMs: result.latencyMs,
        action: result.action,
        targetPlaceId: result.targetPlaceId || execution.targetPlaceId,
        targetName: result.targetPlaceName || execution.targetName,
        mobilityMode: result.mobilityMode || execution.mobilityMode || null,
        mobilitySource: result.mobilitySource || execution.mobilitySource || null,
        mobilityContext,
        execution,
        parsed: result.parsed,
        runtime,
        createdAt: Date.now(),
      }
      const currentSamples = useCityStore.getState().pedestrianSamples || []
      if (currentSamples.length) {
        store.setPedestrianSamples(currentSamples.map(sample => sample.id === agent.id
          ? {
              ...sample,
              currentIntent: thought,
              llmAutonomyThought: thought,
              llmAutonomySource: result.source,
              llmAutonomyLatencyMs: result.latencyMs,
              llmAutonomyReason: reason,
              llmAutonomyAction: result.action,
              llmAutonomyExecuted: execution.executed,
              llmAutonomyOutcome: execution.outcome,
              llmAutonomyTargetName: execution.targetName,
              llmAutonomyMobilityMode: result.mobilityMode || execution.mobilityMode || null,
              llmAutonomyMobilitySource: result.mobilitySource || execution.mobilitySource || null,
              llmAutonomyNearestDock: mobilityContext.nearestDock?.name || null,
              needErrandMobilityMode: agent.needErrand?.mobilityMode || null,
              needErrandMobilitySource: agent.needErrand?.mobilitySource || null,
              needErrandMobilityDockName: agent.needErrand?.mobilityDockName || null,
              sharedMobilityPhase: agent.needErrand?.sharedMobilityTrip?.phase || null,
              sharedMobilityPickupDockName: agent.needErrand?.sharedMobilityTrip?.pickupStationName || null,
              sharedMobilityReturnDockName: agent.needErrand?.sharedMobilityTrip?.returnStationName || null,
              sharedMobilityReturnSlotReserved: agent.needErrand?.sharedMobilityTrip?.returnSlotReserved ?? null,
              sharedMobilityPickupInventoryAfter: agent.needErrand?.sharedMobilityTrip?.pickupInventoryAfter || null,
              sharedMobilityReturnInventoryAfter: agent.needErrand?.sharedMobilityTrip?.returnInventoryAfter || null,
              sharedMobilityPickupProgress: agent.needErrand?.sharedMobilityTrip?.pickupAnimationProgress ?? null,
              sharedMobilityReturnProgress: agent.needErrand?.sharedMobilityTrip?.returnAnimationProgress ?? null,
              sharedMobilityRideProp: agent.needErrand?.sharedMobilityTrip?.phase === 'riding-to-return-dock' && isSharedMobilityMode(agent.needErrand?.mobilityMode) ? `${agent.needErrand.mobilityMode}-visible-prop` : null,
              sharedMobilityVisualSource: agent.needErrand?.mobilitySource || null,
              lastMemory: thought,
            }
          : sample))
      }
      return window.__REALCITY_LLM_AUTONOMY__
    } finally {
      autonomyLlmBusy.current = false
    }
  }

  const runLlmSocialConversation = async (a, b, reason = 'debug local LLM NPC social conversation', seconds = 10) => {
    if (!a || !b || a === b || socialLlmBusy.current || typeof window === 'undefined') return null
    if (window.location.hostname.endsWith('.vercel.app')) return null
    socialLlmBusy.current = true
    try {
      const store = useCityStore.getState()
      const fallbackTopic = conversationTopicFor(a, b, store.timeMinutes)
      const result = await askLocalNPCConversation(a.snapshot(places), b.snapshot(places), {
        topic: fallbackTopic,
        timeLabel: `Day ${store.day}, ${formatTime(store.timeMinutes)}`,
        placeName: a.placeName || b.placeName || 'sidewalk',
        streetContext: `${reason}; keep pedestrians on sidewalks, respect traffic, remember useful personal details, and make each NPC sound distinct.`,
      })
      const topic = llmConversationTopicFor(a, b, fallbackTopic, result)
      const duration = clampValue(Number(seconds) || 10, 3, 22)
      a.debugSocialConversation = true
      b.debugSocialConversation = true
      a.talk(duration, b, topic, store.timeMinutes)
      b.talk(duration, a, topic, store.timeMinutes)
      const event = conversationEventFor(a, b, topic, store.timeMinutes, `llm_social_${Date.now()}`)
      store.addCityEvent(event)
      const player = store.player || { x: 0, z: 0 }
      if (Math.min(
        Math.hypot(a.pos.x - player.x, a.pos.z - player.z),
        Math.hypot(b.pos.x - player.x, b.pos.z - player.z),
      ) < 55) {
        store.setPulse(event.text)
      }

      const socialRecord = {
        pair: [
          { id: a.id, name: a.name, line: a.talkLine },
          { id: b.id, name: b.name, line: b.talkLine },
        ],
        reason,
        source: result?.source || topic.source,
        ok: !!result?.ok,
        latencyMs: result?.latencyMs ?? null,
        topic: topic.label,
        event,
        llm: result?.llm || null,
        runtime: window.__REALCITY_LLM__ || null,
        createdAt: Date.now(),
      }
      window.__REALCITY_LLM_SOCIAL__ = socialRecord

      const currentSamples = useCityStore.getState().pedestrianSamples || []
      if (currentSamples.length) {
        store.setPedestrianSamples(currentSamples.map(sample => {
          if (sample.id !== a.id && sample.id !== b.id) return sample
          const agent = sample.id === a.id ? a : b
          return {
            ...sample,
            currentIntent: agent.currentIntent,
            talkPartnerId: agent.talkPartnerId,
            talkPartnerName: agent.talkPartnerName,
            talkTopicLabel: agent.talkTopicLabel,
            talkLine: agent.talkLine,
            talkSource: agent.talkSource,
            lastInteractionPartner: agent.lastInteraction?.partnerName || null,
            lastInteractionTopic: agent.lastInteraction?.topic || null,
            lastInteractionSource: agent.lastInteraction?.source || null,
            lastInteractionLine: agent.lastInteraction?.line || null,
            llmSocialSource: agent.lastLlmConversation?.source || null,
            llmSocialLine: agent.lastLlmConversation?.line || null,
            llmSocialPartnerName: agent.lastLlmConversation?.partnerName || null,
            llmSocialLatencyMs: agent.lastLlmConversation?.latencyMs ?? null,
            lastMemory: agent.memories?.[0]?.text || sample.lastMemory,
            memoryCount: agent.memories?.length || sample.memoryCount,
            relationshipCount: agent.relationshipCount || sample.relationshipCount,
          }
        }))
      }

      return socialRecord
    } finally {
      socialLlmBusy.current = false
    }
  }

  useEffect(() => {
    const store = useCityStore.getState()
    store.setStats({ npcs: agents.length, cars: city.cars.length, tiles: city.tiles.length, llm: llmStatus() })
    agents.slice(0, 4).forEach((agent, index) => {
      const event = autonomyEventFor(agent, store.timeMinutes + index * 0.01)
      agent.remember(event.kind, event.text, event.placeName, 0.5)
      store.addCityEvent({ ...event, id: `initial_${event.id}_${index}` })
    })
    for (let index = 0; index < Math.min(8, agents.length - 1); index += 2) {
      const a = agents[index]
      const b = agents[index + 1]
      if (!a || !b) continue
      const topic = conversationTopicFor(a, b, store.timeMinutes + index * 0.04)
      a.talk(2.6, b, topic, store.timeMinutes)
      b.talk(2.6, a, topic, store.timeMinutes)
      store.addCityEvent(conversationEventFor(a, b, topic, store.timeMinutes, `initial_social_${index}`))
    }
  }, [agents.length, city.cars.length, city.tiles.length])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const unique = selector => new Set(agents.map(agent => selector(agent)).filter(Boolean)).size
    window.__REALCITY_ACTOR_RENDERING__ = {
      npcBase: DIGITAL_HUMAN_SOURCE.base,
      playerReference: 'PlayerRig.Character',
      digitalHumanSource: DIGITAL_HUMAN_SOURCE,
      rigScale: {
        npcBaseY: 0.95,
        playerBaseY: 1.1,
        playerCharacterOffsetY: -0.9,
        torsoCapsuleTotalHeight: 0.94,
        armCapsuleTotalHeight: 0.53,
        legCapsuleTotalHeight: 0.65,
        morphSystem: 'MakeHuman-style height, chest, waist, hip, limb, hand, foot, face-width, and age-posture parameters',
        sharedBaseRule: DIGITAL_HUMAN_SOURCE.sharedBaseRule,
      },
      anatomicalRig: {
        base: DIGITAL_HUMAN_SOURCE.base,
        sourceLicense: DIGITAL_HUMAN_SOURCE.license,
        morphTargets: ['height', 'shoulder', 'chest', 'waist', 'hip', 'torsoDepth', 'limbThickness', 'armLength', 'legLength', 'headScale', 'faceWidth', 'eyeSpacing', 'agePosture'],
        perAgentDeterministic: true,
        copiedExternalMeshCode: false,
      },
      bodyParts: [
        'hips',
        'torso',
        'chest',
        'neck',
        'head',
        'hairCap',
        'hairBack',
        'ears',
        'eyes',
        'eyeWhites',
        'pupils',
        'eyelids',
        'brows',
        'nose',
        'mouth',
        'faceMarks',
        'cheeks',
        'arms',
        'sleeves',
        'hands',
        'legs',
        'shoes',
        'collar',
        'lapels',
        'badge',
        'cuffs',
        'belt',
        'backSeam',
        'shoulderStraps',
        'bag',
        'hat',
        'scarf',
        'skirt',
        'glasses',
        'speechCue',
        'phoneProp',
        'gestureCue',
        'sharedMobilityDeck',
        'sharedMobilityWheels',
        'sharedMobilityHandlebar',
      ],
      socialVisualCues: {
        speechCueInstances: agents.length,
        phonePropInstances: agents.length,
        gestureCueInstances: agents.length,
        partnerFacingRule: 'active conversation partners rotate toward each other within social radius',
        gestureStyleVariants: unique(agent => agent.gestureStyle),
        cueKinds: ['speechCue', 'checks-phone', 'points-while-speaking', 'small-wave', 'formal-bow', 'quick-nod'],
      },
      sharedMobilityVisualCues: {
        propInstances: agents.length,
        wheelInstances: agents.length * 2,
        supportedModes: ['shared-bike', 'shared-scooter'],
        dockRule: 'props appear only when an LLM/need route executes a GBFS shared-bike or shared-scooter trip',
        source: 'GBFS station_status + SmartCities geofence mobility mode',
      },
      facialAnimation: {
        blinkRule: 'per-agent asynchronous eyelid closure over visible eye whites',
        pupilRule: 'small dark pupils sit over the eye whites with subtle saccade offsets',
        sharedWithPlayer: 'PlayerRig.Character now uses the same eye-white, pupil, and eyelid face stack',
        perAgentSeeded: true,
      },
      directionReadability: {
        frontCues: ['eye whites', 'pupils', 'nose bridge', 'mouth line', 'front badge', 'lapels'],
        backCues: ['hairBack volume', 'vertical back seam', 'shoulder straps', 'backpack silhouette'],
        sideCues: ['ears', 'hands', 'shoe toe length', 'arm swing'],
        gaitCues: ['stride-synced legs', 'counter-swing arms', 'visible forward shoe offset'],
        purpose: 'street-camera front/back recognition so pedestrians read as humans, not robots',
      },
      variation: {
        count: agents.length,
        heightVariants: unique(agent => agent.appearance?.heightScale?.toFixed(2)),
        bodyVariants: unique(agent => agent.appearance?.bodyArchetype),
        ageBands: unique(agent => agent.appearance?.ageBand),
        ages: unique(agent => String(agent.age)),
        genders: unique(agent => agent.gender),
        hairStyles: unique(agent => agent.appearance?.hairStyle),
        outfitSignatures: unique(agent => agent.appearance?.signature),
        skinTones: unique(agent => agent.appearance?.skinColor),
        faceAccessoryVariants: unique(agent => `${agent.appearance?.glassesStyle}:${agent.appearance?.ageBand}:${agent.gender}`),
        digitalHumanMorphs: unique(agent => makeHumanStyleRig(agent, agentLook(agent)).summary),
      },
      streetReadableDetails: ['collar', 'lapels', 'cheeks', 'eye whites', 'pupils', 'blink eyelids', 'front badge', 'pant cuffs', 'back seam', 'shoulder straps'],
      samplePeople: agents.slice(0, 12).map(agent => ({
        id: agent.id,
        name: agent.name,
        age: agent.age,
        gender: agent.gender,
        heightScale: Number((agent.appearance?.heightScale ?? 1).toFixed(3)),
        bodyArchetype: agent.appearance?.bodyArchetype,
        digitalHumanMorph: makeHumanStyleRig(agent, agentLook(agent)).summary,
        hairStyle: agent.appearance?.hairStyle,
        outfit: agent.appearance?.styleBrief,
      })),
      speechSamples: agents.slice(0, 12).map(agent => ({
        id: agent.id,
        name: agent.name,
        prefix: agent.speechStyle?.prefix || '',
        label: agent.speechStyle?.label || '',
        flavor: agent.speechStyle?.flavor || '',
        signature: agent.speechStyle?.signature || '',
      })),
    }
  }, [agents])

  useFrame((state, delta) => {
    clockRef.current = state.clock.elapsedTime
    if (!hipsRef.current || !torsoRef.current || !neckRef.current || !headRef.current || !hairBackRef.current || !faceMarkRef.current || !cheekRef.current || !legRef.current || !armRef.current || !sleeveRef.current || !shinRef.current || !forearmRef.current || !hairRef.current || !eyeRef.current || !pupilRef.current || !eyelidRef.current || !browRef.current || !noseRef.current || !mouthRef.current || !shoeRef.current || !chestRef.current || !collarRef.current || !lapelRef.current || !badgeRef.current || !beltRef.current || !cuffRef.current || !bagRef.current || !backSeamRef.current || !shoulderStrapRef.current || !handRef.current || !earRef.current || !hatRef.current || !skirtRef.current || !glassesRef.current || !scarfRef.current || !speechCueRef.current || !phoneRef.current || !gestureCueRef.current || !mobilityDeckRef.current || !mobilityWheelRef.current || !mobilityHandleRef.current || !thumbRef.current) return
    const dt = Math.min(delta, 0.05)
    const store = useCityStore.getState()
    const time = store.timeMinutes
    let talks = 0
    let nearestAgent = null
    let nearestDistance = Infinity
    const player = new THREE.Vector3(store.player.x, store.player.y, store.player.z)

    if (!colorsReady.current) {
      agents.forEach((agent, i) => {
        const look = agentLook(agent)
        hipsRef.current.setColorAt(i, color.set(look.pantsColor))
        torsoRef.current.setColorAt(i, color.set(look.topColor))
        chestRef.current.setColorAt(i, color.set(look.jacketColor))
        neckRef.current.setColorAt(i, color.set(skinTone(agent)))
        headRef.current.setColorAt(i, color.set(skinTone(agent)))
        hairRef.current.setColorAt(i, color.set(hairTone(agent)))
        hairBackRef.current.setColorAt(i, color.set(hairTone(agent)))
        faceMarkRef.current.setColorAt(i * 2, color.set(agent.appearance?.ageBand === 'senior' ? '#7b5b4e' : hairTone(agent)))
        faceMarkRef.current.setColorAt(i * 2 + 1, color.set(agent.appearance?.ageBand === 'senior' ? '#6f5b52' : hairTone(agent)))
        cheekRef.current.setColorAt(i * 2, color.set(skinTone(agent)))
        cheekRef.current.setColorAt(i * 2 + 1, color.set(skinTone(agent)))
        armRef.current.setColorAt(i * 2, color.set(skinTone(agent)))
        armRef.current.setColorAt(i * 2 + 1, color.set(skinTone(agent)))
        sleeveRef.current.setColorAt(i * 2, color.set(look.topColor))
        sleeveRef.current.setColorAt(i * 2 + 1, color.set(look.topColor))
        handRef.current.setColorAt(i * 2, color.set(skinTone(agent)))
        handRef.current.setColorAt(i * 2 + 1, color.set(skinTone(agent)))
        earRef.current.setColorAt(i * 2, color.set(skinTone(agent)))
        earRef.current.setColorAt(i * 2 + 1, color.set(skinTone(agent)))
        eyelidRef.current.setColorAt(i * 2, color.set(skinTone(agent)))
        eyelidRef.current.setColorAt(i * 2 + 1, color.set(skinTone(agent)))
        browRef.current.setColorAt(i * 2, color.set(hairTone(agent)))
        browRef.current.setColorAt(i * 2 + 1, color.set(hairTone(agent)))
        legRef.current.setColorAt(i * 2, color.set(look.pantsColor))
        legRef.current.setColorAt(i * 2 + 1, color.set(look.pantsColor))
        shinRef.current.setColorAt(i * 2, color.set(look.pantsColor))
        shinRef.current.setColorAt(i * 2 + 1, color.set(look.pantsColor))
        forearmRef.current.setColorAt(i * 2, color.set(skinTone(agent)))
        forearmRef.current.setColorAt(i * 2 + 1, color.set(skinTone(agent)))
        shoeRef.current.setColorAt(i * 2, color.set(look.shoeColor))
        shoeRef.current.setColorAt(i * 2 + 1, color.set(look.shoeColor))
        collarRef.current.setColorAt(i, color.set(look.outerwear === 'hoodie' ? look.topColor : '#eee4d4'))
        lapelRef.current.setColorAt(i * 2, color.set(look.jacketColor))
        lapelRef.current.setColorAt(i * 2 + 1, color.set(look.jacketColor))
        badgeRef.current.setColorAt(i, color.set(look.accessoryColor))
        beltRef.current.setColorAt(i, color.set(look.accessoryColor))
        cuffRef.current.setColorAt(i * 2, color.set(look.shoeColor))
        cuffRef.current.setColorAt(i * 2 + 1, color.set(look.shoeColor))
        bagRef.current.setColorAt(i, color.set(look.accessoryColor))
        backSeamRef.current.setColorAt(i, color.set(look.accessoryColor))
        shoulderStrapRef.current.setColorAt(i * 2, color.set(look.accessoryColor))
        shoulderStrapRef.current.setColorAt(i * 2 + 1, color.set(look.accessoryColor))
        hatRef.current.setColorAt(i, color.set(look.accessoryColor))
        skirtRef.current.setColorAt(i, color.set(look.pantsColor))
        scarfRef.current.setColorAt(i, color.set(look.accessoryColor))
      })
      if (hipsRef.current.instanceColor) hipsRef.current.instanceColor.needsUpdate = true
      if (torsoRef.current.instanceColor) torsoRef.current.instanceColor.needsUpdate = true
      if (chestRef.current.instanceColor) chestRef.current.instanceColor.needsUpdate = true
      if (neckRef.current.instanceColor) neckRef.current.instanceColor.needsUpdate = true
      if (headRef.current.instanceColor) headRef.current.instanceColor.needsUpdate = true
      if (hairRef.current.instanceColor) hairRef.current.instanceColor.needsUpdate = true
      if (hairBackRef.current.instanceColor) hairBackRef.current.instanceColor.needsUpdate = true
      if (faceMarkRef.current.instanceColor) faceMarkRef.current.instanceColor.needsUpdate = true
      if (cheekRef.current.instanceColor) cheekRef.current.instanceColor.needsUpdate = true
      if (armRef.current.instanceColor) armRef.current.instanceColor.needsUpdate = true
      if (sleeveRef.current.instanceColor) sleeveRef.current.instanceColor.needsUpdate = true
      if (handRef.current.instanceColor) handRef.current.instanceColor.needsUpdate = true
      if (earRef.current.instanceColor) earRef.current.instanceColor.needsUpdate = true
      if (eyelidRef.current.instanceColor) eyelidRef.current.instanceColor.needsUpdate = true
      if (browRef.current.instanceColor) browRef.current.instanceColor.needsUpdate = true
      if (legRef.current.instanceColor) legRef.current.instanceColor.needsUpdate = true
      if (shinRef.current.instanceColor) shinRef.current.instanceColor.needsUpdate = true
      if (forearmRef.current.instanceColor) forearmRef.current.instanceColor.needsUpdate = true
      if (shoeRef.current.instanceColor) shoeRef.current.instanceColor.needsUpdate = true
      if (collarRef.current.instanceColor) collarRef.current.instanceColor.needsUpdate = true
      if (lapelRef.current.instanceColor) lapelRef.current.instanceColor.needsUpdate = true
      if (badgeRef.current.instanceColor) badgeRef.current.instanceColor.needsUpdate = true
      if (beltRef.current.instanceColor) beltRef.current.instanceColor.needsUpdate = true
      if (cuffRef.current.instanceColor) cuffRef.current.instanceColor.needsUpdate = true
      if (bagRef.current.instanceColor) bagRef.current.instanceColor.needsUpdate = true
      if (backSeamRef.current.instanceColor) backSeamRef.current.instanceColor.needsUpdate = true
      if (shoulderStrapRef.current.instanceColor) shoulderStrapRef.current.instanceColor.needsUpdate = true
      if (hatRef.current.instanceColor) hatRef.current.instanceColor.needsUpdate = true
      if (skirtRef.current.instanceColor) skirtRef.current.instanceColor.needsUpdate = true
      if (scarfRef.current.instanceColor) scarfRef.current.instanceColor.needsUpdate = true
      colorsReady.current = true
    }

    for (let i = 0; i < agents.length; i += 1) {
      const agent = agents[i]
      const agentState = agent.update(dt, time, places, city)
      if (agentState === 'talking') talks += 1
      const talking = agentState === 'talking'
      const talkPartner = talking && agent.talkPartnerId ? agentsById.get(agent.talkPartnerId) : null
      agent.renderFacingPartner = false
      agent.facingPartnerAngle = null
      if (talking) {
        agent.visualGesture = agent.visualGesture || socialGestureKind(agent)
        if (talkPartner && talkPartner.pos && agent.pos.distanceTo(talkPartner.pos) < 12) {
          const desired = Math.atan2(talkPartner.pos.x - agent.pos.x, talkPartner.pos.z - agent.pos.z)
          const turn = Math.atan2(Math.sin(desired - agent.heading), Math.cos(desired - agent.heading))
          agent.heading += turn * Math.min(1, dt * 5.2)
          const afterTurn = Math.atan2(Math.sin(desired - agent.heading), Math.cos(desired - agent.heading))
          agent.renderFacingPartner = true
          agent.facingPartnerAngle = Number(Math.abs(afterTurn).toFixed(3))
        }
      }
      const playerDistance = agent.pos.distanceTo(player)
      if (!agent.mission && playerDistance < nearestDistance) {
        nearestAgent = agent
        nearestDistance = playerDistance
      }
      agent.playerDistance = Number(playerDistance.toFixed(2))
      agent.facingPlayerAngle = null
      agent.socialReaction = null
      if (!agent.mission && agentState !== 'walking' && playerDistance < NPC_GLANCE_RADIUS) {
        const desired = Math.atan2(store.player.x - agent.pos.x, store.player.z - agent.pos.z)
        const turn = Math.atan2(Math.sin(desired - agent.heading), Math.cos(desired - agent.heading))
        const keepPartnerFocus = talking && agent.debugSocialConversation && agent.renderFacingPartner
        if (!keepPartnerFocus) agent.heading += turn * Math.min(1, dt * 3.8)
        const afterTurn = Math.atan2(Math.sin(desired - agent.heading), Math.cos(desired - agent.heading))
        agent.facingPlayerAngle = Number(Math.abs(afterTurn).toFixed(3))
        agent.socialReaction = Math.abs(afterTurn) < 0.72 ? 'glancing-at-player' : 'turning-toward-player'
        if (agent.glanceCooldown <= 0) {
          agent.glanceCooldown = 7 + Math.random() * 8
          if (playerDistance < NPC_GLANCE_PULSE_RADIUS) {
            store.setPulse(`${agent.name} glances over as you pass through ${agent.placeName}.`)
          }
        }
      }

      const fallen = agentState === 'fallen'
      const stumbling = agentState === 'stumbling'
      const fallSide = hashValue(agent.id) % 2 === 0 ? 1 : -1
      const stumbleLean = stumbling ? Math.sin(state.clock.elapsedTime * 18 + i) * 0.22 : 0
      const gestureKind = talking ? (agent.visualGesture || socialGestureKind(agent)) : null
      const gesturePulse = talking ? Math.sin((performance.now() - (agent.talkStartedAt || 0)) * 0.006 + i * 0.7) : 0
      const socialLean = talking && gestureKind === 'formal-bow' ? 0.13 + gesturePulse * 0.025 : 0
      let bodyRotX = fallen ? 1.12 : socialLean
      let bodyRotZ = fallen ? fallSide * 0.72 : stumbleLean
      const look = agentLook(agent)
      const walking = agentState === 'walking'
      const walk = look.walkStyle || { cadence: 1, stride: 1, armSwing: 1 }
      // `base` (root transform) and `stride` are finalised in the gait/action block
      // below, once the rig proportions and gesture flags are known.
      const armSwing = walk.armSwing || 1
      const human = makeHumanStyleRig(agent, look)
      const height = human.heightScale
      const shoulder = human.shoulderScale * 0.93 // v2: narrower, less blocky shoulder line
      const bodyScale = human.bodyScale
      const legScale = human.legScale
      const headScale = human.headScale
      const chestWidth = human.chestWidth
      const waistWidth = human.waistWidth
      const hipWidth = human.hipWidth
      const torsoDepth = human.torsoDepth
      const armThickness = human.armThickness
      const legThickness = human.legThickness
      const stanceWidth = human.stanceWidth
      const faceWidth = human.faceWidth
      const faceDepth = human.faceDepth
      const eyeSpacing = human.eyeSpacing
      const longHair = look.hairStyle === 'long'
      const bobHair = look.hairStyle === 'bob'
      const hairLong = longHair || bobHair
      const hairBun = look.hairStyle === 'bun'
      const shaved = look.hairStyle === 'shaved'
      const hatVisible = (look.hatStyle && look.hatStyle !== 'none') || look.hairStyle === 'cap'
      const bagVisible = look.bagStyle && look.bagStyle !== 'none'
      const skirtVisible = look.bottomStyle === 'skirt'
      const glassesVisible = look.glassesStyle && look.glassesStyle !== 'none'
      const scarfVisible = look.scarfStyle && look.scarfStyle !== 'none'
      const seniorFace = look.ageBand === 'senior' || agent.age >= 60
      const facialHair = agent.gender === 'man' && (seniorFace || hashValue(`${agent.id}_face_hair`) % 4 === 0)
      const blinkPeriod = 3.1 + (hashValue(`${agent.id}_blink`) % 140) / 70
      const blinkWindow = 0.13 + (hashValue(`${agent.id}_blink_window`) % 5) * 0.006
      const blinkPhase = (state.clock.elapsedTime + (hashValue(`${agent.id}_blink_offset`) % 1000) * 0.003) % blinkPeriod
      const blink = blinkPhase > blinkPeriod - blinkWindow
        ? Math.sin(((blinkPhase - (blinkPeriod - blinkWindow)) / blinkWindow) * Math.PI)
        : 0
      const saccade = talking || agent.socialReaction
        ? Math.sin(state.clock.elapsedTime * 3.4 + i * 0.63) * 0.003
        : Math.sin(state.clock.elapsedTime * 1.15 + i * 1.31) * 0.006
      const pupilY = Math.sin(state.clock.elapsedTime * 0.9 + i * 0.47) * 0.002
      const phoneVisible = talking && gestureKind === 'checks-phone' && !fallen
      const talkCueVisible = talking && !fallen
      const sharedMobilityPhase = agent.needErrand?.sharedMobilityTrip?.phase || null
      const sharedMobilityMode = sharedMobilityPhase === 'riding-to-return-dock' ? agent.needErrand?.mobilityMode || null : null
      const ridingSharedBike = sharedMobilityMode === 'shared-bike' && !fallen
      const ridingSharedScooter = sharedMobilityMode === 'shared-scooter' && !fallen
      const sharedMobilityVisible = ridingSharedBike || ridingSharedScooter
      const rideFront = ridingSharedBike ? 0.46 : 0.36
      const rideRear = ridingSharedBike ? -0.46 : -0.31
      const wheelRadius = ridingSharedBike ? 0.18 : 0.1
      const rideBob = sharedMobilityVisible ? Math.sin(state.clock.elapsedTime * 8.6 + i) * 0.012 : 0
      const handTalkLift = talkCueVisible
        ? gestureKind === 'folds-arms'
          ? 0.14
          : gestureKind === 'hands-in-pockets'
            ? -0.03
            : 0.18 + Math.max(0, gesturePulse) * 0.06
        : 0
      const leftHandLift = talkCueVisible && gestureKind === 'folds-arms' ? 0.18 : handTalkLift * 0.32
      const rightHandLift = phoneVisible ? 0.26 : handTalkLift

      // ---- Humanoid v2 gait + capability-action solve -----------------------
      // Gait phase advances with distance travelled (not raw time) so planted
      // feet do not skate. Full articulation is reserved for agents near the
      // player or running a capability action; everyone else keeps the cheap
      // single-capsule swing.
      const tSec = state.clock.elapsedTime
      if (agent._px === undefined) { agent._px = agent.pos.x; agent._pz = agent.pos.z; agent._gait = i * 0.7 }
      const moved = Math.hypot(agent.pos.x - agent._px, agent.pos.z - agent._pz)
      agent._px = agent.pos.x
      agent._pz = agent.pos.z
      const gaitSpeed = moved / Math.max(dt, 0.0001)
      if (walking) agent._gait += moved * NPC_GAIT_STRIDE_RATE
      const phaseWalk = agent._gait
      const swing = Math.sin(phaseWalk)
      const running = walking && gaitSpeed > NPC_RUN_SPEED
      const stride = walking ? swing * 0.46 * (walk.stride || 1) : Math.sin(tSec * 1.2 + i * 0.83) * 0.035
      // action envelope (ease in over BLEND, hold, ease back out)
      let actionW = 0
      if (agent._action) {
        const el = tSec - agent._action.t0
        if (el >= agent._action.dur + NPC_ACTION_BLEND) agent._action = null
        else actionW = Math.max(0, Math.min(1, Math.min(el / NPC_ACTION_BLEND, (agent._action.dur + NPC_ACTION_BLEND - el) / NPC_ACTION_BLEND)))
      }
      const articulated = !fallen && (playerDistance < NPC_NEAR_DIST || actionW > 0)
      // gait-driven joint angles (opposite arm/leg, relaxed elbows, knee flexion on swing)
      const thighAmp = walking ? (running ? 0.92 : 0.5) : 0.05
      const kneeAmp = walking ? (running ? 1.0 : 0.66) : 0.08
      const armAmp = walking ? (running ? 0.9 : 0.5) * armSwing : 0.06
      let thighR = swing * thighAmp
      let thighL = -swing * thighAmp
      let kneeR = 0.12 + kneeAmp * Math.max(0, Math.sin(phaseWalk - 0.5))
      let kneeL = 0.12 + kneeAmp * Math.max(0, Math.sin(phaseWalk + Math.PI - 0.5))
      let shoulderR = 0.1 - swing * armAmp
      let shoulderL = 0.1 + swing * armAmp
      let elbowR = 0.32 + (running ? 0.2 : 0) + Math.max(0, swing) * 0.12
      let elbowL = 0.32 + (running ? 0.2 : 0) + Math.max(0, -swing) * 0.12
      let latR = 0.05
      let latL = 0.05
      let rootDrop = 0
      let actionLean = running ? 0.2 : (walking ? 0.06 : 0) // subtle forward spine lean into the walk
      let actionLeanZ = 0
      if (!walking && !fallen) {
        // idle: breathing sway plus an occasional weight shift
        bodyRotX += Math.sin(tSec * 1.5 + i) * 0.02
        const shiftPhase = Math.sin(tSec * 0.32 + i * 1.3)
        if (Math.abs(shiftPhase) > 0.72) bodyRotZ += Math.sign(shiftPhase) * 0.045
      }
      if (talkCueVisible && actionW <= 0) {
        // conversational hand gestures reuse the articulated arms
        const g = Math.sin((performance.now() - (agent.talkStartedAt || 0)) * 0.004 + i)
        shoulderR = 0.5 + Math.max(0, g) * 0.25; elbowR = 1.0 + g * 0.2
        shoulderL = 0.35; elbowL = 0.9
        if (gestureKind === 'folds-arms') { shoulderR = shoulderL = 0.2; elbowR = elbowL = 1.8; latR = latL = 0.05 }
        else if (gestureKind === 'checks-phone' || phoneVisible) { shoulderR = 1.35; latR = 0.28; elbowR = 2.45 }
        else if (gestureKind === 'hands-in-pockets') { shoulderR = shoulderL = 0.05; elbowR = elbowL = 0.5 }
      }
      if (actionW > 0) {
        actionPose(NPC_ACTION_SCRATCH, agent._action.id, tSec - agent._action.t0, agent._action.dur, height)
        const ap = NPC_ACTION_SCRATCH
        const w = actionW
        thighR += (ap.thighR - thighR) * w; thighL += (ap.thighL - thighL) * w
        kneeR += (ap.kneeR - kneeR) * w; kneeL += (ap.kneeL - kneeL) * w
        shoulderR += (ap.shR - shoulderR) * w; shoulderL += (ap.shL - shoulderL) * w
        elbowR += (ap.elbR - elbowR) * w; elbowL += (ap.elbL - elbowL) * w
        latR += (ap.latR - latR) * w; latL += (ap.latL - latL) * w
        rootDrop = ap.rootDrop * w; actionLean = ap.lean * w; actionLeanZ = ap.leanZ * w
      }
      bodyRotX += actionLean
      bodyRotZ += actionLeanZ
      // slight torso bob on the walk cycle; the head stays stable (bob is applied
      // only to the torso/chest locals, not the root)
      const torsoBob = walking && articulated ? Math.abs(swing) * 0.02 * height : 0
      let base
      if (fallen) {
        NPC_BASE_SCRATCH.x = agent.pos.x; NPC_BASE_SCRATCH.y = agent.pos.y - 0.46; NPC_BASE_SCRATCH.z = agent.pos.z; base = NPC_BASE_SCRATCH
      } else if (rootDrop !== 0) {
        NPC_BASE_SCRATCH.x = agent.pos.x; NPC_BASE_SCRATCH.y = agent.pos.y - rootDrop; NPC_BASE_SCRATCH.z = agent.pos.z; base = NPC_BASE_SCRATCH
      } else {
        base = agent.pos
      }

      const hipY = 0.03 * height
      const torsoY = 0.45 * height
      const chestY = 0.52 * height
      const shoulderY = 0.59 * height
      const neckY = 0.82 * height
      const headY = 0.97 * height
      const eyeY = 1.0 * height
      const browY = 1.04 * height
      const mouthY = 0.875 * height
      const hairY = (hairLong ? 1.02 : 1.13) * height
      const hairBackY = (longHair ? 0.78 : bobHair ? 0.9 : 0.97) * height
      const hairCapHeight = hairBun ? 0.15 : longHair ? 0.22 : bobHair ? 0.16 : 0.105
      setLocalPart(hipsRef.current, i, dummy, base, agent.heading, [0, hipY, 0], [0.345 * hipWidth, 0.185 * height * bodyScale, 0.24 * torsoDepth], bodyRotX, bodyRotZ) // v2: tighter pelvis block
      setLocalPart(torsoRef.current, i, dummy, base, agent.heading, [0, torsoY + torsoBob, human.postureLean], [0.21 * waistWidth, (walking ? 0.25 : 0.235) * height * bodyScale, 0.16 * torsoDepth], bodyRotX, bodyRotZ)
      setLocalPart(neckRef.current, i, dummy, base, agent.heading, [0, neckY + 0.01 * height, 0.012 + human.postureLean], [0.066 * human.neckScale, 0.135 * height, 0.066 * human.neckScale], bodyRotX * 0.82, bodyRotZ) // v2: slimmer, slightly longer neck
      // v2: subtle head micro-turn. The body already orients toward a talk partner (social solve
      // above); the head leads it with a little life — most active mid-conversation, a gentle idle
      // sway otherwise. Neck/chest stay on the body heading so only the head-and-face group turns.
      const headTurn = talkCueVisible
        ? Math.sin(tSec * 0.9 + i * 1.7) * 0.13 + (agent.renderFacingPartner ? 0.05 : 0)
        : agent.socialReaction
          ? Math.sin(tSec * 0.7 + i) * 0.05
          : Math.sin(tSec * 0.45 + i * 2.3) * 0.03
      const headHeading = agent.heading + headTurn
      setLocalPart(headRef.current, i, dummy, base, headHeading, [0, headY, 0.025 + human.postureLean], [0.205 * faceWidth, 0.225 * headScale, 0.205 * faceDepth], bodyRotX * 0.68, bodyRotZ)
      setLocalPart(hairRef.current, i, dummy, base, headHeading, [0, hairY, hairLong ? -0.055 : -0.02], shaved ? [0.16 * faceWidth, 0.035 * headScale, 0.17 * faceDepth] : [0.215 * faceWidth, hairCapHeight * headScale, 0.22 * faceDepth], bodyRotX * 0.68, bodyRotZ)
      setLocalPart(hairBackRef.current, i, dummy, base, headHeading, [0, hairBackY, hairLong ? -0.16 : -0.145], shaved ? [0.001, 0.001, 0.001] : [0.33 * faceWidth, (longHair ? 0.42 : bobHair ? 0.26 : 0.14) * headScale, 0.075 * faceDepth], bodyRotX * 0.64, bodyRotZ)
      setLocalPart(earRef.current, i * 2, dummy, base, headHeading, [-0.215 * faceWidth, 0.96 * height, 0.02], [0.03 * headScale, 0.042 * headScale, 0.02 * faceDepth])
      setLocalPart(earRef.current, i * 2 + 1, dummy, base, headHeading, [0.215 * faceWidth, 0.96 * height, 0.02], [0.03 * headScale, 0.042 * headScale, 0.02 * faceDepth])
      setLocalPart(eyeRef.current, i * 2, dummy, base, headHeading, [-0.086 * eyeSpacing, eyeY, 0.188 * faceDepth], [0.032 * faceWidth, 0.019, 0.012])
      setLocalPart(eyeRef.current, i * 2 + 1, dummy, base, headHeading, [0.086 * eyeSpacing, eyeY, 0.188 * faceDepth], [0.032 * faceWidth, 0.019, 0.012])
      setLocalPart(pupilRef.current, i * 2, dummy, base, headHeading, [-0.086 * eyeSpacing + saccade, eyeY + pupilY, 0.205 * faceDepth], [0.010, Math.max(0.002, 0.01 * (1 - blink * 0.86)), 0.006])
      setLocalPart(pupilRef.current, i * 2 + 1, dummy, base, headHeading, [0.086 * eyeSpacing + saccade, eyeY + pupilY, 0.205 * faceDepth], [0.010, Math.max(0.002, 0.01 * (1 - blink * 0.86)), 0.006])
      setLocalPart(eyelidRef.current, i * 2, dummy, base, headHeading, [-0.086 * eyeSpacing, eyeY + 0.004, 0.209 * faceDepth], [0.06 * faceWidth, Math.max(0.001, 0.038 * blink), 0.014])
      setLocalPart(eyelidRef.current, i * 2 + 1, dummy, base, headHeading, [0.086 * eyeSpacing, eyeY + 0.004, 0.209 * faceDepth], [0.06 * faceWidth, Math.max(0.001, 0.038 * blink), 0.014])
      setLocalPart(browRef.current, i * 2, dummy, base, headHeading, [-0.086 * eyeSpacing, browY, 0.2 * faceDepth], [0.058 * human.browWidth, 0.009, 0.011], 0, -0.08)
      setLocalPart(browRef.current, i * 2 + 1, dummy, base, headHeading, [0.086 * eyeSpacing, browY, 0.2 * faceDepth], [0.058 * human.browWidth, 0.009, 0.011], 0, 0.08)
      setLocalPart(noseRef.current, i, dummy, base, headHeading, [0, 0.94 * height, 0.215 * faceDepth], [0.026 * faceWidth, 0.052 * headScale, 0.026 * faceDepth])
      setLocalPart(mouthRef.current, i, dummy, base, headHeading, [0, mouthY, 0.202 * faceDepth], [0.088 * faceWidth, 0.012, 0.014])
      setLocalPart(faceMarkRef.current, i * 2, dummy, base, headHeading, [0, 0.915 * height, 0.222 * faceDepth], facialHair ? [0.12 * faceWidth, 0.018, 0.012] : [0.001, 0.001, 0.001])
      setLocalPart(faceMarkRef.current, i * 2 + 1, dummy, base, headHeading, [0, 1.025 * height, 0.21 * faceDepth], seniorFace ? [0.13 * faceWidth, 0.008, 0.01] : [0.001, 0.001, 0.001])
      setLocalPart(cheekRef.current, i * 2, dummy, base, headHeading, [-0.07 * eyeSpacing, 0.925 * height, 0.218 * faceDepth], [0.033 * faceWidth, 0.018, 0.011])
      setLocalPart(cheekRef.current, i * 2 + 1, dummy, base, headHeading, [0.07 * eyeSpacing, 0.925 * height, 0.218 * faceDepth], [0.033 * faceWidth, 0.018, 0.011])
      setLocalPart(glassesRef.current, i * 2, dummy, base, headHeading, [-0.086 * eyeSpacing, eyeY, 0.21 * faceDepth], glassesVisible ? [0.06 * faceWidth, 0.014, 0.014] : [0.001, 0.001, 0.001])
      setLocalPart(glassesRef.current, i * 2 + 1, dummy, base, headHeading, [0.086 * eyeSpacing, eyeY, 0.21 * faceDepth], glassesVisible ? [0.06 * faceWidth, 0.014, 0.014] : [0.001, 0.001, 0.001])
      setLocalPart(chestRef.current, i, dummy, base, agent.heading, [0, chestY + torsoBob, 0.18 * torsoDepth], [0.28 * chestWidth, 0.34 * height, 0.035 * torsoDepth], bodyRotX, bodyRotZ)
      setLocalPart(collarRef.current, i, dummy, base, agent.heading, [0, 0.75 * height, 0.205 * torsoDepth], [0.155 * chestWidth, 0.03 * height, 0.018], bodyRotX, bodyRotZ) // v2: narrower collar to match shoulders
      setLocalPart(lapelRef.current, i * 2, dummy, base, agent.heading, [-0.072 * chestWidth, 0.52 * height, 0.206 * torsoDepth], [0.035 * chestWidth, 0.2 * height, 0.015], bodyRotX, bodyRotZ - 0.16)
      setLocalPart(lapelRef.current, i * 2 + 1, dummy, base, agent.heading, [0.072 * chestWidth, 0.52 * height, 0.206 * torsoDepth], [0.035 * chestWidth, 0.2 * height, 0.015], bodyRotX, bodyRotZ + 0.16)
      setLocalPart(badgeRef.current, i, dummy, base, agent.heading, [0.105 * chestWidth, 0.58 * height, 0.222 * torsoDepth], [0.028, 0.038, 0.012], bodyRotX, bodyRotZ)
      setLocalPart(beltRef.current, i, dummy, base, agent.heading, [0, 0.15 * height, 0.158 * torsoDepth], [0.19 * waistWidth, 0.025, 0.032])
      setLocalPart(bagRef.current, i, dummy, base, agent.heading, [0.24 * shoulder, 0.38 * height, -0.13 * torsoDepth], bagVisible ? [0.1 * torsoDepth, 0.22 * height, 0.055 * torsoDepth] : [0.001, 0.001, 0.001])
      setLocalPart(backSeamRef.current, i, dummy, base, agent.heading, [0, 0.5 * height, -0.205 * torsoDepth], [0.014, 0.31 * height, 0.014], bodyRotX, bodyRotZ)
      setLocalPart(shoulderStrapRef.current, i * 2, dummy, base, agent.heading, [-0.12 * chestWidth, 0.5 * height, -0.215 * torsoDepth], bagVisible ? [0.03, 0.29 * height, 0.018] : [0.014, 0.22 * height, 0.014], bodyRotX, bodyRotZ - 0.08)
      setLocalPart(shoulderStrapRef.current, i * 2 + 1, dummy, base, agent.heading, [0.12 * chestWidth, 0.5 * height, -0.215 * torsoDepth], bagVisible ? [0.03, 0.29 * height, 0.018] : [0.014, 0.22 * height, 0.014], bodyRotX, bodyRotZ + 0.08)
      setLocalPart(hatRef.current, i, dummy, base, agent.heading, [0, 1.18 * height, 0.006], hatVisible ? [0.2 * faceWidth, 0.08, 0.2 * faceDepth] : [0.001, 0.001, 0.001])
      setLocalPart(skirtRef.current, i, dummy, base, agent.heading, [0, -0.05 * height, 0], skirtVisible ? [0.22 * hipWidth, 0.3 * height, 0.18 * torsoDepth] : [0.001, 0.001, 0.001])
      setLocalPart(scarfRef.current, i, dummy, base, agent.heading, [0, 0.75 * height, 0.15 * torsoDepth], scarfVisible ? [0.19 * chestWidth, look.scarfStyle === 'wide' ? 0.052 : 0.034, 0.044] : [0.001, 0.001, 0.001])
      if (articulated) {
        // Near / action LOD: two-segment forward-kinematics limbs so joints bend
        // at the knee and elbow instead of reading as a single swinging stick.
        const cosH = Math.cos(agent.heading)
        const sinH = Math.sin(agent.heading)
        const hipDX = 0.12 * stanceWidth
        const hipJy = -0.02 * height
        const thighLen = 0.33 * height * legScale
        const shinLen = 0.33 * height * legScale
        const legRad = 0.062 * legThickness
        const shinRad = 0.055 * legThickness
        const shLean = bodyRotX // shoulders ride with the torso lean
        const shDX = 0.2 * shoulder
        const shJy = 0.548 * height * Math.cos(shLean) // v2: shoulders ride a touch lower -> gentle slope
        const shJz = 0.56 * height * Math.sin(shLean) + 0.02 * torsoDepth
        const upperLen = 0.24 * height * human.armLength
        const foreLen = 0.24 * height * human.armLength
        const armRad = 0.052 * armThickness
        const foreRad = 0.046 * armThickness

        // left leg: hip -> knee -> ankle
        _boneV.set(0, -1, 0).applyAxisAngle(_XA, -thighL)
        const kLx = -hipDX + thighLen * _boneV.x
        const kLy = hipJy + thighLen * _boneV.y
        const kLz = thighLen * _boneV.z
        _boneV.applyAxisAngle(_XA, kneeL)
        const aLx = kLx + shinLen * _boneV.x
        const aLy = kLy + shinLen * _boneV.y
        const aLz = kLz + shinLen * _boneV.z
        localWorld(base, cosH, sinH, -hipDX, hipJy, 0, _jointA)
        localWorld(base, cosH, sinH, kLx, kLy, kLz, _jointB)
        localWorld(base, cosH, sinH, aLx, aLy, aLz, _jointC)
        setBone(legRef.current, i * 2, dummy, _jointA, _jointB, legRad)
        setBone(shinRef.current, i * 2, dummy, _jointB, _jointC, shinRad)
        const footPitchL = Math.max(-0.36, Math.min(0.55, (thighL - kneeL) * 0.4 + (walking ? Math.sin(phaseWalk + 0.6) * 0.26 : 0))) // v2: heel-toe roll through the gait
        setLocalPart(shoeRef.current, i * 2, dummy, base, agent.heading, [aLx, aLy, aLz + 0.05], [0.11 * human.footScale, 0.06, 0.18 * human.footScale], footPitchL)
        setLocalPart(cuffRef.current, i * 2, dummy, base, agent.heading, [aLx, aLy + 0.08 * height, aLz], [0.075 * legThickness, 0.03, 0.078 * legThickness], footPitchL)

        // right leg
        _boneV.set(0, -1, 0).applyAxisAngle(_XA, -thighR)
        const kRx = hipDX + thighLen * _boneV.x
        const kRy = hipJy + thighLen * _boneV.y
        const kRz = thighLen * _boneV.z
        _boneV.applyAxisAngle(_XA, kneeR)
        const aRx = kRx + shinLen * _boneV.x
        const aRy = kRy + shinLen * _boneV.y
        const aRz = kRz + shinLen * _boneV.z
        localWorld(base, cosH, sinH, hipDX, hipJy, 0, _jointA)
        localWorld(base, cosH, sinH, kRx, kRy, kRz, _jointB)
        localWorld(base, cosH, sinH, aRx, aRy, aRz, _jointC)
        setBone(legRef.current, i * 2 + 1, dummy, _jointA, _jointB, legRad)
        setBone(shinRef.current, i * 2 + 1, dummy, _jointB, _jointC, shinRad)
        const footPitchR = Math.max(-0.36, Math.min(0.55, (thighR - kneeR) * 0.4 + (walking ? Math.sin(phaseWalk + Math.PI + 0.6) * 0.26 : 0))) // v2: heel-toe roll through the gait
        setLocalPart(shoeRef.current, i * 2 + 1, dummy, base, agent.heading, [aRx, aRy, aRz + 0.05], [0.11 * human.footScale, 0.06, 0.18 * human.footScale], footPitchR)
        setLocalPart(cuffRef.current, i * 2 + 1, dummy, base, agent.heading, [aRx, aRy + 0.08 * height, aRz], [0.075 * legThickness, 0.03, 0.078 * legThickness], footPitchR)

        // left arm: shoulder -> elbow -> wrist
        _boneV.set(0, -1, 0).applyAxisAngle(_XA, -(shoulderL + shLean)).applyAxisAngle(_ZA, -latL)
        const eLx = -shDX + upperLen * _boneV.x
        const eLy = shJy + upperLen * _boneV.y
        const eLz = shJz + upperLen * _boneV.z
        _boneV.applyAxisAngle(_XA, -elbowL)
        const wLx = eLx + foreLen * _boneV.x
        const wLy = eLy + foreLen * _boneV.y
        const wLz = eLz + foreLen * _boneV.z
        localWorld(base, cosH, sinH, -shDX, shJy, shJz, _jointA)
        localWorld(base, cosH, sinH, eLx, eLy, eLz, _jointB)
        localWorld(base, cosH, sinH, wLx, wLy, wLz, _jointC)
        setBone(armRef.current, i * 2, dummy, _jointA, _jointB, armRad)
        setBone(forearmRef.current, i * 2, dummy, _jointB, _jointC, foreRad)
        setLocalPart(sleeveRef.current, i * 2, dummy, base, agent.heading, [-shDX, shJy, shJz], [0.075 * armThickness, 0.06 * height, 0.075 * armThickness])
        setLocalPart(handRef.current, i * 2, dummy, base, agent.heading, [wLx, wLy, wLz], [0.058 * human.handScale, 0.072 * human.handScale, 0.042 * human.handScale]) // v2: flattened mitten palm
        setLocalPart(thumbRef.current, i * 2, dummy, base, agent.heading, [wLx + 0.028, wLy + 0.01, wLz + 0.012], [0.028 * human.handScale, 0.05 * human.handScale, 0.03 * human.handScale])

        // right arm
        _boneV.set(0, -1, 0).applyAxisAngle(_XA, -(shoulderR + shLean)).applyAxisAngle(_ZA, latR)
        const eRx = shDX + upperLen * _boneV.x
        const eRy = shJy + upperLen * _boneV.y
        const eRz = shJz + upperLen * _boneV.z
        _boneV.applyAxisAngle(_XA, -elbowR)
        const wRx = eRx + foreLen * _boneV.x
        const wRy = eRy + foreLen * _boneV.y
        const wRz = eRz + foreLen * _boneV.z
        localWorld(base, cosH, sinH, shDX, shJy, shJz, _jointA)
        localWorld(base, cosH, sinH, eRx, eRy, eRz, _jointB)
        localWorld(base, cosH, sinH, wRx, wRy, wRz, _jointC)
        setBone(armRef.current, i * 2 + 1, dummy, _jointA, _jointB, armRad)
        setBone(forearmRef.current, i * 2 + 1, dummy, _jointB, _jointC, foreRad)
        setLocalPart(sleeveRef.current, i * 2 + 1, dummy, base, agent.heading, [shDX, shJy, shJz], [0.075 * armThickness, 0.06 * height, 0.075 * armThickness])
        setLocalPart(handRef.current, i * 2 + 1, dummy, base, agent.heading, [wRx, wRy, wRz], [0.058 * human.handScale, 0.072 * human.handScale, 0.042 * human.handScale]) // v2: flattened mitten palm
        setLocalPart(thumbRef.current, i * 2 + 1, dummy, base, agent.heading, [wRx - 0.028, wRy + 0.01, wRz + 0.012], [0.028 * human.handScale, 0.05 * human.handScale, 0.03 * human.handScale])
      } else {
        // Far LOD: original cheap single-capsule swing; the extra knee/elbow
        // segments are collapsed to zero so they stay hidden at distance.
        setLocalPart(legRef.current, i * 2, dummy, base, agent.heading, [-0.12 * stanceWidth, -0.35 * height, 0], [0.065 * legThickness, 0.1625 * height * legScale, 0.065 * legThickness], fallen ? 0.55 : stride, bodyRotZ * 0.35)
        setLocalPart(legRef.current, i * 2 + 1, dummy, base, agent.heading, [0.12 * stanceWidth, -0.35 * height, 0], [0.065 * legThickness, 0.1625 * height * legScale, 0.065 * legThickness], fallen ? -0.35 : -stride, bodyRotZ * 0.35)
        setLocalPart(armRef.current, i * 2, dummy, base, agent.heading, [-0.28 * shoulder, 0.33 * height + leftHandLift * 0.34, 0.02 * torsoDepth], [0.055 * armThickness, 0.1325 * height * human.armLength, 0.055 * armThickness], fallen ? 0.92 : talkCueVisible ? -0.28 - gesturePulse * 0.05 : -stride * 0.55 * armSwing, bodyRotZ)
        setLocalPart(armRef.current, i * 2 + 1, dummy, base, agent.heading, [0.28 * shoulder, 0.33 * height + rightHandLift * 0.34, 0.02 * torsoDepth], [0.055 * armThickness, 0.1325 * height * human.armLength, 0.055 * armThickness], fallen ? -0.72 : talkCueVisible ? 0.38 + gesturePulse * 0.08 : stride * 0.55 * armSwing, bodyRotZ)
        setLocalPart(sleeveRef.current, i * 2, dummy, base, agent.heading, [-0.27 * shoulder, shoulderY, 0.026 * torsoDepth], [0.065 * armThickness, 0.065 * height, 0.065 * armThickness], -stride * 0.38 * armSwing)
        setLocalPart(sleeveRef.current, i * 2 + 1, dummy, base, agent.heading, [0.27 * shoulder, shoulderY, 0.026 * torsoDepth], [0.065 * armThickness, 0.065 * height, 0.065 * armThickness], stride * 0.38 * armSwing)
        setLocalPart(handRef.current, i * 2, dummy, base, agent.heading, [-0.28 * shoulder, 0.08 * height + leftHandLift, 0.035 * torsoDepth], [0.06 * human.handScale, 0.074 * human.handScale, 0.044 * human.handScale])
        setLocalPart(thumbRef.current, i * 2, dummy, base, agent.heading, NPC_ZERO, NPC_HIDE)
        setLocalPart(handRef.current, i * 2 + 1, dummy, base, agent.heading, [0.28 * shoulder, 0.08 * height + rightHandLift, phoneVisible ? 0.16 : 0.035 * torsoDepth], [0.06 * human.handScale, 0.074 * human.handScale, 0.044 * human.handScale])
        setLocalPart(thumbRef.current, i * 2 + 1, dummy, base, agent.heading, NPC_ZERO, NPC_HIDE)
        setLocalPart(shoeRef.current, i * 2, dummy, base, agent.heading, [-0.12 * stanceWidth, -0.68 * height, 0.055], [0.11 * human.footScale, 0.06, 0.18 * human.footScale])
        setLocalPart(shoeRef.current, i * 2 + 1, dummy, base, agent.heading, [0.12 * stanceWidth, -0.68 * height, 0.055], [0.11 * human.footScale, 0.06, 0.18 * human.footScale])
        setLocalPart(cuffRef.current, i * 2, dummy, base, agent.heading, [-0.12 * stanceWidth, -0.58 * height, 0.046], [0.075 * legThickness, 0.026, 0.078 * legThickness], fallen ? 0.55 : stride, bodyRotZ * 0.35)
        setLocalPart(cuffRef.current, i * 2 + 1, dummy, base, agent.heading, [0.12 * stanceWidth, -0.58 * height, 0.046], [0.075 * legThickness, 0.026, 0.078 * legThickness], fallen ? -0.35 : -stride, bodyRotZ * 0.35)
        setLocalPart(shinRef.current, i * 2, dummy, base, agent.heading, NPC_ZERO, NPC_HIDE)
        setLocalPart(shinRef.current, i * 2 + 1, dummy, base, agent.heading, NPC_ZERO, NPC_HIDE)
        setLocalPart(forearmRef.current, i * 2, dummy, base, agent.heading, NPC_ZERO, NPC_HIDE)
        setLocalPart(forearmRef.current, i * 2 + 1, dummy, base, agent.heading, NPC_ZERO, NPC_HIDE)
      }
      setLocalPart(speechCueRef.current, i, dummy, base, agent.heading, [0, 1.47 * height + Math.max(0, gesturePulse) * 0.035, 0.08], talkCueVisible ? [0.13, 0.1, 0.13] : [0.001, 0.001, 0.001])
      setLocalPart(phoneRef.current, i, dummy, base, agent.heading, [0.34 * shoulder, 0.38 * height + rightHandLift, 0.2 * torsoDepth], phoneVisible ? [0.055, 0.105, 0.012] : [0.001, 0.001, 0.001])
      setLocalPart(gestureCueRef.current, i, dummy, base, agent.heading, [0.38 * shoulder, 0.56 * height + rightHandLift * 0.52, 0.18 * torsoDepth], talkCueVisible && !phoneVisible ? [0.045 + Math.max(0, gesturePulse) * 0.018, 0.045, 0.045] : [0.001, 0.001, 0.001])
      setLocalPart(mobilityDeckRef.current, i, dummy, base, agent.heading, [0, -0.7 * height + rideBob, 0.02], sharedMobilityVisible ? (ridingSharedBike ? [0.22, 0.035, 0.98] : [0.18, 0.035, 0.72]) : [0.001, 0.001, 0.001])
      setLocalPart(mobilityWheelRef.current, i * 2, dummy, base, agent.heading, [0, -0.73 * height + rideBob, rideFront], sharedMobilityVisible ? [wheelRadius, 0.045, wheelRadius] : [0.001, 0.001, 0.001], 0, Math.PI / 2)
      setLocalPart(mobilityWheelRef.current, i * 2 + 1, dummy, base, agent.heading, [0, -0.73 * height + rideBob, rideRear], sharedMobilityVisible ? [wheelRadius, 0.045, wheelRadius] : [0.001, 0.001, 0.001], 0, Math.PI / 2)
      setLocalPart(mobilityHandleRef.current, i, dummy, base, agent.heading, [0, -0.24 * height + rideBob, rideFront + 0.08], sharedMobilityVisible ? (ridingSharedBike ? [0.54, 0.035, 0.055] : [0.38, 0.035, 0.05]) : [0.001, 0.001, 0.001])
    }

    socialClock.current += dt
    statsClock.current += dt
    nearbyClock.current += dt
    cityEventClock.current += dt
    autonomyLlmClock.current += dt

    if (socialClock.current > 0.8) {
      socialClock.current = 0
      for (let tries = 0; tries < 18; tries += 1) {
        const a = agents[Math.floor(Math.random() * agents.length)]
        const b = agents[Math.floor(Math.random() * agents.length)]
        if (!a || !b || a === b || a.socialCooldown > 0 || b.socialCooldown > 0) continue
        if (a.pos.distanceTo(b.pos) > 4.4) continue
        const topic = conversationTopicFor(a, b, time)
        a.talk(5, b, topic, time)
        b.talk(5, a, topic, time)
        store.addCityEvent(conversationEventFor(a, b, topic, time))
        if (a.pos.distanceTo(player) < 45) store.setPulse(`${a.name} and ${b.name} discuss ${topic.label} near ${a.placeName}.`)
        break
      }
    }

    if (cityEventClock.current > 2.8) {
      cityEventClock.current = 0
      const index = Math.floor((state.clock.elapsedTime * 17 + time) % agents.length)
      const agent = agents[index]
      if (agent) {
        const event = autonomyEventFor(agent, time)
        agent.remember(event.kind, event.text, event.placeName, event.kind === 'need' ? 0.78 : 0.46)
        store.addCityEvent(event)
      }
    }

    if (
      autonomyLlmClock.current > 85 &&
      !autonomyLlmBusy.current &&
      !requestBusy.current &&
      typeof window !== 'undefined' &&
      !window.location.hostname.endsWith('.vercel.app')
    ) {
      autonomyLlmClock.current = 0
      const candidates = agents
        .filter(agent => !agent.mission && !agent.selfTaxi && agent.talkTimer <= 0 && agent.fallTimer <= 0)
        .map(agent => ({ agent, distance: agent.pos.distanceTo(player), pressure: Math.max(agent.needs?.hunger || 0, 1 - (agent.needs?.energy || 1), agent.needs?.social || 0) }))
        .filter(item => item.distance < 80 || item.pressure > 0.82)
        .sort((a, b) => (b.pressure - a.pressure) || (a.distance - b.distance))
      const selected = candidates.find(item => item.agent.id !== autonomyLlmLastAgent.current)?.agent || candidates[0]?.agent
      if (selected) void runAutonomyLlm(selected, 'ambient city autonomy')
    }

    if (statsClock.current > 1.25) {
      statsClock.current = 0
      store.setStats({ talks })
    }

    if (nearbyClock.current > 0.22) {
      nearbyClock.current = 0
      store.setPedestrianSamples(agents.map(agent => {
        const slot = scheduleFor(agent, time)
        return {
          sampleTimeMinutes: Number(time.toFixed(1)),
          scheduleTarget: slot?.target || null,
          scheduleActivity: slot?.activity || null,
          scheduleWindow: slot ? `${slot.start.toFixed(1)}-${slot.end.toFixed(1)}` : null,
          id: agent.id,
          name: agent.name,
          job: agent.job,
          role: agent.role,
          digitalHumanBase: DIGITAL_HUMAN_SOURCE.base,
          digitalHumanMorph: makeHumanStyleRig(agent, agentLook(agent)).summary,
          x: agent.pos.x,
          z: agent.pos.z,
          radius: 0.82,
          state: agent.fallTimer > 0 ? 'fallen' : agent.bumpTimer > 0 ? 'stumbling' : agent.activity,
          placeName: agent.placeName || null,
          socialReaction: agent.socialReaction || null,
          playerDistance: agent.playerDistance,
          facingPlayerAngle: agent.facingPlayerAngle,
          currentIntent: agent.currentIntent || null,
          llmAutonomyThought: agent.llmAutonomy?.thought || null,
          llmAutonomySource: agent.llmAutonomy?.source || null,
          llmAutonomyLatencyMs: agent.llmAutonomy?.latencyMs ?? null,
          llmAutonomyReason: agent.llmAutonomy?.reason || null,
          llmAutonomyAction: agent.llmAutonomy?.action || null,
          llmAutonomyExecuted: agent.llmAutonomy?.execution?.executed ?? null,
          llmAutonomyOutcome: agent.llmAutonomy?.execution?.outcome || null,
          llmAutonomyTargetName: agent.llmAutonomy?.execution?.targetName || agent.llmAutonomy?.targetName || null,
          llmAutonomyMobilityMode: agent.llmAutonomy?.mobilityMode || agent.llmAutonomy?.execution?.mobilityMode || null,
          llmAutonomyMobilitySource: agent.llmAutonomy?.mobilitySource || agent.llmAutonomy?.execution?.mobilitySource || null,
          llmAutonomyNearestDock: agent.llmAutonomy?.mobilityContext?.nearestDock?.name || null,
          autonomyGoal: agent.autonomy?.dailyGoal || null,
          relationshipStyle: agent.autonomy?.relationshipStyle || null,
          relationshipCount: agent.relationshipCount || 0,
          lastInteractionPartner: agent.lastInteraction?.partnerName || null,
          lastInteractionTopic: agent.lastInteraction?.topic || null,
          lastInteractionSource: agent.lastInteraction?.source || null,
          lastInteractionLine: agent.lastInteraction?.line || null,
          lastInteractionTrust: agent.lastInteraction?.trust ?? null,
          llmSocialSource: agent.lastLlmConversation?.source || null,
          llmSocialLine: agent.lastLlmConversation?.line || null,
          llmSocialPartnerName: agent.lastLlmConversation?.partnerName || null,
          llmSocialLatencyMs: agent.lastLlmConversation?.latencyMs ?? null,
          knownContacts: Object.values(agent.relationships || {}).slice(0, 3).map(contact => ({
            id: contact.agentId,
            name: contact.name,
            job: contact.job,
            trust: Number(contact.trust.toFixed(2)),
            talks: contact.talks,
            lastTopic: contact.lastTopic,
          })),
          memoryCount: agent.memories?.length || 0,
          lastMemory: agent.memories?.[0]?.text || null,
          cognitionArchitecture: agent.cognition?.architecture?.id || null,
          cognitionPolicy: agent.cognition?.selectedPolicy?.id || null,
          cognitionPolicyScore: agent.cognition?.selectedPolicy?.score ?? null,
          cognitionReflection: agent.cognition?.reflection?.text || null,
          cognitionRetrievedMemories: agent.cognition?.retrievedMemories?.length || 0,
          cognitionUtilityScores: (agent.cognition?.utilityScores || []).slice(0, 4).map(item => ({
            id: item.id,
            score: item.score,
          })),
          energy: agent.needs ? Number(agent.needs.energy.toFixed(2)) : null,
          hunger: agent.needs ? Number(agent.needs.hunger.toFixed(2)) : null,
          socialNeed: agent.needs ? Number(agent.needs.social.toFixed(2)) : null,
          strongestNeed: strongestNeedPhrase(agent),
          needErrandReason: agent.needErrand?.reason || null,
          needErrandLabel: agent.needErrand?.label || null,
          needErrandTargetName: agent.needErrand?.targetName || null,
          needErrandCognitiveReason: agent.needErrand?.cognitiveReason || null,
          needErrandCognitionPolicy: agent.needErrand?.cognitionPolicy || null,
          needErrandMobilityMode: agent.needErrand?.mobilityMode || null,
          needErrandMobilitySource: agent.needErrand?.mobilitySource || null,
          needErrandMobilityDockName: agent.needErrand?.mobilityDockName || null,
          sharedMobilityPhase: agent.needErrand?.sharedMobilityTrip?.phase || null,
          sharedMobilityPickupDockName: agent.needErrand?.sharedMobilityTrip?.pickupStationName || null,
          sharedMobilityReturnDockName: agent.needErrand?.sharedMobilityTrip?.returnStationName || null,
          sharedMobilityReturnSlotReserved: agent.needErrand?.sharedMobilityTrip?.returnSlotReserved ?? null,
          sharedMobilityPickupInventoryAfter: agent.needErrand?.sharedMobilityTrip?.pickupInventoryAfter || null,
          sharedMobilityReturnInventoryAfter: agent.needErrand?.sharedMobilityTrip?.returnInventoryAfter || null,
          sharedMobilityPickupProgress: agent.needErrand?.sharedMobilityTrip?.pickupAnimationProgress ?? null,
          sharedMobilityReturnProgress: agent.needErrand?.sharedMobilityTrip?.returnAnimationProgress ?? null,
          sharedMobilityRideProp: agent.needErrand?.sharedMobilityTrip?.phase === 'riding-to-return-dock' && isSharedMobilityMode(agent.needErrand?.mobilityMode) ? `${agent.needErrand.mobilityMode}-visible-prop` : null,
          sharedMobilityVisualSource: agent.needErrand?.mobilitySource || null,
          needErrandRemainingMinutes: agent.needErrand ? Number(errandMinutesRemaining(agent.needErrand, time).toFixed(1)) : null,
          targetName: agent.walkPlan?.targetName || agent.placeName || null,
          travelMode: agent.selfTaxi ? 'taxi' : agent.needErrand?.mobilityMode || 'walk',
          taxiPhase: agent.selfTaxi?.phase || null,
          taxiDriverName: agent.selfTaxi?.driverName || null,
          taxiTargetName: agent.selfTaxi?.targetName || null,
          taxiRouteMeters: agent.selfTaxi?.routeMeters ? Number(agent.selfTaxi.routeMeters.toFixed(1)) : null,
          routeStatus: agent.routeStatus || null,
          routeMode: agent.walkPlan?.mode || 'direct',
          crosswalkWaiting: !!agent.walkPlan?.crosswalkWaiting,
          crosswalkSignal: agent.walkPlan?.crosswalkSignal || null,
          crosswalkVehicleSignal: agent.walkPlan?.crosswalkVehicleSignal || null,
          crosswalkPhaseId: agent.walkPlan?.crosswalkPhaseId || null,
          crosswalkNoStart: agent.walkPlan?.crosswalkNoStart ?? null,
          crosswalkCountdown: agent.walkPlan?.crosswalkCountdown ?? null,
          crosswalkProgram: agent.walkPlan?.crosswalkProgram || null,
          crosswalkControl: agent.walkPlan?.crosswalkControl || null,
          crosswalkPriorityRule: agent.walkPlan?.crosswalkPriorityRule || null,
          crosswalkGapClear: agent.walkPlan?.crosswalkGapClear ?? null,
          crosswalkGapSeconds: agent.walkPlan?.crosswalkGapSeconds ?? null,
          crosswalkNearestVehicleId: agent.walkPlan?.crosswalkNearestVehicleId || null,
          crosswalkLaneHold: !!agent.walkPlan?.crosswalkLaneHold,
          crosswalkCorridorMeters: agent.walkPlan?.crosswalkCorridorMeters ?? null,
          crosswalkWaitSeconds: Number((agent.crosswalkWaitTimer || 0).toFixed(2)),
          routeRoadId: agent.walkPlan?.roadId || null,
          routeRoadName: agent.walkPlan?.roadName || null,
          routeRoadAxis: agent.walkPlan?.roadAxis || null,
          stableRoute: !!agent.walkPlan?.stableRoute,
          routeIndex: agent.walkPlan?.routeIndex ?? null,
          routePoints: agent.walkPlan?.routePoints ?? null,
          replanCount: agent.walkPlan?.replanCount ?? 0,
          blockedContacts: agent.blockedContacts || 0,
          waypointName: agent.walkPlan?.waypointName || null,
          waypointX: agent.walkPlan?.waypoint?.x ?? null,
          waypointZ: agent.walkPlan?.waypoint?.z ?? null,
          crosswalkX: agent.walkPlan?.crosswalk?.x ?? null,
          crosswalkZ: agent.walkPlan?.crosswalk?.z ?? null,
          distanceToTarget: agent.walkPlan?.distanceToTarget ? Number(agent.walkPlan.distanceToTarget.toFixed(2)) : null,
          distanceToWaypoint: agent.walkPlan?.distanceToWaypoint ? Number(agent.walkPlan.distanceToWaypoint.toFixed(2)) : null,
          talkPartnerId: agent.talkPartnerId || null,
          talkPartnerName: agent.talkPartnerName || null,
          talkTopicLabel: agent.talkTopicLabel || null,
          talkLine: agent.talkLine || null,
          talkSource: agent.talkSource || null,
          visualGesture: agent.visualGesture || null,
          renderFacingPartner: !!agent.renderFacingPartner,
          facingPartnerAngle: agent.facingPartnerAngle,
          sharedHumanoidBase: DIGITAL_HUMAN_SOURCE.base,
        }
      }))
      store.setNearbyAgent(nearestAgent && nearestDistance <= 24
        ? { ...nearestAgent.snapshot(places), distance: nearestDistance }
        : null)
      if (typeof window !== 'undefined') {
        const cognitionSamples = agents.slice(0, 18).map(agent => ({
          id: agent.id,
          name: agent.name,
          policy: agent.cognition?.selectedPolicy?.id || null,
          policyScore: agent.cognition?.selectedPolicy?.score ?? null,
          reflection: agent.cognition?.reflection?.text || null,
          retrievedMemories: agent.cognition?.retrievedMemories?.length || 0,
          utilityScores: (agent.cognition?.utilityScores || []).slice(0, 4).map(item => ({ id: item.id, score: item.score })),
          contract: agent.cognition?.executionContract || null,
        }))
        window.__REALCITY_NPC_COGNITION__ = {
          architectureId: NPC_COGNITION_ARCHITECTURE.id,
          modules: NPC_COGNITION_ARCHITECTURE.modules,
          researchBasis: NPC_COGNITION_ARCHITECTURE.researchBasis,
          agentCount: agents.length,
          sampledAgents: cognitionSamples.length,
          samplesWithReflection: cognitionSamples.filter(sample => sample.reflection).length,
          samplesWithRetrievedMemories: cognitionSamples.filter(sample => sample.retrievedMemories > 0).length,
          policyKinds: [...new Set(cognitionSamples.map(sample => sample.policy).filter(Boolean))],
          executionContract: cognitionSamples.find(sample => sample.contract)?.contract || null,
          sourceNote: 'Derived from intelligent NPC article themes plus generative-agent, LLM game-agent, GOBT, navigation, norm, and steering research.',
        }
      }
    }

    hipsRef.current.instanceMatrix.needsUpdate = true
    torsoRef.current.instanceMatrix.needsUpdate = true
    neckRef.current.instanceMatrix.needsUpdate = true
    headRef.current.instanceMatrix.needsUpdate = true
    hairRef.current.instanceMatrix.needsUpdate = true
    hairBackRef.current.instanceMatrix.needsUpdate = true
    faceMarkRef.current.instanceMatrix.needsUpdate = true
    cheekRef.current.instanceMatrix.needsUpdate = true
    eyeRef.current.instanceMatrix.needsUpdate = true
    pupilRef.current.instanceMatrix.needsUpdate = true
    eyelidRef.current.instanceMatrix.needsUpdate = true
    browRef.current.instanceMatrix.needsUpdate = true
    noseRef.current.instanceMatrix.needsUpdate = true
    mouthRef.current.instanceMatrix.needsUpdate = true
    chestRef.current.instanceMatrix.needsUpdate = true
    collarRef.current.instanceMatrix.needsUpdate = true
    lapelRef.current.instanceMatrix.needsUpdate = true
    badgeRef.current.instanceMatrix.needsUpdate = true
    beltRef.current.instanceMatrix.needsUpdate = true
    cuffRef.current.instanceMatrix.needsUpdate = true
    bagRef.current.instanceMatrix.needsUpdate = true
    backSeamRef.current.instanceMatrix.needsUpdate = true
    shoulderStrapRef.current.instanceMatrix.needsUpdate = true
    handRef.current.instanceMatrix.needsUpdate = true
    thumbRef.current.instanceMatrix.needsUpdate = true
    earRef.current.instanceMatrix.needsUpdate = true
    hatRef.current.instanceMatrix.needsUpdate = true
    skirtRef.current.instanceMatrix.needsUpdate = true
    glassesRef.current.instanceMatrix.needsUpdate = true
    scarfRef.current.instanceMatrix.needsUpdate = true
    speechCueRef.current.instanceMatrix.needsUpdate = true
    phoneRef.current.instanceMatrix.needsUpdate = true
    gestureCueRef.current.instanceMatrix.needsUpdate = true
    mobilityDeckRef.current.instanceMatrix.needsUpdate = true
    mobilityWheelRef.current.instanceMatrix.needsUpdate = true
    mobilityHandleRef.current.instanceMatrix.needsUpdate = true
    legRef.current.instanceMatrix.needsUpdate = true
    armRef.current.instanceMatrix.needsUpdate = true
    sleeveRef.current.instanceMatrix.needsUpdate = true
    shinRef.current.instanceMatrix.needsUpdate = true
    forearmRef.current.instanceMatrix.needsUpdate = true
    shoeRef.current.instanceMatrix.needsUpdate = true
  })

  useEffect(() => {
    const onKey = async (event) => {
      if (event.target?.closest?.('input, textarea, select, button')) return
      if (event.code !== 'KeyE' || busy.current) return
      const store = useCityStore.getState()
      const player = new THREE.Vector3(store.player.x, store.player.y, store.player.z)
      let best = null
      let bestDistance = Infinity
      for (const agent of agents) {
        const distance = agent.pos.distanceTo(player)
        if (distance < bestDistance) {
          best = agent
          bestDistance = distance
        }
      }
      if (!best || bestDistance > 24 || best.playerCooldown > 0) {
        store.setPulse('No one is close enough to talk. Move nearer to a pedestrian and press E.')
        return
      }

      busy.current = true
      best.talk(6)
      best.playerCooldown = 2.2
      const agent = best.snapshot(places)
      store.openInteraction(agent)
      store.showDialogue({
        speaker: best.name,
        role: best.job,
        text: styleNpcSpeech(best, '말씀하세요. 제가 가능한 일인지 판단하고 같이 움직일게요.'),
        agent,
      })
      store.showDialogue({
        speaker: best.name,
        role: best.job,
        text: styleNpcSpeech(best, '로컬 LLM과 이 사람의 기억, 일정, 현재 거리 상황을 확인하는 중입니다. 잠시만요.'),
        agent,
      })
      window.setTimeout(() => {
        const beforeGreeting = useCityStore.getState()
        if (beforeGreeting.interaction?.agent?.id !== best.id || beforeGreeting.interaction?.status !== 'open') return
        void askLocalNPC(agent, `Day ${store.day}, ${formatTime(store.timeMinutes)}. Player district: ${store.player.district}. Player is ${Math.round(bestDistance)}m away.`)
          .then(line => {
            const latest = useCityStore.getState()
            const runtime = typeof window !== 'undefined' ? window.__REALCITY_LLM__ : null
            const spoken = line || fallbackLine(best)
            if (latest.focusedAgent?.id !== best.id && latest.interaction?.agent?.id !== best.id) return
            best.remember(runtime?.lastSource === 'local-llm' ? 'llm-greeting' : 'fallback-greeting', spoken, best.placeName, runtime?.lastSource === 'local-llm' ? 0.72 : 0.46)
            latest.addCityEvent({
              id: `llm_greeting_${best.id}_${Date.now()}`,
              kind: runtime?.lastSource === 'local-llm' ? 'llm' : 'dialogue',
              agentId: best.id,
              agentName: best.name,
              placeName: best.placeName,
              topic: runtime?.lastSource === 'local-llm' ? 'local LLM greeting' : 'fallback greeting',
              text: runtime?.lastSource === 'local-llm'
                ? `${best.name} answers through local ${runtime.provider}:${runtime.model}: ${spoken}`.slice(0, 180)
                : `${best.name} answers from fallback dialogue because local LLM was unavailable: ${spoken}`.slice(0, 180),
            })
            latest.showDialogue({ speaker: best.name, role: best.job, text: spoken, agent: best.snapshot(places) })
          })
      }, 900)
      window.setTimeout(() => { busy.current = false }, 450)
    }

    const onNpcRequest = async (event) => {
      if (requestBusy.current) return
      const { agentId, text } = event.detail || {}
      const request = String(text || '').trim()
      if (!agentId || !request) return
      const best = agents.find(agent => agent.id === agentId)
      if (!best) return

      requestBusy.current = true
      const store = useCityStore.getState()
      const work = places.get(best.workId)
      const cityPlaces = routePlacesForRequest(request, city, store.player)
      const distanceToWork = work ? Math.hypot(work.x - store.player.x, work.z - store.player.z) : 0
      const snapshot = best.snapshot(places)
      if (!store.interaction || store.interaction.agent?.id !== best.id) {
        store.openInteraction(snapshot)
      }
      store.setInteraction({ status: 'thinking', request })
      store.showDialogue({ speaker: best.name, role: best.job, text: styleNpcSpeech(best, '잠깐 생각해볼게요...'), agent: snapshot })

      const plan = await planLocalNPCAction(snapshot, request, {
        distanceToWork,
        timeLabel: `Day ${store.day}, ${formatTime(store.timeMinutes)}`,
        playerDistrict: store.player.district,
        player: { x: store.player.x, z: store.player.z },
        places: cityPlaces,
      })
      best.remember('player-request', `Player asked: ${request}. ${plan.offer || plan.reasoning || plan.intent}.`, best.placeName, 0.84)
      store.addCityEvent({
        id: `request_${best.id}_${Date.now()}`,
        kind: 'request',
        agentId: best.id,
        agentName: best.name,
        placeName: best.placeName,
        topic: plan.reasoning || plan.intent,
        text: `${best.name} considers the player's request: ${plan.offer || plan.intent}. ${plan.safety || ''}`.slice(0, 180),
      })
      const updatedSnapshot = best.snapshot(places)

      if (plan.decision !== 'accept' || plan.mode === 'talk') {
        store.setInteraction({ status: 'done', plan })
        store.showDialogue({ speaker: best.name, role: best.job, text: plan.speech || fallbackLine(best), agent: updatedSnapshot })
        window.setTimeout(() => { requestBusy.current = false }, 700)
        return
      }

      const destination = destinationFromPlan(plan, best, places, request, destinations)
      const destinationTarget = entranceTargetFor(destination, city.roads, best.offset)
      const distance = Math.hypot(destinationTarget.x - store.player.x, destinationTarget.z - store.player.z)
      const mode = plan.mode === 'taxi' || distance > 420 ? 'taxi' : 'walk'
      const mission = {
        id: `${best.id}_${Date.now()}`,
        agentId: best.id,
        agentName: best.name,
        mode,
        phase: mode === 'taxi' ? 'to_pickup' : 'leading',
        source: plan.source,
        destination: destinationTarget,
        pickup: nearestRoadPickup(best.pos, city.roads),
        steps: plan.steps,
        reasoning: plan.reasoning,
        safety: plan.safety,
        offer: plan.offer,
        urgency: plan.urgency,
        llm: plan.llm,
        request,
      }

      best.needErrand = null
      best.needErrandCooldown = 18
      best.mission = mission
      best.talk(2.4)
      store.setInteraction({ status: 'active', plan })
      store.startMission({
        id: mission.id,
        agentId: best.id,
        agentName: best.name,
        mode,
        phase: mission.phase,
        destination: destinationTarget,
        pickup: mission.pickup,
        steps: plan.steps,
        reasoning: plan.reasoning,
        safety: plan.safety,
        offer: plan.offer,
        urgency: plan.urgency,
        llm: plan.llm,
        request,
        source: plan.source,
        summary: plan.speech,
      })
      if (mode === 'taxi') {
        beginTaxiDispatch(best, mission, store, city)
      }
      store.showDialogue({ speaker: best.name, role: best.job, text: plan.speech, agent: updatedSnapshot })
      window.setTimeout(() => { requestBusy.current = false }, 700)
    }

    const onNpcHit = (event) => {
      const { id, playerX, playerZ, impulse } = event.detail || {}
      if (!id) return
      const agent = agents.find(item => item.id === id)
      if (!agent) return
      agent.bumpFrom(playerX ?? agent.pos.x, playerZ ?? agent.pos.z, impulse)
      const store = useCityStore.getState()
      const distanceToPlayer = Math.hypot(agent.pos.x - store.player.x, agent.pos.z - store.player.z)
      if (distanceToPlayer < 18) {
        store.setPulse(impulse > 1.02
          ? `${agent.name} is knocked down and starts getting back up.`
          : `${agent.name} stumbles and steps back after the collision.`)
      }
    }

    const onTaxiBoardRequested = (event) => {
      const { missionId } = event.detail || {}
      if (!missionId) return
      const agent = agents.find(item => item.mission?.id === missionId)
      if (agent?.mission) {
        const storeMission = useCityStore.getState().mission
        agent.mission.boardingRequested = true
        agent.mission.phase = storeMission?.phase || 'taxi_boarding'
        agent.mission.boardingStartedAt = storeMission?.boardingStartedAt || performance.now()
        agent.mission.boardingPlayerStart = storeMission?.boardingPlayerStart || null
      }
    }

    const debugPlaceNpc = (detail = {}) => {
      if (!import.meta.env.DEV) return false
      const agent = agents.find(item => item.id === detail.id)
      const x = Number(detail.x)
      const z = Number(detail.z)
      if (!agent || !Number.isFinite(x) || !Number.isFinite(z)) return false
      agent.pos.set(x, terrainHeight(x, z) + 0.95, z)
      agent.heading = Number.isFinite(Number(detail.heading)) ? Number(detail.heading) : agent.heading
      agent.walkRoute = null
      agent.walkPlan = null
      agent.crosswalkWaitTimer = 0
      agent.lastCrosswalkWaitAt = 0
      agent.mission = null
      agent.selfTaxi = null
      agent.boardingTaxi = null
      agent.needErrand = null
      agent.needErrandCooldown = 0
      agent.stuckTimer = 0
      agent.blockedContacts = 0
      agent.bumpTimer = 0
      agent.fallTimer = 0
      agent.bumpVelocity.set(0, 0)
      agent.activity = detail.activity || 'available for directions'
      agent.placeName = detail.placeName || 'verification sidewalk'
      agent.currentIntent = 'ready to guide the player on foot'
      agent.talkTimer = Number.isFinite(Number(detail.talkSeconds)) ? Math.max(0, Number(detail.talkSeconds)) : 0
      agent.talkPartnerId = null
      agent.talkPartnerName = null
      agent.talkTopicLabel = null
      agent.talkLine = null
      agent.talkSource = null
      agent.visualGesture = agent.talkTimer > 0 ? socialGestureKind(agent) : null
      agent.renderFacingPartner = false
      agent.facingPartnerAngle = null
      agent.debugSocialConversation = false
      agent.glanceCooldown = 0
      agent.debugSpeedScale = Number.isFinite(Number(detail.speedScale)) ? Math.max(1, Number(detail.speedScale)) : 1
      return true
    }

    const debugNeedErrand = (detail = {}) => {
      if (!import.meta.env.DEV) return false
      const store = useCityStore.getState()
      const agent = agents.find(item => item.id === detail.id) || agents[0]
      if (!agent) return false
      agent.mission = null
      agent.selfTaxi = null
      agent.boardingTaxi = null
      agent.walkRoute = null
      agent.walkPlan = null
      agent.crosswalkWaitTimer = 0
      agent.lastCrosswalkWaitAt = 0
      agent.needErrand = null
      agent.needErrandCooldown = 0
      agent.needs.hunger = Number.isFinite(Number(detail.hunger)) ? clampValue(Number(detail.hunger), 0, 1) : 0.91
      agent.needs.energy = Number.isFinite(Number(detail.energy)) ? clampValue(Number(detail.energy), 0, 1) : Math.max(agent.needs.energy, 0.44)
      agent.needs.social = Number.isFinite(Number(detail.social)) ? clampValue(Number(detail.social), 0, 1) : Math.max(agent.needs.social, 0.4)
      agent.needs.urgency = Number.isFinite(Number(detail.urgency)) ? clampValue(Number(detail.urgency), 0, 1) : agent.needs.urgency
      const profile = needErrandProfile(agent) || {
        reason: 'hunger',
        label: 'food break',
        activity: 'getting food',
        targetKinds: ['cafe', 'retail'],
        memory: 'I need a visible debug food break.',
      }
      const started = agent.startNeedErrand(profile, places, store.timeMinutes, true)
      return started ? {
        id: agent.id,
        name: agent.name,
        reason: agent.needErrand.reason,
        targetName: agent.needErrand.targetName,
      } : false
    }

    const debugCrosswalkWait = (detail = {}) => {
      if (!import.meta.env.DEV) return false
      const store = useCityStore.getState()
      const agent = agents.find(item => item.id === detail.id) || agents[0]
      const road = city.roads.find(item => item.id === detail.roadId) ||
        city.roads.find(item => item.main && item.axis === (detail.axis || 'x')) ||
        city.roads.find(item => item.main) ||
        city.roads[0]
      if (!agent || !road) return false
      const cross = city.roads.find(item => item.axis !== road.axis && item.main) ||
        city.roads.find(item => item.axis !== road.axis)
      if (!cross) return false
      const side = Number(detail.side) === -1 ? -1 : 1
      const curb = road.width / 2 + 4.2
      const approach = road.axis === 'x'
        ? { x: clampValue(cross.x, road.from + 6, road.to - 6), z: road.z + side * curb, name: `${road.name} crosswalk approach` }
        : { x: road.x + side * curb, z: clampValue(cross.z, road.from + 6, road.to - 6), name: `${road.name} crosswalk approach` }
      const exit = road.axis === 'x'
        ? { x: approach.x, z: road.z - side * curb, name: `${road.name} crosswalk exit` }
        : { x: road.x - side * curb, z: approach.z, name: `${road.name} crosswalk exit` }
      const [ax, az] = resolveBuildingCollision(city, approach.x, approach.z, approach.x, approach.z, 0.68)
      const destination = {
        ...exit,
        y: terrainHeight(exit.x, exit.z),
        entryRule: 'crosswalk-signal-test',
      }
      agent.pos.set(ax, terrainHeight(ax, az) + 0.95, az)
      agent.heading = Math.atan2(exit.x - approach.x, exit.z - approach.z)
      agent.mission = {
        id: `debug_crosswalk_${Date.now()}`,
        mode: 'walk',
        phase: 'leading',
        destination,
        request: 'Debug crosswalk signal compliance',
      }
      agent.selfTaxi = null
      agent.boardingTaxi = null
      agent.taxiCooldown = 0
      agent.walkRoute = {
        targetKey: walkTargetKey(destination),
        targetName: destination.name,
        activity: 'debug crosswalk signal compliance',
        waypoints: [routePoint(destination, 'crosswalk-crossing', {
          roadId: road.id,
          roadName: road.name,
          roadAxis: road.axis,
          name: destination.name,
          crosswalk: road.axis === 'x' ? { x: exit.x, z: road.z } : { x: road.x, z: exit.z },
          crossingControl: 'traffic-light',
          crossingPriorityRule: 'SUMO tlLogic protected WALK debug crossing',
          crossingGapSeconds: 0,
          crossingSource: 'Eclipse SUMO Traffic_Lights',
        })],
        index: 0,
        createdAt: nowMs(),
        replanCount: 0,
        final: { x: destination.x, z: destination.z },
      }
      agent.walkPlan = null
      agent.crosswalkWaitTimer = 0
      agent.lastCrosswalkWaitAt = 0
      agent.bumpTimer = 0
      agent.fallTimer = 0
      agent.bumpVelocity.set(0, 0)
      agent.needErrand = null
      agent.needErrandCooldown = 0
      agent.talkTimer = 0
      agent.talkPartnerId = null
      agent.talkPartnerName = null
      agent.talkTopicLabel = null
      agent.talkLine = null
      agent.talkSource = null
      agent.visualGesture = null
      agent.renderFacingPartner = false
      agent.facingPartnerAngle = null
      agent.debugSocialConversation = false
      agent.glanceCooldown = 0
      agent.debugSpeedScale = Number.isFinite(Number(detail.speedScale)) ? Math.max(1, Number(detail.speedScale)) : 1
      agent.activity = 'approaching crosswalk signal'
      agent.placeName = road.name
      agent.currentIntent = `waiting to cross ${road.name} by signal`
      store.addCityEvent({
        id: `debug_crosswalk_setup_${agent.id}_${Date.now()}`,
        kind: 'crosswalk',
        agentId: agent.id,
        agentName: agent.name,
        placeName: road.name,
        topic: 'signal compliance setup',
        text: `${agent.name} approaches ${road.name} crosswalk and checks the signal before entering the lane.`,
      })
      return {
        id: agent.id,
        name: agent.name,
        roadId: road.id,
        roadName: road.name,
        roadAxis: road.axis,
        roadWidth: road.width,
        roadCenter: road.axis === 'x' ? road.z : road.x,
        approach: { ...approach, x: ax, z: az },
        exit: destination,
      }
    }

    const debugSocialPair = (detail = {}) => {
      if (!import.meta.env.DEV) return false
      const store = useCityStore.getState()
      const first = agents.find(item => item.id === detail.aId) || agents[0]
      const second = agents.find(item => item.id === detail.bId && item !== first) || agents.find(item => item !== first)
      if (!first || !second) return false
      const spacing = Number.isFinite(Number(detail.spacing)) ? clampValue(Number(detail.spacing), 1.8, 4.6) : 2.8
      const center = pedestrianSafeTarget({
        x: Number.isFinite(Number(detail.x)) ? Number(detail.x) : 8,
        z: Number.isFinite(Number(detail.z)) ? Number(detail.z) : 40,
        y: 0,
        name: 'debug social sidewalk',
      }, { x: 8, z: 40 }, city.roads)
      const aSpot = pedestrianSafeTarget({ x: center.x - spacing / 2, z: center.z, y: 0, name: center.name }, center, city.roads)
      const bSpot = pedestrianSafeTarget({ x: center.x + spacing / 2, z: center.z, y: 0, name: center.name }, center, city.roads)
      const [ax, az] = resolveBuildingCollision(city, aSpot.x, aSpot.z, aSpot.x, aSpot.z, 0.68)
      const [bx, bz] = resolveBuildingCollision(city, bSpot.x, bSpot.z, bSpot.x, bSpot.z, 0.68)
      first.pos.set(ax, terrainHeight(ax, az) + 0.95, az)
      second.pos.set(bx, terrainHeight(bx, bz) + 0.95, bz)
      first.heading = Math.atan2(second.pos.x - first.pos.x, second.pos.z - first.pos.z)
      second.heading = Math.atan2(first.pos.x - second.pos.x, first.pos.z - second.pos.z)
      for (const agent of [first, second]) {
        agent.mission = null
        agent.selfTaxi = null
        agent.boardingTaxi = null
        agent.walkRoute = null
        agent.walkPlan = { mode: 'dwelling', targetName: 'verification sidewalk', waypointName: 'conversation spot', stableRoute: true, routePoints: 1 }
        agent.crosswalkWaitTimer = 0
        agent.lastCrosswalkWaitAt = 0
        agent.activity = 'talking on the sidewalk'
        agent.placeName = 'verification sidewalk'
        agent.bumpTimer = 0
        agent.fallTimer = 0
        agent.bumpVelocity.set(0, 0)
        agent.debugSocialConversation = true
      }
      const topic = conversationTopicFor(first, second, store.timeMinutes)
      const seconds = Number.isFinite(Number(detail.seconds)) ? clampValue(Number(detail.seconds), 3, 20) : 8
      first.talk(seconds, second, topic, store.timeMinutes)
      second.talk(seconds, first, topic, store.timeMinutes)
      store.addCityEvent(conversationEventFor(first, second, topic, store.timeMinutes, `debug_social_${Date.now()}`))
      return {
        aId: first.id,
        bId: second.id,
        topic: topic.label,
      }
    }

    const debugLlmSocialPair = async (detail = {}) => {
      if (!import.meta.env.DEV) return false
      const setup = debugSocialPair({
        ...detail,
        seconds: Number.isFinite(Number(detail.seconds)) ? detail.seconds : 12,
      })
      if (!setup) return false
      const first = agentsById.get(setup.aId)
      const second = agentsById.get(setup.bId)
      if (!first || !second) return false
      return runLlmSocialConversation(
        first,
        second,
        detail.reason || 'debug local LLM NPC social conversation',
        Number.isFinite(Number(detail.seconds)) ? Number(detail.seconds) : 12,
      )
    }

    const debugLlmAutonomy = async (detail = {}) => {
      if (!import.meta.env.DEV) return false
      const agent = agents.find(item => item.id === detail.id) ||
        agents.find(item => !item.mission && !item.selfTaxi) ||
        agents[0]
      if (!agent) return false
      return runAutonomyLlm(agent, detail.reason || 'debug forced autonomy', {
        forceAction: detail.forceAction,
        forceTargetPlaceId: detail.forceTargetPlaceId,
        forceTargetPlaceName: detail.forceTargetPlaceName,
        forceTargetKind: detail.forceTargetKind,
      })
    }

    const debugAdvanceSharedMobility = (detail = {}) => {
      if (!import.meta.env.DEV) return false
      const store = useCityStore.getState()
      const agent = agents.find(item => item.id === detail.id) || agents.find(item => item.needErrand?.sharedMobilityTrip)
      const trip = agent?.needErrand?.sharedMobilityTrip
      if (!agent || !trip) return false
      let ridePropDuringRide = trip.phase === 'riding-to-return-dock' ? `${trip.mode}-visible-prop` : null
      const pickup = sharedMobilityTripPoint(trip, 'pickup', 'debug pickup')
      const returnDock = sharedMobilityTripPoint(trip, 'return', 'debug return')
      if (pickup && trip.phase === 'walking-to-dock') {
        agent.pos.set(pickup.x, terrainHeight(pickup.x, pickup.z) + 0.95, pickup.z)
        agent.updateSharedMobilityTrip(0.2, store.timeMinutes, places, city)
      }
      if (trip.phase === 'pickup') {
        trip.phaseStartedAt = performance.now() - (trip.pickupAnimationSeconds + 0.2) * 1000
        agent.updateSharedMobilityTrip(0.2, store.timeMinutes, places, city)
        if (trip.phase === 'riding-to-return-dock') ridePropDuringRide = `${trip.mode}-visible-prop`
      }
      if (returnDock && trip.phase === 'riding-to-return-dock') {
        agent.pos.set(returnDock.x, terrainHeight(returnDock.x, returnDock.z) + 0.95, returnDock.z)
        agent.updateSharedMobilityTrip(0.2, store.timeMinutes, places, city)
      }
      if (trip.phase === 'return') {
        trip.phaseStartedAt = performance.now() - (trip.returnAnimationSeconds + 0.2) * 1000
        agent.updateSharedMobilityTrip(0.2, store.timeMinutes, places, city)
      }
      return {
        agentId: agent.id,
        agentName: agent.name,
        mode: trip.mode,
        phase: trip.phase,
        pickupStationName: trip.pickupStationName,
        returnStationName: trip.returnStationName,
        returnSlotReserved: trip.returnSlotReserved,
        pickupInventoryAfter: trip.pickupInventoryAfter,
        returnInventoryAfter: trip.returnInventoryAfter,
        pickupAnimationProgress: trip.pickupAnimationProgress,
        returnAnimationProgress: trip.returnAnimationProgress,
        ridePropDuringRide,
      }
    }
    const onDebugPlaceNpc = event => debugPlaceNpc(event.detail || {})
    const onDebugSocialPair = event => debugSocialPair(event.detail || {})
    const onDebugNeedErrand = event => debugNeedErrand(event.detail || {})
    const onDebugCrosswalkWait = event => debugCrosswalkWait(event.detail || {})
    const onDebugLlmSocial = event => { void debugLlmSocialPair(event.detail || {}) }
    const onDebugLlmAutonomy = event => { void debugLlmAutonomy(event.detail || {}) }

    if (import.meta.env.DEV && typeof window !== 'undefined') {
      window.__REALCITY_NPC_DEBUG__ = {
        placeNpc: debugPlaceNpc,
        startConversation: debugSocialPair,
        startNeedErrand: debugNeedErrand,
        startCrosswalkWait: debugCrosswalkWait,
        runLlmConversation: debugLlmSocialPair,
        runLlmAutonomy: debugLlmAutonomy,
        advanceSharedMobilityTrip: debugAdvanceSharedMobility,
      }
      window.addEventListener('realcity:debug-place-npc', onDebugPlaceNpc)
      window.addEventListener('realcity:debug-social-pair', onDebugSocialPair)
      window.addEventListener('realcity:debug-need-errand', onDebugNeedErrand)
      window.addEventListener('realcity:debug-crosswalk-wait', onDebugCrosswalkWait)
      window.addEventListener('realcity:debug-llm-social', onDebugLlmSocial)
      window.addEventListener('realcity:debug-llm-autonomy', onDebugLlmAutonomy)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('realcity:npc-request', onNpcRequest)
    window.addEventListener('realcity:player-hit-npc', onNpcHit)
    window.addEventListener('realcity:taxi-board-requested', onTaxiBoardRequested)
    return () => {
      if (import.meta.env.DEV && typeof window !== 'undefined') {
        window.removeEventListener('realcity:debug-place-npc', onDebugPlaceNpc)
        window.removeEventListener('realcity:debug-social-pair', onDebugSocialPair)
        window.removeEventListener('realcity:debug-need-errand', onDebugNeedErrand)
        window.removeEventListener('realcity:debug-crosswalk-wait', onDebugCrosswalkWait)
        window.removeEventListener('realcity:debug-llm-social', onDebugLlmSocial)
        window.removeEventListener('realcity:debug-llm-autonomy', onDebugLlmAutonomy)
        if (window.__REALCITY_NPC_DEBUG__?.placeNpc === debugPlaceNpc) delete window.__REALCITY_NPC_DEBUG__
      }
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('realcity:npc-request', onNpcRequest)
      window.removeEventListener('realcity:player-hit-npc', onNpcHit)
      window.removeEventListener('realcity:taxi-board-requested', onTaxiBoardRequested)
    }
  }, [agents, city, city.roads, places, destinations])

  return (
    <>
      <instancedMesh ref={hipsRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.fabric} color="#ffffff" vertexColors roughness={0.82} metalness={0.03} />
      </instancedMesh>
      <instancedMesh ref={torsoRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <capsuleGeometry args={[1, 2, 8, 14]} />
        <meshStandardMaterial map={textures.fabric} color="#ffffff" vertexColors roughness={0.78} metalness={0.03} />
      </instancedMesh>
      <instancedMesh ref={chestRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.fabric} color="#ffffff" vertexColors roughness={0.64} metalness={0.04} />
      </instancedMesh>
      <instancedMesh ref={collarRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.fabric} color="#eee4d4" vertexColors roughness={0.62} metalness={0.02} />
      </instancedMesh>
      <instancedMesh ref={lapelRef} args={[undefined, undefined, agents.length * 2]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.fabric} color="#ffffff" vertexColors roughness={0.68} metalness={0.03} />
      </instancedMesh>
      <instancedMesh ref={badgeRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.metal} color="#c49a4f" vertexColors roughness={0.38} metalness={0.36} />
      </instancedMesh>
      <instancedMesh ref={beltRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.metal} color="#473120" vertexColors roughness={0.62} metalness={0.12} />
      </instancedMesh>
      <instancedMesh ref={backSeamRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.fabric} color="#4b3426" vertexColors roughness={0.7} metalness={0.04} />
      </instancedMesh>
      <instancedMesh ref={shoulderStrapRef} args={[undefined, undefined, agents.length * 2]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.fabric} color="#4b3426" vertexColors roughness={0.72} metalness={0.04} />
      </instancedMesh>
      <instancedMesh ref={neckRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 12]} />
        <meshStandardMaterial map={textures.skin} color="#efc29a" vertexColors roughness={0.72} />
      </instancedMesh>
      <instancedMesh ref={headRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <sphereGeometry args={[1, 16, 12]} />
        <meshStandardMaterial map={textures.skin} color="#efc29a" vertexColors roughness={0.72} />
      </instancedMesh>
      <instancedMesh ref={hairRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <sphereGeometry args={[1, 16, 10, 0, Math.PI * 2, 0, Math.PI * 0.56]} />
        <meshStandardMaterial map={textures.hair} color="#19130f" vertexColors roughness={0.9} />
      </instancedMesh>
      <instancedMesh ref={hairBackRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.hair} color="#19130f" vertexColors roughness={0.9} />
      </instancedMesh>
      <instancedMesh ref={eyeRef} args={[undefined, undefined, agents.length * 2]} frustumCulled={false}>
        <sphereGeometry args={[1, 10, 8]} />
        <meshStandardMaterial color="#f7f3ea" roughness={0.44} />
      </instancedMesh>
      <instancedMesh ref={pupilRef} args={[undefined, undefined, agents.length * 2]} frustumCulled={false}>
        <sphereGeometry args={[1, 8, 6]} />
        <meshStandardMaterial color="#05070a" roughness={0.32} />
      </instancedMesh>
      <instancedMesh ref={eyelidRef} args={[undefined, undefined, agents.length * 2]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.skin} color="#efc29a" vertexColors roughness={0.72} />
      </instancedMesh>
      <instancedMesh ref={browRef} args={[undefined, undefined, agents.length * 2]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.hair} color="#19130f" vertexColors roughness={0.7} />
      </instancedMesh>
      <instancedMesh ref={glassesRef} args={[undefined, undefined, agents.length * 2]} frustumCulled={false}>
        <torusGeometry args={[1, 0.18, 6, 12]} />
        <meshStandardMaterial map={textures.glass} color="#07090d" roughness={0.28} metalness={0.42} />
      </instancedMesh>
      <instancedMesh ref={noseRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.skin} color="#b98262" roughness={0.72} />
      </instancedMesh>
      <instancedMesh ref={mouthRef} args={[undefined, undefined, agents.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#6e2f2f" roughness={0.7} />
      </instancedMesh>
      <instancedMesh ref={faceMarkRef} args={[undefined, undefined, agents.length * 2]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#4b2b22" vertexColors roughness={0.76} />
      </instancedMesh>
      <instancedMesh ref={cheekRef} args={[undefined, undefined, agents.length * 2]} frustumCulled={false}>
        <sphereGeometry args={[1, 8, 6]} />
        <meshStandardMaterial map={textures.skin} color="#efc29a" vertexColors roughness={0.7} />
      </instancedMesh>
      <instancedMesh ref={earRef} args={[undefined, undefined, agents.length * 2]} castShadow frustumCulled={false}>
        <sphereGeometry args={[1, 8, 6]} />
        <meshStandardMaterial map={textures.skin} color="#efc29a" vertexColors roughness={0.72} />
      </instancedMesh>
      <instancedMesh ref={bagRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.fabric} color="#473120" vertexColors roughness={0.78} />
      </instancedMesh>
      <instancedMesh ref={hatRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 12]} />
        <meshStandardMaterial map={textures.fabric} color="#27313d" vertexColors roughness={0.74} metalness={0.04} />
      </instancedMesh>
      <instancedMesh ref={skirtRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <coneGeometry args={[1, 1, 8]} />
        <meshStandardMaterial map={textures.fabric} color="#293241" vertexColors roughness={0.82} />
      </instancedMesh>
      <instancedMesh ref={scarfRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.fabric} color="#ffffff" vertexColors roughness={0.66} metalness={0.02} />
      </instancedMesh>
      <instancedMesh ref={legRef} args={[undefined, undefined, agents.length * 2]} castShadow frustumCulled={false}>
        <capsuleGeometry args={[1, 2, 6, 10]} />
        <meshStandardMaterial map={textures.fabric} color="#1f2937" vertexColors roughness={0.84} />
      </instancedMesh>
      <instancedMesh ref={armRef} args={[undefined, undefined, agents.length * 2]} castShadow frustumCulled={false}>
        <capsuleGeometry args={[1, 2, 6, 10]} />
        <meshStandardMaterial map={textures.skin} color="#d7a17d" vertexColors roughness={0.7} />
      </instancedMesh>
      <instancedMesh ref={sleeveRef} args={[undefined, undefined, agents.length * 2]} castShadow frustumCulled={false}>
        <capsuleGeometry args={[1, 2, 5, 10]} />
        <meshStandardMaterial map={textures.fabric} color="#ffffff" vertexColors roughness={0.78} metalness={0.03} />
      </instancedMesh>
      <instancedMesh ref={shinRef} args={[undefined, undefined, agents.length * 2]} castShadow frustumCulled={false}>
        <capsuleGeometry args={[1, 2, 6, 10]} />
        <meshStandardMaterial map={textures.fabric} color="#1f2937" vertexColors roughness={0.84} />
      </instancedMesh>
      <instancedMesh ref={forearmRef} args={[undefined, undefined, agents.length * 2]} castShadow frustumCulled={false}>
        <capsuleGeometry args={[1, 2, 6, 10]} />
        <meshStandardMaterial map={textures.skin} color="#d7a17d" vertexColors roughness={0.7} />
      </instancedMesh>
      <instancedMesh ref={handRef} args={[undefined, undefined, agents.length * 2]} castShadow frustumCulled={false}>
        <sphereGeometry args={[1, 10, 8]} />
        <meshStandardMaterial map={textures.skin} color="#d7a17d" vertexColors roughness={0.72} />
      </instancedMesh>
      <instancedMesh ref={thumbRef} args={[undefined, undefined, agents.length * 2]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.skin} color="#cf9d78" roughness={0.74} />
      </instancedMesh>
      <instancedMesh ref={shoeRef} args={[undefined, undefined, agents.length * 2]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.rubber} color="#10151c" vertexColors roughness={0.82} />
      </instancedMesh>
      <instancedMesh ref={cuffRef} args={[undefined, undefined, agents.length * 2]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.rubber} color="#10151c" vertexColors roughness={0.78} />
      </instancedMesh>
      <instancedMesh ref={speechCueRef} args={[undefined, undefined, agents.length]} frustumCulled={false} renderOrder={8}>
        <sphereGeometry args={[1, 12, 8]} />
        <meshBasicMaterial color="#f8fafc" transparent opacity={0.78} depthWrite={false} />
      </instancedMesh>
      <instancedMesh ref={phoneRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#111827" roughness={0.42} metalness={0.18} />
      </instancedMesh>
      <instancedMesh ref={gestureCueRef} args={[undefined, undefined, agents.length]} frustumCulled={false} renderOrder={8}>
        <sphereGeometry args={[1, 10, 8]} />
        <meshStandardMaterial color="#4aadff" emissive="#1f7fd1" emissiveIntensity={0.55} roughness={0.48} />
      </instancedMesh>
      <instancedMesh ref={mobilityDeckRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.metal} color="#0f766e" roughness={0.42} metalness={0.34} />
      </instancedMesh>
      <instancedMesh ref={mobilityWheelRef} args={[undefined, undefined, agents.length * 2]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 14]} />
        <meshStandardMaterial map={textures.rubber} color="#0b1016" roughness={0.84} metalness={0.04} />
      </instancedMesh>
      <instancedMesh ref={mobilityHandleRef} args={[undefined, undefined, agents.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={textures.metal} color="#d9f99d" roughness={0.32} metalness={0.48} />
      </instancedMesh>
    </>
  )
}

export default function Actors({ city }) {
  return (
    <>
      <Traffic cars={city.cars} roads={city.roads} mobilitySystem={city.mobilitySystem} />
      <PlayerTaxiController city={city} />
      <TaxiRouteRibbon />
      <MissionTaxi />
      <NPCs city={city} />
    </>
  )
}
