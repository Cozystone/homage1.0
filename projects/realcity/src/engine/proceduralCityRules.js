const TAU = Math.PI * 2

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function smoothstep(edge0, edge1, value) {
  const t = clamp((value - edge0) / Math.max(0.0001, edge1 - edge0), 0, 1)
  return t * t * (3 - 2 * t)
}

function fract(value) {
  return value - Math.floor(value)
}

function signedNoise(x, z) {
  return fract(Math.sin(x * 12.9898 + z * 78.233) * 43758.5453) * 2 - 1
}

function fbm(x, z) {
  let value = 0
  let amp = 0.56
  let freq = 0.0038
  for (let octave = 0; octave < 4; octave += 1) {
    value += signedNoise(x * freq, z * freq) * amp
    freq *= 2.03
    amp *= 0.52
  }
  return value
}

export const PROCEDURAL_CITY_SOURCE_MODEL = {
  source: 'RealCity procedural-city-rule-port',
  compatibleReferences: [
    'magnificus/Procedural-Cities MIT: heatmap road growth, branch pressure, plot subdivision, sidewalk decorations',
  ],
  conceptOnlyReferences: [
    'phiresky/procedural-cities AGPL: L-system global goals and local constraints, no code copied',
    'aljanue/Procedural-City-Blender-Addon no visible license: density/vehicle-control concepts only',
  ],
  rules: [
    'noise-weighted growth heatmap',
    'radial and raster district patterns',
    'block subdivision pressure',
    'sidewalk furniture spacing',
    'parcel density and height gradients',
  ],
}

export function cityGrowthHeat(x, z) {
  const distance = Math.hypot(x, z)
  const core = 1 - smoothstep(160, 760, distance)
  const midRing = smoothstep(160, 430, distance) * (1 - smoothstep(620, 960, distance))
  const waterfront = 1 - smoothstep(80, 310, Math.abs(z + 530 + Math.sin(x * 0.006) * 36))
  const transitSpine = 1 - smoothstep(0, 260, Math.min(Math.abs(x + 300), Math.abs(x - 230)))
  const ridge = Math.max(0, Math.sin((x + z) * 0.0065) * 0.32)
  const organic = fbm(x + 170, z - 230)
  return clamp(core * 0.54 + midRing * 0.24 + waterfront * 0.16 + transitSpine * 0.12 + ridge + organic * 0.18, 0, 1)
}

export function roadGrowthProfile({ axis, coordinate, index, isMain, half, spacing }) {
  const sampleX = axis === 'x' ? 0 : coordinate
  const sampleZ = axis === 'x' ? coordinate : 0
  const heat = cityGrowthHeat(sampleX, sampleZ)
  const normalized = clamp((coordinate + half) / Math.max(1, half * 2), 0, 1)
  const radialWave = Math.sin((normalized * TAU) + (axis === 'x' ? 0.45 : 1.25))
  const localConstraint = 1 - smoothstep(0.65, 1, Math.abs(coordinate) / Math.max(1, half))
  const branchPressure = clamp((isMain ? 0.58 : 0.28) + heat * 0.34 + Math.max(0, radialWave) * 0.13, 0, 1)
  const turnBias = clamp(signedNoise(index * 11.7, coordinate * 0.07) * 0.18 + radialWave * 0.08, -0.28, 0.28)
  const pattern = isMain
    ? Math.abs(coordinate) < spacing * 1.5
      ? 'civic-radial-spine'
      : heat > 0.58
        ? 'arterial-growth-spine'
        : 'regional-grid-spine'
    : heat > 0.62
      ? 'dense-lot-local'
      : Math.abs(radialWave) > 0.58
        ? 'branching-neighborhood-local'
        : 'quiet-grid-local'

  return {
    source: 'magnificus-mit-heatmap-growth-port',
    pattern,
    heat: Number(heat.toFixed(3)),
    branchPressure: Number(branchPressure.toFixed(3)),
    turnBias: Number(turnBias.toFixed(3)),
    localConstraint: Number(localConstraint.toFixed(3)),
    trafficDemand: Number(clamp(0.82 + heat * 0.35 + (isMain ? 0.18 : -0.04), 0.72, 1.38).toFixed(3)),
    suggestedStepLength: Number((spacing * (isMain ? 1.12 : 0.92) * clamp(0.9 + heat * 0.18, 0.88, 1.08)).toFixed(2)),
    rule: 'global heatmap goal plus local edge constraint, held axis-aligned for current lane/taxi solver stability',
  }
}

