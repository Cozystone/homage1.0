import { cognitionPromptLines } from './agentCognition'

const provider = import.meta.env.VITE_LOCAL_LLM_PROVIDER || 'ollama'
const endpoint = import.meta.env.VITE_LOCAL_LLM_ENDPOINT || '/ollama/api/generate'
const model = import.meta.env.VITE_LOCAL_LLM_MODEL || 'dolphin3:latest'

const llmRuntime = {
  provider,
  endpoint,
  model,
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
}

function publishLlmRuntime(patch = {}) {
  Object.assign(llmRuntime, patch, { lastCheckedAt: Date.now() })
  const snapshot = { ...llmRuntime }
  if (typeof window !== 'undefined') {
    window.__REALCITY_LLM__ = snapshot
    window.dispatchEvent(new CustomEvent('realcity:llm-runtime', { detail: snapshot }))
  }
  return snapshot
}

export function llmRuntimeSnapshot() {
  return { ...llmRuntime }
}

const PLACE_ALIASES = [
  {
    id: 'hanbit_hospital',
    aliases: ['hospital', 'clinic', 'medical', 'emergency', '\ubcd1\uc6d0', '\uc751\uae09\uc2e4', '\uc9c4\ub8cc'],
  },
  {
    id: 'river_cafe',
    aliases: ['cafe', 'coffee', 'river cafe', '\uce74\ud398', '\ucee4\ud53c'],
  },
  {
    id: 'mirae_school',
    aliases: ['school', 'campus', 'class', '\ud559\uad50', '\ucea0\ud37c\uc2a4', '\uc218\uc5c5'],
  },
  {
    id: 'hill_park',
    aliases: ['park', 'garden', 'hill park', '\uacf5\uc6d0', '\uc815\uc6d0'],
  },
  {
    id: 'central_station',
    aliases: ['station', 'central station', 'train', 'metro', 'transit', '\uc5ed', '\uc815\uac70\uc7a5', '\uae30\ucc28', '\uc9c0\ud558\ucca0'],
  },
  {
    id: 'market_lane',
    aliases: ['market', 'shop', 'retail', 'market lane', '\uc2dc\uc7a5', '\ub9c8\ucf13', '\uc0c1\uc810'],
  },
  {
    id: 'aster_exchange',
    aliases: ['exchange', 'bank', 'finance', 'office tower', '\uc740\ud589', '\uae08\uc735', '\uac70\ub798\uc18c'],
  },
  {
    id: 'neon_square',
    aliases: ['square', 'plaza', 'neon square', 'nightlife', '\uad11\uc7a5', '\ud50c\ub77c\uc790'],
  },
  {
    id: 'south_depot',
    aliases: ['depot', 'warehouse', 'logistics', 'delivery hub', '\ucc3d\uace0', '\ubb3c\ub958', '\ubc30\uc1a1'],
  },
  {
    id: 'maker_yard',
    aliases: ['maker', 'workshop', 'robotics', 'yard', '\uacf5\ubc29', '\uc791\uc5c5\uc7a5', '\ub85c\ubcf4\ud2f1\uc2a4'],
  },
]

export function llmStatus() {
  const live = llmRuntime.lastSource === 'local-llm' || llmRuntime.lastSource === 'local-llm+fallback-route'
  const pending = llmRuntime.status === 'thinking'
  const state = live ? 'live' : pending ? 'thinking' : llmRuntime.failures > 0 ? 'fallback-ready' : 'ready'
  return `${provider}:${model} ${state}`
}

export function styleNpcSpeech(agent, speech) {
  const cleanSpeech = String(speech || '').replace(/\s+/g, ' ').trim()
  if (!cleanSpeech) return cleanSpeech
  const speechPrefix = String(agent?.speechStyle?.prefix || '').trim()
  const speechKnownPrefixes = ['네.', '좋아요.', '간단히 말하면,', '확인했습니다.', '좋죠.', '음,', '바로 보면,', '확인해볼게요.', '좋지.', '가능합니다.']
  if (!speechPrefix || cleanSpeech.startsWith(speechPrefix) || speechKnownPrefixes.some(item => cleanSpeech.startsWith(item))) {
    return cleanSpeech.slice(0, 220)
  }
  return `${speechPrefix} ${cleanSpeech}`.replace(/\s+/g, ' ').slice(0, 220)
}

async function completeLocal(prompt, { temperature = 0.7, maxTokens = 160, purpose = 'npc-dialogue', agentName = null, json = false, timeoutMs = 32000, brainOverride = null } = {}) {
  if (typeof window === 'undefined') {
    return { ok: false, text: null, source: 'server-unavailable', latencyMs: 0, error: 'window-unavailable' }
  }
  // Per-agent brain routing (populationMix.js tags agent.dialogueBrain). An absent tag falls back to
  // 'atanor', i.e. the configured VITE_LOCAL_LLM_ENDPOINT, so every existing behavior is preserved.
  //  - 'engine': make NO network call at all (zero LLM load for the quiet majority); return a
  //    failed-completion shape so each caller's existing canned fallback fires.
  //  - 'ollama': hit the local ollama daemon directly through the vite proxy, regardless of the
  //    configured endpoint, using the classic ollama /generate body.
  const brain = brainOverride || 'atanor'
  if (brain === 'engine') {
    return { ok: false, text: null, source: 'engine-cast', latencyMs: 0, error: 'engine-cast' }
  }
  const useOllama = brain === 'ollama'
  const activeEndpoint = useOllama ? '/ollama/api/generate' : endpoint
  const activeModel = useOllama ? (import.meta.env.VITE_OLLAMA_MODEL || 'dolphin3:latest') : model
  if (window.location.hostname.endsWith('.vercel.app') && activeEndpoint.startsWith('/ollama')) {
    publishLlmRuntime({
      status: 'disabled-production',
      available: false,
      lastSource: 'production-disabled',
      lastPurpose: purpose,
      lastAgentName: agentName,
      lastError: 'Local Ollama calls are disabled on Vercel production.',
    })
    return { ok: false, text: null, source: 'production-disabled', latencyMs: 0, error: 'production-local-llm-disabled' }
  }

  const startedAt = performance.now()
  publishLlmRuntime({
    status: 'thinking',
    available: null,
    requests: llmRuntime.requests + 1,
    lastSource: 'pending',
    lastPurpose: purpose,
    lastAgentName: agentName,
    lastLatencyMs: null,
    lastError: null,
  })
  let timeout = null
  try {
    const controller = new AbortController()
    timeout = window.setTimeout(() => controller.abort(), timeoutMs)
    const body = (provider === 'openai-compatible' && !useOllama)
      ? {
          model: activeModel,
          messages: prompt.messages,
          temperature,
          max_tokens: maxTokens,
        }
      : {
          model: activeModel,
          prompt: prompt.text,
          stream: false,
          format: json ? 'json' : undefined,
          keep_alive: '10m',
          options: { temperature, num_predict: maxTokens },
        }

    const response = await fetch(activeEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    if (!response.ok) {
      const latencyMs = Math.round(performance.now() - startedAt)
      publishLlmRuntime({
        status: 'fallback',
        available: false,
        failures: llmRuntime.failures + 1,
        lastSource: 'fallback-http-error',
        lastLatencyMs: latencyMs,
        lastError: `HTTP ${response.status}`,
      })
      return { ok: false, text: null, source: 'fallback-http-error', latencyMs, error: `HTTP ${response.status}` }
    }
    const data = await response.json()
    const text = (data.response || data.choices?.[0]?.message?.content || data.message?.content || '').trim()
    const latencyMs = Math.round(performance.now() - startedAt)
    if (!text) {
      publishLlmRuntime({
        status: 'fallback',
        available: false,
        failures: llmRuntime.failures + 1,
        lastSource: 'fallback-empty-response',
        lastLatencyMs: latencyMs,
        lastError: 'empty-response',
      })
      return { ok: false, text: null, source: 'fallback-empty-response', latencyMs, error: 'empty-response' }
    }
    publishLlmRuntime({
      status: 'live',
      available: true,
      successes: llmRuntime.successes + 1,
      lastSource: 'local-llm',
      lastLatencyMs: latencyMs,
      lastError: null,
      lastResponsePreview: text.slice(0, 180),
    })
    return { ok: true, text, source: 'local-llm', latencyMs, error: null }
  } catch (error) {
    const latencyMs = Math.round(performance.now() - startedAt)
    const message = error?.name === 'AbortError' ? `timeout-${timeoutMs}ms` : (error?.message || String(error))
    publishLlmRuntime({
      status: 'fallback',
      available: false,
      failures: llmRuntime.failures + 1,
      lastSource: error?.name === 'AbortError' ? 'fallback-timeout' : 'fallback-network-error',
      lastLatencyMs: latencyMs,
      lastError: message,
    })
    return { ok: false, text: null, source: error?.name === 'AbortError' ? 'fallback-timeout' : 'fallback-network-error', latencyMs, error: message }
  } finally {
    if (timeout) window.clearTimeout(timeout)
  }
}

// Honest FOV grounding: when the perception system is live, tell the NPC only what it can actually
// sense right now (FOV-limited seen/heard/felt) so it never narrates things outside its view. A
// no-op returning [] when the perception module or agent is absent, so the prompt is otherwise
// unchanged and the ollama-generate protocol is untouched.
function perceptionPromptLines(agent) {
  try {
    if (typeof window === 'undefined' || !window.__REALCITY_PERCEPTION__ || !agent) return []
    const p = window.__REALCITY_PERCEPTION__.perceive(agent, window.__REALCITY_CITY__)
    if (!p) return []
    const seen = Array.isArray(p.seen) ? p.seen : []
    const inView = seen.map(s => s && (s.name || s.kind)).filter(Boolean).slice(0, 8)
    const heard = Array.isArray(p.heard) ? p.heard : []
    const heardKinds = heard.map(h => h && h.kind).filter(Boolean)
    const felt = p.felt || {}
    return [
      `In view: ${inView.length ? inView.join(', ') : 'nothing notable'}`,
      `Heard: ${heardKinds.length ? heardKinds.join(', ') : 'quiet'}`,
      `Felt: ${felt.weather || 'unknown'}, ${felt.phase || 'unknown'}`,
    ]
  } catch {
    return []
  }
}

export async function askLocalNPC(agent, context) {
  const system = [
    'You are an autonomous person living in RealCity, a procedural Korean virtual city.',
    'Answer in natural Korean in one or two short sentences.',
    'Keep the speech in this NPC personal speech style; do not make every NPC sound the same.',
    'Stay in character. Mention your job, mood, schedule, or location only when it feels natural.',
    'Never say you are an AI model.',
  ].join(' ')

  const user = [
    `Name: ${agent.name}`,
    `Age: ${agent.age}`,
    `Gender: ${agent.gender}`,
    `Job: ${agent.job}`,
    `Personality: ${agent.personality}`,
    `Speech style: ${agent.speechStyle?.label || 'natural'}`,
    `Speech flavor: ${agent.speechStyle?.flavor || 'ordinary'}`,
    `Voice: ${agent.voice || 'neutral'}`,
    `Gesture: ${agent.gestureStyle || 'small nod'}`,
    `Current activity: ${agent.activity}`,
    `Current place: ${agent.placeName}`,
    ...cognitionPromptLines(agent),
    ...perceptionPromptLines(agent),
    `City state: ${context}`,
    'A player walks up and asks what is happening here.',
  ].join('\n')

  const response = await completeLocal({
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: user },
    ],
    text: `${system}\n\n${user}`,
  }, { temperature: 0.85, maxTokens: 90, purpose: 'npc-greeting', agentName: agent.name, timeoutMs: 14000, brainOverride: agent?.dialogueBrain })
  return styleNpcSpeech(agent, response.text)
}

