import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { CITY_HALF, CITY_WORLD_SIZE } from '../engine/cityEngine'
import { clockLabel, useCityStore } from '../engine/cityStore'
import { placeRhythmFor } from '../engine/placeRhythm'
import { buildTaxiRoute } from '../engine/taxiRouting'
import VirtualPhone from './VirtualPhone'

const DEFAULT_WORLD_POINT = { x: 0, z: 40 }
const DEFAULT_LNGLAT = [0, 0]

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

function activeTaxiPose(mission, ride) {
  return ride?.taxiPose || mission?.taxi?.pose || null
}

function finiteNumber(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function finitePoint(point, fallback = DEFAULT_WORLD_POINT) {
  const safeFallback = {
    x: finiteNumber(fallback?.x, DEFAULT_WORLD_POINT.x),
    z: finiteNumber(fallback?.z, DEFAULT_WORLD_POINT.z),
  }
  return {
    x: finiteNumber(point?.x, safeFallback.x),
    z: finiteNumber(point?.z, safeFallback.z),
  }
}

function hasFinitePoint(point) {
  return Number.isFinite(Number(point?.x)) && Number.isFinite(Number(point?.z))
}

function normalizeLngLat(coords, fallback = null) {
  const lng = Number(coords?.[0])
  const lat = Number(coords?.[1])
  if (Number.isFinite(lng) && Number.isFinite(lat)) return [lng, lat]
  if (fallback) return normalizeLngLat(fallback, DEFAULT_LNGLAT)
  return DEFAULT_LNGLAT
}

function worldToLngLatSafe(city, point) {
  if (typeof city?.worldToLngLat !== 'function') return null
  try {
    return city.worldToLngLat(point.x, point.z)
  } catch {
    return null
  }
}

function safeLngLat(city, x, z, fallback = DEFAULT_WORLD_POINT) {
  const point = finitePoint({ x, z }, fallback)
  const coords = normalizeLngLat(worldToLngLatSafe(city, point), null)
  if (coords !== DEFAULT_LNGLAT) return coords
  const fallbackPoint = finitePoint(fallback, DEFAULT_WORLD_POINT)
  return normalizeLngLat(worldToLngLatSafe(city, fallbackPoint), DEFAULT_LNGLAT)
}

function routeGeoJSON(city, route) {
  const points = (route || []).filter(hasFinitePoint)
  return {
    type: 'FeatureCollection',
    features: points.length >= 2
      ? [{
          type: 'Feature',
          properties: { layer: 'taxi-route' },
          geometry: {
            type: 'LineString',
            coordinates: points.map(point => safeLngLat(city, point.x, point.z)),
          },
        }]
      : [],
  }
}

function routeDistance(points = []) {
  let total = 0
  for (let i = 1; i < points.length; i += 1) {
    total += Math.hypot(points[i].x - points[i - 1].x, points[i].z - points[i - 1].z)
  }
  return total
}

function formatMeters(value) {
  const meters = Math.max(0, finiteNumber(value, 0))
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`
  return `${Math.round(meters)} m`
}

function routeProgressRatio(points = [], pose = null) {
  if (!pose || points.length < 2) return 0
  let best = { distance: Infinity, along: 0 }
  let traveled = 0
  for (let i = 1; i < points.length; i += 1) {
    const a = points[i - 1]
    const b = points[i]
    const dx = b.x - a.x
    const dz = b.z - a.z
    const segment = Math.max(0.001, Math.hypot(dx, dz))
    const t = clamp(((pose.x - a.x) * dx + (pose.z - a.z) * dz) / (segment * segment), 0, 1)
    const px = a.x + dx * t
    const pz = a.z + dz * t
    const distance = Math.hypot(pose.x - px, pose.z - pz)
    if (distance < best.distance) best = { distance, along: traveled + segment * t }
    traveled += segment
  }
  return clamp(best.along / Math.max(0.001, traveled), 0, 1)
}

function pointAtRouteRatio(points = [], ratio = 0) {
  if (!points.length) return null
  if (points.length === 1) return points[0]
  const total = routeDistance(points)
  let target = total * clamp(ratio, 0, 1)
  for (let i = 1; i < points.length; i += 1) {
    const a = points[i - 1]
    const b = points[i]
    const segment = Math.max(0.001, Math.hypot(b.x - a.x, b.z - a.z))
    if (target <= segment) {
      const t = target / segment
      return {
        x: a.x + (b.x - a.x) * t,
        z: a.z + (b.z - a.z) * t,
      }
    }
    target -= segment
  }
  return points[points.length - 1]
}

function routeMilestones(points = []) {
  if (points.length < 2) return []
  return [0.25, 0.5, 0.75]
    .map(ratio => pointAtRouteRatio(points, ratio))
    .filter(Boolean)
}

function routePhaseLabel(mission, ride, mapRoute = null) {
  if (ride) return 'Taxi ride in progress'
  if (mission?.phase === 'taxi_dispatch') return 'Taxi driving to pickup'
  if (mission?.phase === 'taxi_waiting') return 'Taxi waiting at curb'
  if (mission?.phase === 'taxi_boarding') return 'Boarding at pickup'
  if (mission?.mode === 'walk') return 'Walking escort route'
  if (mission?.mode === 'taxi') return 'Taxi route planned'
  if (mapRoute?.route?.length >= 2) return 'Pinned map route'
  return 'Live city scan'
}

function routeDestinationLabel(mission, ride, mapRoute = null) {
  if (ride?.to?.name || ride?.to?.address) return ride.to.address || ride.to.name
  if (mission?.destination?.address || mission?.destination?.name) return mission.destination.address || mission.destination.name
  if (mission?.taxi?.targetName) return mission.taxi.targetName
  if (mapRoute?.destination?.address || mapRoute?.destination?.name) return mapRoute.destination.address || mapRoute.destination.name
  return 'No active destination'
}

function distance2d(a, b) {
  return Math.hypot(finiteNumber(a?.x) - finiteNumber(b?.x), finiteNumber(a?.z) - finiteNumber(b?.z))
}

function nearestLandmark(city, point) {
  return [...(city.landmarks || [])]
    .filter(hasFinitePoint)
    .sort((a, b) => distance2d(a, point) - distance2d(b, point))[0] || null
}

function placeActivitySummary(place, pedestrianSamples = [], vehicleSamples = []) {
  if (!place) return { npcs: 0, vehicles: 0, taxis: 0, radius: 120 }
  const radius = Math.max(85, Math.min(170, (place.radius || 20) * 3.2))
  const near = item => hasFinitePoint(item) && distance2d(item, place) <= radius
  return {
    radius,
    npcs: pedestrianSamples.filter(near).length,
    vehicles: vehicleSamples.filter(near).length,
    taxis: vehicleSamples.filter(item => near(item) && item.kind === 'taxi').length,
  }
}

function socialSummaryFor(person) {
  if (!person) return 'No social context'
  if (person.needErrandLabel && person.needErrandTargetName) return `Detouring for ${person.needErrandLabel} at ${person.needErrandTargetName}`
  if (person.talkPartnerName && person.talkTopicLabel) return `Talking with ${person.talkPartnerName} about ${person.talkTopicLabel}`
  if (person.lastInteractionPartner && person.lastInteractionTopic) return `Knows ${person.lastInteractionPartner}: ${person.lastInteractionTopic}`
  if (person.knownContacts?.[0]) return `Remembers ${person.knownContacts[0].name}: ${person.knownContacts[0].lastTopic || 'recent contact'}`
  if (person.lastMemory) return person.lastMemory
  return person.currentIntent || person.autonomyGoal || person.state || 'Following daily routine'
}

function socialScore(person) {
  return (person.talkPartnerId ? 80 : 0) +
    (person.needErrandLabel ? 36 : 0) +
    (person.relationshipCount || 0) * 8 +
    (person.knownContacts?.length || 0) * 5 +
    (person.lastMemory ? 3 : 0)
}

function placeAccessSummary(place) {
  if (!place) return 'Unknown access'
  const floors = place.interior?.floorCount || place.interior?.floors || 1
  const core = place.interior?.verticalCore || 'front door'
  const entry = place.interior?.entryRule || place.entryRule || 'front-door'
  return `${entry.replaceAll('-', ' ')} / ${floors}F / ${core}`
}

function cityMapGeoJSON(city) {
  const roads = Array.isArray(city?.roads) ? city.roads : []
  const landmarks = Array.isArray(city?.landmarks) ? city.landmarks : []
  return {
    type: 'FeatureCollection',
    features: [
      ...roads.map(road => ({
        type: 'Feature',
        properties: {
          layer: 'road',
          id: road.id,
          name: road.name,
          tier: road.tier,
          main: !!road.main,
        },
        geometry: {
          type: 'LineString',
          coordinates: road.axis === 'x'
            ? [safeLngLat(city, road.from, road.z), safeLngLat(city, road.to, road.z)]
            : [safeLngLat(city, road.x, road.from), safeLngLat(city, road.x, road.to)],
        },
      })),
      ...landmarks.filter(hasFinitePoint).map(place => ({
        type: 'Feature',
        properties: { layer: 'place', id: place.id, name: place.name, kind: place.kind },
        geometry: { type: 'Point', coordinates: safeLngLat(city, place.x, place.z) },
      })),
    ],
  }
}

function buildingGeoJSON(city) {
  const buildings = Array.isArray(city?.buildings) ? city.buildings : []
  return {
    type: 'FeatureCollection',
    features: buildings.filter(building =>
      hasFinitePoint(building) &&
      Number.isFinite(Number(building.w)) &&
      Number.isFinite(Number(building.d)),
    ).map(building => {
      const x1 = building.x - building.w / 2
      const x2 = building.x + building.w / 2
      const z1 = building.z - building.d / 2
      const z2 = building.z + building.d / 2
      return {
        type: 'Feature',
        properties: { id: building.id, type: building.type, district: building.district },
        geometry: {
          type: 'Polygon',
          coordinates: [[
            safeLngLat(city, x1, z1),
            safeLngLat(city, x2, z1),
            safeLngLat(city, x2, z2),
            safeLngLat(city, x1, z2),
            safeLngLat(city, x1, z1),
          ]],
        },
      }
    }),
  }
}

function sampleGeoJSON(city, samples) {
  return {
    type: 'FeatureCollection',
    features: samples.filter(hasFinitePoint).map(sample => ({
      type: 'Feature',
      properties: {
        id: sample.id,
        kind: sample.kind || sample.state || 'person',
        assignment: sample.assignment || '',
      },
      geometry: { type: 'Point', coordinates: safeLngLat(city, sample.x, sample.z) },
    })),
  }
}

function formatCardinalCoordinate(value, positiveLabel, negativeLabel) {
  const number = finiteNumber(value, 0)
  const label = number < -0.000005 ? negativeLabel : positiveLabel
  return `${Math.abs(number).toFixed(5)}${label}`
}

function formatLatitude(value) {
  return formatCardinalCoordinate(value, 'N', 'S')
}

function formatLongitude(value) {
  return formatCardinalCoordinate(value, 'E', 'W')
}

function normalizeDegrees(value) {
  return ((finiteNumber(value, 0) % 360) + 360) % 360
}

function headingToMapDegrees(heading) {
  return normalizeDegrees((finiteNumber(heading, Math.PI) * 180) / Math.PI)
}

function headingToMinimapBearing(heading) {
  const degrees = headingToMapDegrees(heading)
  return degrees > 180 ? degrees - 360 : degrees
}

function minimapProjectionProbe(mapInstance, city, x, z, heading) {
  if (!mapInstance?.project) return null
  try {
    const center = mapInstance.project(safeLngLat(city, x, z))
    const forward = mapInstance.project(safeLngLat(
      city,
      x + Math.sin(heading) * 36,
      z + Math.cos(heading) * 36,
    ))
    const north = mapInstance.project(safeLngLat(city, x, z + 36))
    const forwardDx = finiteNumber(forward?.x - center?.x, 0)
    const forwardDy = finiteNumber(forward?.y - center?.y, 0)
    const northDy = finiteNumber(north?.y - center?.y, 0)
    return {
      forwardDx: Number(forwardDx.toFixed(2)),
      forwardDy: Number(forwardDy.toFixed(2)),
      northDy: Number(northDy.toFixed(2)),
      headingUp: forwardDy < -0.8,
    }
  } catch {
    return null
  }
}

function nearestAddress(city, x, z) {
  const point = finitePoint({ x, z })
  let nearest = null
  for (const place of city.addressBook || []) {
    const distance = Math.hypot(place.x - point.x, place.z - point.z)
    if (!nearest || distance < nearest.distance) nearest = { ...place, distance }
  }
  if (nearest?.address) return nearest

  let roadMatch = city.roads?.[0] || null
  let roadDistance = Infinity
  for (const road of city.roads || []) {
    const distance = road.axis === 'x' ? Math.abs(point.z - road.z) : Math.abs(point.x - road.x)
    if (distance < roadDistance) {
      roadDistance = distance
      roadMatch = road
    }
  }
  return roadMatch ? { address: roadMatch.name, name: roadMatch.name, distance: roadDistance } : null
}

function clamp(value, min, max) {
  if (min > max) return 0
  return Math.min(max, Math.max(min, value))
}

function preventDefaultIfCancelable(event) {
  if (!event?.cancelable || event.type === 'wheel') return
  event.preventDefault()
}

function clampMapCenter(center, zoom) {
  const safeZoom = Math.max(0.1, finiteNumber(zoom, 1))
  const safeCenter = finitePoint(center, { x: 0, z: 40 })
  const span = CITY_WORLD_SIZE / safeZoom
  const edge = span / 2
  return {
    x: clamp(safeCenter.x, -CITY_HALF + edge, CITY_HALF - edge),
    z: clamp(safeCenter.z, -CITY_HALF + edge, CITY_HALF - edge),
  }
}

function mapViewport(center, zoom) {
  const safeCenter = finitePoint(center, { x: 0, z: 40 })
  const safeZoom = Math.max(0.1, finiteNumber(zoom, 1))
  const span = CITY_WORLD_SIZE / safeZoom
  return `${safeCenter.x - span / 2} ${mapY(safeCenter.z) - span / 2} ${span} ${span}`
}

function mapY(z) {
  return -finiteNumber(z, 0)
}

function roadTextTransform(road) {
  if (road.axis === 'x') return undefined
  return `rotate(-90 ${road.x} 0)`
}

function Minimap({ city, player, mission, ride, mapRoute, pedestrianSamples, vehicleSamples }) {
  const container = useRef(null)
  const wheelShield = useRef(null)
  const map = useRef(null)
  const safePlayer = finitePoint(player, { x: 0, z: 40 })
  const viewHeading = finiteNumber(player.viewHeading ?? player.heading, Math.PI)
  const minimapBearing = headingToMinimapBearing(viewHeading)
  const route = activeTaxiRoute(mission, ride, mapRoute)
  const mapData = useMemo(() => cityMapGeoJSON(city), [city])
  const buildingData = useMemo(() => buildingGeoJSON(city), [city])
  const [headingUpProjection, setHeadingUpProjection] = useState(true)
  const gps = useMemo(() => {
    const [lng, lat] = safeLngLat(city, safePlayer.x, safePlayer.z)
    return { lng, lat, address: nearestAddress(city, safePlayer.x, safePlayer.z)?.address || player.district }
  }, [city, safePlayer.x, safePlayer.z, player.district])

  useEffect(() => {
    if (!container.current || map.current) return

    map.current = new maplibregl.Map({
      container: container.current,
      attributionControl: false,
      interactive: false,
      center: safeLngLat(city, safePlayer.x, safePlayer.z),
      zoom: 13.2,
      bearing: 0,
      pitch: 0,
      style: {
        version: 8,
        sources: {
          realcity: { type: 'geojson', data: mapData },
          buildings: { type: 'geojson', data: buildingData },
          taxiRoute: { type: 'geojson', data: routeGeoJSON(city, []) },
          vehicles: { type: 'geojson', data: sampleGeoJSON(city, []) },
          pedestrians: { type: 'geojson', data: sampleGeoJSON(city, []) },
        },
        layers: [
          { id: 'background', type: 'background', paint: { 'background-color': '#0c1519' } },
          {
            id: 'buildings',
            type: 'fill',
            source: 'buildings',
            paint: {
              'fill-color': [
                'match',
                ['get', 'type'],
                'house',
                '#53666a',
                'apartment',
                '#61747d',
                'office',
                '#6d7f87',
                '#718995',
              ],
              'fill-opacity': 0.58,
              'fill-outline-color': 'rgba(242, 247, 250, 0.2)',
            },
          },
          {
            id: 'roads-local',
            type: 'line',
            source: 'realcity',
            filter: ['all', ['==', ['get', 'layer'], 'road'], ['==', ['get', 'main'], false]],
            paint: { 'line-color': '#58666b', 'line-width': 1.15, 'line-opacity': 0.72 },
          },
          {
            id: 'roads-main',
            type: 'line',
            source: 'realcity',
            filter: ['all', ['==', ['get', 'layer'], 'road'], ['==', ['get', 'main'], true]],
            paint: { 'line-color': '#d7d3bf', 'line-width': 2.3, 'line-opacity': 0.92 },
          },
          {
            id: 'taxi-route',
            type: 'line',
            source: 'taxiRoute',
            paint: {
              'line-color': '#ffd447',
              'line-width': 4.6,
              'line-opacity': 0.94,
            },
          },
          {
            id: 'places',
            type: 'circle',
            source: 'realcity',
            filter: ['==', ['get', 'layer'], 'place'],
            paint: {
              'circle-radius': 3.3,
              'circle-stroke-width': 0.7,
              'circle-stroke-color': '#f8fbff',
              'circle-color': [
                'match',
                ['get', 'kind'],
                'hospital',
                '#e85d75',
                'park',
                '#8ac926',
                'transit',
                '#55a7ff',
                'finance',
                '#8ecae6',
                'leisure',
                '#ff7ab6',
                '#f2c14e',
              ],
            },
          },
          {
            id: 'vehicle-points',
            type: 'circle',
            source: 'vehicles',
            paint: {
              'circle-radius': 3.5,
              'circle-color': [
                'match',
                ['get', 'kind'],
                'taxi',
                '#ffd447',
                '#7dd3fc',
              ],
              'circle-stroke-color': '#0b1320',
              'circle-stroke-width': 1,
            },
          },
          {
            id: 'pedestrian-points',
            type: 'circle',
            source: 'pedestrians',
            paint: {
              'circle-radius': 2.4,
              'circle-color': '#ffffff',
              'circle-opacity': 0.78,
              'circle-stroke-color': '#111920',
              'circle-stroke-width': 0.8,
            },
          },
        ],
      },
    })
    map.current.scrollZoom?.disable()
    map.current.boxZoom?.disable()
    map.current.dragPan?.disable()
    map.current.keyboard?.disable()
    map.current.doubleClickZoom?.disable()
    map.current.touchZoomRotate?.disable()

    const minimapNode = wheelShield.current || container.current
    const stopMinimapWheel = (event) => {
      preventDefaultIfCancelable(event)
      event.stopPropagation()
    }
    minimapNode?.addEventListener('wheel', stopMinimapWheel, { passive: false })

    return () => {
      minimapNode?.removeEventListener('wheel', stopMinimapWheel)
      map.current?.remove()
      map.current = null
    }
  }, [buildingData, city, mapData])

  useEffect(() => {
    if (!map.current) return
    try {
      map.current.jumpTo({
        center: safeLngLat(city, safePlayer.x, safePlayer.z),
        bearing: finiteNumber(minimapBearing, 0),
        zoom: 13.6,
      })
      const projection = minimapProjectionProbe(map.current, city, safePlayer.x, safePlayer.z, viewHeading)
      setHeadingUpProjection(projection?.headingUp !== false)
      window.__REALCITY_MINIMAP__ = {
        x: safePlayer.x,
        z: safePlayer.z,
        viewHeading,
        mapHeading: headingToMapDegrees(viewHeading),
        bearing: minimapBearing,
        gps: safeLngLat(city, safePlayer.x, safePlayer.z),
        projection,
        headingUpProjection: projection?.headingUp ?? null,
        orientationRule: 'player heading-up map; world positive-z is north/up',
      }
    } catch (error) {
      setHeadingUpProjection(false)
      console.warn('Skipped minimap camera update because MapLibre rejected the GPS fix.', error)
    }
  }, [city, safePlayer.x, safePlayer.z, viewHeading, minimapBearing])

  useEffect(() => {
    const source = map.current?.getSource('taxiRoute')
    if (!source) return
    source.setData(routeGeoJSON(city, route))
  }, [city, route, mission?.updatedAt, ride?.updatedAt, mapRoute?.updatedAt])

  useEffect(() => {
    const vehicles = map.current?.getSource('vehicles')
    const pedestrians = map.current?.getSource('pedestrians')
    vehicles?.setData(sampleGeoJSON(city, vehicleSamples.slice(0, 90)))
    pedestrians?.setData(sampleGeoJSON(city, pedestrianSamples.slice(0, 70)))
  }, [city, pedestrianSamples, vehicleSamples])

  return (
    <div className="minimap" data-heading={viewHeading.toFixed(5)} data-map-heading={headingToMapDegrees(viewHeading).toFixed(2)} data-bearing={minimapBearing.toFixed(2)} data-heading-up={headingUpProjection ? 'true' : 'false'} data-north-z="positive">
      <div ref={container} className="minimap-map" />
      <div ref={wheelShield} className="minimap-hit-shield" aria-hidden="true" />
      <div className="minimap-grid" />
      <div className="minimap-gps">
        <strong>GPS</strong>
        <span>{formatLatitude(gps.lat)} {formatLongitude(gps.lng)}</span>
      </div>
      <div className="minimap-status">
        <span>{route.length >= 2 ? 'NAV ROUTE' : 'LIVE CITY'}</span>
        <strong>{gps.address}</strong>
      </div>
      <div className="minimap-player" />
    </div>
  )
}

function Compass({ heading }) {
  const degrees = ((heading * 180 / Math.PI) % 360 + 360) % 360
  const labels = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
  return (
    <div className="compass">
      {Array.from({ length: 72 }, (_, i) => {
        const tick = i * 5
        const diff = ((tick - degrees + 180 + 360) % 360) - 180
        if (Math.abs(diff) > 48) return null
        const x = 50 + (diff / 48) * 50
        const major = tick % 45 === 0
        const cardinal = tick % 90 === 0
        return (
          <div className={`compass-tick ${cardinal ? 'major' : ''}`} key={i} style={{ left: `${x}%` }}>
            {major ? labels[Math.round(tick / 45) % labels.length] : ''}
            <span />
          </div>
        )
      })}
      <div className="compass-center" />
    </div>
  )
}

function Dialogue({ dialogue }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 500)
    return () => window.clearInterval(id)
  }, [])

  if (!dialogue || now - dialogue.shownAt > 7800) return null

  return (
    <div className="dialogue">
      <div className="dialogue-speaker">
        <strong>{dialogue.speaker}</strong>
        <span>{dialogue.role}</span>
      </div>
      <p>{dialogue.text}</p>
    </div>
  )
}

function LlmRuntimeLine({ stats, runtime }) {
  const source = runtime?.lastSource || 'idle'
  const endpoint = runtime?.endpoint || '/ollama/api/generate'
  const localOllamaEndpoint = endpoint.startsWith('/ollama')
  const productionLocalDisabled = typeof window !== 'undefined' && window.location.hostname.endsWith('.vercel.app') && localOllamaEndpoint
  const live = source === 'local-llm' || source === 'local-llm+fallback-route'
  const thinking = runtime?.status === 'thinking'
  const label = live
    ? 'LIVE'
    : thinking
      ? 'THINKING'
      : productionLocalDisabled
        ? 'LOCAL ONLY'
        : runtime?.failures > 0
          ? 'FALLBACK'
          : 'READY'
  const latency = runtime?.lastLatencyMs ? `${Math.round(runtime.lastLatencyMs / 100) / 10}s` : ''
  const modelLabel = `${runtime?.provider || 'ollama'}:${runtime?.model || stats?.llm || 'dolphin3:latest'}`
  const mode = live
    ? 'local-llm'
    : productionLocalDisabled
      ? 'production-fallback'
      : runtime?.lastSource?.startsWith?.('fallback')
        ? 'deterministic-fallback'
        : thinking
          ? 'thinking'
          : 'local-ready'
  const note = productionLocalDisabled && !live
    ? 'Vercel fallback / local Ollama only on dev'
    : runtime?.lastError
      ? runtime.lastError
      : runtime?.requests > 0
        ? `${runtime.successes || 0}/${runtime.requests || 0} local calls`
        : 'NPC cognition ready'

  return (
    <div
      className="agent-llm"
      data-llm-source={source}
      data-llm-live={live ? 'true' : 'false'}
      data-llm-mode={mode}
      data-llm-provider={runtime?.provider || 'ollama'}
      data-llm-model={runtime?.model || stats?.llm || 'dolphin3:latest'}
      data-llm-requests={runtime?.requests || 0}
      data-llm-successes={runtime?.successes || 0}
    >
      <span>Local LLM</span>
      <strong>{label}</strong>
      <small>{modelLabel}{latency ? ` / ${latency}` : ''}</small>
      <small>{note}</small>
      {runtime?.lastAgentName ? <small>{runtime.lastPurpose || 'npc'} / {runtime.lastAgentName}</small> : null}
    </div>
  )
}

function AgentCard({ agent, stats, pulse, llmRuntime }) {
  if (agent) {
    const needs = agent.needs || {}
    const needRows = [
      ['Energy', needs.energy],
      ['Hunger', needs.hunger],
      ['Social', needs.social],
    ].filter(([, value]) => typeof value === 'number')
    const lifeRoute = [agent.homeAddress, agent.workAddress || agent.workName, agent.thirdAddress || agent.thirdName].filter(Boolean)
    return (
      <aside className="agent-card">
        <div className="eyebrow">Nearby Agent</div>
        <h2>{agent.name}</h2>
        <p>{agent.job} / {agent.age} / {agent.gender}</p>
        <p>{agent.activity} at {agent.placeName}</p>
        {agent.needErrand ? (
          <div className="agent-errand" data-need-errand="true">
            <span>{agent.needErrand.label}</span>
            <strong>{agent.needErrand.targetName}</strong>
            <small>{Math.ceil(agent.needErrand.remainingMinutes || 0)} city min before returning to schedule</small>
          </div>
        ) : null}
        {needRows.length ? (
          <div className="agent-needs" aria-label="NPC needs">
            {needRows.map(([label, value]) => (
              <div key={label}>
                <span>{label}</span>
                <i><b style={{ width: `${Math.round(value * 100)}%` }} /></i>
                <em>{Math.round(value * 100)}</em>
              </div>
            ))}
          </div>
        ) : null}
        {lifeRoute.length ? (
          <small className="agent-life-route">Daily route: {lifeRoute.slice(0, 3).join(' -> ')}</small>
        ) : null}
        <LlmRuntimeLine stats={stats} runtime={llmRuntime} />
        {agent.llmAutonomy?.action ? (
          <div className="agent-llm-action" data-llm-action={agent.llmAutonomy.action}>
            <span>LLM action</span>
            <strong>{agent.llmAutonomy.action.replaceAll('_', ' ')}</strong>
            <small>{agent.llmAutonomy.execution?.outcome || agent.llmAutonomy.targetName || 'queued'}</small>
          </div>
        ) : null}
        {agent.lastLlmConversation?.line ? (
          <div className="agent-llm-action" data-llm-action="social-conversation">
            <span>LLM social</span>
            <strong>{agent.lastLlmConversation.partnerName}</strong>
            <small>{agent.lastLlmConversation.line}</small>
          </div>
        ) : null}
        {agent.socialReaction ? <small>{agent.socialReaction.replaceAll('-', ' ')}</small> : null}
        {agent.currentIntent ? <small>{agent.currentIntent}</small> : null}
        {agent.memories?.[0]?.text ? <small>{agent.memories[0].text}</small> : null}
      </aside>
    )
  }

  return (
    <aside className="agent-card">
      <div className="eyebrow">City State</div>
      <div className="metrics">
        <div><span>NPC</span><strong>{stats.npcs}</strong></div>
        <div><span>Cars</span><strong>{stats.cars}</strong></div>
        <div><span>Talks</span><strong>{stats.talks}</strong></div>
        <div><span>Tiles</span><strong>{stats.tiles}</strong></div>
      </div>
      <p>{pulse}</p>
      <LlmRuntimeLine stats={stats} runtime={llmRuntime} />
    </aside>
  )
}

function MultiplayerPanel({ multiplayer }) {
  const [form, setForm] = useState({
    playerId: multiplayer.playerId,
    name: multiplayer.name,
    roomId: multiplayer.roomId,
    color: multiplayer.color,
  })
  const [copied, setCopied] = useState(false)
  const activeRoomId = multiplayer.enabled ? multiplayer.roomId : form.roomId
  const inviteUrl = useMemo(() => multiplayerInviteUrl(activeRoomId), [activeRoomId])

  useEffect(() => {
    if (!multiplayer.enabled) {
      setForm({
        playerId: multiplayer.playerId,
        name: multiplayer.name,
        roomId: multiplayer.roomId,
        color: multiplayer.color,
      })
    }
  }, [multiplayer.playerId, multiplayer.name, multiplayer.roomId, multiplayer.color, multiplayer.enabled])

  const update = (key, value) => setForm(current => ({ ...current, [key]: value }))
  const join = (event) => {
    event.preventDefault()
    const store = useCityStore.getState()
    store.setMultiplayerIdentity(form)
    store.setMultiplayerEnabled(true)
    applyMultiplayerInviteUrl(form.roomId)
  }
  const leave = () => useCityStore.getState().setMultiplayerEnabled(false)
  const copyInvite = async () => {
    if (!inviteUrl) return
    try {
      await navigator.clipboard?.writeText(inviteUrl)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }

  if (multiplayer.enabled) {
    return (
      <aside className="multiplayer-panel">
        <div className="multiplayer-header">
          <span className={`multiplayer-dot ${multiplayer.status}`} />
          <strong>{multiplayer.name}</strong>
          <button type="button" onClick={copyInvite}>{copied ? 'Copied' : 'Invite'}</button>
          <button type="button" onClick={leave}>Leave</button>
        </div>
        <div className="multiplayer-grid">
          <span>Room</span><strong>{multiplayer.roomId}</strong>
          <span>ID</span><strong>{multiplayer.playerId}</strong>
          <span>Online</span><strong>{multiplayer.playerCount}</strong>
        </div>
        <div className="multiplayer-invite">
          <span>Invite Link</span>
          <output>{inviteUrl}</output>
        </div>
        {multiplayer.peers.length ? (
          <ul>
            {multiplayer.peers.slice(0, 4).map(peer => (
              <li key={peer.id}>
                <i style={{ background: peer.color }} />
                <span>{peer.name}</span>
                <small>{peer.district}</small>
              </li>
            ))}
          </ul>
        ) : <small>{multiplayer.status === 'online' ? 'Waiting for other players' : multiplayer.status}</small>}
        {multiplayer.lastError ? <small className="multiplayer-error">{multiplayer.lastError}</small> : null}
      </aside>
    )
  }

  return (
    <form className="multiplayer-panel" onSubmit={join} onKeyDown={event => event.stopPropagation()}>
      <div className="multiplayer-title">
        <strong>Multiplayer</strong>
        <span>city room</span>
      </div>
      <div className="multiplayer-form">
        <label>
          <span>Name</span>
          <input value={form.name} maxLength={28} onChange={event => update('name', event.target.value)} />
        </label>
        <label>
          <span>ID</span>
          <input value={form.playerId} maxLength={48} onChange={event => update('playerId', event.target.value)} />
        </label>
        <label>
          <span>Room</span>
          <input value={form.roomId} maxLength={32} onChange={event => update('roomId', event.target.value)} />
        </label>
        <label>
          <span>Color</span>
          <input type="color" value={form.color} onChange={event => update('color', event.target.value)} />
        </label>
      </div>
      <button type="submit">Join Server</button>
      <div className="multiplayer-invite">
        <span>Invite Link</span>
        <output>{inviteUrl}</output>
        <button type="button" onClick={copyInvite}>{copied ? 'Copied' : 'Copy Link'}</button>
      </div>
    </form>
  )
}

function InteractionPanel({ interaction }) {
  const [text, setText] = useState('')

  useEffect(() => {
    setText('')
  }, [interaction?.agent?.id])

  if (!interaction?.agent) return null

  const disabled = interaction.status === 'thinking'
  const workLabel = interaction.agent.workAddress || interaction.agent.workName || 'your workplace'
  const presets = [
    {
      label: 'To work',
      text: `Please take me to ${workLabel}. If it is far or urgent, call a taxi and stay with me until we arrive.`,
    },
    {
      label: 'Taxi ride',
      text: 'Please call the nearest passing taxi, wait with me at the curb, and ride with me to the destination.',
    },
    {
      label: 'Ask schedule',
      text: 'Where are you going now, what is your schedule today, and can I come with you?',
    },
  ]
  const submit = (event) => {
    event.preventDefault()
    const request = text.trim()
    if (!request || disabled) return
    useCityStore.getState().setInteraction({ status: 'thinking', request })
    window.dispatchEvent(new CustomEvent('realcity:npc-request', {
      detail: { agentId: interaction.agent.id, text: request },
    }))
  }

  return (
    <form className="interaction-panel" onSubmit={submit} onKeyDown={event => event.stopPropagation()}>
      <div>
        <strong>{interaction.agent.name}</strong>
        <span>{interaction.status === 'thinking' ? 'Thinking' : interaction.status === 'active' ? 'Acting' : 'Ready'}</span>
      </div>
      <textarea
        value={text}
        disabled={disabled}
        onChange={event => setText(event.target.value)}
        placeholder="예: 나를 당신이 일하는 곳까지 데려다주세요. 멀면 택시를 불러 같이 가주세요."
        rows={3}
      />
      <div className="request-presets" aria-label="Quick requests">
        {presets.map(item => (
          <button key={item.label} type="button" disabled={disabled} onClick={() => setText(item.text)}>
            {item.label}
          </button>
        ))}
      </div>
      <div className="interaction-actions">
        <button type="submit" disabled={disabled || !text.trim()}>{disabled ? 'Thinking...' : 'Send'}</button>
        <button type="button" onClick={() => useCityStore.getState().closeInteraction()}>Close</button>
      </div>
    </form>
  )
}

function openPhone(tab = 'messages') {
  window.dispatchEvent(new CustomEvent('realcity:open-phone', { detail: { tab } }))
}

function pressTalk() {
  window.dispatchEvent(new KeyboardEvent('keydown', {
    code: 'KeyE',
    key: 'e',
    bubbles: true,
    cancelable: true,
  }))
}

function pressBoardTaxi() {
  window.dispatchEvent(new KeyboardEvent('keydown', {
    code: 'KeyF',
    key: 'f',
    bubbles: true,
    cancelable: true,
  }))
}

function pressHailTaxi() {
  window.dispatchEvent(new KeyboardEvent('keydown', {
    code: 'KeyH',
    key: 'h',
    bubbles: true,
    cancelable: true,
  }))
}

function multiplayerInviteUrl(roomId) {
  if (typeof window === 'undefined') return ''
  const url = new URL(window.location.href)
  url.searchParams.set('room', String(roomId || 'lobby').trim().toLowerCase() || 'lobby')
  url.searchParams.set('mp', '1')
  url.searchParams.delete('playerId')
  url.searchParams.delete('id')
  url.searchParams.delete('name')
  url.searchParams.delete('playerName')
  return url.toString()
}

function applyMultiplayerInviteUrl(roomId) {
  if (typeof window === 'undefined') return
  const url = new URL(window.location.href)
  url.searchParams.set('room', String(roomId || 'lobby').trim().toLowerCase() || 'lobby')
  url.searchParams.set('mp', '1')
  window.history.replaceState({}, '', url)
}

function KeyPrompt({ keyName, label, detail, primary = false, onClick }) {
  const Component = onClick ? 'button' : 'div'
  return (
    <Component
      type={onClick ? 'button' : undefined}
      className={`key-prompt ${primary ? 'primary' : ''}`}
      onClick={onClick}
    >
      <kbd>{keyName}</kbd>
      <span>{label}</span>
      {detail ? <small>{detail}</small> : null}
    </Component>
  )
}

function ContextPrompts({ nearbyAgent, mission, ride, player, onOpenMap }) {
  const actions = []

  if (mission) {
    const phase = ride
      ? 'In taxi'
      : mission.phase === 'to_pickup'
        ? 'Go to curb'
        : mission.phase === 'taxi_dispatch'
          ? 'Taxi en route'
          : mission.phase === 'taxi_waiting'
            ? 'Board taxi'
        : mission.phase === 'taxi_boarding'
          ? 'Boarding taxi'
          : mission.phase === 'leading'
            ? 'Follow agent'
            : 'Active plan'
    actions.push({
      keyName: mission.mode === 'taxi' && mission.phase === 'taxi_waiting' ? 'F' : mission.mode === 'taxi' ? 'TAXI' : 'GO',
      label: phase,
      detail: mission.destination?.address || mission.destination?.name,
      primary: true,
      onClick: mission.mode === 'taxi' && mission.phase === 'taxi_waiting' ? pressBoardTaxi : undefined,
    })
  } else if (nearbyAgent) {
    actions.push({
      keyName: 'E',
      label: `Talk to ${nearbyAgent.name.split(' ')[0]}`,
      detail: `${Math.round(nearbyAgent.distance)}m`,
      primary: true,
      onClick: pressTalk,
    })
  } else {
    actions.push({ keyName: 'E', label: 'Talk', detail: 'near NPC', primary: true })
  }

  if (player?.indoors && player.floorCount > 1) {
    actions.push({
      keyName: 'PgUp/Dn',
      label: player.coreHint || 'Floor core',
      detail: player.floorLabel || `Floor ${player.floor}`,
    })
  }

  actions.push(
    { keyName: 'T', label: 'Taxi', detail: 'phone route', onClick: () => openPhone('taxi') },
    { keyName: 'H', label: 'Hail', detail: 'passing cab', onClick: pressHailTaxi },
    { keyName: 'M', label: 'Map', detail: 'city', onClick: onOpenMap },
    { keyName: 'P', label: 'Phone', detail: 'contacts', onClick: () => openPhone('messages') },
  )

  return (
    <div className="prompt-stack" aria-label="Context actions">
      <div className="prompt-actions">
        {actions.map(action => (
          <KeyPrompt
            key={`${action.keyName}-${action.label}`}
            keyName={action.keyName}
            label={action.label}
            detail={action.detail}
            primary={action.primary}
            onClick={action.onClick}
          />
        ))}
      </div>
      <div className="control-ribbon" aria-label="Movement controls">
        <span><kbd>W/S</kbd> Move</span>
        <span><kbd>A/D</kbd> Turn</span>
        <span><kbd>Arrows</kbd> Look</span>
        <span><kbd>Space</kbd> Jump</span>
        <span><kbd>H/F</kbd> Taxi</span>
        {player?.indoors ? <span><kbd>PgUp/Dn</kbd> Floor</span> : null}
      </div>
    </div>
  )
}

function MissionPanel({ mission, ride }) {
  if (!mission) return null
  const taxiRoute = activeTaxiRoute(mission, ride)
  const routeMeters = ride?.routeMeters || (mission.phase === 'taxi_dispatch' ? mission.taxi?.routeMeters : mission.taxi?.destinationMeters) || mission.taxi?.routeMeters || 0
  const phase = ride
    ? `Taxi ${(Math.min(1, (performance.now() - ride.startedAt) / (ride.duration * 1000)) * 100).toFixed(0)}%`
    : mission.phase === 'taxi_dispatch'
      ? 'Taxi en route'
      : mission.phase === 'taxi_waiting'
        ? 'Taxi arrived'
        : mission.phase

  return (
    <aside className="mission-panel">
      <div className="eyebrow">Active Plan</div>
      <h2>{mission.agentName}</h2>
      <p>{mission.mode === 'taxi' ? 'Taxi escort' : 'Walking escort'} to {mission.destination?.name}</p>
      {mission.destination?.address ? <small>{mission.destination.address}</small> : null}
      <small>{phase}</small>
      {taxiRoute.length >= 2 ? <small>{Math.round(routeMeters)}m road route plotted</small> : null}
      {mission.offer || mission.reasoning || mission.safety ? (
        <div className="mission-rationale">
          {mission.offer ? <span>{mission.offer}</span> : null}
          {mission.reasoning ? <span>{mission.reasoning}</span> : null}
          {mission.safety ? <span>{mission.safety}</span> : null}
        </div>
      ) : null}
      <ol>
        {(mission.steps || []).slice(0, 4).map(step => <li key={step}>{step}</li>)}
      </ol>
    </aside>
  )
}

function IndoorDirectoryPanel({ player }) {
  if (!player?.indoors) return null
  const floors = Array.isArray(player.floorDirectory) ? player.floorDirectory : []
  const currentFloor = Math.max(1, player.floor || 1)
  const preview = floors.length
    ? floors
      .filter(entry => Math.abs((entry.level || 1) - currentFloor) <= 2)
      .slice(0, 5)
    : [{
        level: currentFloor,
        label: player.floorLabel || `Floor ${currentFloor}`,
        zone: player.floorZone || 'active interior',
        core: player.coreHint || 'Floor core',
      }]

  return (
    <aside className="indoor-directory-panel" aria-label="Indoor floor directory">
      <div className="eyebrow">Indoor Directory</div>
      <h2>{player.placeName}</h2>
      <p>{player.coreHint || 'Floor core'} / Floor {currentFloor} of {player.floorCount || 1}</p>
      {player.floorGuide ? <small>{player.floorGuide}</small> : null}
      <div className="indoor-floor-list">
        {preview.map(entry => (
          <article key={`${entry.level}-${entry.label}`} data-current={entry.level === currentFloor ? 'true' : 'false'}>
            <span>{entry.level}F</span>
            <div>
              <strong>{entry.label}</strong>
              <small>{entry.zone}</small>
            </div>
          </article>
        ))}
      </div>
    </aside>
  )
}

function placeColor(kind) {
  return {
    hospital: '#e85d75',
    park: '#8ac926',
    transit: '#55a7ff',
    finance: '#8ecae6',
    leisure: '#ff7ab6',
    cafe: '#d98b5f',
    retail: '#f4a261',
    school: '#78c6a3',
    workshop: '#9b7ede',
    logistics: '#adb5bd',
  }[kind] || '#f2c14e'
}

function FullCityMap({ city, player, mission, ride, mapRoute, pedestrianSamples, vehicleSamples, onClose }) {
  const safePlayer = finitePoint(player, { x: 0, z: 40 })
  const heading = headingToMapDegrees(player.viewHeading ?? player.heading)
  const route = activeTaxiRoute(mission, ride, mapRoute)
  const taxiPose = activeTaxiPose(mission, ride)
  const taxi = hasFinitePoint(taxiPose) ? taxiPose : null
  const taxiHeading = taxi ? headingToMapDegrees(taxi.heading ?? taxi.yaw ?? Math.PI) : 0
  const nearestPlace = useMemo(() => nearestLandmark(city, safePlayer), [city, safePlayer.x, safePlayer.z])
  const [selectedPlaceId, setSelectedPlaceId] = useState(() => nearestPlace?.id || city.landmarks?.[0]?.id || null)
  const [zoom, setZoom] = useState(1)
  const [center, setCenter] = useState(() => clampMapCenter(safePlayer, 1))
  const [followGps, setFollowGps] = useState(true)
  const drag = useRef(null)
  const mapSvgRef = useRef(null)
  const gps = useMemo(() => {
    const [lng, lat] = safeLngLat(city, safePlayer.x, safePlayer.z)
    const fix = nearestAddress(city, safePlayer.x, safePlayer.z)
    return {
      lng,
      lat,
      address: fix?.address || player.district,
      label: fix?.name || player.district,
      accuracy: `${Math.max(4, Math.min(28, Math.round((fix?.distance || 0) * 0.08 + 5)))}m`,
    }
  }, [city, safePlayer.x, safePlayer.z, player.district])
  const visibleVehicles = useMemo(() => vehicleSamples.filter(hasFinitePoint).slice(0, 140), [vehicleSamples])
  const visiblePedestrians = useMemo(() => pedestrianSamples.filter(hasFinitePoint).slice(0, 120), [pedestrianSamples])
  const mobilitySummary = useMemo(() => {
    const mobility = city.mobilitySystem || {}
    const stations = mobility.gbfs?.stations || []
    const nearestDock = stations
      .filter(hasFinitePoint)
      .map(station => ({ ...station, distance: distance2d(station, safePlayer) }))
      .sort((a, b) => a.distance - b.distance)[0] || null
    return {
      stationCount: stations.length,
      curbZones: mobility.smartCity?.curbZones?.length || 0,
      geofences: mobility.gbfs?.geofencingZones?.length || 0,
      disruptions: mobility.gatsim?.disruptionEvents?.length || 0,
      nearestDock,
    }
  }, [city.mobilitySystem, safePlayer.x, safePlayer.z])
  const primaryRoads = useMemo(() => city.roads.filter(road => road.main), [city.roads])
  const routePoints = useMemo(() => route.filter(hasFinitePoint), [route])
  const activeRoutePoints = useMemo(() => routePoints.map(point => `${point.x},${mapY(point.z)}`).join(' '), [routePoints])
  const routeActorPose = taxi || safePlayer
  const routeMeters = useMemo(() => finiteNumber(mapRoute?.routeMeters, routeDistance(routePoints)) || routeDistance(routePoints), [mapRoute?.routeMeters, routePoints])
  const routeProgress = useMemo(() => routeProgressRatio(routePoints, routeActorPose), [routePoints, routeActorPose.x, routeActorPose.z])
  const routeProgressPoint = useMemo(() => pointAtRouteRatio(routePoints, routeProgress), [routePoints, routeProgress])
  const routeMarkers = useMemo(() => routeMilestones(routePoints), [routePoints])
  const routeRemaining = routeMeters * (1 - routeProgress)
  const routeHasNavigation = routePoints.length >= 2
  const routePhase = routePhaseLabel(mission, ride, mapRoute)
  const routeDestination = routeDestinationLabel(mission, ride, mapRoute)
  const routeStart = routePoints[0]
  const routeEnd = routePoints[routePoints.length - 1]
  const selectedPlace = useMemo(
    () => city.landmarks.find(place => place.id === selectedPlaceId) || nearestPlace || city.landmarks[0] || null,
    [city.landmarks, selectedPlaceId, nearestPlace],
  )
  const placeDirectory = useMemo(() => [...city.landmarks]
    .filter(hasFinitePoint)
    .sort((a, b) => distance2d(a, safePlayer) - distance2d(b, safePlayer))
    .slice(0, 10), [city.landmarks, safePlayer.x, safePlayer.z])
  const selectedPlaceActivity = useMemo(
    () => placeActivitySummary(selectedPlace, pedestrianSamples, vehicleSamples),
    [selectedPlace, pedestrianSamples, vehicleSamples],
  )
  const selectedPlaceRhythm = useMemo(
    () => placeRhythmFor(selectedPlace, pedestrianSamples, useCityStore.getState().timeMinutes),
    [selectedPlace, pedestrianSamples],
  )
  const socialLinks = useMemo(() => {
    const byId = new Map(visiblePedestrians.map(person => [person.id, person]))
    const links = []
    for (const person of visiblePedestrians) {
      if (!person.talkPartnerId || String(person.id) > String(person.talkPartnerId)) continue
      const partner = byId.get(person.talkPartnerId)
      if (!partner) continue
      links.push({
        id: `${person.id}_${partner.id}`,
        a: person,
        b: partner,
        topic: person.talkTopicLabel || partner.talkTopicLabel || 'conversation',
      })
    }
    return links.slice(0, 12)
  }, [visiblePedestrians])
  const socialAgents = useMemo(() => [...visiblePedestrians]
    .filter(person => socialScore(person) > 0)
    .sort((a, b) => socialScore(b) - socialScore(a))
    .slice(0, 5), [visiblePedestrians])
  const selectedPlaceDistance = selectedPlace ? distance2d(selectedPlace, safePlayer) : 0
  const canRequestPlaceTaxi = !!selectedPlace && !mission && !ride

  useEffect(() => {
    if (!followGps) return
    setCenter(clampMapCenter(safePlayer, zoom))
  }, [followGps, safePlayer.x, safePlayer.z, zoom])

  useEffect(() => {
    if (!selectedPlaceId && nearestPlace?.id) setSelectedPlaceId(nearestPlace.id)
  }, [nearestPlace?.id, selectedPlaceId])

  const changeZoom = useCallback((factor) => {
    const nextZoom = clamp(zoom * factor, 0.82, 5.2)
    setZoom(nextZoom)
    setCenter(current => clampMapCenter(followGps ? safePlayer : current, nextZoom))
  }, [followGps, safePlayer.x, safePlayer.z, zoom])

  const recenter = useCallback(() => {
    setFollowGps(true)
    setCenter(clampMapCenter(safePlayer, zoom))
  }, [safePlayer.x, safePlayer.z, zoom])

  const pinSelectedPlace = useCallback(() => {
    if (!selectedPlace) return
    const routePlan = buildTaxiRoute(safePlayer, selectedPlace, city.roads || [])
    if (routePlan.points.length < 2) {
      useCityStore.getState().setPulse(`Could not plot a road route to ${selectedPlace.address || selectedPlace.name}.`)
      return
    }
    const destination = {
      id: selectedPlace.id,
      name: selectedPlace.name,
      address: selectedPlace.address || selectedPlace.roadName || selectedPlace.name,
      district: selectedPlace.district || 'RealCity',
      kind: selectedPlace.kind,
      x: selectedPlace.x,
      z: selectedPlace.z,
    }
    useCityStore.getState().setMapRoute({
      id: `map_route_${selectedPlace.id}_${Date.now()}`,
      source: 'map_place_pin',
      destination,
      route: routePlan.points,
      routeMeters: routePlan.routeMeters,
      directMeters: routePlan.directMeters,
      routeNames: routePlan.roadNames,
      summary: `Pinned lane-following route to ${destination.address}.`,
    })
    useCityStore.getState().addCityEvent({
      id: `navigation_pin_${selectedPlace.id}_${Math.round(performance.now())}`,
      kind: 'navigation',
      placeName: selectedPlace.name,
      topic: 'map route pin',
      text: `Map pinned a lane-following route to ${destination.address} before any taxi was called.`,
    })
    setFollowGps(false)
    setCenter(clampMapCenter(selectedPlace, Math.max(zoom, 1.35)))
  }, [city.roads, safePlayer.x, safePlayer.z, selectedPlace, zoom])

  const requestSelectedPlaceTaxi = useCallback(() => {
    if (!selectedPlace) return
    const store = useCityStore.getState()
    if (store.ride || store.mission) {
      store.setPulse('Finish the current plan before calling another taxi.')
      return
    }
    window.dispatchEvent(new CustomEvent('realcity:player-taxi-request', {
      detail: {
        target: selectedPlace,
        source: 'map_place_card',
        requestChannel: 'map_place_card',
        channelLabel: 'Map place taxi',
        direct: true,
      },
    }))
    store.setPulse(`Map taxi requested directly to ${selectedPlace.address || selectedPlace.name}.`)
    onClose?.()
  }, [selectedPlace, onClose])

  const onPointerDown = useCallback((event) => {
    if (event.button !== 0) return
    event.currentTarget.setPointerCapture?.(event.pointerId)
    drag.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      center,
      zoom,
      rect: event.currentTarget.getBoundingClientRect(),
    }
  }, [center, zoom])

  const onPointerMove = useCallback((event) => {
    if (!drag.current || drag.current.pointerId !== event.pointerId) return
    const { rect, center: startCenter, zoom: startZoom, x, y } = drag.current
    const span = CITY_WORLD_SIZE / startZoom
    const dx = event.clientX - x
    const dy = event.clientY - y
    setFollowGps(false)
    setCenter(clampMapCenter({
      x: startCenter.x - (dx / Math.max(1, rect.width)) * span,
      z: startCenter.z + (dy / Math.max(1, rect.height)) * span,
    }, startZoom))
  }, [])

  const onPointerUp = useCallback((event) => {
    if (drag.current?.pointerId === event.pointerId) drag.current = null
    event.currentTarget.releasePointerCapture?.(event.pointerId)
  }, [])

  useEffect(() => {
    const node = mapSvgRef.current
    if (!node) return undefined
    const onWheel = (event) => {
      preventDefaultIfCancelable(event)
      event.stopPropagation()
      setFollowGps(false)
      changeZoom(event.deltaY < 0 ? 1.18 : 0.84)
    }
    node.addEventListener('wheel', onWheel, { passive: false })
    return () => node.removeEventListener('wheel', onWheel)
  }, [changeZoom])

  return (
    <div className="full-map-overlay" onClick={onClose}>
      <section className="full-map-panel" onClick={event => event.stopPropagation()}>
        <div className="full-map-header">
          <div>
            <h2>RealCity Map</h2>
            <p>{gps.address} / {formatLatitude(gps.lat)} {formatLongitude(gps.lng)} / accuracy {gps.accuracy}</p>
          </div>
          <button type="button" className="full-map-close" onClick={onClose}>Close</button>
        </div>
        <div className="full-map-body">
          <svg
            ref={mapSvgRef}
            className="full-city-map"
            viewBox={mapViewport(center, zoom)}
            data-zoom={zoom.toFixed(2)}
            data-follow={followGps ? 'true' : 'false'}
            data-north-z="positive"
            data-map-y="negative-z"
            role="img"
            aria-label="Interactive full city map with player position, live traffic, NPCs, and taxi route"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onDoubleClick={(event) => {
              preventDefaultIfCancelable(event)
              setFollowGps(false)
              changeZoom(1.24)
            }}
          >
            <rect x={-CITY_HALF} y={-CITY_HALF} width={CITY_WORLD_SIZE} height={CITY_WORLD_SIZE} />
            <g className="full-map-grid">
              {Array.from({ length: 13 }, (_, i) => {
                const p = -900 + i * 150
                return (
                  <g key={p}>
                    <line x1={p} y1={-CITY_HALF} x2={p} y2={CITY_HALF} />
                    <line x1={-CITY_HALF} y1={p} x2={CITY_HALF} y2={p} />
                  </g>
                )
              })}
            </g>
            <g className="full-map-buildings">
              {city.buildings.map(building => (
                <rect
                  key={building.id}
                  className={building.type}
                  x={building.x - building.w / 2}
                  y={mapY(building.z) - building.d / 2}
                  width={building.w}
                  height={building.d}
                  rx={building.type === 'house' ? 2 : 4}
                />
              ))}
            </g>
            <g className="full-map-roads">
              {city.roads.map(road => (
                <line
                  key={road.id}
                  className={road.main ? 'main' : 'local'}
                  x1={road.axis === 'x' ? road.from : road.x}
                  y1={road.axis === 'x' ? mapY(road.z) : mapY(road.from)}
                  x2={road.axis === 'x' ? road.to : road.x}
                  y2={road.axis === 'x' ? mapY(road.z) : mapY(road.to)}
                  strokeWidth={road.width}
                />
              ))}
            </g>
            <g className="full-map-road-labels">
              {primaryRoads.map(road => (
                <text
                  key={`label_${road.id}`}
                  x={road.axis === 'x' ? -CITY_HALF + 52 : road.x + 15}
                  y={road.axis === 'x' ? mapY(road.z) - road.width * 0.7 : 0}
                  transform={roadTextTransform(road)}
                >
                  {road.name}
                </text>
              ))}
            </g>
            {routePoints.length >= 2 ? (
              <>
                <polyline className="full-map-route-halo" points={activeRoutePoints} />
                <polyline className="full-map-route" points={activeRoutePoints} />
                <g className="full-map-route-markers">
                  {routeStart ? (
                    <g className="route-start" transform={`translate(${routeStart.x} ${mapY(routeStart.z)})`}>
                      <circle r="13" />
                      <text y="-18">START</text>
                    </g>
                  ) : null}
                  {routeMarkers.map((point, index) => (
                    <circle key={`milestone_${index}`} className="route-milestone" cx={point.x} cy={mapY(point.z)} r="7" />
                  ))}
                  {routeProgressPoint ? (
                    <g className="route-progress" transform={`translate(${routeProgressPoint.x} ${mapY(routeProgressPoint.z)})`}>
                      <circle r="10" />
                      <text y="26">{Math.round(routeProgress * 100)}%</text>
                    </g>
                  ) : null}
                  {routeEnd ? (
                    <g className="route-end" transform={`translate(${routeEnd.x} ${mapY(routeEnd.z)})`}>
                      <circle r="15" />
                      <text y="-20">DEST</text>
                    </g>
                  ) : null}
                </g>
              </>
            ) : null}
            <g className="full-map-landmarks">
              {city.landmarks.map(place => (
                <g
                  key={place.id}
                  className={place.id === selectedPlace?.id ? 'selected' : ''}
                  transform={`translate(${place.x} ${mapY(place.z)})`}
                  onPointerDown={event => event.stopPropagation()}
                  onClick={event => {
                    event.stopPropagation()
                    setSelectedPlaceId(place.id)
                    setFollowGps(false)
                    setCenter(clampMapCenter(place, zoom))
                  }}
                >
                  <circle r={place.kind === 'park' ? 25 : 17} fill={placeColor(place.kind)} />
                  <text x="24" y="7">{place.name}</text>
                  {place.address ? <text className="address" x="24" y="29">{place.address}</text> : null}
                </g>
              ))}
            </g>
            <g className="full-map-live-vehicles">
              {visibleVehicles.map(vehicle => (
                <g
                  key={vehicle.id}
                  className={vehicle.kind === 'taxi' ? 'taxi' : 'car'}
                  transform={`translate(${vehicle.x} ${mapY(vehicle.z)}) rotate(${headingToMapDegrees(vehicle.heading ?? Math.PI)})`}
                >
                  <rect x="-6" y="-12" width="12" height="24" rx="3" />
                </g>
              ))}
            </g>
            <g className="full-map-social-links" aria-label="Active NPC social links">
              {socialLinks.map(link => (
                <line
                  key={link.id}
                  className="full-map-social-link"
                  x1={link.a.x}
                  y1={mapY(link.a.z)}
                  x2={link.b.x}
                  y2={mapY(link.b.z)}
                />
              ))}
            </g>
            <g className="full-map-live-pedestrians">
              {visiblePedestrians.map(person => (
                <circle
                  key={person.id}
                  className={person.talkPartnerId ? 'talking' : person.relationshipCount > 0 ? 'known' : ''}
                  cx={person.x}
                  cy={mapY(person.z)}
                  r={person.state === 'crossing' ? 5.4 : person.talkPartnerId ? 5.2 : 4.4}
                />
              ))}
            </g>
            {taxi ? (
              <g className="full-map-taxi" transform={`translate(${taxi.x} ${mapY(taxi.z)}) rotate(${taxiHeading})`}>
                <rect x="-15" y="-24" width="30" height="48" rx="5" />
                <rect x="-10" y="-7" width="20" height="16" rx="3" />
              </g>
            ) : null}
            <g className="full-map-player" transform={`translate(${safePlayer.x} ${mapY(safePlayer.z)}) rotate(${heading})`}>
              <circle r="22" />
              <path d="M 0 -38 L 16 18 L 0 8 L -16 18 Z" />
            </g>
          </svg>
          <div className="full-map-controls" aria-label="Map controls">
            <button type="button" onClick={() => changeZoom(1.22)} aria-label="Zoom in">+</button>
            <button type="button" onClick={() => changeZoom(0.82)} aria-label="Zoom out">-</button>
            <button type="button" className={followGps ? 'active' : ''} onClick={recenter}>GPS</button>
          </div>
          <aside className="full-map-gps-card">
            <span>Live GPS fix</span>
            <strong>{gps.label}</strong>
            <small>{gps.address}</small>
            <small>{formatLatitude(gps.lat)} / {formatLongitude(gps.lng)}</small>
          </aside>
          <aside className="full-map-social-card" data-agent-social="true">
            <span>Agent society</span>
            <strong>{socialLinks.length ? `${socialLinks.length} live conversations` : `${socialAgents.length} known social traces`}</strong>
            {socialAgents.length ? socialAgents.slice(0, 3).map(person => (
              <article key={person.id} className="full-map-social-agent">
                <b>{person.name}</b>
                <small>{person.job} / {person.relationshipCount || 0} contacts</small>
                <p>{socialSummaryFor(person)}</p>
              </article>
            )) : (
              <p>NPC memories and relationships will appear as they meet around the city.</p>
            )}
          </aside>
          <aside className="full-map-mobility-card" data-smart-mobility="true">
            <span>Smart mobility</span>
            <strong>{mobilitySummary.stationCount} GBFS docks / {mobilitySummary.curbZones} curb rules</strong>
            <small>{mobilitySummary.geofences} geofences / {mobilitySummary.disruptions} GATSim events</small>
            {mobilitySummary.nearestDock ? (
              <p>{mobilitySummary.nearestDock.name}: {formatMeters(mobilitySummary.nearestDock.distance)} / {mobilitySummary.nearestDock.numBikesAvailable} bikes / {mobilitySummary.nearestDock.numScootersAvailable} scooters</p>
            ) : (
              <p>Shared mobility stations appear near major landmarks and legal curb zones.</p>
            )}
          </aside>
          {selectedPlace ? (
            <aside className="full-map-place-card" data-place-id={selectedPlace.id}>
              <span>Place intel</span>
              <strong>{selectedPlace.name}</strong>
              <small>{selectedPlace.address || selectedPlace.roadName} / {selectedPlace.district || 'RealCity'}</small>
              <p>{selectedPlace.gameplayRole || `${selectedPlace.kind} destination`}</p>
              <dl>
                <div><dt>Access</dt><dd>{placeAccessSummary(selectedPlace)}</dd></div>
                <div><dt>Distance</dt><dd>{formatMeters(selectedPlaceDistance)}</dd></div>
                <div><dt>Live</dt><dd>{selectedPlaceActivity.npcs} NPC / {selectedPlaceActivity.vehicles} cars / {selectedPlaceActivity.taxis} taxis</dd></div>
              </dl>
              <div className="full-map-place-rhythm" data-phase={selectedPlaceRhythm.phase}>
                <b>{selectedPlaceRhythm.status}</b>
                <small>{selectedPlaceRhythm.inbound} inbound / {selectedPlaceRhythm.onSite} on-site / {selectedPlaceRhythm.topActivity}</small>
                <div className="full-map-place-agents" aria-label="NPC movement near selected place">
                  {selectedPlaceRhythm.examples.length ? selectedPlaceRhythm.examples.map(agent => (
                    <article key={agent.id} className="full-map-place-agent">
                      <span>
                        <strong>{agent.name}</strong>
                        <small>{agent.job}</small>
                      </span>
                      <em>{agent.flow} / {agent.eta}</em>
                      <small>{agent.intent}</small>
                    </article>
                  )) : (
                    <small className="full-map-place-no-agents">No named NPC route is active here yet.</small>
                  )}
                </div>
              </div>
              <div className="full-map-place-actions">
                <button type="button" className="full-map-place-pin" onClick={pinSelectedPlace}>Pin</button>
                <button type="button" className="full-map-place-taxi" onClick={requestSelectedPlaceTaxi} disabled={!canRequestPlaceTaxi}>
                  Call Taxi
                </button>
              </div>
              <small className="full-map-place-action-note">Direct cab dispatch / no NPC relay</small>
              <div className="full-map-place-list" aria-label="Nearby places">
                {placeDirectory.slice(0, 6).map(place => (
                  <button
                    type="button"
                    key={place.id}
                    className="full-map-place-button"
                    data-active={place.id === selectedPlace.id ? 'true' : 'false'}
                    onClick={() => {
                      setSelectedPlaceId(place.id)
                      setFollowGps(false)
                      setCenter(clampMapCenter(place, zoom))
                    }}
                  >
                    <i style={{ background: placeColor(place.kind) }} />
                    <span>{place.name}</span>
                  </button>
                ))}
              </div>
            </aside>
          ) : null}
          <aside
            className="full-map-navigation-card"
            data-has-route={routeHasNavigation ? 'true' : 'false'}
            data-route-source={mapRoute?.source || mission?.source || ride?.taxiSource || 'live'}
          >
            <span>Live navigation</span>
            <strong>{routeHasNavigation ? routePhase : 'No active route'}</strong>
            <small>{routeHasNavigation ? routeDestination : 'Ask a contact, hail a taxi, or choose RealPhone Taxi.'}</small>
            {routeHasNavigation ? (
              <>
                <small>{formatMeters(routeRemaining)} remaining / {formatMeters(routeMeters)} total</small>
                <div className="full-map-route-progressbar" aria-label="Route progress">
                  <i style={{ width: `${Math.round(routeProgress * 100)}%` }} />
                </div>
                <small>{routePoints.length} lane-following points / {Math.round(routeProgress * 100)}% complete</small>
              </>
            ) : null}
          </aside>
          <div className="full-map-legend">
            <span><i className="legend-player" />You</span>
            <span><i className="legend-route" />Route</span>
            <span><i className="legend-taxi" />Taxi</span>
            <span><i className="legend-npc" />NPC</span>
            <span><i className="legend-social" />Social</span>
          </div>
        </div>
      </section>
    </div>
  )
}

export default function HUD({ city }) {
  const [mapOpen, setMapOpen] = useState(false)
  const timeMinutes = useCityStore(state => state.timeMinutes)
  const day = useCityStore(state => state.day)
  const player = useCityStore(state => state.player)
  const playerPhysics = useCityStore(state => state.playerPhysics)
  const weather = useCityStore(state => state.weather)
  const stats = useCityStore(state => state.stats)
  const pulse = useCityStore(state => state.pulse)
  const focusedAgent = useCityStore(state => state.focusedAgent)
  const nearbyAgent = useCityStore(state => state.nearbyAgent)
  const dialogue = useCityStore(state => state.dialogue)
  const interaction = useCityStore(state => state.interaction)
  const mission = useCityStore(state => state.mission)
  const ride = useCityStore(state => state.ride)
  const mapRoute = useCityStore(state => state.mapRoute)
  const multiplayer = useCityStore(state => state.multiplayer)
  const pedestrianSamples = useCityStore(state => state.pedestrianSamples)
  const vehicleSamples = useCityStore(state => state.vehicleSamples)
  const llmRuntime = useCityStore(state => state.llmRuntime)
  const viewHeading = player.viewHeading ?? player.heading
  const displayedAgent = focusedAgent || nearbyAgent

  useEffect(() => {
    const applyRuntime = event => useCityStore.getState().setLlmRuntime(event.detail)
    window.addEventListener('realcity:llm-runtime', applyRuntime)
    if (window.__REALCITY_LLM__) useCityStore.getState().setLlmRuntime(window.__REALCITY_LLM__)
    return () => window.removeEventListener('realcity:llm-runtime', applyRuntime)
  }, [])

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.target?.closest?.('input, textarea, select, button')) return
      if (event.code === 'KeyM') {
        event.preventDefault()
        setMapOpen(open => !open)
      } else if (event.code === 'KeyP') {
        event.preventDefault()
        openPhone('messages')
      } else if (event.code === 'KeyT') {
        event.preventDefault()
        openPhone('taxi')
      } else if (event.code === 'Escape') {
        setMapOpen(false)
        useCityStore.getState().closeInteraction()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <div className="hud">
      <section className="time-card">
        <h1>{clockLabel(timeMinutes)}</h1>
        <p>Day {day} / {weather.label} / {weather.tempC}C</p>
        <span>{player.indoors ? `${player.placeName} / Floor ${player.floor || 1}${player.floorCount ? ` of ${player.floorCount}` : ''}` : player.district}</span>
        {player.indoors ? <small>{player.floorLabel} / {player.floorZone}</small> : null}
        {player.indoors && player.accessHint ? <small>{player.accessHint} / {player.coreHint}</small> : null}
      </section>

      <Compass heading={viewHeading} />
      <AgentCard agent={displayedAgent} stats={stats} pulse={pulse} llmRuntime={llmRuntime} />
      <IndoorDirectoryPanel player={player} />
      <MultiplayerPanel multiplayer={multiplayer} />
      <Dialogue dialogue={dialogue} />
      <InteractionPanel interaction={interaction} />
      <MissionPanel mission={mission} ride={ride} />
      {!interaction ? (
        <ContextPrompts
          nearbyAgent={nearbyAgent}
          mission={mission}
          ride={ride}
          player={player}
          onOpenMap={() => setMapOpen(true)}
        />
      ) : null}

      <button type="button" className="map-shell" onClick={() => setMapOpen(true)} aria-label="Open full city map">
        <Minimap
          city={city}
          player={player}
          mission={mission}
          ride={ride}
          mapRoute={mapRoute}
          pedestrianSamples={pedestrianSamples}
          vehicleSamples={vehicleSamples}
        />
      </button>
      {mapOpen ? (
        <FullCityMap
          city={city}
          player={player}
          mission={mission}
          ride={ride}
          mapRoute={mapRoute}
          pedestrianSamples={pedestrianSamples}
          vehicleSamples={vehicleSamples}
          onClose={() => setMapOpen(false)}
        />
      ) : null}
      <VirtualPhone city={city} player={player} focusedAgent={focusedAgent} timeMinutes={timeMinutes} />

      <div className="vitals" data-player-impact={playerPhysics?.lastImpact?.kind || 'none'}>
        <div><span>HP</span><i style={{ width: `${Math.round((playerPhysics?.health ?? 1) * 100)}%` }} /></div>
        <div><span>ST</span><i style={{ width: `${Math.max(12, Math.round((playerPhysics?.stability ?? 1) * 100))}%` }} /></div>
        <div className={playerPhysics?.impactFlash > 0.05 ? 'impact active' : 'impact'}>
          <span>IM</span>
          <i style={{ width: `${Math.round((playerPhysics?.impactFlash || 0) * 100)}%` }} />
        </div>
        {playerPhysics?.lastImpact ? (
          <small className="impact-note">
            {playerPhysics.lastImpact.kind} / {playerPhysics.lastImpact.sourceName || 'street body'} / {Math.round(playerPhysics.lastImpact.intensity * 100)}%
          </small>
        ) : null}
      </div>
    </div>
  )
}