export function sidewalkDecorationPlan(road, index) {
  const heat = road.growth?.heat ?? cityGrowthHeat(road.axis === 'x' ? 0 : road.x, road.axis === 'x' ? road.z : 0)
  const main = !!road.main
  return {
    treeSpacing: Number(clamp(main ? 28 - heat * 4 : 22 - heat * 5, 14, 30).toFixed(1)),
    lampSpacing: Number(clamp(main ? 24 - heat * 3 : 28 - heat * 2, 18, 32).toFixed(1)),
    hydrantEveryMeters: main ? 92 : 128,
    benchChance: Number(clamp(0.12 + heat * 0.28 + (main ? 0.08 : 0), 0.08, 0.48).toFixed(3)),
    planterChance: Number(clamp(0.18 + heat * 0.22, 0.12, 0.42).toFixed(3)),
    seed: `${road.id}_${index}`,
    source: 'magnificus-mit-sidewalk-info-port',
  }
}

export function blockGrowthPlan(x, z, district, rng) {
  const heat = cityGrowthHeat(x, z)
  const distance = Math.hypot(x, z)
  const districtId = district?.id || 'outer'
  const centerBias = 1 - smoothstep(120, 780, distance)
  const parcelNoise = signedNoise(x * 0.21 + 17, z * 0.21 - 9)
  const subdivisionPressure = clamp(heat * 0.62 + centerBias * 0.26 + (parcelNoise + 1) * 0.08, 0, 1)
  const greenChance = clamp(0.02 + (1 - heat) * 0.08 + (districtId === 'outer' ? 0.08 : 0), 0.02, 0.18)
  const roll = rng()
  const landUse = roll < greenChance && distance > 260 ? 'green-pocket' : heat > 0.62 ? 'dense-mixed' : districtId === 'outer' ? 'residential-neighborhood' : 'mixed-block'
  const parcelCount = landUse === 'green-pocket'
    ? 0
    : districtId === 'core'
      ? 1 + Math.floor(rng() * 2)
      : districtId === 'outer'
        ? 2 + Math.floor(rng() * 3)
        : 1 + Math.floor(rng() * 3 + subdivisionPressure)
  const heightMultiplier = clamp(0.82 + heat * 0.54 + (districtId === 'core' ? 0.3 : districtId === 'outer' ? -0.24 : 0), 0.58, 1.78)
  const footprintScale = clamp(0.84 + subdivisionPressure * 0.24 - (parcelCount > 2 ? 0.08 : 0), 0.72, 1.16)
  return {
    source: 'magnificus-mit-plotbuilder-port',
    conceptModel: 'heatmap density plus local parcel subdivision',
    pattern: heat > 0.64 ? 'dense-raster' : distance < 360 ? 'civic-radial' : districtId === 'outer' ? 'branching-residential' : 'mixed-grid',
    landUse,
    heat: Number(heat.toFixed(3)),
    subdivisionPressure: Number(subdivisionPressure.toFixed(3)),
    parcelCount,
    heightMultiplier: Number(heightMultiplier.toFixed(3)),
    footprintScale: Number(footprintScale.toFixed(3)),
    setbackBias: Number(clamp(0.9 - heat * 0.16 + (districtId === 'outer' ? 0.12 : 0), 0.7, 1.08).toFixed(3)),
    facadeDensityBias: Number(clamp(0.9 + heat * 0.26, 0.82, 1.18).toFixed(3)),
    publicRealm: landUse === 'green-pocket'
      ? 'pocket-park'
      : heat > 0.58
        ? 'active-frontage'
        : 'quiet-frontage',
  }
}

export function chooseBuildingTypeForPlan(district, plan, rng) {
  if (district?.id === 'core') return 'skyscraper'
  if (district?.type === 'house') return plan.heat > 0.52 && rng() > 0.68 ? 'apartment' : 'house'
  if (district?.type === 'apartment') return rng() > 0.42 || plan.heat > 0.6 ? 'apartment' : 'office'
  if (plan.heat > 0.72 && rng() > 0.22) return 'office'
  return rng() > 0.52 ? 'office' : 'apartment'
}
