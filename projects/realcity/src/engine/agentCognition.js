const MEMORY_HALF_LIFE_MS = 1000 * 60 * 4

export const NPC_COGNITION_ARCHITECTURE = {
  id: 'realcity-generative-gobt-v1',
  label: 'Generative memory/reflection/planning with utility-scored behavior-tree execution',
  modules: [
    'observation',
    'memory-stream',
    'recency-importance-relevance-retrieval',
    'reflection',
    'utility-goal-selection',
    'behavior-tree-execution',
    'pathfinding-steering-collision-avoidance',
    'social-norm-compliance',
  ],
  researchBasis: [
    'Park et al. 2023 generative agents: memory stream, reflection, planning',
    'Hu et al. 2024/2025 LLM game agents survey: memory, reasoning, perception-action, communication',
    'Zeng et al. 2024 city navigation: perceive, reflect, plan to avoid short-sighted repeated movement',
    'Hong et al. 2023 GOBT: utility and GOAP-style decisions inside behavior trees',
    'Ren et al. 2024 CRSEC: norms represented and incorporated into agent planning',
    'Reynolds 1999 steering: locomotion/path following stays below high-level goals',
  ],
}

function nowMs() {
  return typeof performance !== 'undefined' ? performance.now() : Date.now()
}

function clamp(value, min = 0, max = 1) {
  return Math.max(min, Math.min(max, value))
}

function words(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9가-힣\s-]/g, ' ')
    .split(/\s+/)
    .filter(token => token.length > 2)
}

function relevanceScore(memory, context) {
  const memoryWords = new Set(words(`${memory?.text || ''} ${memory?.placeName || ''} ${memory?.kind || ''}`))
  if (!memoryWords.size) return 0
  const contextWords = words([
    context?.activity,
    context?.placeName,
    context?.target?.name,
    context?.target?.activity,
    context?.request,
    context?.partner?.name,
    context?.topic?.label,
    context?.profile?.reason,
  ].filter(Boolean).join(' '))
  if (!contextWords.length) return 0.15
  const hits = contextWords.filter(token => memoryWords.has(token)).length
  return clamp(hits / Math.max(3, contextWords.length), 0, 1)
}

function memoryRecency(memory, currentTime = nowMs()) {
  if (!memory?.time) return 0.28
  const age = Math.max(0, currentTime - memory.time)
  return Math.exp(-age / MEMORY_HALF_LIFE_MS)
}