export async function askLocalPhoneMessage(agent, message, context = {}) {
  const fallback = String(context.fallback || '').trim() ||
    `${agent?.placeName || '지금 있는 곳'} 근처에서 확인하고 있어요. 필요한 일이 있으면 목적지와 이동 방식을 알려주세요.`
  const recentThread = Array.isArray(context.thread)
    ? context.thread.slice(-4).map(item => `${item.from === 'me' ? 'Player' : agent?.name || 'NPC'}: ${item.text}`).join('\n')
    : ''
  const system = [
    'You are a named autonomous RealCity NPC replying through RealPhone.',
    'Reply in natural Korean in one or two short text-message sentences.',
    'Stay in this person\'s speech style, job, schedule, relationship, current place, and city norms.',
    'If the player asks for a taxi directly, remind them RealPhone Taxi dispatches the cab directly; do not pretend you personally called it.',
    'If the player asks you to guide or meet them, answer as a person who can consider distance, sidewalk/crosswalk safety, and taxi vs walking.',
    'Never say you are an AI model.',
  ].join(' ')
  const user = [
    `Name: ${agent?.name || 'NPC'}`,
    `Age/Gender: ${agent?.age || 'unknown'} / ${agent?.gender || 'unknown'}`,
    `Job: ${agent?.job || 'resident'}`,
    `Personality: ${agent?.personality || 'ordinary'}`,
    `Speech style: ${agent?.speechStyle?.label || 'natural'} / ${agent?.speechStyle?.flavor || 'ordinary'}`,
    `Relationship: ${context.relation || 'known contact'} / affinity ${context.affinity || 'unknown'}`,
    `Current place/activity: ${agent?.placeName || 'RealCity'} / ${agent?.activity || 'following schedule'}`,
    `Work: ${agent?.workName || 'unknown'}${agent?.workAddress ? ` / ${agent.workAddress}` : ''}`,
    `Player state: ${context.playerPlace || context.playerDistrict || 'RealCity'}, ${context.timeLabel || 'unknown time'}`,
    recentThread ? `Recent RealPhone thread:\n${recentThread}` : null,
    ...perceptionPromptLines(agent),
    `Player message: ${message}`,
  ].filter(Boolean).join('\n')

  const completion = await completeLocal({
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: user },
    ],
    text: `${system}\n\n${user}`,
  }, { temperature: 0.62, maxTokens: 90, purpose: 'npc-phone-message', agentName: agent?.name || null, timeoutMs: 18000, brainOverride: agent?.dialogueBrain })
  const text = completion.ok
    ? cleanPlanSpeech(agent, completion.text, fallback)
    : styleNpcSpeech(agent, fallback)
  return {
    ok: completion.ok,
    text,
    source: completion.ok ? 'local-llm-phone' : `fallback:${completion.source}`,
    latencyMs: completion.latencyMs,
    error: completion.error || null,
    llm: {
      provider,
      model,
      endpoint,
      ok: completion.ok,
      source: completion.source,
      latencyMs: completion.latencyMs,
      error: completion.error || null,
      responsePreview: completion.text ? completion.text.slice(0, 180) : null,
    },
  }
}

export async function askLocalNPCConversation(a, b, context = {}) {
  const fallbackTopic = context.topic || {}
  const fallbackLabel = fallbackTopic.label || `${a?.name || 'Someone'} and ${b?.name || 'someone'} sidewalk conversation`
  const fallbackEvent = fallbackTopic.event ||
    `${a?.name || 'One NPC'} and ${b?.name || 'another NPC'} talk briefly near ${a?.placeName || b?.placeName || 'the street'}.`
  const fallbackMemoryA = typeof fallbackTopic.memoryFor === 'function'
    ? fallbackTopic.memoryFor(a, b)
    : `Talked with ${b?.name || 'a neighbor'} about ${fallbackLabel}.`
  const fallbackMemoryB = typeof fallbackTopic.memoryFor === 'function'
    ? fallbackTopic.memoryFor(b, a)
    : `Talked with ${a?.name || 'a neighbor'} about ${fallbackLabel}.`

  const schema = {
    topicId: 'short id like route, work, needs, schedule',
    label: 'short topic label',
    lineA: 'one natural Korean sentence from NPC A',
    lineB: 'one natural Korean sentence from NPC B',
    event: 'one sentence summary of what changed in the city',
  }

  const brief = agent => [
    `${agent.name}: ${agent.age} ${agent.gender}, ${agent.job}, ${agent.personality}`,
    `Speech: ${agent.speechStyle?.label || 'natural'}, ${agent.voice || 'neutral'}, gesture ${agent.gestureStyle || 'small nod'}`,
    `Now: ${agent.activity} near ${agent.placeName}`,
    `Intent: ${agent.currentIntent || agent.autonomy?.dailyGoal || 'daily routine'}`,
    `Needs: hunger ${Number(agent.needs?.hunger || 0).toFixed(2)}, energy ${Number(agent.needs?.energy || 0).toFixed(2)}, social ${Number(agent.needs?.social || 0).toFixed(2)}, urgency ${Number(agent.needs?.urgency || 0).toFixed(2)}`,
    agent.lastInteraction?.partnerName ? `Recent social memory: ${agent.lastInteraction.partnerName}, ${agent.lastInteraction.topic}` : null,
    agent.memories?.[0]?.text ? `Latest memory: ${String(agent.memories[0].text).slice(0, 120)}` : null,
  ].filter(Boolean).join('\n')

  const system = [
    'Return JSON only. No markdown.',
    'You are the local LLM social layer for two autonomous RealCity NPCs.',
    'Create a believable two-person micro-conversation that can be executed by the simulator.',
    'The conversation must be grounded in schedule, job, street safety, needs, memory, or relationship context.',
    'Use Korean for lineA, lineB, and event.',
    'Keep lineA and lineB short enough to show in a HUD bubble.',
    'Return compact JSON with only these keys:',
    JSON.stringify(schema),
  ].join('\n')

  const user = [
    `Time: ${context.timeLabel || 'unknown'}`,
    `Place: ${context.placeName || a?.placeName || b?.placeName || 'street'}`,
    `Fallback topic: ${fallbackLabel}`,
    `Street context: ${context.streetContext || 'sidewalk social norms; avoid road lanes; use crossings and curb space.'}`,
    'NPC A',
    brief(a),
    'NPC B',
    brief(b),
  ].join('\n')

  const completion = await completeLocal({
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: user },
    ],
    text: `${system}\n\n${user}`,
  }, { temperature: 0.42, maxTokens: 120, purpose: 'npc-social-conversation', agentName: `${a?.name || 'A'} + ${b?.name || 'B'}`, json: true, timeoutMs: 52000, brainOverride: a?.dialogueBrain })

  const parsed = extractJson(completion.text)
  const topicId = cleanPlanText(parsed?.topicId, fallbackTopic.id || 'llm-social', 48)
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'llm-social'
  const label = cleanPlanText(parsed?.label, fallbackLabel, 96)
  const lineA = cleanPlanSpeech(a, parsed?.lineA, `${b?.name || 'Excuse me'}, let's compare notes about ${fallbackLabel}.`)
  const lineB = cleanPlanSpeech(b, parsed?.lineB, `Good idea. I can adjust my next stop around ${fallbackLabel}.`)
  const event = cleanPlanText(parsed?.event, fallbackEvent, 180)

  return {
    ok: completion.ok && !!parsed,
    source: completion.ok
      ? parsed ? 'local-llm-social' : 'local-llm-social-fallback'
      : `fallback:${completion.source}`,
    latencyMs: completion.latencyMs,
    error: completion.error || null,
    topic: {
      id: topicId,
      label,
      lineA,
      lineB,
      event,
      memoryA: cleanPlanText(parsed?.memoryA, `${fallbackMemoryA} ${b?.name || 'They'} said: ${lineB}`, 150),
      memoryB: cleanPlanText(parsed?.memoryB, `${fallbackMemoryB} ${a?.name || 'They'} said: ${lineA}`, 150),
    },
    llm: {
      provider,
      model,
      endpoint,
      ok: completion.ok,
      parsed: !!parsed,
      source: completion.source,
      latencyMs: completion.latencyMs,
      error: completion.error || null,
      responsePreview: completion.text ? completion.text.slice(0, 180) : null,
    },
  }
}

