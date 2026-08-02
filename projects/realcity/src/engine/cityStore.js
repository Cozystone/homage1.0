import { create } from 'zustand'
import { DAY_MINUTES } from './cityEngine'

const PLAYER_COLORS = ['#4aadff', '#ffb703', '#8ac926', '#ff6b9d', '#a78bfa', '#2dd4bf', '#f97316']

function finiteNumber(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function randomToken() {
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    const values = new Uint32Array(1)
    crypto.getRandomValues(values)
    return values[0].toString(36).slice(0, 6)
  }
  return Math.random().toString(36).slice(2, 8)
}

function cleanIdentityText(value, fallback, maxLength = 48) {
  const text = String(value || '')
    .trim()
    .replace(/[^\w\s.-]/g, '')
    .replace(/\s+/g, ' ')
    .slice(0, maxLength)
  return text || fallback
}

function inviteParams() {
  if (typeof window === 'undefined') return {}
  const params = new URLSearchParams(window.location.search)
  const roomId = params.get('room') || params.get('rcRoom') || ''
  const name = params.get('name') || params.get('playerName') || ''
  const playerId = params.get('playerId') || params.get('id') || ''
  const color = params.get('color') || ''
  const autoJoin = !!roomId && ['1', 'true', 'yes'].includes(String(params.get('mp') || params.get('join') || '1').toLowerCase())
  return { roomId, name, playerId, color, autoJoin }
}

function defaultMultiplayerIdentity() {
  const token = randomToken()
  return {
    playerId: `rc-${token}`,
    name: `Player ${token.toUpperCase()}`,
    roomId: 'lobby',
    color: PLAYER_COLORS[Math.floor(Math.random() * PLAYER_COLORS.length)],
  }
}

function readMultiplayerIdentity() {
  const fallback = defaultMultiplayerIdentity()
  const invite = inviteParams()
  if (typeof window === 'undefined') return fallback
  try {
    const saved = JSON.parse(window.localStorage.getItem('realcity:multiplayer') || '{}')
    return {
      playerId: cleanIdentityText(invite.playerId || saved.playerId, fallback.playerId, 48),
      name: cleanIdentityText(invite.name || saved.name, fallback.name, 28),
      roomId: cleanIdentityText(invite.roomId || saved.roomId, fallback.roomId, 32).toLowerCase(),
      color: /^#[0-9a-f]{6}$/i.test(invite.color) ? invite.color : saved.color || fallback.color,
      autoJoin: invite.autoJoin,
    }
  } catch {
    return {
      ...fallback,
      roomId: cleanIdentityText(invite.roomId, fallback.roomId, 32).toLowerCase(),
      name: cleanIdentityText(invite.name, fallback.name, 28),
      playerId: cleanIdentityText(invite.playerId, fallback.playerId, 48),
      color: /^#[0-9a-f]{6}$/i.test(invite.color) ? invite.color : fallback.color,
      autoJoin: invite.autoJoin,
    }
  }
}

function persistMultiplayerIdentity(multiplayer) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem('realcity:multiplayer', JSON.stringify({
    playerId: multiplayer.playerId,
    name: multiplayer.name,
    roomId: multiplayer.roomId,
    color: multiplayer.color,
  }))
}

const initialMultiplayer = readMultiplayerIdentity()

