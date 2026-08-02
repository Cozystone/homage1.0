function distance2d(a, b) {
  return Math.hypot(Number(a?.x || 0) - Number(b?.x || 0), Number(a?.z || 0) - Number(b?.z || 0))
}

function phaseFor(timeMinutes = 0) {
  const hour = (((Number(timeMinutes) || 0) / 60) % 24 + 24) % 24
  if (hour < 6) return { id: 'late-night', label: 'Late night', expected: 'quiet returns' }
  if (hour < 9) return { id: 'morning', label: 'Morning', expected: 'commute wave' }
  if (hour < 12) return { id: 'workday', label: 'Workday', expected: 'scheduled arrivals' }
  if (hour < 15) return { id: 'midday', label: 'Midday', expected: 'lunch movement' }
  if (hour < 18) return { id: 'afternoon', label: 'Afternoon', expected: 'shift changes' }
  if (hour < 22) return { id: 'evening', label: 'Evening', expected: 'third-place traffic' }
  return { id: 'night', label: 'Night', expected: 'homebound flow' }
}

function expectedForKind(kind, phase) {
  const table = {
    transit: { morning: 'platform arrivals', evening: 'return transfers', night: 'last connections' },
    cafe: { morning: 'coffee queue', midday: 'lunch crowd', evening: 'meetups' },
    retail: { afternoon: 'errands', evening: 'window shopping' },
    leisure: { evening: 'social arrivals', night: 'late visitors' },
    school: { morning: 'class arrivals', afternoon: 'dismissal flow' },
    hospital: { workday: 'shift rounds', night: 'quiet triage' },
    finance: { workday: 'office traffic', afternoon: 'client exits' },
    logistics: { morning: 'loading wave', afternoon: 'dispatch turnover' },
    park: { morning: 'walkers', evening: 'after-work pause' },
  }
  return table[kind]?.[phase.id] || phase.expected
}

function mostCommon(values, fallback) {
  const counts = new Map()
  for (const value of values.filter(Boolean)) counts.set(value, (counts.get(value) || 0) + 1)
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || fallback
}

function finiteNumber(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function sampleMatchesPlace(sample, place, radius) {
  if (!sample || !place) return false
  if (sample.placeName === place.name || sample.targetName === place.name || sample.taxiTargetName === place.name) return true
  return Number.isFinite(Number(sample.x)) && Number.isFinite(Number(sample.z)) && distance2d(sample, place) <= radius
}

function flowForSample(sample, place) {
  const targetName = sample.targetName || sample.taxiTargetName || place.name
  const distanceToTarget = finiteNumber(sample.distanceToTarget, Infinity)
  const routeMode = sample.routeMode || ''

  if (sample.travelMode === 'taxi') return `taxi to ${targetName}`
  if (sample.state === 'crossing' || routeMode === 'crossing') return `crosswalk to ${targetName}`
  if (routeMode && routeMode !== 'dwelling') return `walking to ${targetName}`
  if (sample.placeName === place.name || distanceToTarget <= 8) return `on-site at ${place.name}`
  if (sample.targetName === place.name || sample.taxiTargetName === place.name) return `inbound to ${place.name}`
  return `near ${place.name}`
}

function etaForSample(sample) {
  const distanceToTarget = finiteNumber(sample.distanceToTarget, 0)
  if (distanceToTarget <= 8) return 'arrived'
  const metersPerMinute = sample.travelMode === 'taxi' ? 320 : 76
  return `~${Math.max(1, Math.round(distanceToTarget / metersPerMinute))} min`
}

export function placeRhythmFor(place, pedestrianSamples = [], timeMinutes = 0) {
  if (!place) {
    return {
      phase: 'unknown',
      status: 'No place selected',
      expected: 'no rhythm',
      total: 0,
      inbound: 0,
      onSite: 0,
      topActivity: 'quiet',
      examples: [],
    }
  }

  const phase = phaseFor(timeMinutes)
  const radius = Math.max(90, Math.min(190, (place.radius || 22) * 3.4))
  const related = pedestrianSamples
    .filter(sample => sampleMatchesPlace(sample, place, radius))
    .sort((a, b) => distance2d(a, place) - distance2d(b, place))

  const inbound = related.filter(sample =>
    sample.travelMode === 'taxi' ||
    (sample.routeMode && sample.routeMode !== 'dwelling') ||
    Number(sample.distanceToTarget || 0) > 8
  )
  const onSite = related.filter(sample =>
    sample.routeMode === 'dwelling' ||
    sample.placeName === place.name ||
    Number(sample.distanceToTarget || 0) <= 8
  )
  const topActivity = mostCommon(
    related.map(sample => sample.scheduleActivity || sample.state),
    expectedForKind(place.kind, phase),
  )

  return {
    phase: phase.id,
    phaseLabel: phase.label,
    expected: expectedForKind(place.kind, phase),
    status: `${phase.label} ${expectedForKind(place.kind, phase)}`,
    total: related.length,
    inbound: inbound.length,
    onSite: onSite.length,
    topActivity,
    radius,
    examples: related.slice(0, 3).map(sample => ({
      id: sample.id,
      name: sample.name || sample.id,
      job: sample.job || sample.role || 'resident',
      activity: sample.scheduleActivity || sample.state || 'moving',
      flow: flowForSample(sample, place),
      eta: etaForSample(sample),
      intent: sample.currentIntent || sample.routeStatus || sample.targetName || place.name,
      routeStatus: sample.routeStatus || null,
      distance: Math.round(distance2d(sample, place)),
    })),
  }
}

export function buildPlaceRhythms(city, pedestrianSamples = [], timeMinutes = 0) {
  return [...(city?.landmarks || [])]
    .map(place => ({ place, rhythm: placeRhythmFor(place, pedestrianSamples, timeMinutes) }))
    .filter(item => item.rhythm.total > 0)
    .sort((a, b) => (b.rhythm.inbound + b.rhythm.onSite + b.rhythm.total * 0.2) - (a.rhythm.inbound + a.rhythm.onSite + a.rhythm.total * 0.2))
    .slice(0, 5)
}