const AUTONOMY_ACTIONS = [
  'continue_schedule',
  'start_need_errand',
  'visit_place',
  'social_check_in',
  'hail_taxi',
  'use_shared_bike',
  'use_shared_scooter',
  'replan_route',
  'pause_observe',
]

function normalizeAutonomyAction(action, fallback = 'continue_schedule') {
  const candidate = String(action || '').trim().toLowerCase().replace(/\s+/g, '_').replaceAll('-', '_')
  return AUTONOMY_ACTIONS.includes(candidate) ? candidate : fallback
}

function autonomyPlaceCandidates(context = {}) {
  return Array.isArray(context.placeCandidates)
    ? context.placeCandidates.filter(place => place?.id && place?.name).slice(0, 10)
    : []
}

function placeByKind(places, kinds) {
  return places.find(place => kinds.includes(place.kind)) || null
}

function mobilityChoiceFromContext(context = {}) {
  const mobility = context.mobilityContext || {}
  const dock = mobility.nearestDock || null
  const targetDistance = Number(context.targetDistance || 0)
  const dockDistance = Number(dock?.distanceMeters ?? Infinity)
  const bikes = Number(dock?.numBikesAvailable || 0)
  const scooters = Number(dock?.numScootersAvailable || 0)
  const rideAllowed = mobility.geofence?.rideAllowed !== false
  const disrupted = /station_peak|school_release/i.test(mobility.activeDisruption?.id || '')
  if (!dock || !rideAllowed || dockDistance > 95 || targetDistance < 260 || targetDistance > 1200) return null
  if (disrupted && scooters > 0) {
    return {
      action: 'use_shared_scooter',
      targetPlaceId: context.scheduledTargetId || '',
      targetPlaceName: context.scheduledTargetName || '',
      targetKind: context.scheduledTargetKind || '',
      reason: `${dock.name} has scooters available and the current mobility context favours a short dock-to-dock ride`,
      mobilityMode: 'shared-scooter',
      mobilitySource: 'GBFS station_status + SmartCities geofence',
    }
  }
  if (bikes > 0) {
    return {
      action: 'use_shared_bike',
      targetPlaceId: context.scheduledTargetId || '',
      targetPlaceName: context.scheduledTargetName || '',
      targetKind: context.scheduledTargetKind || '',
      reason: `${dock.name} has bikes available within ${Math.round(dockDistance)}m, so a docked bike is more believable than wandering on foot`,
      mobilityMode: 'shared-bike',
      mobilitySource: 'GBFS station_status + SmartCities geofence',
    }
  }
  if (scooters > 0) {
    return {
      action: 'use_shared_scooter',
      targetPlaceId: context.scheduledTargetId || '',
      targetPlaceName: context.scheduledTargetName || '',
      targetKind: context.scheduledTargetKind || '',
      reason: `${dock.name} has scooters available and the geofence allows riding`,
      mobilityMode: 'shared-scooter',
      mobilitySource: 'GBFS station_status + SmartCities geofence',
    }
  }
  return null
}

function mobilityContextText(context = {}) {
  const mobility = context.mobilityContext || {}
  const dock = mobility.nearestDock
  const curb = mobility.nearestCurbZone
  const flow = mobility.trafficFlow
  const geofence = mobility.geofence
  const disruption = mobility.activeDisruption
  return [
    dock
      ? `nearest GBFS dock ${dock.name}, ${Math.round(dock.distanceMeters)}m away, bikes ${dock.numBikesAvailable}, scooters ${dock.numScootersAvailable}`
      : 'no nearby GBFS dock',
    curb
      ? `nearest SmartCities curb ${curb.purpose} on ${curb.roadName}, ${Math.round(curb.distanceMeters)}m away`
      : 'no nearby curb rule',
    flow
      ? `TrafficFlowObserved ${flow.roadName}: ${flow.congestionLevel}, ${flow.averageVehicleSpeedKph} kph`
      : 'traffic flow unknown',
    geofence
      ? `geofence ${geofence.id}: rideAllowed=${geofence.rideAllowed}, max ${geofence.maxSpeedKph} kph`
      : 'no active geofence',
    disruption
      ? `GATSim event ${disruption.id}: ${disruption.policy}`
      : 'no active GATSim event',
  ].join('; ')
}

function fallbackAutonomyChoice(agent, context = {}) {
  const places = autonomyPlaceCandidates(context)
  const forcedAction = normalizeAutonomyAction(context.forceAction, '')
  const forcedPlace = places.find(place => place.id === context.forceTargetPlaceId) || null
  const mobilityChoice = mobilityChoiceFromContext(context)
  if (forcedAction) {
    return {
      action: forcedAction,
      targetPlaceId: forcedPlace?.id || context.forceTargetPlaceId || context.scheduledTargetId || '',
      targetPlaceName: forcedPlace?.name || context.forceTargetPlaceName || context.scheduledTargetName || '',
      targetKind: forcedPlace?.kind || context.forceTargetKind || context.scheduledTargetKind || '',
      mobilityMode: forcedAction === 'use_shared_bike' ? 'shared-bike' : forcedAction === 'use_shared_scooter' ? 'shared-scooter' : mobilityChoice?.mobilityMode || '',
      mobilitySource: mobilityChoice?.mobilitySource || 'debug scenario selected mobility action',
      reason: 'debug scenario selected a concrete executable affordance',
    }
  }

  const needs = agent?.needs || {}
  if (Number(needs.hunger) > 0.82) {
    const place = placeByKind(places, ['cafe', 'retail', 'leisure', 'transit'])
    return {
      action: 'start_need_errand',
      targetPlaceId: place?.id || '',
      targetPlaceName: place?.name || '',
      targetKind: place?.kind || 'cafe',
      reason: 'hunger pressure is high enough to interrupt the routine',
    }
  }
  if (Number(needs.energy) < 0.22) {
    const place = placeByKind(places, ['park', 'cafe', 'leisure'])
    return {
      action: 'start_need_errand',
      targetPlaceId: place?.id || '',
      targetPlaceName: place?.name || '',
      targetKind: place?.kind || 'park',
      reason: 'energy is low enough to seek a rest stop',
    }
  }
  if (Number(needs.social) < 0.18) {
    return {
      action: 'social_check_in',
      targetPlaceId: '',
      targetPlaceName: '',
      targetKind: '',
      reason: 'social need is low enough to look for a conversation',
    }
  }
  if (mobilityChoice) return mobilityChoice
  if (Number(context.targetDistance) > 520) {
    return {
      action: 'hail_taxi',
      targetPlaceId: context.scheduledTargetId || '',
      targetPlaceName: context.scheduledTargetName || '',
      targetKind: context.scheduledTargetKind || '',
      reason: 'scheduled destination is far enough for road-based mobility',
    }
  }
  if (/blocked|replan|stuck/i.test(agent?.routeStatus || '')) {
    return {
      action: 'replan_route',
      targetPlaceId: context.scheduledTargetId || '',
      targetPlaceName: context.scheduledTargetName || '',
      targetKind: context.scheduledTargetKind || '',
      reason: 'route status suggests short-sighted movement needs repair',
    }
  }
  return {
    action: 'continue_schedule',
    targetPlaceId: context.scheduledTargetId || '',
    targetPlaceName: context.scheduledTargetName || '',
    targetKind: context.scheduledTargetKind || '',
    reason: 'no stronger affordance is more useful than the daily schedule',
  }
}

