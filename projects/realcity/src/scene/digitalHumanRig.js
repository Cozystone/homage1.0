function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function hashValue(value) {
  let hash = 0
  const text = String(value || '')
  for (let i = 0; i < text.length; i += 1) hash = (hash * 31 + text.charCodeAt(i)) >>> 0
  return hash
}

const ARCHETYPE_MORPHS = {
  tall_narrow: { chest: 0.94, waist: 0.9, hip: 0.92, limb: 1.06, thickness: 0.92, foot: 1.04 },
  compact_sturdy: { chest: 1.1, waist: 1.08, hip: 1.08, limb: 0.96, thickness: 1.11, foot: 0.98 },
  average_relaxed: { chest: 1, waist: 1.03, hip: 1.02, limb: 1, thickness: 1.02, foot: 1 },
  long_legged: { chest: 0.98, waist: 0.94, hip: 0.96, limb: 1.1, thickness: 0.95, foot: 1.06 },
  broad_shouldered: { chest: 1.14, waist: 1.02, hip: 1.0, limb: 0.99, thickness: 1.08, foot: 1.03 },
  slight_quick: { chest: 0.9, waist: 0.88, hip: 0.9, limb: 1.03, thickness: 0.88, foot: 0.96 },
  soft_round: { chest: 1.06, waist: 1.15, hip: 1.13, limb: 0.97, thickness: 1.12, foot: 1.0 },
}

export const DIGITAL_HUMAN_SOURCE = {
  base: 'makehuman-cc0-parametric-digital-human',
  assetSource: 'makehumancommunity/makehuman-assets',
  license: 'CC0-1.0 assets; MakeHuman source code not copied',
  meshStatus: 'procedural runtime rig now, GLB mesh replacement ready when LFS assets are available',
  sharedBaseRule: 'NPCs and player use the same humanoid skeleton proportions; NPC identity is expressed through morph dimensions, face cues, clothing, age, and gait.',
}

export function makeHumanStyleRig(agent, look = agent?.appearance || {}) {
  const morph = ARCHETYPE_MORPHS[look.bodyArchetype] || ARCHETYPE_MORPHS.average_relaxed
  const age = Number(agent?.age || 34)
  const senior = look.ageBand === 'senior' || age >= 60
  const young = look.ageBand === 'young' || age < 24
  const gender = agent?.gender || 'person'
  const genderShoulder = gender === 'man' ? 1.035 : gender === 'woman' ? 0.965 : 1
  const genderHip = gender === 'woman' ? 1.06 : gender === 'man' ? 0.98 : 1
  const seed = hashValue(`${agent?.id || 'agent'}_${look.signature || ''}`)
  const asymmetry = ((seed % 100) / 100 - 0.5) * 0.012

  const heightScale = clamp(look.heightScale || 1, 0.84, 1.22)
  const bodyScale = clamp(look.bodyScale || 1, 0.82, 1.24)
  const shoulderScale = clamp((look.shoulderScale || 1) * genderShoulder, 0.76, 1.28)
  const legScale = clamp((look.legScale || 1) * morph.limb * (senior ? 0.97 : young ? 1.02 : 1), 0.82, 1.32)
  const headScale = clamp((look.headScale || 1) * (young ? 1.035 : senior ? 1.015 : 1), 0.88, 1.16)
  const chestWidth = clamp(shoulderScale * morph.chest * (0.98 + bodyScale * 0.04), 0.72, 1.36)
  const waistWidth = clamp(shoulderScale * morph.waist * (0.94 + bodyScale * 0.08), 0.68, 1.28)
  const hipWidth = clamp(shoulderScale * morph.hip * genderHip * (0.92 + bodyScale * 0.08), 0.72, 1.34)
  const torsoDepth = clamp(morph.waist * (0.92 + bodyScale * 0.08), 0.78, 1.24)
  const limbThickness = clamp(morph.thickness * (0.96 + bodyScale * 0.06), 0.82, 1.22)
  const armLength = clamp(morph.limb * (senior ? 0.98 : 1), 0.88, 1.14)
  const faceWidth = clamp(headScale * (0.98 + asymmetry), 0.86, 1.18)
  const faceDepth = clamp(headScale * (1.02 - asymmetry), 0.88, 1.18)

  return {
    source: DIGITAL_HUMAN_SOURCE.base,
    archetype: look.bodyArchetype || 'average_relaxed',
    ageBand: look.ageBand || 'adult',
    heightScale,
    bodyScale,
    shoulderScale,
    legScale,
    headScale,
    chestWidth,
    waistWidth,
    hipWidth,
    torsoDepth,
    limbThickness,
    armThickness: clamp(limbThickness * (gender === 'man' ? 1.04 : 0.97), 0.8, 1.22),
    legThickness: clamp(limbThickness * (gender === 'woman' ? 0.98 : 1.02), 0.82, 1.24),
    handScale: clamp(0.96 + limbThickness * 0.05 + (gender === 'man' ? 0.04 : 0), 0.9, 1.12),
    footScale: clamp(morph.foot * (heightScale > 1.06 ? 1.04 : 1), 0.88, 1.16),
    armLength,
    faceWidth,
    faceDepth,
    neckScale: clamp(0.94 + shoulderScale * 0.07 + (senior ? -0.02 : 0), 0.9, 1.1),
    eyeSpacing: clamp(faceWidth * (gender === 'woman' ? 0.98 : 1.02), 0.88, 1.12),
    browWidth: clamp(faceWidth * (senior ? 1.06 : 1), 0.88, 1.16),
    postureLean: senior ? 0.025 : young ? -0.01 : 0,
    stanceWidth: clamp(hipWidth * 0.96 + shoulderScale * 0.04, 0.78, 1.26),
    summary: `${look.bodyArchetype || 'average_relaxed'}:${(heightScale * 100).toFixed(0)}:${(chestWidth * 100).toFixed(0)}:${(hipWidth * 100).toFixed(0)}`,
  }
}