export function retrieveAgentMemories(agent, context = {}, limit = 4) {
  const currentTime = nowMs()
  return [...(agent?.memories || [])]
    .map(memory => {
      const recency = memoryRecency(memory, currentTime)
      const importance = clamp(Number(memory.weight ?? 0.45), 0, 1)
      const relevance = relevanceScore(memory, context)
      const score = recency * 0.34 + importance * 0.42 + relevance * 0.24
      return {
        kind: memory.kind || 'memory',
        text: String(memory.text || '').slice(0, 150),
        placeName: memory.placeName || null,
        recency: Number(recency.toFixed(3)),
        importance: Number(importance.toFixed(3)),
        relevance: Number(relevance.toFixed(3)),
        score: Number(score.toFixed(3)),
      }
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
}

export function strongestNeed(agent) {
  const needs = agent?.needs || {}
  const candidates = [
    { id: 'hunger', label: 'finding food', value: clamp((Number(needs.hunger) - 0.58) / 0.42) },
    { id: 'energy', label: 'resting or reducing effort', value: clamp((0.42 - Number(needs.energy)) / 0.42) },
    { id: 'social', label: 'checking in with someone', value: clamp((0.42 - Number(needs.social)) / 0.42) },
    { id: 'urgency', label: 'keeping schedule pressure under control', value: clamp((Number(needs.urgency) - 0.58) / 0.42) },
  ]
  return candidates.sort((a, b) => b.value - a.value)[0] || candidates[0]
}

export function scoreAgentUtilities(agent, context = {}) {
  const need = strongestNeed(agent)
  const hasMission = !!agent?.mission || !!agent?.selfTaxi
  const targetDistance = Number(context.targetDistance ?? context.distanceToTarget ?? 0)
  const nearbyAgents = Number(context.nearbyAgents ?? 0)
  const relationshipCount = Number(agent?.relationshipCount || 0)
  const routeBlocked = Number(agent?.blockedContacts || 0) > 3 || /replanning|blocked/i.test(agent?.routeStatus || '')
  const atCrosswalk = /crosswalk/i.test(agent?.walkPlan?.mode || '')
  const profile = context.profile || null

  const scores = [
    {
      id: 'need-detour',
      label: 'Need detour',
      score: profile && !hasMission ? clamp(0.3 + need.value * 0.72) : 0,
      goal: profile ? profile.label : 'none',
      action: 'start_need_errand',
      reason: profile ? `${need.id} pressure makes ${profile.label} more believable than blind schedule following` : 'no strong need profile',
    },
    {
      id: 'social-check-in',
      label: 'Social check-in',
      score: !hasMission && nearbyAgents > 0 ? clamp((0.42 - Number(agent?.needs?.social ?? 0.5)) * 1.8 + relationshipCount * 0.018) : 0,
      goal: 'maintain relationships',
      action: 'talk_to_nearby_agent',
      reason: 'nearby people and low social need can trigger a short conversation',
    },
    {
      id: 'autonomous-taxi',
      label: 'Autonomous taxi',
      score: !hasMission && targetDistance > 520 ? clamp(0.42 + targetDistance / 1800 + Number(agent?.needs?.urgency ?? 0.3) * 0.24) : 0,
      goal: 'reach distant scheduled place without unrealistic walking',
      action: 'hail_cruising_taxi',
      reason: 'long-distance schedule movement should use the road/taxi system',
    },
    {
      id: 'route-repair',
      label: 'Route repair',
      score: !hasMission && routeBlocked ? 0.76 : 0,
      goal: 'recover sidewalk route',
      action: 'replan_sidewalk_route',
      reason: 'blocked contacts or route churn indicate short-sighted movement',
    },
    {
      id: 'norm-compliance',
      label: 'Norm compliance',
      score: atCrosswalk ? 0.68 : 0.18,
      goal: 'obey traffic and pedestrian norms',
      action: 'wait_or_cross_by_signal',
      reason: 'crosswalk behavior is governed by pedestrian signal and traffic state',
    },
    {
      id: 'routine',
      label: 'Daily routine',
      score: hasMission ? 0.12 : clamp(0.62 - need.value * 0.22 + Number(agent?.autonomy?.routineTolerance ?? 0.4) * 0.22),
      goal: agent?.autonomy?.dailyGoal || 'follow schedule',
      action: 'continue_schedule',
      reason: 'default behavior-tree leaf when no stronger utility goal is active',
    },
  ]

  return scores
    .map(item => ({ ...item, score: Number(clamp(item.score).toFixed(3)) }))
    .sort((a, b) => b.score - a.score)
}

function buildReflection(agent, memories, utilities, context = {}) {
  const need = strongestNeed(agent)
  const topMemory = memories[0]
  const topPolicy = utilities[0]
  const place = context.target?.name || agent?.placeName || 'this block'
  const relationship = agent?.lastInteraction?.partnerName
    ? `recently spoke with ${agent.lastInteraction.partnerName}`
    : `${agent?.relationshipCount || 0} known contacts`
  const text = [
    `${agent?.name || 'This NPC'} is ${agent?.activity || 'acting'} near ${place}`,
    `strongest pressure is ${need.label}`,
    topMemory ? `relevant memory: ${topMemory.text}` : 'no strong memory yet',
    `policy: ${topPolicy?.label || 'Daily routine'} because ${topPolicy?.reason || 'routine is stable'}`,
    relationship,
  ].join('; ')

  return {
    text: text.slice(0, 280),
    importance: Number(clamp(0.42 + need.value * 0.28 + (topMemory?.importance || 0) * 0.2 + (topPolicy?.score || 0) * 0.1).toFixed(3)),
    trigger: context.trigger || 'routine',
  }
}

export function buildAgentCognition(agent, context = {}) {
  const target = context.target || null
  const targetDistance = target && agent?.pos
    ? Math.hypot((target.x || 0) - agent.pos.x, (target.z || 0) - agent.pos.z)
    : Number(context.targetDistance || 0)
  const contextWithDistance = {
    ...context,
    activity: context.activity || agent?.activity,
    placeName: context.placeName || agent?.placeName,
    target,
    targetDistance,
  }
  const retrievedMemories = retrieveAgentMemories(agent, contextWithDistance, context.limit || 4)
  const utilityScores = scoreAgentUtilities(agent, contextWithDistance)
  const selectedPolicy = utilityScores[0] || null
  const reflection = buildReflection(agent, retrievedMemories, utilityScores, contextWithDistance)

  return {
    architecture: NPC_COGNITION_ARCHITECTURE,
    observedAt: nowMs(),
    trigger: context.trigger || 'routine',
    targetName: target?.name || null,
    targetDistance: Number(targetDistance.toFixed(2)),
    retrievedMemories,
    reflection,
    utilityScores,
    selectedPolicy,
    executionContract: {
      llmRole: 'high-level speech, intent, reflection, and plan choice',
      gameLoopRole: 'behavior-tree state, route following, taxi dispatch, collision, and animation',
      safetyRule: 'language plans must be grounded into existing city affordances before execution',
    },
  }
}

export function shouldStartNeedErrandFromCognition(agent, profile, cognition) {
  if (!profile || !cognition?.selectedPolicy) return false
  if (cognition.selectedPolicy.id !== 'need-detour') return false
  const tolerance = Number(agent?.autonomy?.routineTolerance ?? 0.5)
  const threshold = clamp(0.58 + tolerance * 0.12, 0.58, 0.72)
  return cognition.selectedPolicy.score >= threshold
}

export function cognitionPromptLines(agent) {
  const cognition = agent?.cognition
  if (!cognition) return ['Cognition: not yet sampled']
  const memories = (cognition.retrievedMemories || [])
    .slice(0, 3)
    .map(memory => `- ${memory.kind}: ${memory.text}`)
    .join('\n')
  const utilities = (cognition.utilityScores || [])
    .slice(0, 4)
    .map(item => `${item.id}:${item.score}`)
    .join(', ')
  return [
    `Cognitive architecture: ${cognition.architecture?.id || NPC_COGNITION_ARCHITECTURE.id}`,
    `Reflection: ${cognition.reflection?.text || 'none'}`,
    `Selected policy: ${cognition.selectedPolicy?.id || 'routine'} (${cognition.selectedPolicy?.reason || 'default'})`,
    `Utility scores: ${utilities || 'none'}`,
    `Retrieved memories:\n${memories || '- none'}`,
  ]
}