export async function askLocalAutonomy(agent, context = {}) {
  const needText = agent.needs
    ? `energy ${Math.round(agent.needs.energy * 100)}, hunger ${Math.round(agent.needs.hunger * 100)}, social ${Math.round(agent.needs.social * 100)}`
    : 'needs unknown'
  const cognition = agent.cognition || {}
  const policy = cognition.selectedPolicy?.label || cognition.selectedPolicy?.id || 'daily routine'
  const memory = agent.memories?.[0]?.text || cognition.reflection?.text || agent.currentIntent || 'following routine'
  const places = autonomyPlaceCandidates(context)
  const fallbackChoice = fallbackAutonomyChoice(agent, context)
  const forcedAction = normalizeAutonomyAction(context.forceAction, '')
  const placeList = places.length
    ? places.map(place => `${place.id}: ${place.name} (${place.kind})${place.address ? ` / ${place.address}` : ''}`).join('\n')
    : 'none'
  const schema = {
    thought: 'short Korean private thought',
    action: AUTONOMY_ACTIONS.join(' | '),
    targetPlaceId: 'one listed place id or empty string',
    targetKind: 'place kind or empty string',
    mobilityMode: 'walk | taxi | shared-bike | shared-scooter | empty string',
    reason: 'short reason grounded in needs, memory, schedule, or social norms',
  }
  const system = [
    'You are the private thought layer for one autonomous NPC in RealCity.',
    'Return one-line JSON only. No markdown.',
    'Choose exactly one executable action the simulator can run in the next few city minutes.',
    'Stay grounded in the NPC job, needs, memory, current place, schedule, traffic, GBFS dock availability, SmartCities curb/geofence rules, and social norms.',
    'Use shared-bike or shared-scooter only when the listed GBFS dock has available vehicles and the geofence allows riding.',
    'Use hail_taxi only from a legal curb or taxi-stand context when the destination is too far for walking or micromobility.',
    `JSON schema: ${JSON.stringify(schema)}`,
  ].join('\n')
  const user = [
    `${agent.name}, ${agent.age}, ${agent.gender}, ${agent.job}.`,
    `Personality: ${agent.personality}; speech: ${agent.speechStyle?.label || 'natural'}.`,
    `Current place/activity: ${agent.placeName}, ${agent.activity}.`,
    `Needs: ${needText}.`,
    `Policy: ${policy}.`,
    `Memory: ${String(memory).slice(0, 140)}.`,
    `Scheduled destination: ${context.scheduledTargetName || 'unknown'} (${Math.round(Number(context.targetDistance) || 0)}m).`,
    `City context: ${context.timeLabel || 'unknown time'}, ${context.placeContext || 'normal city life'}.`,
    `Mobility context: ${mobilityContextText(context)}.`,
    `Candidate places:\n${placeList}`,
    `Simulator fallback affordance: ${fallbackChoice.action} / ${fallbackChoice.targetPlaceName || fallbackChoice.targetKind || 'no target'} / ${fallbackChoice.mobilityMode || 'no mobility mode'} / ${fallbackChoice.reason}.`,
  ].join('\n')
  const completion = await completeLocal({
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: user },
    ],
    text: `${system}\n\n${user}`,
  }, { temperature: 0.2, maxTokens: 110, purpose: 'npc-autonomy', agentName: agent.name, json: true, timeoutMs: 42000 })
  const parsed = extractJson(completion.text)
  const fallback = `${agent.name} keeps following ${agent.autonomy?.dailyGoal || agent.currentIntent || 'the daily routine'} near ${agent.placeName}.`
  const thought = cleanPlanText(parsed?.thought || completion.text, fallback, 150)
  const action = forcedAction || normalizeAutonomyAction(parsed?.action, fallbackChoice.action)
  const targetById = places.find(place => place.id === (forcedAction ? fallbackChoice.targetPlaceId : parsed?.targetPlaceId)) ||
    places.find(place => place.id === fallbackChoice.targetPlaceId) ||
    null
  const targetByKind = places.find(place => place.kind === (forcedAction ? fallbackChoice.targetKind : parsed?.targetKind)) ||
    places.find(place => place.kind === fallbackChoice.targetKind) ||
    null
  const target = targetById || targetByKind
  return {
    ok: completion.ok,
    text: styleNpcSpeech(agent, thought),
    action,
    targetPlaceId: target?.id || fallbackChoice.targetPlaceId || '',
    targetPlaceName: target?.name || fallbackChoice.targetPlaceName || parsed?.targetPlaceName || '',
    targetKind: target?.kind || parsed?.targetKind || fallbackChoice.targetKind || '',
    mobilityMode: cleanPlanText(parsed?.mobilityMode, fallbackChoice.mobilityMode || '', 48),
    mobilitySource: fallbackChoice.mobilitySource || (context.mobilityContext ? 'runtime mobility context' : ''),
    mobilityContext: context.mobilityContext || null,
    reason: cleanPlanText(parsed?.reason, fallbackChoice.reason, 150),
    parsed: !!parsed,
    parsedAction: normalizeAutonomyAction(parsed?.action, ''),
    forcedAction: forcedAction || null,
    source: completion.ok ? 'local-llm-autonomy' : `fallback:${completion.source}`,
    provider,
    model,
    latencyMs: completion.latencyMs,
    error: completion.error || null,
    responsePreview: completion.text ? completion.text.slice(0, 180) : null,
  }
}

function extractJson(text) {
  if (!text) return null
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i)
  const raw = fenced ? fenced[1] : text
  const start = raw.indexOf('{')
  const end = raw.lastIndexOf('}')
  if (start < 0 || end <= start) return null
  try {
    return JSON.parse(raw.slice(start, end + 1))
  } catch {
    return null
  }
}

function includesToken(text, tokens) {
  return tokens.some(token => token && text.includes(token.toLowerCase()))
}