export const useCityStore = create((set, get) => ({
  timeMinutes: 10 * 60 + 30,
  day: 1,
  player: {
    x: 0,
    y: 6,
    z: 40,
    heading: Math.PI,
    viewHeading: Math.PI,
    speed: 0,
    district: 'Central Core',
    placeId: null,
    placeName: null,
    indoors: false,
    floor: 0,
    floorCount: 0,
    verticalCore: null,
    floorLabel: null,
    floorZone: null,
    accessHint: null,
    coreHint: null,
    floorGuide: null,
    floorDirectory: [],
  },
  weather: {
    label: 'Clear',
    tempC: 22,
    windAngle: 0.72,
    windSpeed: 5.8,
    clouds: 0.44,
  },
  sky: {
    phase: 'day',
    sunElevation: 0.75,
    sunlight: 1,
    reflection: 1,
  },
  stats: {
    npcs: 0,
    cars: 0,
    talks: 0,
    tiles: 0,
    llm: 'ollama',
  },
  llmRuntime: {
    provider: 'ollama',
    endpoint: '/ollama/api/generate',
    model: 'dolphin3:latest',
    status: 'idle',
    available: null,
    requests: 0,
    successes: 0,
    failures: 0,
    lastSource: 'idle',
    lastPurpose: null,
    lastAgentName: null,
    lastLatencyMs: null,
    lastError: null,
    lastResponsePreview: null,
    lastCheckedAt: null,
  },
  playerPhysics: {
    health: 1,
    stability: 1,
    impactFlash: 0,
    collisions: 0,
    lastImpact: null,
  },
  focusedAgent: null,
  nearbyAgent: null,
  dialogue: null,
  interaction: null,
  mission: null,
  ride: null,
  mapRoute: null,
  cityEvents: [],
  pedestrianSamples: [],
  vehicleSamples: [],
  multiplayer: {
    enabled: !!initialMultiplayer.autoJoin,
    roomId: initialMultiplayer.roomId,
    playerId: initialMultiplayer.playerId,
    name: initialMultiplayer.name,
    color: initialMultiplayer.color,
    status: 'offline',
    lastError: null,
    updatedAt: 0,
    serverTime: null,
    playerCount: 1,
    peers: [],
  },
  collisionRules: {
    playerRadius: 0.72,
    pedestrianRadius: 0.82,
    vehiclePadding: 0.78,
    solidObjects: ['buildings', 'landmarks', 'pedestrians', 'vehicles'],
    reactions: ['push-away', 'stumble', 'fall', 'driver-brake', 'following-distance', 'brake-lights', 'amber-caution-signal', 'player-stability-loss', 'impact-camera-shake'],
  },
  pulse: 'Morning traffic is building around Central Station.',

  tick(delta) {
    const state = get()
    const next = state.timeMinutes + delta * 1.25
    const physics = state.playerPhysics || {}
    const nextStability = Math.min(1, finiteNumber(physics.stability, 1) + delta * 0.16)
    const nextImpactFlash = Math.max(0, finiteNumber(physics.impactFlash, 0) - delta * 0.85)
    set({
      timeMinutes: next % DAY_MINUTES,
      day: state.day + (next >= DAY_MINUTES ? 1 : 0),
      playerPhysics: {
        ...physics,
        stability: nextStability,
        impactFlash: nextImpactFlash,
      },
    })
  },

  setClock(timeMinutes, day) {
    const minutes = Number.isFinite(Number(timeMinutes)) ? Number(timeMinutes) : get().timeMinutes
    const normalized = ((minutes % DAY_MINUTES) + DAY_MINUTES) % DAY_MINUTES
    set({
      timeMinutes: normalized,
      day: Number.isFinite(Number(day)) ? Math.max(1, Math.floor(Number(day))) : get().day,
    })
  },

  setPlayer(player) {
    const current = get().player
    const nextPlayer = {
      ...current,
      ...player,
      x: finiteNumber(player?.x, current.x),
      y: finiteNumber(player?.y, current.y),
      z: finiteNumber(player?.z, current.z),
      heading: finiteNumber(player?.heading, current.heading),
      viewHeading: finiteNumber(player?.viewHeading ?? player?.heading, current.viewHeading ?? current.heading),
      speed: finiteNumber(player?.speed, current.speed),
      floor: Math.max(0, Math.floor(finiteNumber(player?.floor, current.floor || 0))),
      floorCount: Math.max(0, Math.floor(finiteNumber(player?.floorCount, current.floorCount || 0))),
    }
    if (
      Math.abs(nextPlayer.x - current.x) < 0.12 &&
      Math.abs(nextPlayer.y - current.y) < 0.12 &&
      Math.abs(nextPlayer.z - current.z) < 0.12 &&
      Math.abs(nextPlayer.heading - current.heading) < 0.008 &&
      Math.abs((nextPlayer.viewHeading ?? nextPlayer.heading) - (current.viewHeading ?? current.heading)) < 0.008 &&
      Math.abs(nextPlayer.speed - current.speed) < 0.2 &&
      (nextPlayer.placeId || null) === (current.placeId || null) &&
      !!nextPlayer.indoors === !!current.indoors &&
      (nextPlayer.floor || 0) === (current.floor || 0) &&
      (nextPlayer.floorCount || 0) === (current.floorCount || 0) &&
      (nextPlayer.floorLabel || null) === (current.floorLabel || null) &&
      (nextPlayer.floorZone || null) === (current.floorZone || null)
    ) return

    set({ player: nextPlayer })
  },

  setStats(stats) {
    set(state => ({ stats: { ...state.stats, ...stats } }))
  },

  setLlmRuntime(patch) {
    if (!patch) return
    set(state => ({ llmRuntime: { ...state.llmRuntime, ...patch } }))
  },

  setSky(sky) {
    set(state => ({ sky: { ...state.sky, ...sky } }))
  },

  setNearbyAgent(agent) {
    const current = get().nearbyAgent
    if (!agent) {
      if (current) set({ nearbyAgent: null })
      return
    }

    const currentDistance = current ? Math.round(current.distance || 0) : null
    const nextDistance = Math.round(agent.distance || 0)
    if (
      current?.id === agent.id &&
      currentDistance === nextDistance &&
      current.activity === agent.activity &&
      current.placeName === agent.placeName
    ) return

    set({ nearbyAgent: agent })
  },

  showDialogue(dialogue) {
    set({
      dialogue: { ...dialogue, shownAt: Date.now() },
      focusedAgent: dialogue.agent || null,
    })
  },

  openInteraction(agent) {
    set({
      interaction: { agent, status: 'open', request: '', plan: null, updatedAt: Date.now() },
      focusedAgent: agent,
    })
  },

  setInteraction(patch) {
    set(state => ({
      interaction: state.interaction ? { ...state.interaction, ...patch, updatedAt: Date.now() } : null,
    }))
  },

  closeInteraction() {
    set({ interaction: null })
  },

  startMission(mission) {
    set({
      mission: { ...mission, updatedAt: Date.now() },
      mapRoute: null,
      pulse: mission.summary || `${mission.agentName} is acting on your request.`,
    })
  },

  updateMission(patch) {
    set(state => ({
      mission: state.mission ? { ...state.mission, ...patch, updatedAt: Date.now() } : null,
    }))
  },

  finishMission(text) {
    set(state => ({
      mission: null,
      interaction: state.interaction ? { ...state.interaction, status: 'done', updatedAt: Date.now() } : null,
      pulse: text || 'The requested action is complete.',
    }))
  },

  startRide(ride) {
    set({
      ride: { ...ride, startedAt: performance.now(), updatedAt: Date.now() },
      mapRoute: null,
      pulse: ride.label || 'Taxi ride started.',
    })
  },

  finishRide(text) {
    set({
      ride: null,
      pulse: text || 'Taxi ride complete.',
    })
  },

  setPulse(pulse) {
    set({ pulse })
  },

  registerPlayerImpact(impact) {
    if (!impact) return
    set(state => {
      const now = Date.now()
      const intensity = Math.max(0.05, Math.min(1.8, finiteNumber(impact.intensity, 0.2)))
      const kind = impact.kind || 'contact'
      const previous = state.playerPhysics || {}
      const healthLoss = kind === 'vehicle' ? intensity * 0.028 : intensity * 0.008
      const text = String(impact.text || `${kind} impact`).slice(0, 160)
      const entry = {
        id: `impact_${now}_${previous.collisions || 0}`,
        kind,
        sourceId: impact.sourceId || null,
        sourceName: impact.sourceName || null,
        intensity: Number(intensity.toFixed(3)),
        x: finiteNumber(impact.x, state.player.x),
        z: finiteNumber(impact.z, state.player.z),
        nx: finiteNumber(impact.nx, 0),
        nz: finiteNumber(impact.nz, 0),
        text,
        createdAt: now,
        timeMinutes: state.timeMinutes,
      }
      return {
        playerPhysics: {
          health: Math.max(0.08, finiteNumber(previous.health, 1) - healthLoss),
          stability: Math.max(0, finiteNumber(previous.stability, 1) - intensity * (kind === 'vehicle' ? 0.34 : 0.16)),
          impactFlash: Math.min(1, finiteNumber(previous.impactFlash, 0) + intensity * 0.55),
          collisions: (previous.collisions || 0) + 1,
          lastImpact: entry,
        },
        pulse: text,
        cityEvents: [{
          id: entry.id,
          timeMinutes: state.timeMinutes,
          day: state.day,
          createdAt: now,
          kind: 'collision',
          agentId: 'player',
          agentName: 'Player',
          partnerId: entry.sourceId,
          partnerName: entry.sourceName,
          placeName: state.player.placeName || state.player.district || null,
          topic: `${kind} impact`,
          relationshipTrust: null,
          relationshipDelta: null,
          text,
        }, ...state.cityEvents].slice(0, 24),
      }
    })
  },

  setMapRoute(route) {
    set(state => ({
      mapRoute: route ? { ...route, updatedAt: Date.now() } : null,
      pulse: route?.summary || state.pulse,
    }))
  },

  clearMapRoute(text) {
    set(state => ({
      mapRoute: null,
      pulse: text || state.pulse,
    }))
  },

  addCityEvent(event) {
    if (!event?.text) return
    set(state => {
      const now = Date.now()
      const entry = {
        id: event.id || `event_${now}_${state.cityEvents.length}`,
        timeMinutes: state.timeMinutes,
        day: state.day,
        createdAt: now,
        kind: event.kind || 'city',
        agentId: event.agentId || null,
        agentName: event.agentName || null,
        partnerId: event.partnerId || null,
        partnerName: event.partnerName || null,
        placeName: event.placeName || null,
        topic: event.topic || null,
        source: event.source || null,
        lineA: event.lineA || null,
        lineB: event.lineB || null,
        llmLatencyMs: typeof event.llmLatencyMs === 'number' ? event.llmLatencyMs : null,
        relationshipTrust: typeof event.relationshipTrust === 'number' ? event.relationshipTrust : null,
        relationshipDelta: typeof event.relationshipDelta === 'number' ? event.relationshipDelta : null,
        text: String(event.text).slice(0, 180),
      }
      const duplicate = state.cityEvents[0]
      if (
        duplicate &&
        duplicate.agentId === entry.agentId &&
        duplicate.kind === entry.kind &&
        duplicate.text === entry.text &&
        now - duplicate.createdAt < 2500
      ) {
        return state
      }
      return { cityEvents: [entry, ...state.cityEvents].slice(0, 24) }
    })
  },

  setPedestrianSamples(pedestrianSamples) {
    set({ pedestrianSamples })
  },

  setVehicleSamples(vehicleSamples) {
    set({ vehicleSamples })
  },

  setMultiplayerIdentity(patch) {
    set(state => {
      const next = {
        ...state.multiplayer,
        ...patch,
        roomId: String(patch.roomId ?? state.multiplayer.roomId).trim().toLowerCase() || 'lobby',
        playerId: String(patch.playerId ?? state.multiplayer.playerId).trim() || state.multiplayer.playerId,
        name: String(patch.name ?? state.multiplayer.name).trim().slice(0, 28) || state.multiplayer.name,
      }
      persistMultiplayerIdentity(next)
      return { multiplayer: next }
    })
  },

  setMultiplayerEnabled(enabled) {
    set(state => ({
      multiplayer: {
        ...state.multiplayer,
        enabled,
        status: enabled ? 'connecting' : 'offline',
        lastError: null,
        peers: enabled ? state.multiplayer.peers : [],
        updatedAt: Date.now(),
      },
    }))
  },

  setMultiplayerPresence(patch) {
    set(state => ({
      multiplayer: {
        ...state.multiplayer,
        ...patch,
        updatedAt: Date.now(),
      },
    }))
  },
}))

if (typeof window !== 'undefined' && import.meta.env.DEV) {
  window.__REALCITY_STORE__ = useCityStore
}

export function clockLabel(minutes) {
  const h = Math.floor(minutes / 60)
  const m = Math.floor(minutes % 60)
  const suffix = h >= 12 ? 'PM' : 'AM'
  return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${suffix}`
}