function normalizeText(value) {
  return String(value || '')
    .toLowerCase()
    .normalize('NFKC')
    .replace(/[^a-z0-9가-힣]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function containsCandidate(text, candidate) {
  if (!candidate) return false
  const numericCandidate = /^\s*\d/.test(candidate)
  if (!numericCandidate) return text.includes(candidate)

  let index = text.indexOf(candidate)
  while (index >= 0) {
    const before = index > 0 ? text[index - 1] : ''
    const after = text[index + candidate.length] || ''
    if (!/[a-z0-9]/i.test(before) && !/[a-z0-9]/i.test(after)) return true
    index = text.indexOf(candidate, index + 1)
  }
  return false
}

export function includesPlaceCandidate(request, values) {
  const raw = String(request || '').toLowerCase()
  const normalized = normalizeText(request)
  return values.some(value => {
    if (!value) return false
    const candidate = String(value).toLowerCase()
    const normalizedCandidate = normalizeText(value)
    return containsCandidate(raw, candidate) || (normalizedCandidate && containsCandidate(normalized, normalizedCandidate))
  })
}

export function matchRequestedPlace(request, places = []) {
  const list = Array.isArray(places) ? places : []

  for (const place of list) {
    if (includesPlaceCandidate(request, [place.address])) return place
  }

  for (const place of list) {
    const candidates = [place.id, place.name, place.kind, place.district, place.buildingType]
    if (includesPlaceCandidate(request, candidates)) return place
  }

  const text = String(request || '').toLowerCase()
  for (const group of PLACE_ALIASES) {
    if (!includesToken(text, group.aliases)) continue
    const byId = list.find(place => place.id === group.id)
    if (byId) return byId
  }

  for (const place of list) {
    if (includesPlaceCandidate(request, [place.roadName])) return place
  }

  return null
}

function distanceTo(place, context) {
  if (!place || typeof place.x !== 'number' || typeof place.z !== 'number') return 0
  const player = context.player || {}
  if (typeof player.x !== 'number' || typeof player.z !== 'number') return 0
  return Math.hypot(place.x - player.x, place.z - player.z)
}

function fallbackActionPlan(agent, request, context = {}) {
  const text = String(request || '').toLowerCase()
  const targetPlace = matchRequestedPlace(request, context.places)
  const wantsWork = /work|office|workplace|job|\uc9c1\uc7a5|\ud68c\uc0ac|\uadfc\ubb34|\uc77c\ud558\ub294/.test(text)
  const wantsEscort = /guide|take|lead|escort|bring|drive|walk|go to|\ub370\ub824|\uc548\ub0b4|\uac19\uc774|\ub530\ub77c|\uac00\uc790/.test(text)
  const wantsTaxi = /taxi|cab|car|ride|drive|\ud0dd\uc2dc|\ucc28|\uc2b9\ucc28|\ud0dc\uc6cc/.test(text)
  const asksIdentity = /who|name|job|work|identity|\ub204\uad6c|\uc774\ub984|\uc9c1\uc5c5/.test(text)
  const namedAddress = targetPlace && includesPlaceCandidate(request, [targetPlace.address, targetPlace.roadName])
  const asksLocation = /where|location|address|street|road|\uc5b4\ub514|\uc704\uce58|\uc8fc\uc18c|\ub3c4\ub85c\uba85|\uae38|\ub85c/.test(text)

  if (targetPlace && (wantsEscort || wantsTaxi || asksLocation || namedAddress)) {
    const tripDistance = distanceTo(targetPlace, context)
    const mode = wantsTaxi || tripDistance > 420 ? 'taxi' : 'walk'
    const label = targetPlace.address || targetPlace.name
    return {
      intent: 'escort_to_place',
      decision: 'accept',
      mode,
      destination: 'named_place',
      targetPlaceId: targetPlace.id || '',
      targetPlaceName: targetPlace.name || label || 'requested place',
      speech: styleNpcSpeech(agent, mode === 'taxi'
        ? `${label}까지 데려다드릴게요. 길가로 나가서 택시를 잡고 같이 이동하죠.`
        : `${label}까지 안내할게요. 제 뒤를 따라오세요.`),
      steps: mode === 'taxi'
        ? ['Move to the nearest curb', 'Hail a taxi', `Ride with the player to ${label}`, 'Confirm arrival at the entrance']
        : ['Confirm the destination', `Walk toward ${label}`, 'Stop at the entrance and brief the player'],
    }
  }

  if (wantsWork || (wantsEscort && /work|office|job|\uc9c1\uc7a5|\ud68c\uc0ac/.test(text))) {
    const far = typeof context.distanceToWork === 'number' && context.distanceToWork > 260
    const mode = wantsTaxi || far ? 'taxi' : 'walk'
    return {
      intent: 'escort_to_work',
      decision: 'accept',
      mode,
      destination: 'work',
      targetPlaceId: agent.workId || '',
      targetPlaceName: agent.workName || 'workplace',
      speech: styleNpcSpeech(agent, mode === 'taxi'
        ? `제 일터는 ${agent.workName || '근처'}입니다. 택시를 불러서 같이 가죠.`
        : `제 일터는 ${agent.workName || '근처'}입니다. 따라오시면 걸어서 안내할게요.`),
      steps: mode === 'taxi'
        ? ['Move to the nearest curb', 'Hail a taxi', 'Ride together to the workplace', 'Guide the player to the entrance']
        : ['Check that the player is following', 'Walk along the route', 'Stop at the workplace entrance'],
    }
  }

  if (asksIdentity) {
    return {
      intent: 'smalltalk',
      decision: 'answer',
      mode: 'talk',
      destination: 'none',
      targetPlaceId: '',
      targetPlaceName: '',
      speech: styleNpcSpeech(agent, `저는 ${agent.name}, ${agent.job}입니다. 지금은 ${agent.placeName || '이 블록'} 근처에서 ${agent.activity || '이동 중'}이에요.`),
      steps: ['Introduce identity and current activity'],
    }
  }

  return {
    intent: 'clarify',
    decision: 'clarify',
    mode: 'talk',
    destination: 'none',
    targetPlaceId: '',
    targetPlaceName: '',
    speech: styleNpcSpeech(agent, '정확한 장소나 사람을 말해 주세요. 걸어갈지, 택시를 탈지, 더 잘 아는 사람에게 물어볼지 판단할게요.'),
    steps: ['Ask for a clearer destination', 'Choose walking or taxi after the destination is known'],
  }
}

function cleanFallbackActionPlan(agent, request, context = {}) {
  const text = String(request || '').toLowerCase()
  const targetPlace = matchRequestedPlace(request, context.places)
  const wantsWork = /work|office|workplace|job|\uc9c1\uc7a5|\ud68c\uc0ac|\uadfc\ubb34|\uc77c\ud558\ub294/.test(text)
  const wantsEscort = /guide|take|lead|escort|bring|drive|walk|go to|\ub370\ub824|\uc548\ub0b4|\uac19\uc774|\ub530\ub77c|\uac00\uc790/.test(text)
  const wantsTaxi = /taxi|cab|car|ride|drive|\ud0dd\uc2dc|\ucc28|\uc2b9\ucc28|\ud0dc\uc6cc/.test(text)
  const asksIdentity = /who|name|job|work|identity|\ub204\uad6c|\uc774\ub984|\uc9c1\uc5c5/.test(text)
  const namedAddress = targetPlace && includesPlaceCandidate(request, [targetPlace.address, targetPlace.roadName])
  const asksLocation = /where|location|address|street|road|\uc5b4\ub514|\uc704\uce58|\uc8fc\uc18c|\ub3c4\ub85c\uba85|\uae38|\ub85c/.test(text)

  if (targetPlace && (wantsEscort || wantsTaxi || asksLocation || namedAddress)) {
    const tripDistance = distanceTo(targetPlace, context)
    const mode = wantsTaxi || tripDistance > 420 ? 'taxi' : 'walk'
    const label = targetPlace.address || targetPlace.name
    return {
      intent: 'escort_to_place',
      decision: 'accept',
      mode,
      destination: 'named_place',
      targetPlaceId: targetPlace.id || '',
      targetPlaceName: targetPlace.name || label || 'requested place',
      speech: styleNpcSpeech(agent, mode === 'taxi'
        ? `${label}까지 데려다드릴게요. 길가에서 안전하게 택시를 잡고 같이 이동하죠.`
        : `${label}까지 안내할게요. 인도와 횡단보도를 따라오세요.`),
      reasoning: mode === 'taxi'
        ? `${Math.round(tripDistance)}m 거리라 택시 이동이 더 자연스럽습니다.`
        : `${label}은 걸어서 안내할 수 있는 거리입니다.`,
      safety: mode === 'taxi'
        ? '인도에서 기다리고, 택시는 차선 안에 정차한 뒤 탑승합니다.'
        : '차도는 피하고 횡단보도와 인도를 이용합니다.',
      offer: mode === 'taxi'
        ? `${label}까지 택시를 잡아 함께 이동하겠습니다.`
        : `${label} 입구까지 걸어서 안내하겠습니다.`,
      urgency: tripDistance > 420 ? 'normal-far' : 'normal',
      steps: mode === 'taxi'
        ? ['Move to the nearest curb', 'Hail a taxi', `Ride with the player to ${label}`, 'Confirm arrival at the entrance']
        : ['Confirm the destination', `Walk toward ${label}`, 'Stop at the entrance and brief the player'],
    }
  }

  if (wantsWork || (wantsEscort && /work|office|job|\uc9c1\uc7a5|\ud68c\uc0ac/.test(text))) {
    const far = typeof context.distanceToWork === 'number' && context.distanceToWork > 260
    const mode = wantsTaxi || far ? 'taxi' : 'walk'
    const workplace = agent.workName || '제 직장'
    return {
      intent: 'escort_to_work',
      decision: 'accept',
      mode,
      destination: 'work',
      targetPlaceId: agent.workId || '',
      targetPlaceName: workplace,
      speech: styleNpcSpeech(agent, mode === 'taxi'
        ? `제 일터는 ${workplace}입니다. 택시를 불러서 같이 가시죠.`
        : `제 일터는 ${workplace}입니다. 따라오시면 걸어서 안내할게요.`),
      reasoning: far
        ? `직장까지 ${Math.round(context.distanceToWork || 0)}m라 택시가 더 알맞습니다.`
        : '직장까지 걸어서 안내할 수 있는 거리입니다.',
      safety: mode === 'taxi'
        ? '차도에 내려서지 말고 연석 안쪽에서 기다린 뒤 택시가 멈추면 탑승합니다.'
        : '건물 벽을 통과하지 않고 인도와 출입구를 따라 이동합니다.',
      offer: mode === 'taxi'
        ? `${workplace}까지 택시로 동행하겠습니다.`
        : `${workplace} 입구까지 걸어서 동행하겠습니다.`,
      urgency: far ? 'normal-far' : 'normal',
      steps: mode === 'taxi'
        ? ['Move to the nearest curb', 'Hail a taxi', 'Ride together to the workplace', 'Guide the player to the entrance']
        : ['Check that the player is following', 'Walk along the route', 'Stop at the workplace entrance'],
    }
  }

  if (asksIdentity) {
    return {
      intent: 'smalltalk',
      decision: 'answer',
      mode: 'talk',
      destination: 'none',
      targetPlaceId: '',
      targetPlaceName: '',
      speech: styleNpcSpeech(agent, `저는 ${agent.name}, ${agent.job}입니다. 지금은 ${agent.placeName || '이 블록'} 근처에서 ${agent.activity || '이동 중'}이에요.`),
      reasoning: '플레이어가 신원이나 현재 상황을 물었습니다.',
      safety: '대화만 진행하므로 이동을 시작하지 않습니다.',
      offer: '필요하면 목적지를 정한 뒤 안내할 수 있습니다.',
      urgency: 'normal',
      steps: ['Introduce identity and current activity'],
    }
  }

  return {
    intent: 'clarify',
    decision: 'clarify',
    mode: 'talk',
    destination: 'none',
    targetPlaceId: '',
    targetPlaceName: '',
    speech: styleNpcSpeech(agent, '목적지를 조금 더 정확히 말해 주세요. 걸어갈지, 택시를 탈지, 또는 누구에게 물어볼지 같이 정할게요.'),
    reasoning: '요청에 실행 가능한 목적지나 행동이 부족합니다.',
    safety: '불명확한 요청으로 이동을 시작하지 않습니다.',
    offer: '목적지와 이동 방식을 정하면 바로 도와줄 수 있습니다.',
    urgency: 'normal',
    steps: ['Ask for a clearer destination', 'Choose walking or taxi after the destination is known'],
  }
}

function readableFallbackActionPlan(agent, request, context = {}) {
  const text = String(request || '').toLowerCase()
  const targetPlace = matchRequestedPlace(request, context.places)
  const wantsWork = /work|office|workplace|job|직장|회사|근무|일하는/.test(text)
  const wantsEscort = /guide|take|lead|escort|bring|drive|walk|go to|데려|안내|같이|따라|가자/.test(text)
  const wantsTaxi = /taxi|cab|car|ride|drive|택시|차|승차|태워/.test(text)
  const asksIdentity = /who|name|job|work|identity|누구|이름|직업/.test(text)
  const namedAddress = targetPlace && includesPlaceCandidate(request, [targetPlace.address, targetPlace.roadName])
  const asksLocation = /where|location|address|street|road|어디|위치|주소|도로명|길|로/.test(text)

  if (targetPlace && (wantsEscort || wantsTaxi || asksLocation || namedAddress)) {
    const tripDistance = distanceTo(targetPlace, context)
    const mode = wantsTaxi || tripDistance > 420 ? 'taxi' : 'walk'
    const label = targetPlace.address || targetPlace.name
    return {
      intent: 'escort_to_place',
      decision: 'accept',
      mode,
      destination: 'named_place',
      targetPlaceId: targetPlace.id || '',
      targetPlaceName: targetPlace.name || label || 'requested place',
      speech: styleNpcSpeech(agent, mode === 'taxi'
        ? `${label}까지는 택시로 가는 편이 자연스럽습니다. 길가에서 차가 멈출 때까지 기다렸다가 같이 타면 돼요.`
        : `${label}까지 안내할게요. 인도와 횡단보도를 따라가면 됩니다.`),
      reasoning: mode === 'taxi'
        ? `${Math.round(tripDistance)}m 거리라 택시 이동이 더 자연스럽습니다.`
        : `${label}은 걸어서 안내할 수 있는 거리입니다.`,
      safety: mode === 'taxi'
        ? '승객은 인도 쪽에서 기다리고, 택시는 차선 안의 curbside 정차 지점에 멈춘 뒤 탑승합니다.'
        : '차도를 가로지르지 않고 인도와 횡단보도만 사용합니다.',
      offer: mode === 'taxi'
        ? `${label}까지 택시를 잡아 함께 이동하겠습니다.`
        : `${label} 입구까지 걸어서 안내하겠습니다.`,
      urgency: tripDistance > 420 ? 'normal-far' : 'normal',
      steps: mode === 'taxi'
        ? ['Move to the nearest curb', 'Hail a taxi', `Ride with the player to ${label}`, 'Confirm arrival at the entrance']
        : ['Confirm the destination', `Walk toward ${label}`, 'Stop at the entrance and brief the player'],
    }
  }

  if (wantsWork || (wantsEscort && /work|office|job|직장|회사/.test(text))) {
    const far = typeof context.distanceToWork === 'number' && context.distanceToWork > 260
    const mode = wantsTaxi || far ? 'taxi' : 'walk'
    const workplace = agent.workName || '직장'
    return {
      intent: 'escort_to_work',
      decision: 'accept',
      mode,
      destination: 'work',
      targetPlaceId: agent.workId || '',
      targetPlaceName: workplace,
      speech: styleNpcSpeech(agent, mode === 'taxi'
        ? `제 일터는 ${workplace}입니다. 택시가 길가에 멈추면 같이 타고 이동하죠.`
        : `제 일터는 ${workplace}입니다. 따라오시면 인도로 안내할게요.`),
      reasoning: far
        ? `직장까지 ${Math.round(context.distanceToWork || 0)}m라 택시가 더 안전하고 빠릅니다.`
        : '직장까지 걸어서 안내할 수 있는 거리입니다.',
      safety: mode === 'taxi'
        ? '차도로 내려서지 않고 인도 가장자리에서 기다린 뒤, 택시가 완전히 정차하면 탑승합니다.'
        : '건물 벽이나 도로를 가로지르지 않고 보행자 경로를 따라 이동합니다.',
      offer: mode === 'taxi'
        ? `${workplace}까지 택시로 동행하겠습니다.`
        : `${workplace} 입구까지 걸어서 동행하겠습니다.`,
      urgency: far ? 'normal-far' : 'normal',
      steps: mode === 'taxi'
        ? ['Move to the nearest curb', 'Hail a taxi', 'Ride together to the workplace', 'Guide the player to the entrance']
        : ['Check that the player is following', 'Walk along the route', 'Stop at the workplace entrance'],
    }
  }

  if (asksIdentity) {
    return {
      intent: 'smalltalk',
      decision: 'answer',
      mode: 'talk',
      destination: 'none',
      targetPlaceId: '',
      targetPlaceName: '',
      speech: styleNpcSpeech(agent, `저는 ${agent.name}, ${agent.job}입니다. 지금은 ${agent.placeName || '이 블록'} 근처에서 ${agent.activity || '이동 중'}이에요.`),
      reasoning: '플레이어가 신원이나 현재 상황을 물었습니다.',
      safety: '대화만 진행하므로 이동을 시작하지 않습니다.',
      offer: '목적지를 말하면 이동 방법까지 정리해줄 수 있습니다.',
      urgency: 'normal',
      steps: ['Introduce identity and current activity'],
    }
  }

  return {
    intent: 'clarify',
    decision: 'clarify',
    mode: 'talk',
    destination: 'none',
    targetPlaceId: '',
    targetPlaceName: '',
    speech: styleNpcSpeech(agent, '목적지를 조금 더 정확히 말해 주세요. 걸어갈지, 택시를 탈지, 또는 누구에게 물어볼지 같이 정하겠습니다.'),
    reasoning: '요청에 실행 가능한 목적지나 행동이 부족합니다.',
    safety: '불명확한 요청으로 이동을 시작하지 않습니다.',
    offer: '목적지와 이동 방식을 정하면 바로 도와줄 수 있습니다.',
    urgency: 'normal',
    steps: ['Ask for a clearer destination', 'Choose walking or taxi after the destination is known'],
  }
}

function missionFallbackActionPlan(agent, request, context = {}) {
  const text = String(request || '').toLowerCase()
  const targetPlace = matchRequestedPlace(request, context.places)
  const wantsWork = /work|office|workplace|job|직장|회사|근무|일터/.test(text)
  const wantsEscort = /guide|take|lead|escort|bring|drive|walk|go to|데려|안내|같이|따라|가자/.test(text)
  const wantsTaxi = /taxi|cab|car|ride|drive|택시|차|승차|태워/.test(text)
  const asksIdentity = /who|name|job|work|identity|누구|이름|직업/.test(text)
  const namedAddress = targetPlace && includesPlaceCandidate(request, [targetPlace.address, targetPlace.roadName])
  const asksLocation = /where|location|address|street|road|어디|위치|주소|도로명|길|로/.test(text)

  if (targetPlace && (wantsEscort || wantsTaxi || asksLocation || namedAddress)) {
    const tripDistance = distanceTo(targetPlace, context)
    const mode = wantsTaxi || tripDistance > 420 ? 'taxi' : 'walk'
    const label = targetPlace.address || targetPlace.name
    return {
      intent: 'escort_to_place',
      decision: 'accept',
      mode,
      destination: 'named_place',
      targetPlaceId: targetPlace.id || '',
      targetPlaceName: targetPlace.name || label || 'requested place',
      speech: styleNpcSpeech(agent, mode === 'taxi'
        ? `${label}까지 택시로 같이 이동하겠습니다. 길가에서 택시가 완전히 멈출 때까지 기다렸다가 탑승하면 됩니다.`
        : `${label}까지 안내하겠습니다. 인도와 횡단보도를 따라가면 됩니다.`),
      reasoning: mode === 'taxi'
        ? `${Math.round(tripDistance)}m 거리라 택시 이동이 걷는 것보다 안전하고 자연스럽습니다.`
        : `${label}은 걸어서 안내할 수 있는 거리입니다.`,
      safety: mode === 'taxi'
        ? '승객은 인도 안쪽에서 기다리고, 택시는 차선 안의 curbside 정차 지점에 멈춘 뒤 탑승합니다.'
        : '차도를 가로지르지 않고 인도와 횡단보도만 사용합니다.',
      offer: mode === 'taxi'
        ? `${label}까지 택시로 함께 이동하겠습니다.`
        : `${label} 입구까지 걸어서 안내하겠습니다.`,
      urgency: tripDistance > 420 ? 'normal-far' : 'normal',
      steps: mode === 'taxi'
        ? ['Move to the nearest curb', 'Hail a taxi', `Ride with the player to ${label}`, 'Confirm arrival at the entrance']
        : ['Confirm the destination', `Walk toward ${label}`, 'Stop at the entrance and brief the player'],
    }
  }

  if (wantsWork || (wantsEscort && /work|office|job|직장|회사|일터/.test(text))) {
    const far = typeof context.distanceToWork === 'number' && context.distanceToWork > 260
    const mode = wantsTaxi || far ? 'taxi' : 'walk'
    const workplace = agent.workName || '제 직장'
    return {
      intent: 'escort_to_work',
      decision: 'accept',
      mode,
      destination: 'work',
      targetPlaceId: agent.workId || '',
      targetPlaceName: workplace,
      speech: styleNpcSpeech(agent, mode === 'taxi'
        ? `제 일터는 ${workplace}입니다. 택시가 길가에 멈추면 같이 타고 이동하죠.`
        : `제 일터는 ${workplace}입니다. 따라오시면 인도로 안내하겠습니다.`),
      reasoning: far
        ? `직장까지 ${Math.round(context.distanceToWork || 0)}m라 택시가 더 안전하고 빠릅니다.`
        : '직장까지 걸어서 안내할 수 있는 거리입니다.',
      safety: mode === 'taxi'
        ? '차도로 내려서지 않고 인도 가장자리에서 기다린 뒤 택시가 완전히 정차하면 탑승합니다.'
        : '건물 벽이나 도로를 가로지르지 않고 보행자 경로를 따라 이동합니다.',
      offer: mode === 'taxi'
        ? `${workplace}까지 택시로 동행하겠습니다.`
        : `${workplace} 입구까지 걸어서 동행하겠습니다.`,
      urgency: far ? 'normal-far' : 'normal',
      steps: mode === 'taxi'
        ? ['Move to the nearest curb', 'Hail a taxi', 'Ride together to the workplace', 'Guide the player to the entrance']
        : ['Check that the player is following', 'Walk along the route', 'Stop at the workplace entrance'],
    }
  }

  if (asksIdentity) {
    return {
      intent: 'smalltalk',
      decision: 'answer',
      mode: 'talk',
      destination: 'none',
      targetPlaceId: '',
      targetPlaceName: '',
      speech: styleNpcSpeech(agent, `저는 ${agent.name}, ${agent.job}입니다. 지금은 ${agent.placeName || '이 블록'} 근처에서 ${agent.activity || '이동 중'}이에요.`),
      reasoning: '플레이어가 신원이나 현재 상황을 물었습니다.',
      safety: '대화만 진행하므로 이동을 시작하지 않습니다.',
      offer: '목적지를 말하면 이동 방법까지 정리해줄 수 있습니다.',
      urgency: 'normal',
      steps: ['Introduce identity and current activity'],
    }
  }

  return {
    intent: 'clarify',
    decision: 'clarify',
    mode: 'talk',
    destination: 'none',
    targetPlaceId: '',
    targetPlaceName: '',
    speech: styleNpcSpeech(agent, '목적지를 조금 더 정확히 말해 주세요. 걸어갈지, 택시를 탈지, 누구에게 물어볼지 같이 정하겠습니다.'),
    reasoning: '요청에 실행 가능한 목적지나 행동이 부족합니다.',
    safety: '불명확한 요청으로는 이동을 시작하지 않습니다.',
    offer: '목적지와 이동 방식을 정하면 바로 도와줄 수 있습니다.',
    urgency: 'normal',
    steps: ['Ask for a clearer destination', 'Choose walking or taxi after the destination is known'],
  }
}

function resolvePlanPlace(plan, request, places = []) {
  if (!plan || plan.destination !== 'named_place') return null
  const list = Array.isArray(places) ? places : []
  const id = typeof plan.targetPlaceId === 'string' ? plan.targetPlaceId.trim() : ''
  if (id) {
    const byId = list.find(place => place.id === id)
    if (byId) return byId
  }

  const name = typeof plan.targetPlaceName === 'string' ? plan.targetPlaceName.trim().toLowerCase() : ''
  if (name) {
    const normalizedName = normalizeText(name)
    const byName = list.find(place => [place.name, place.kind, place.id, place.address, place.roadName, place.district, place.buildingType].some(value => {
      const normalizedValue = normalizeText(value)
      return normalizedValue && (normalizedValue.includes(normalizedName) || normalizedName.includes(normalizedValue))
    }))
    if (byName) return byName
  }

  return matchRequestedPlace(request, list)
}

function planDetails(agent, plan, request, context = {}, resolvedPlace = null) {
  const destinationName = resolvedPlace?.address || resolvedPlace?.name || plan.targetPlaceName || agent.workName || 'the destination'
  const distance = resolvedPlace
    ? distanceTo(resolvedPlace, context)
    : plan.destination === 'work'
      ? context.distanceToWork || 0
      : 0
  const far = distance > 420
  const urgent = /urgent|hurry|quick|fast|急|빨리|급해|서둘/.test(String(request || '').toLowerCase())
  const modeReason = plan.mode === 'taxi'
    ? far
      ? `${Math.round(distance)}m is far enough that a taxi is safer and faster than walking.`
      : 'The player asked for a ride, so the NPC will use a taxi instead of walking.'
    : plan.mode === 'walk'
      ? `${destinationName} is close enough for a sidewalk route.`
      : 'The request is best handled as conversation before movement.'
  const safety = plan.mode === 'taxi'
    ? 'Wait at the curb, let the taxi stop in the lane, board only after it arrives, and follow the road route.'
    : plan.mode === 'walk'
      ? 'Stay on sidewalks, use crosswalks at road crossings, and avoid cutting through buildings or traffic lanes.'
      : 'Clarify the request before committing to movement or transport.'
  const offer = plan.mode === 'taxi'
    ? `I can call a taxi and ride with you to ${destinationName}.`
    : plan.mode === 'walk'
      ? `I can walk with you to ${destinationName} and stop at the entrance.`
      : 'I can answer first, then help choose a destination or transport option.'

  return {
    reasoning: modeReason,
    safety,
    offer,
    urgency: urgent ? 'urgent' : far ? 'normal-far' : 'normal',
  }
}

const MOJIBAKE_PATTERN = /[�源뚯앹몃곕뺥吏紐媛醫蹂諛濡湲鍮]|[?]{2,}/u

function cleanPlanText(value, fallback, maxLength = 150) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  const candidate = text && !MOJIBAKE_PATTERN.test(text) ? text : fallback
  return String(candidate || '').slice(0, maxLength)
}

function cleanPlanSpeech(agent, value, fallback) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  const candidate = text && !MOJIBAKE_PATTERN.test(text) ? text : fallback
  return styleNpcSpeech(agent, candidate)
}

export async function planLocalNPCAction(agent, request, context = {}) {
  const places = Array.isArray(context.places) ? context.places : []
  const safe = missionFallbackActionPlan(agent, request, context)
  const schema = {
    speech: 'short Korean sentence spoken by the NPC',
    reasoning: 'short private reason',
    safety: 'one concrete safety or social norm',
    offer: 'what the NPC offers to do',
    urgency: 'low | normal | urgent | normal-far',
  }

  const importantPlaces = []
  const pushPlace = place => {
    if (place && !importantPlaces.some(item => item.id === place.id)) importantPlaces.push(place)
  }
  pushPlace(places.find(place => place.id === safe.targetPlaceId))
  pushPlace(places.find(place => place.id === agent.workId))
  places.filter(place => includesPlaceCandidate(request, [place.id, place.name, place.address, place.roadName, place.kind])).slice(0, 5).forEach(pushPlace)
  places.slice(0, 8).forEach(pushPlace)

  const knownPlaces = importantPlaces
    .slice(0, 10)
    .map(place => `${place.id}: ${place.name} (${place.kind})${place.address ? ` at ${place.address}` : ''}`)
    .join('\n')
  const cognitionBrief = [
    agent.cognition?.selectedPolicy?.label ? `Policy: ${agent.cognition.selectedPolicy.label}` : null,
    agent.cognition?.reflection?.text ? `Reflection: ${agent.cognition.reflection.text.slice(0, 150)}` : null,
    agent.memories?.[0]?.text ? `Memory: ${agent.memories[0].text.slice(0, 120)}` : null,
  ].filter(Boolean).join('\n')

  const system = [
    'Return one-line JSON only. No markdown.',
    'You are a fast local-LLM personality layer for one autonomous NPC in RealCity.',
    'The simulator already made an executable candidate plan; you only add NPC speech and short rationale.',
    'JSON schema:',
    JSON.stringify(schema),
    'Use Korean for speech, reasoning, safety, and offer.',
    'Safety must mention sidewalk, curb, taxi, road, crosswalk, or lane.',
  ].join('\n')

  const user = [
    `NPC ${agent.name}: ${agent.age} ${agent.gender}, ${agent.job}, ${agent.personality}, ${agent.speechStyle?.label || 'natural'}.`,
    `Now: ${agent.activity} at ${agent.placeName}.`,
    cognitionBrief,
    `Candidate: ${safe.mode} / ${safe.destination} / ${safe.targetPlaceName || safe.targetPlaceId || 'none'} / ${safe.offer || safe.reasoning}`,
    `Known places: ${knownPlaces || 'none'}`,
    `Player request: ${request}`,
  ].join('\n')

  const completion = await completeLocal({
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: user },
    ],
    text: `${system}\n\n${user}`,
  }, { temperature: 0.12, maxTokens: 50, purpose: 'npc-action-plan', agentName: agent.name, timeoutMs: 18000 })

  const parsed = extractJson(completion.text)
  const parsedExecutable = parsed ? {
    ...safe,
    ...parsed,
    intent: typeof parsed.intent === 'string' ? parsed.intent : safe.intent,
    decision: typeof parsed.decision === 'string' ? parsed.decision : safe.decision,
    mode: typeof parsed.mode === 'string' ? parsed.mode : safe.mode,
    destination: typeof parsed.destination === 'string' ? parsed.destination : safe.destination,
    targetPlaceId: typeof parsed.targetPlaceId === 'string' && parsed.targetPlaceId ? parsed.targetPlaceId : safe.targetPlaceId,
    targetPlaceName: typeof parsed.targetPlaceName === 'string' && parsed.targetPlaceName ? parsed.targetPlaceName : safe.targetPlaceName,
    steps: Array.isArray(parsed.steps) && parsed.steps.length ? parsed.steps : safe.steps,
  } : null
  const parsedPlace = resolvePlanPlace(parsedExecutable, request, places)
  const safePlace = resolvePlanPlace(safe, request, places)
  const safeAddressExact = safePlace?.address && includesPlaceCandidate(request, [safePlace.address])
  const parsedMatchesSafeAddress = parsedPlace?.id && safePlace?.id && parsedPlace.id === safePlace.id
  const safeAcceptsRoute = safe.decision === 'accept' && safe.destination !== 'none'
  const parsedCanRoute = parsedExecutable && (
    parsedExecutable.destination === 'work' ||
    parsedExecutable.destination === 'home' ||
    parsedExecutable.destination === 'third' ||
    (parsedExecutable.destination === 'named_place' && parsedPlace)
  )
  const plan = safeAddressExact && !parsedMatchesSafeAddress
    ? safe
    : parsedCanRoute || !safeAcceptsRoute ? (parsedExecutable || safe) : safe
  const resolvedPlace = resolvePlanPlace(plan, request, places)
  const details = planDetails(agent, plan, request, context, resolvedPlace)
  const source = parsed
    ? (plan === safe ? 'local-llm+fallback-route' : 'local-llm+sim-route')
    : completion.ok ? 'local-llm-unparsed+fallback' : `fallback:${completion.source}`

  return {
    intent: typeof plan.intent === 'string' ? plan.intent : safe.intent,
    decision: ['accept', 'clarify', 'decline', 'answer'].includes(plan.decision) ? plan.decision : safe.decision,
    mode: ['walk', 'taxi', 'talk'].includes(plan.mode) ? plan.mode : safe.mode,
    destination: ['work', 'home', 'third', 'named_place', 'none'].includes(plan.destination) ? plan.destination : safe.destination,
    targetPlaceId: resolvedPlace?.id || (typeof plan.targetPlaceId === 'string' ? plan.targetPlaceId : safe.targetPlaceId || ''),
    targetPlaceName: resolvedPlace?.name || (typeof plan.targetPlaceName === 'string' ? plan.targetPlaceName : safe.targetPlaceName || ''),
    speech: cleanPlanSpeech(agent, plan.speech, safe.speech),
    reasoning: cleanPlanText(plan.reasoning, details.reasoning, 170),
    safety: cleanPlanText(plan.safety, details.safety, 170),
    offer: cleanPlanText(plan.offer, details.offer, 150),
    urgency: ['low', 'normal', 'urgent', 'normal-far'].includes(plan.urgency) ? plan.urgency : details.urgency,
    steps: Array.isArray(plan.steps) && plan.steps.length
      ? plan.steps.slice(0, 5).map(step => String(step).slice(0, 90))
      : safe.steps,
    source,
    llm: {
      provider,
      model,
      endpoint,
      ok: completion.ok,
      source: completion.source,
      parsed: !!parsed,
      latencyMs: completion.latencyMs,
      error: completion.error || null,
      responsePreview: completion.text ? completion.text.slice(0, 180) : null,
    },
  }
}

function cleanFallbackLine(agent) {
  const place = agent.placeName || '이 블록'
  const lines = {
    banker: `${place} 쪽 자금 흐름이 오늘 꽤 바쁩니다. 다음 미팅 전까지 시장 분위기를 보고 있어요.`,
    doctor: '병원은 바쁘지만 아직 통제되고 있어요. 조용히 10분만 쉬어도 다시 움직일 수 있겠습니다.',
    teacher: '수업 사이에 잠깐 쉬는 중이에요. 오늘 학생들이 꽤 활기차네요.',
    courier: '교통은 거칠지만 배송 시간은 기다려주지 않죠. 다음 경유지로 가는 중입니다.',
    barista: '주문이 계속 밀리고 있어요. 아침에는 도시 전체가 조금 더 빠르게 움직이네요.',
    engineer: '인도 쪽 센서 흐름이 조금 이상합니다. 이 블록에서 작은 변화가 생긴 것 같아요.',
    artist: '지금 건물 유리와 빛이 좋아요. 오늘 밤 작업에 쓸 아이디어가 떠오릅니다.',
    security: '사람 흐름만 봐도 상황이 보입니다. 이 시간대에는 주 출입구가 특히 붐벼요.',
    student: '수업 전에 주변을 둘러보고 있어요. 오늘은 평소보다 조금 바쁜 하루예요.',
    shopkeeper: '사람들을 오래 보면 시장의 흐름이 느껴집니다. 오늘은 손님이 조금 빠르게 움직여요.',
    gardener: '바람이 건조하네요. 오후 전에 공원 나무들에 물을 줘야 할 것 같습니다.',
    retiree: '이 길은 매일 걷습니다. 천천히 걸어도 빠른 거리에서는 못 보는 게 보여요.',
  }
  return styleNpcSpeech(agent, lines[agent.role] || `${place} 근처에 있어요. 오늘 RealCity는 평소보다 조금 빠르게 움직이는 느낌입니다.`)
}

export function fallbackLine(agent) {
  return cleanFallbackLine(agent)
}
