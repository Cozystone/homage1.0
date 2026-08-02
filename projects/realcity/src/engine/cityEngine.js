import { DISTRICT_BLUEPRINT, LANDMARK_BLUEPRINTS, ROAD_TIERS } from './cityBlueprint'
import {
  PROCEDURAL_CITY_SOURCE_MODEL,
  blockGrowthPlan,
  chooseBuildingTypeForPlan,
  roadGrowthProfile,
  sidewalkDecorationPlan,
} from './proceduralCityRules'

const TAU = Math.PI * 2

export const CITY_WORLD_SIZE = 2400
export const CITY_HALF = CITY_WORLD_SIZE / 2
export const CITY_GRID_HALF = 920
export const ROAD_SPACING = 76
export const ROAD_WIDTH = 11
export const TILE_SIZE = 240
export const DAY_MINUTES = 24 * 60
export const CITY_BASE_Y = 0
export const TRAFFIC_SIGNAL_CYCLE_SECONDS = 54
export const TRAFFIC_SIGNAL_YELLOW_SECONDS = 4.5
export const TRAFFIC_SIGNAL_ALL_RED_SECONDS = 2.5
export const TRAFFIC_SIGNAL_LEFT_TURN_SECONDS = 6
export const TRAFFIC_SIGNAL_MIN_GREEN_SECONDS = 12
export const TRAFFIC_SIGNAL_MAX_GREEN_SECONDS = 34
export const BUILDING_ROAD_SETBACK = 8.5

export const SUMO_TL_LOGIC = [
  {
    id: 'x-protected-green',
    kind: 'green',
    duration: 20,
    activeAxis: 'x',
    nextAxis: 'z',
    sumoState: 'GGrr',
    vehicleLinks: { x: 'G', z: 'r' },
    movementLinks: { x: { through: 'G', right: 'G', left: 'g' }, z: { through: 'r', right: 'r', left: 'r' } },
    protectedLeftTurn: { axis: 'x', finalSeconds: TRAFFIC_SIGNAL_LEFT_TURN_SECONDS, priority: 'late-green protected left-turn G window after permissive g' },
    pedestrianLinks: { crossX: 'r', crossZ: 'G' },
    rule: 'east-west through/right vehicles have protected green; left turns start permissive g and become protected G during the late left-turn window; pedestrians may cross north-south roads only before the left-turn window',
  },
  {
    id: 'x-yellow-clearance',
    kind: 'yellow',
    duration: TRAFFIC_SIGNAL_YELLOW_SECONDS,
    activeAxis: 'x',
    nextAxis: 'z',
    sumoState: 'yyrr',
    vehicleLinks: { x: 'y', z: 'r' },
    movementLinks: { x: { through: 'y', right: 'y', left: 'y' }, z: { through: 'r', right: 'r', left: 'r' } },
    pedestrianLinks: { crossX: 'r', crossZ: 'r' },
    rule: 'east-west close vehicles clear; no pedestrian starts',
  },
  {
    id: 'x-all-red-clearance',
    kind: 'all-red',
    duration: TRAFFIC_SIGNAL_ALL_RED_SECONDS,
    activeAxis: null,
    clearingAxis: 'x',
    nextAxis: 'z',
    sumoState: 'rrrr',
    vehicleLinks: { x: 'r', z: 'r' },
    movementLinks: { x: { through: 'r', right: 'r', left: 'r' }, z: { through: 'r', right: 'r', left: 'r' } },
    pedestrianLinks: { crossX: 'r', crossZ: 'r' },
    rule: 'all vehicles hold for intersection clearance; no new pedestrian starts',
  },
  {
    id: 'z-protected-green',
    kind: 'green',
    duration: 20,
    activeAxis: 'z',
    nextAxis: 'x',
    sumoState: 'rrGG',
    vehicleLinks: { x: 'r', z: 'G' },
    movementLinks: { x: { through: 'r', right: 'r', left: 'r' }, z: { through: 'G', right: 'G', left: 'g' } },
    protectedLeftTurn: { axis: 'z', finalSeconds: TRAFFIC_SIGNAL_LEFT_TURN_SECONDS, priority: 'late-green protected left-turn G window after permissive g' },
    pedestrianLinks: { crossX: 'G', crossZ: 'r' },
    rule: 'north-south through/right vehicles have protected green; left turns start permissive g and become protected G during the late left-turn window; pedestrians may cross east-west roads only before the left-turn window',
  },
  {
    id: 'z-yellow-clearance',
    kind: 'yellow',
    duration: TRAFFIC_SIGNAL_YELLOW_SECONDS,
    activeAxis: 'z',
    nextAxis: 'x',
    sumoState: 'rryy',
    vehicleLinks: { x: 'r', z: 'y' },
    movementLinks: { x: { through: 'r', right: 'r', left: 'r' }, z: { through: 'y', right: 'y', left: 'y' } },
    pedestrianLinks: { crossX: 'r', crossZ: 'r' },
    rule: 'north-south close vehicles clear; no pedestrian starts',
  },
  {
    id: 'z-all-red-clearance',
    kind: 'all-red',
    duration: TRAFFIC_SIGNAL_ALL_RED_SECONDS,
    activeAxis: null,
    clearingAxis: 'z',
    nextAxis: 'x',
    sumoState: 'rrrr',
    vehicleLinks: { x: 'r', z: 'r' },
    movementLinks: { x: { through: 'r', right: 'r', left: 'r' }, z: { through: 'r', right: 'r', left: 'r' } },
    pedestrianLinks: { crossX: 'r', crossZ: 'r' },
    rule: 'all vehicles hold for intersection clearance; no new pedestrian starts',
  },
]

export const SMART_MOBILITY_STANDARDS = {
  sumo: {
    reference: 'Eclipse SUMO actuated tlLogic',
    linkOrder: ['x_vehicle_forward', 'x_vehicle_reverse', 'z_vehicle_forward', 'z_vehicle_reverse', 'ped_cross_x', 'ped_cross_z'],
    pedestrianRule: 'pedestrian crossings are modeled as separate controlled links after vehicle links',
    crossingTypes: ['traffic-light', 'priority-zebra', 'uncontrolled-gap'],
    detectorModel: 'SUMO induction-loop-style pressure sensors feed actuated green splits from TrafficFlowObserved intensity, occupancy, headway, and queue estimates',
    leftTurnModel: 'SUMO g/G conflict relationship: left turns are permissive g during protected through green, then become protected G in a 6s late-green window with pedestrian no-start',
  },
  gbfs: {
    reference: 'MobilityData GBFS station_information, station_status, vehicle_types, geofencing_zones',
    updateCadenceSeconds: 20,
    feeds: ['system_information', 'station_information', 'station_status', 'vehicle_types', 'geofencing_zones'],
  },
  smartCities: {
    reference: 'smart-data-models SmartCities / Transportation',
    entities: ['TrafficFlowObserved', 'RoadSegment', 'ParkingSpot', 'BikeHireDockingStation', 'RestrictedTrafficArea'],
  },
  gatsim: {
    reference: 'qiliuchn/GATSim generative-agent transport loop',
    cognitionLoop: ['perceive traffic state', 'retrieve travel memory', 'adapt departure/mode/route', 'reflect after trip'],
  },
}

const ROLE_LIBRARY = [
  { role: 'banker', job: 'Banker', workplace: 'aster_exchange', color: '#2c5f8a', pace: 1.05 },
  { role: 'doctor', job: 'ER Doctor', workplace: 'hanbit_hospital', color: '#e8f4ff', pace: 1.18 },
  { role: 'teacher', job: 'Teacher', workplace: 'mirae_school', color: '#6aa38f', pace: 0.98 },
  { role: 'courier', job: 'Courier', workplace: 'south_depot', color: '#f6b73c', pace: 1.35 },
  { role: 'barista', job: 'Barista', workplace: 'river_cafe', color: '#9b6648', pace: 1.08 },
  { role: 'engineer', job: 'Robotics Engineer', workplace: 'maker_yard', color: '#566d7e', pace: 1.0 },
  { role: 'artist', job: 'Artist', workplace: 'neon_square', color: '#d35f8d', pace: 0.9 },
  { role: 'security', job: 'Station Security', workplace: 'central_station', color: '#28395f', pace: 0.95 },
  { role: 'student', job: 'Student', workplace: 'mirae_school', color: '#536dfe', pace: 1.16 },
  { role: 'shopkeeper', job: 'Shopkeeper', workplace: 'market_lane', color: '#c77d3f', pace: 0.96 },
  { role: 'gardener', job: 'Park Gardener', workplace: 'hill_park', color: '#4f8a4f', pace: 0.86 },
  { role: 'retiree', job: 'Retiree', workplace: 'hill_park', color: '#b7a779', pace: 0.7 },
]

const GIVEN_NAMES = [
  'Minji', 'Hana', 'Joon', 'Sora', 'Doyun', 'Ara', 'Hyun', 'Yujin', 'Noel', 'Mina', 'Taeyang', 'Rin',
  'Eun', 'Garam', 'Iseul', 'Jae', 'Nari', 'Seojin', 'Yuna', 'Haru', 'Dami', 'Ian', 'Miso', 'Rowoon',
]
const FAMILY_NAMES = [
  'Kim', 'Park', 'Lee', 'Choi', 'Jung', 'Seo', 'Han', 'Kang', 'Lim', 'Shin', 'Yoon', 'Moon',
  'Baek', 'Kwon', 'Nam', 'Oh', 'Ryu', 'Hong',
]
const PERSONALITIES = [
  'warm', 'reserved', 'curious', 'direct', 'funny', 'tired', 'ambitious', 'careful', 'restless',
  'patient', 'dry-humored', 'formal', 'soft-spoken', 'street-smart', 'optimistic', 'skeptical',
]

// ATANOR ambassadors: citizens whose mind is the ATANOR engine, rendered in a signature colour so
// the player can pick them out of the crowd. Count is env-overridable; the colour is ATANOR teal.
const ATANOR_AMBASSADORS = Number(import.meta?.env?.VITE_ATANOR_AMBASSADORS ?? 3) || 0
const ATANOR_SIGNATURE_COLOR = '#00e5c0'
const EAST_WEST_STREETS = ['Harbor-ro', 'Depot-gil', 'Aster-daero', 'Market-ro', 'Station-daero', 'Mirae-ro', 'Hanbit-ro', 'Neon-gil', 'Hill-ro']
const NORTH_SOUTH_STREETS = ['Sunset-ro', 'River-ro', 'Civic-daero', 'Jungang-ro', 'Glass-ro', 'School-gil', 'Workshop-ro', 'Garden-ro', 'Coast-ro']

const FASHION_PALETTES = [
  { top: '#2f6f9f', jacket: '#e8f1f4', pants: '#17203a', shoes: '#0d1118', accessory: '#5a3f2f' },
  { top: '#6f3f8f', jacket: '#2b2633', pants: '#1f2937', shoes: '#111827', accessory: '#c59b53' },
  { top: '#3f7d55', jacket: '#d8e0d4', pants: '#2f3a2d', shoes: '#1b201b', accessory: '#704c33' },
  { top: '#ba6a3f', jacket: '#f0d4bd', pants: '#384252', shoes: '#1c1d21', accessory: '#7c3f2f' },
  { top: '#425e80', jacket: '#202833', pants: '#111827', shoes: '#05070a', accessory: '#46515c' },
  { top: '#b84f70', jacket: '#f3dce6', pants: '#3d2430', shoes: '#171217', accessory: '#8b5d35' },
]

const BODY_ARCHETYPES = [
  { id: 'tall_narrow', height: 0.09, shoulder: -0.04, body: -0.03, leg: 0.08, head: -0.02 },
  { id: 'compact_sturdy', height: -0.07, shoulder: 0.08, body: 0.08, leg: -0.04, head: 0.03 },
  { id: 'average_relaxed', height: 0, shoulder: 0, body: 0.03, leg: 0, head: 0 },
  { id: 'long_legged', height: 0.04, shoulder: -0.01, body: -0.02, leg: 0.11, head: -0.01 },
  { id: 'broad_shouldered', height: 0.02, shoulder: 0.13, body: 0.05, leg: -0.02, head: 0 },
  { id: 'slight_quick', height: -0.03, shoulder: -0.08, body: -0.06, leg: 0.05, head: 0.02 },
  { id: 'soft_round', height: -0.02, shoulder: 0.04, body: 0.13, leg: -0.03, head: 0.04 },
]

const WALK_STYLES = [
  { id: 'brisk', cadence: 1.14, stride: 1.08, armSwing: 1.2, speed: 1.06 },
  { id: 'measured', cadence: 0.9, stride: 0.88, armSwing: 0.78, speed: 0.94 },
  { id: 'bouncy', cadence: 1.22, stride: 0.96, armSwing: 1.1, speed: 1.02 },
  { id: 'careful', cadence: 0.82, stride: 0.8, armSwing: 0.66, speed: 0.9 },
  { id: 'long_stride', cadence: 0.96, stride: 1.22, armSwing: 0.95, speed: 1.08 },
  { id: 'hurried', cadence: 1.35, stride: 1.04, armSwing: 1.34, speed: 1.16 },
  { id: 'easygoing', cadence: 0.78, stride: 0.92, armSwing: 0.7, speed: 0.88 },
]

const DAILY_GOALS = {
  banker: ['close a client report', 'check the morning market board', 'meet a colleague near the exchange'],
  doctor: ['finish rounds without delaying triage', 'check on an emergency handoff', 'take a short quiet break after shift'],
  teacher: ['prepare the next class', 'walk students safely across campus', 'grade assignments before evening'],
  courier: ['finish a timed delivery loop', 'avoid late traffic near the depot', 'confirm the next pickup address'],
  barista: ['restock cups before lunch', 'remember a regular customer order', 'close the cafe cleanly tonight'],
  engineer: ['test a street sensor prototype', 'bring parts back to Maker Yard', 'debug a delivery robot route'],
  artist: ['sketch a new facade detail', 'meet friends near Neon Square', 'find good evening light for a mural'],
  security: ['keep station entrances clear', 'watch the crosswalk rush', 'help a lost visitor find the platform'],
  student: ['make it to class on time', 'meet a friend after school', 'study before heading home'],
  shopkeeper: ['open the front display', 'track a delivery from the depot', 'check foot traffic after work'],
  gardener: ['water the hill path planters', 'inspect trees near the road edge', 'clear leaves from a park entrance'],
  retiree: ['take a steady morning walk', 'chat near the park benches', 'buy groceries before sunset'],
}

const RELATIONSHIP_STYLES = ['neighborly', 'private', 'helpful', 'busy-but-kind', 'curious', 'formal', 'chatty', 'practical']

const SPEECH_STYLES = [
  { id: 'polite_brief', label: 'polite and brief', prefix: '네, ', flavor: '짧고 정중하게 말함' },
  { id: 'warm_chatty', label: 'warm and chatty', prefix: '좋아요, ', flavor: '상대 기분을 살피며 부드럽게 말함' },
  { id: 'dry_direct', label: 'dry and direct', prefix: '간단히 말하면, ', flavor: '군더더기 없이 건조하게 말함' },
  { id: 'careful_formal', label: 'careful and formal', prefix: '알겠습니다. ', flavor: '존댓말을 정확하게 쓰고 위험을 먼저 확인함' },
  { id: 'bright_casual', label: 'bright and casual', prefix: '오케이, ', flavor: '가볍고 밝은 톤으로 말함' },
  { id: 'tired_soft', label: 'tired but kind', prefix: '음, ', flavor: '조용하고 느리지만 친절하게 말함' },
  { id: 'street_practical', label: 'street practical', prefix: '바로 보면, ', flavor: '길과 교통을 현실적으로 따져 말함' },
  { id: 'curious_precise', label: 'curious and precise', prefix: '확인해볼게요. ', flavor: '질문을 정리하고 이유를 설명함' },
  { id: 'playful', label: 'playful', prefix: '좋죠. ', flavor: '농담을 살짝 섞어 말함' },
  { id: 'reserved', label: 'reserved', prefix: '가능합니다. ', flavor: '감정을 적게 드러내고 차분하게 말함' },
]

const READABLE_SPEECH_STYLES = [
  { id: 'polite_brief', label: 'polite and brief', prefix: '네.', flavor: '짧고 정중하게 말함' },
  { id: 'warm_chatty', label: 'warm and chatty', prefix: '좋아요.', flavor: '따뜻하고 친근하게 말함' },
  { id: 'dry_direct', label: 'dry and direct', prefix: '간단히 말하면,', flavor: '군더더기 없이 건조하게 말함' },
  { id: 'careful_formal', label: 'careful and formal', prefix: '확인했습니다.', flavor: '위험과 절차를 먼저 확인함' },
  { id: 'bright_casual', label: 'bright and casual', prefix: '좋죠.', flavor: '밝고 가볍게 대답함' },
  { id: 'tired_soft', label: 'tired but kind', prefix: '음,', flavor: '조용하지만 친절하게 말함' },
  { id: 'street_practical', label: 'street practical', prefix: '바로 보면,', flavor: '길과 교통을 현실적으로 짚어 말함' },
  { id: 'curious_precise', label: 'curious and precise', prefix: '확인해볼게요.', flavor: '질문을 정리하고 이유를 설명함' },
  { id: 'playful', label: 'playful', prefix: '좋지.', flavor: '농담을 살짝 섞어 말함' },
  { id: 'reserved', label: 'reserved', prefix: '가능합니다.', flavor: '감정을 작게 드러내며 차분히 말함' },
]

const GESTURE_STYLES = [
  'quick nod', 'hands in pockets', 'checks phone often', 'points while speaking', 'small wave',
  'adjusts bag strap', 'folds arms', 'looks around before answering', 'half-smile', 'formal bow',
]

const OUTFIT_PATTERNS = ['solid', 'two-tone', 'striped', 'layered', 'reflective-trim', 'workwear', 'soft-knit', 'streetwear']
const OUTERWEAR = ['hoodie', 'blazer', 'cardigan', 'vest', 'long coat', 'overshirt', 'utility jacket', 'windbreaker']
const ACCESSORIES = ['none', 'round glasses', 'square glasses', 'scarf', 'earbuds', 'watch', 'lanyard', 'crossbody pouch']
const VOICE_PACES = ['quick', 'measured', 'soft', 'low', 'bright', 'slow', 'crisp', 'breathy']
const VOICE_REGISTERS = ['formal', 'casual', 'practical', 'gentle', 'skeptical', 'warm', 'precise', 'dry']

const LANDMARK_INTERIORS = {
  transit: { width: 64, depth: 30, height: 7.2, doorWidth: 14, lobbyDepth: 25, verticalCore: 'escalator' },
  finance: { width: 30, depth: 30, height: 13.5, doorWidth: 9, lobbyDepth: 24, verticalCore: 'elevator' },
  cafe: { width: 28, depth: 22, height: 7.2, doorWidth: 6, lobbyDepth: 17, verticalCore: 'stairs' },
  hospital: { width: 42, depth: 30, height: 12.8, doorWidth: 12, lobbyDepth: 25, verticalCore: 'elevator' },
  workshop: { width: 30, depth: 24, height: 8.4, doorWidth: 8, lobbyDepth: 20, verticalCore: 'stairs' },
  retail: { width: 34, depth: 24, height: 8.2, doorWidth: 10, lobbyDepth: 20, verticalCore: 'escalator' },
  school: { width: 38, depth: 28, height: 8.6, doorWidth: 10, lobbyDepth: 22, verticalCore: 'stairs' },
  leisure: { width: 36, depth: 28, height: 9, doorWidth: 12, lobbyDepth: 23, verticalCore: 'escalator' },
  logistics: { width: 58, depth: 34, height: 10.8, doorWidth: 13, lobbyDepth: 28, verticalCore: 'stairs' },
}

function mulberry32(seed) {
  let value = seed >>> 0
  return () => {
    value += 0x6d2b79f5
    let t = value
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function pick(rng, list) {
  return list[Math.floor(rng() * list.length)]
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function hslToHex(h, s, l) {
  const hue = ((h % 360) + 360) % 360
  const sat = clamp(s, 0, 100) / 100
  const light = clamp(l, 0, 100) / 100
  const c = (1 - Math.abs(2 * light - 1)) * sat
  const x = c * (1 - Math.abs((hue / 60) % 2 - 1))
  const m = light - c / 2
  const [r1, g1, b1] = hue < 60
    ? [c, x, 0]
    : hue < 120
      ? [x, c, 0]
      : hue < 180
        ? [0, c, x]
        : hue < 240
          ? [0, x, c]
          : hue < 300
            ? [x, 0, c]
            : [c, 0, x]
  const toHex = value => Math.round((value + m) * 255).toString(16).padStart(2, '0')
  return `#${toHex(r1)}${toHex(g1)}${toHex(b1)}`
}

function colorFromHue(h, s = 52, l = 50) {
  return hslToHex(h, s, l)
}

function uniqueName(rng, usedNames, index) {
  for (let tries = 0; tries < 80; tries += 1) {
    const name = `${pick(rng, GIVEN_NAMES)} ${pick(rng, FAMILY_NAMES)}`
    if (!usedNames.has(name)) {
      usedNames.add(name)
      return name
    }
  }
  const fallback = `${GIVEN_NAMES[index % GIVEN_NAMES.length]} ${FAMILY_NAMES[Math.floor(index / GIVEN_NAMES.length) % FAMILY_NAMES.length]} ${index + 1}`
  usedNames.add(fallback)
  return fallback
}

function createSpeechStyle(rng, role, personality, index) {
  const base = READABLE_SPEECH_STYLES[(index + Math.floor(rng() * READABLE_SPEECH_STYLES.length)) % READABLE_SPEECH_STYLES.length]
  const voice = `${pick(rng, VOICE_PACES)} ${pick(rng, VOICE_REGISTERS)}`
  const gesture = GESTURE_STYLES[(index * 3 + Math.floor(rng() * GESTURE_STYLES.length)) % GESTURE_STYLES.length]
  return {
    ...base,
    voice,
    gesture,
    roleBias: role,
    personalityBias: personality,
    signature: `${base.id}-${voice.replace(/\s+/g, '_')}-${gesture.replace(/\s+/g, '_')}-${index}`,
  }
}

function smoothstep(edge0, edge1, x) {
  const t = clamp((x - edge0) / (edge1 - edge0), 0, 1)
  return t * t * (3 - 2 * t)
}

function streetName(axis, index, isMain) {
  const names = axis === 'x' ? EAST_WEST_STREETS : NORTH_SOUTH_STREETS
  const base = names[index % names.length]
  if (isMain && !base.includes('daero')) return base.replace(/-ro|-gil/, '-daero')
  return base
}

function hashNoise(x, z) {
  const n = Math.sin(x * 127.1 + z * 311.7) * 43758.5453123
  return (n - Math.floor(n)) * 2 - 1
}

function fbm(x, z) {
  let value = 0
  let amp = 0.5
  let freq = 0.004
  for (let i = 0; i < 5; i += 1) {
    value += hashNoise(x * freq, z * freq) * amp
    freq *= 2.07
    amp *= 0.52
  }
  return value
}

export function terrainHeight(x, z) {
  const safeX = Number.isFinite(Number(x)) ? Number(x) : 0
  const safeZ = Number.isFinite(Number(z)) ? Number(z) : 40
  const distance = Math.hypot(safeX, safeZ)
  const cityBlend = smoothstep(900, 1160, distance)
  const cityFloor = CITY_BASE_Y + fbm(safeX * 0.1, safeZ * 0.1) * 0.035
  const hills = 4 + Math.max(0, fbm(safeX + 450, safeZ - 250) + 0.5) * 92
  const coastalDip = smoothstep(74, 0, Math.abs(safeZ + 980 + Math.sin(safeX * 0.003) * 40)) * 6
  return cityFloor * (1 - cityBlend) + hills * cityBlend - coastalDip
}

export function terrainTone(x, z) {
  const h = terrainHeight(x, z)
  const distance = Math.hypot(x, z)
  const coastal = Math.abs(z + 980 + Math.sin(x * 0.003) * 40)
  if (coastal < 70) return [0.08, 0.18, 0.25]
  if (distance < 940) return [0.24, 0.245, 0.24]
  if (h > 70) return [0.29, 0.31, 0.28]
  return [0.19, 0.36, 0.22]
}

function axisForRoadId(roadId = '') {
  if (String(roadId).startsWith('ew_')) return 'x'
  if (String(roadId).startsWith('ns_')) return 'z'
  return null
}

function pressureForFlow(flow) {
  if (!flow) return 0
  const intensity = Number(flow.intensity) || 0
  const occupancy = Number(flow.occupancy) || 0
  const queue = Number(flow.queueLengthEstimate) || 0
  const headway = Number(flow.averageHeadwayTime) || 6
  const gap = Number(flow.averageGapDistance) || 40
  return Math.max(0, intensity * 0.46 + occupancy * 0.82 + queue * 0.08 + Math.max(0, 4.8 - headway) * 0.16 + Math.max(0, 32 - gap) * 0.018)
}

export function trafficPressureByAxis(mobilitySystem = null) {
  const flows = mobilitySystem?.smartCity?.trafficFlowObserved || []
  const totals = {
    x: { pressure: 0, flowCount: 0, queueEstimate: 0, maxOccupancy: 0, minHeadway: Infinity },
    z: { pressure: 0, flowCount: 0, queueEstimate: 0, maxOccupancy: 0, minHeadway: Infinity },
  }
  for (const flow of flows) {
    const axis = axisForRoadId(flow.roadId)
    if (!axis) continue
    totals[axis].pressure += pressureForFlow(flow)
    totals[axis].flowCount += 1
    totals[axis].queueEstimate += Number(flow.queueLengthEstimate) || 0
    totals[axis].maxOccupancy = Math.max(totals[axis].maxOccupancy, Number(flow.occupancy) || 0)
    totals[axis].minHeadway = Math.min(totals[axis].minHeadway, Number(flow.averageHeadwayTime) || Infinity)
  }
  for (const axis of ['x', 'z']) {
    if (!totals[axis].flowCount) {
      totals[axis].minHeadway = null
      continue
    }
    totals[axis].pressure = Number((totals[axis].pressure / totals[axis].flowCount).toFixed(3))
    totals[axis].queueEstimate = Number(totals[axis].queueEstimate.toFixed(2))
    totals[axis].maxOccupancy = Number(totals[axis].maxOccupancy.toFixed(2))
    totals[axis].minHeadway = Number(totals[axis].minHeadway.toFixed(2))
  }
  return totals
}

export function actuatedSignalProgram(mobilitySystem = null) {
  const pressure = trafficPressureByAxis(mobilitySystem)
  const xPressure = pressure.x.pressure || 1
  const zPressure = pressure.z.pressure || 1
  const xBias = xPressure - zPressure
  const zBias = -xBias
  const xGreen = clamp(20 + xBias * 5.5 + (pressure.x.queueEstimate || 0) * 0.16, TRAFFIC_SIGNAL_MIN_GREEN_SECONDS, TRAFFIC_SIGNAL_MAX_GREEN_SECONDS)
  const zGreen = clamp(20 + zBias * 5.5 + (pressure.z.queueEstimate || 0) * 0.16, TRAFFIC_SIGNAL_MIN_GREEN_SECONDS, TRAFFIC_SIGNAL_MAX_GREEN_SECONDS)

  return SUMO_TL_LOGIC.map(phase => {
    const duration = phase.id === 'x-protected-green'
      ? xGreen
      : phase.id === 'z-protected-green'
        ? zGreen
        : phase.duration
    return {
      ...phase,
      duration: Number(duration.toFixed(2)),
      baseDuration: phase.duration,
      actuated: phase.kind === 'green',
      detectorPressure: phase.activeAxis ? pressure[phase.activeAxis] : null,
      actuationPolicy: phase.kind === 'green'
        ? {
            mode: 'actuated-detector-pressure',
            minGreenSeconds: TRAFFIC_SIGNAL_MIN_GREEN_SECONDS,
            maxGreenSeconds: TRAFFIC_SIGNAL_MAX_GREEN_SECONDS,
            leftTurnWindowSeconds: TRAFFIC_SIGNAL_LEFT_TURN_SECONDS,
            pressureSignals: ['intensity', 'occupancy', 'averageHeadwayTime', 'averageGapDistance', 'queueLengthEstimate'],
          }
        : null,
    }
  })
}

export function trafficPhaseAt(timeMinutes = 0, mobilitySystem = null) {
  const program = mobilitySystem ? actuatedSignalProgram(mobilitySystem) : SUMO_TL_LOGIC
  const cycle = program.reduce((sum, phase) => sum + phase.duration, 0)
  const second = ((timeMinutes * 60) % cycle + cycle) % cycle
  let elapsed = 0
  for (let index = 0; index < program.length; index += 1) {
    const phase = program[index]
    const nextElapsed = elapsed + phase.duration
    if (second < nextElapsed || index === program.length - 1) {
      const phaseSecond = second - elapsed
      const leftTurnWindowSeconds = phase.kind === 'green'
        ? Math.min(TRAFFIC_SIGNAL_LEFT_TURN_SECONDS, Math.max(0, phase.duration * 0.38))
        : 0
      const leftTurnProtected = !!(phase.protectedLeftTurn && leftTurnWindowSeconds > 0 && phase.duration - phaseSecond <= leftTurnWindowSeconds)
      const movementLinks = phase.movementLinks
        ? {
            x: { ...phase.movementLinks.x },
            z: { ...phase.movementLinks.z },
          }
        : null
      if (movementLinks && leftTurnProtected && phase.activeAxis) {
        movementLinks[phase.activeAxis] = {
          ...movementLinks[phase.activeAxis],
          left: 'G',
        }
      }
      const pedestrianLinks = leftTurnProtected
        ? { crossX: 'r', crossZ: 'r' }
        : phase.pedestrianLinks
      return {
        ...phase,
        index,
        protectedAxis: phase.kind === 'green' ? phase.activeAxis : null,
        phaseSecond,
        cycleSecond: second,
        cycleSeconds: cycle,
        secondsRemaining: Math.max(0, phase.duration - phaseSecond),
        label: phase.id.replaceAll('-', ' '),
        noPedestrianStart: phase.kind !== 'green' || leftTurnProtected,
        movementLinks,
        pedestrianLinks,
        leftTurnWindowSeconds,
        leftTurnProtected,
        protectedLeftTurnAxis: leftTurnProtected ? phase.activeAxis : null,
        movementPriority: leftTurnProtected ? 'protected-left-turn-window' : phase.kind === 'green' ? 'protected-through-permissive-left' : phase.kind,
        pedestrianLinkOrder: SMART_MOBILITY_STANDARDS.sumo.linkOrder.slice(-2),
        signalModel: mobilitySystem ? 'SUMO-inspired actuated tlLogic' : 'SUMO-inspired static tlLogic',
      }
    }
    elapsed = nextElapsed
  }
  return {
    ...program[0],
    index: 0,
    protectedAxis: 'x',
    phaseSecond: 0,
    cycleSecond: 0,
    cycleSeconds: cycle,
    secondsRemaining: program[0].duration,
    label: program[0].id.replaceAll('-', ' '),
    noPedestrianStart: false,
    movementLinks: program[0].movementLinks,
    leftTurnWindowSeconds: 0,
    leftTurnProtected: false,
    protectedLeftTurnAxis: null,
    movementPriority: 'protected-through-permissive-left',
    pedestrianLinkOrder: SMART_MOBILITY_STANDARDS.sumo.linkOrder.slice(-2),
    signalModel: mobilitySystem ? 'SUMO-inspired actuated tlLogic' : 'SUMO-inspired static tlLogic',
  }
}

export function trafficSignalForAxis(axis, timeMinutes = 0, mobilitySystem = null) {
  const phase = trafficPhaseAt(timeMinutes, mobilitySystem)
  if (phase.kind === 'all-red') return 'red'
  if (axis !== phase.activeAxis) return 'red'
  return phase.kind === 'yellow' ? 'yellow' : 'green'
}

export function trafficSignalForMovement(axis, movement = 'through', timeMinutes = 0, mobilitySystem = null) {
  const phase = trafficPhaseAt(timeMinutes, mobilitySystem)
  const normalizedMovement = movement === 'left' ? 'left' : movement === 'right' ? 'right' : 'through'
  const linkState = phase.movementLinks?.[axis]?.[normalizedMovement] || phase.vehicleLinks?.[axis] || 'r'
  const signal = linkState === 'y'
    ? 'yellow'
    : linkState === 'G' || linkState === 'g'
      ? 'green'
      : 'red'
  return {
    signal,
    linkState,
    movement: normalizedMovement,
    priority: linkState === 'G'
      ? normalizedMovement === 'left' && phase.leftTurnProtected
        ? 'protected-left-turn'
        : 'protected-vehicle-link'
      : linkState === 'g'
        ? 'permissive-left-turn-yield-to-foes'
        : signal === 'yellow'
          ? 'yellow-clearance'
          : phase.kind === 'all-red'
            ? 'all-red-clearance'
            : 'stop-or-yield',
    phaseId: phase.id,
    phaseKind: phase.kind,
    sumoState: phase.sumoState,
    leftTurnProtected: !!phase.leftTurnProtected,
    leftTurnWindowSeconds: phase.leftTurnWindowSeconds || 0,
    source: 'SUMO g/G movement-link interpretation',
  }
}

export function pedestrianSignalForAxis(crossedAxis, timeMinutes = 0, mobilitySystem = null) {
  const phase = trafficPhaseAt(timeMinutes, mobilitySystem)
  const vehicleSignal = trafficSignalForAxis(crossedAxis, timeMinutes, mobilitySystem)
  const pedestrianKey = crossedAxis === 'x' ? 'crossX' : 'crossZ'
  const pedestrianLinkState = phase.pedestrianLinks?.[pedestrianKey] || 'r'
  const protectedWalk = pedestrianLinkState === 'G' && phase.kind === 'green' && phase.activeAxis && phase.activeAxis !== crossedAxis && vehicleSignal === 'red'
  const clearance = !protectedWalk && vehicleSignal === 'red' && (phase.kind === 'yellow' || phase.kind === 'all-red')
  return {
    vehicleSignal,
    walk: !!protectedWalk,
    clearance,
    noStart: !protectedWalk,
    pedestrianLinkState,
    secondsRemaining: Number((phase.secondsRemaining || 0).toFixed(2)),
    sourceProgram: mobilitySystem ? 'SUMO_ACTUATED_TL_LOGIC' : 'SUMO_TL_LOGIC',
    signalModel: phase.signalModel,
    phase: phase.kind,
    phaseId: phase.id,
    activeVehicleAxis: phase.activeAxis,
    label: protectedWalk
      ? 'protected walk'
      : clearance
        ? 'clearance wait'
        : vehicleSignal === 'yellow'
          ? 'wait yellow'
          : vehicleSignal === 'green'
            ? 'wait vehicle green'
            : 'wait',
  }
}

function districtAt(x, z) {
  const context = { x, z, distance: Math.hypot(x, z) }
  const district = DISTRICT_BLUEPRINT.find(rule => rule.match(context)) || DISTRICT_BLUEPRINT[DISTRICT_BLUEPRINT.length - 1]
  return {
    id: district.id,
    name: district.name,
    type: district.type,
    activation: district.activation,
  }
}

function roadGrid() {
  const roads = []
  let index = 0
  for (let p = -CITY_GRID_HALF; p <= CITY_GRID_HALF + 1; p += ROAD_SPACING) {
    const isMain = Math.round((p + CITY_GRID_HALF) / ROAD_SPACING) % 4 === 0
    const tier = isMain ? ROAD_TIERS.primary : ROAD_TIERS.local
    const eastWestGrowth = roadGrowthProfile({ axis: 'x', coordinate: p, index, isMain, half: CITY_GRID_HALF, spacing: ROAD_SPACING })
    const northSouthGrowth = roadGrowthProfile({ axis: 'z', coordinate: p, index, isMain, half: CITY_GRID_HALF, spacing: ROAD_SPACING })
    const eastWest = {
      id: `ew_${index}`,
      axis: 'x',
      z: p,
      from: -CITY_GRID_HALF,
      to: CITY_GRID_HALF,
      width: ROAD_WIDTH * tier.widthMultiplier,
      main: isMain,
      tier: tier.id,
      trafficWeight: Number((tier.trafficWeight * eastWestGrowth.trafficDemand).toFixed(3)),
      name: streetName('x', index, isMain),
      growth: eastWestGrowth,
      pattern: eastWestGrowth.pattern,
      sourceAlgorithm: 'heatmap-road-growth-port',
      laneModel: {
        drivingSide: 'right-hand',
        lanesPerDirection: 1,
        positiveDirectionLaneOffset: ROAD_WIDTH * tier.widthMultiplier * 0.27,
        rule: 'positive eastbound traffic uses the south/right lane; negative westbound traffic uses the north/right lane',
        turnLanePolicy: isMain ? 'shared through lane with marked left-turn pocket and right-turn yield area before main intersections' : 'shared local lane, turn signal before side-street turns',
        turnSignalDistanceMeters: isMain ? 52 : 34,
        turnPocketLengthMeters: isMain ? 34 : 18,
      },
      pedestrianPolicy: {
        sidewalks: 'both-sides',
        lanePermission: 'pedestrians-forbidden-except-crossings',
        crossingControl: isMain ? 'traffic-light-on-main-main-crossings' : 'priority-zebra-or-gap-crossing',
        gapAcceptanceSeconds: isMain ? 0 : 4.5,
      },
    }
    const northSouth = {
      id: `ns_${index}`,
      axis: 'z',
      x: p,
      from: -CITY_GRID_HALF,
      to: CITY_GRID_HALF,
      width: ROAD_WIDTH * tier.widthMultiplier,
      main: isMain,
      tier: tier.id,
      trafficWeight: Number((tier.trafficWeight * northSouthGrowth.trafficDemand).toFixed(3)),
      name: streetName('z', index, isMain),
      growth: northSouthGrowth,
      pattern: northSouthGrowth.pattern,
      sourceAlgorithm: 'heatmap-road-growth-port',
      laneModel: {
        drivingSide: 'right-hand',
        lanesPerDirection: 1,
        positiveDirectionLaneOffset: ROAD_WIDTH * tier.widthMultiplier * 0.27,
        rule: 'positive northbound traffic uses the west/right lane; negative southbound traffic uses the east/right lane',
        turnLanePolicy: isMain ? 'shared through lane with marked left-turn pocket and right-turn yield area before main intersections' : 'shared local lane, turn signal before side-street turns',
        turnSignalDistanceMeters: isMain ? 52 : 34,
        turnPocketLengthMeters: isMain ? 34 : 18,
      },
      pedestrianPolicy: {
        sidewalks: 'both-sides',
        lanePermission: 'pedestrians-forbidden-except-crossings',
        crossingControl: isMain ? 'traffic-light-on-main-main-crossings' : 'priority-zebra-or-gap-crossing',
        gapAcceptanceSeconds: isMain ? 0 : 4.5,
      },
    }
    eastWest.sidewalkDecor = sidewalkDecorationPlan(eastWest, index)
    northSouth.sidewalkDecor = sidewalkDecorationPlan(northSouth, index)
    roads.push(eastWest)
    roads.push(northSouth)
    index += 1
  }
  return roads
}

function roadDistanceToPoint(road, x, z) {
  if (road.axis === 'x') {
    const px = clamp(x, road.from, road.to)
    return Math.hypot(x - px, z - road.z)
  }
  const pz = clamp(z, road.from, road.to)
  return Math.hypot(x - road.x, z - pz)
}

function addressInfoForPoint(x, z, roads) {
  let best = roads[0]
  let bestDistance = Infinity
  for (const road of roads) {
    const distance = roadDistanceToPoint(road, x, z)
    if (distance < bestDistance) {
      bestDistance = distance
      best = road
    }
  }
  const along = best.axis === 'x' ? x : z
  const block = Math.max(1, Math.floor((along + CITY_GRID_HALF) / 18) + 1)
  const side = best.axis === 'x'
    ? z >= best.z ? 0 : 1
    : x >= best.x ? 0 : 1
  const number = block * 2 + side
  return {
    address: `${number} ${best.name}`,
    roadId: best.id,
    roadName: best.name,
    addressNumber: number,
  }
}

function entryFaceForPoint(x, z, roadId, roads) {
  const road = roads.find(item => item.id === roadId)
  if (!road) return 'south'
  if (road.axis === 'x') return road.z >= z ? 'north' : 'south'
  return road.x >= x ? 'east' : 'west'
}

function oppositeFace(face) {
  return {
    north: 'south',
    south: 'north',
    east: 'west',
    west: 'east',
  }[face] || 'north'
}

function createFacadePlan(type, form, entryFace, rng, growthPlan = {}) {
  const faces = ['north', 'south', 'east', 'west']
  const densityBias = growthPlan.facadeDensityBias || 1
  const baseDensity = (type === 'skyscraper' ? 0.95 : type === 'office' ? 0.78 : type === 'apartment' ? 0.64 : 0.42) * densityBias
  const rearFace = oppositeFace(entryFace)
  const primaryRhythm = pick(rng, ['regular-grid', 'offset-grid', 'vertical-bands', 'punched-openings'])
  const sideRhythm = pick(rng, ['regular-grid', 'offset-grid', 'vertical-bands', 'punched-openings'])
  const balconyPattern = type === 'apartment'
    ? form.profile === 'balcony_stack'
      ? 'stacked-centered'
      : pick(rng, ['stacked-centered', 'paired-balanced', 'corner-return'])
    : 'none'
  return {
    entryFace,
    rearFace,
    balconyPattern,
    glazingWrap: type === 'skyscraper' ? 'curtain-wall-all-sides' : type === 'office' ? 'mixed-all-sides' : 'residential-all-sides',
    faces: Object.fromEntries(faces.map((face, index) => {
      const role = face === entryFace ? 'front' : face === rearFace ? 'rear' : 'side'
      const roleFactor = role === 'front' ? 1.04 : role === 'rear' ? 0.92 : 0.86
      const density = clamp(baseDensity * roleFactor + (rng() - 0.5) * 0.045, type === 'house' ? 0.24 : 0.34, 1)
      const rhythm = role === 'side' ? sideRhythm : primaryRhythm
      const supportsBalcony = type === 'apartment' && (role === 'front' || (role === 'rear' && balconyPattern !== 'corner-return'))
      return [face, {
        role,
        glazingDensity: density,
        hasWindows: true,
        hasEntry: role === 'front',
        rhythm,
        trim: form.facade,
        balconyBias: supportsBalcony,
        balconyPattern: supportsBalcony ? balconyPattern : 'none',
        pairedWith: face === entryFace ? rearFace : face === rearFace ? entryFace : oppositeFace(face),
        articulation: role === 'front'
          ? 'primary-entry'
          : role === 'rear'
            ? 'service-rear'
            : index % 2 === 0
              ? 'balanced-side-a'
              : 'balanced-side-b',
        urbanPattern: growthPlan.pattern || 'grid',
      }]
    })),
    coherence: {
      frontBackLinked: true,
      sideFacesBalanced: true,
      balconyRule: balconyPattern,
      entryRule: 'street-facing-door',
      sourcePattern: growthPlan.source || 'realcity-procedural-facade',
    },
  }
}

function floorDirectoryFor({ type, kind, floors, zones = [], verticalCore, unitCount = 1, publicAccess = 'public' }) {
  const count = Math.max(1, floors || 1)
  const coreLabel = verticalCore === 'elevator'
    ? 'elevator bank'
    : verticalCore === 'escalator'
      ? 'escalator hall'
      : 'stair core'

  return Array.from({ length: count }, (_, index) => {
    const level = index + 1
    let label = level === 1 ? 'Ground lobby' : `Floor ${level}`
    let zone = zones[index % Math.max(1, zones.length)] || 'tenant space'
    let access = publicAccess

    if (kind === 'hospital') {
      zone = level === 1 ? 'reception and triage' : level === 2 ? 'clinics and imaging' : 'patient rooms and staff stations'
      label = level === 1 ? 'Hospital reception' : `Care floor ${level}`
      access = level === 1 ? 'public care entry' : 'staff guided'
    } else if (kind === 'transit') {
      zone = level === 1 ? 'ticketing and gates' : 'platform concourse and transfers'
      label = level === 1 ? 'Station concourse' : `Transit level ${level}`
      access = 'public transit'
    } else if (kind === 'finance') {
      zone = level === 1 ? 'banking hall and security desk' : level < count ? 'offices and meeting rooms' : 'executive sky lobby'
      label = level === 1 ? 'Bank lobby' : `Office floor ${level}`
      access = level === 1 ? 'public counter' : 'badge controlled'
    } else if (kind === 'logistics') {
      zone = level === 1 ? 'dispatch desk and loading office' : 'secure storage mezzanine'
      label = level === 1 ? 'Depot office' : `Operations floor ${level}`
      access = 'staff and escorted visitors'
    } else if (kind === 'cafe' || kind === 'retail') {
      zone = level === 1 ? 'shopfront and cashier' : 'back office and stock room'
      label = level === 1 ? 'Public shop floor' : `Service floor ${level}`
      access = level === 1 ? 'public retail' : 'staff only'
    } else if (kind === 'school') {
      zone = level === 1 ? 'front office and commons' : 'classrooms and labs'
      label = level === 1 ? 'School commons' : `Learning floor ${level}`
      access = 'school visitors'
    } else if (type === 'house') {
      zone = level === 1 ? 'foyer, living room, and kitchen' : level === count ? 'bedrooms and attic storage' : 'bedrooms and family rooms'
      label = level === 1 ? 'Home ground floor' : `Home floor ${level}`
      access = 'private home'
    } else if (type === 'apartment') {
      zone = level === 1 ? 'mail room, lobby, and resident services' : `${unitCount} apartments and corridor alcoves`
      label = level === 1 ? 'Residential lobby' : `Residential floor ${level}`
      access = level === 1 ? 'residents and guests' : 'resident access'
    } else if (type === 'office' || type === 'skyscraper') {
      zone = level === 1 ? 'entry lobby, reception, and security' : level % 7 === 0 ? 'shared amenity lounge and meeting rooms' : 'tenant offices and service corridor'
      label = level === 1 ? 'Office lobby' : level % 7 === 0 ? `Amenity floor ${level}` : `Tenant floor ${level}`
      access = level === 1 ? 'lobby public' : 'badge controlled'
    }

    return {
      level,
      label,
      zone,
      access,
      core: coreLabel,
      guide: `${coreLabel} connects to ${count} ${count === 1 ? 'floor' : 'floors'}.`,
    }
  })
}

function createBuildingInterior(type, form, w, d, h, entryFace, rng) {
  const floorHeight = type === 'house' ? 3.1 : type === 'apartment' ? 3.35 : 4.05
  const floors = Math.max(1, Math.floor(h / floorHeight))
  const verticalCore = type === 'house'
    ? 'stairs'
    : type === 'apartment'
      ? pick(rng, ['stairs', 'elevator'])
      : pick(rng, ['elevator', 'elevator', 'stairs', 'escalator'])
  const lobbyDepth = clamp(type === 'house' ? d * 0.28 : type === 'apartment' ? d * 0.34 : d * 0.42, 2.4, Math.max(2.4, d - 2))
  const lobbyWidth = clamp(type === 'house' ? w * 0.38 : w * 0.58, 2.8, Math.max(2.8, w - 1.4))
  const unitCount = type === 'house'
    ? 1
    : type === 'apartment'
      ? Math.max(2, Math.floor((w + d) / 8))
      : Math.max(3, Math.floor((w + d) / 7))
  const doorWidth = clamp(type === 'house' ? w * 0.22 : w * 0.3, 1.5, Math.max(1.6, w * 0.58))
  const zones = type === 'house'
    ? ['entry', 'living', 'kitchen', 'bedroom']
    : type === 'apartment'
      ? ['entry lobby', 'mail room', 'residential corridor', 'units']
      : ['entry lobby', 'reception', 'vertical core', 'tenant floors']
  const publicAccess = type === 'office' || type === 'skyscraper' ? 'lobby-public' : type === 'apartment' ? 'residents-and-guests' : 'private-home'
  return {
    entryFace,
    solidWalls: true,
    entryRule: 'front-door-and-lobby',
    floors,
    floorHeight,
    lobbyDepth,
    lobbyWidth,
    doorWidth,
    corridorType: type === 'house' ? 'room-to-room' : form.profile === 'atrium' ? 'atrium-loop' : form.profile === 'bar' ? 'linear-spine' : 'central-core',
    verticalCore,
    publicAccess,
    entryPortal: {
      face: entryFace,
      width: doorWidth,
      rule: 'pass-through-door-only',
    },
    floorNavigation: {
      method: verticalCore,
      reachableFloors: floors,
      floorHeight,
      canChangeFloors: floors > 1,
    },
    zones,
    floorDirectory: floorDirectoryFor({ type, floors, zones, verticalCore, unitCount, publicAccess }),
    unitsPerFloor: unitCount,
    coreOffset: {
      along: (rng() - 0.5) * Math.min(w, d) * 0.24,
      depth: lobbyDepth + 1.8 + rng() * Math.max(1.2, Math.min(w, d) * 0.12),
    },
  }
}

function pointInRoadReserve(x, z, roads, margin = 0) {
  return roads.some(road => {
    if (road.axis === 'x') {
      return x >= road.from - margin && x <= road.to + margin && Math.abs(z - road.z) <= road.width / 2 + margin
    }
    return z >= road.from - margin && z <= road.to + margin && Math.abs(x - road.x) <= road.width / 2 + margin
  })
}

function buildableZoneForBlock(blockX, blockZ, roads) {
  const west = roads
    .filter(road => road.axis === 'z' && road.x < blockX)
    .sort((a, b) => b.x - a.x)[0]
  const east = roads
    .filter(road => road.axis === 'z' && road.x > blockX)
    .sort((a, b) => a.x - b.x)[0]
  const south = roads
    .filter(road => road.axis === 'x' && road.z < blockZ)
    .sort((a, b) => b.z - a.z)[0]
  const north = roads
    .filter(road => road.axis === 'x' && road.z > blockZ)
    .sort((a, b) => a.z - b.z)[0]

  if (!west || !east || !south || !north) return null

  const minX = west.x + west.width / 2 + BUILDING_ROAD_SETBACK
  const maxX = east.x - east.width / 2 - BUILDING_ROAD_SETBACK
  const minZ = south.z + south.width / 2 + BUILDING_ROAD_SETBACK
  const maxZ = north.z - north.width / 2 - BUILDING_ROAD_SETBACK
  const width = maxX - minX
  const depth = maxZ - minZ

  if (width < 18 || depth < 18) return null

  return {
    minX,
    maxX,
    minZ,
    maxZ,
    width,
    depth,
    cx: (minX + maxX) / 2,
    cz: (minZ + maxZ) / 2,
  }
}

function nearestBlockCenterCoord(value) {
  const first = -CITY_GRID_HALF + ROAD_SPACING / 2
  const last = CITY_GRID_HALF - ROAD_SPACING / 2
  const index = Math.round((clamp(value, first, last) - first) / ROAD_SPACING)
  return first + index * ROAD_SPACING
}

function blockReferenceForPoint(x, z) {
  return {
    x: nearestBlockCenterCoord(x),
    z: nearestBlockCenterCoord(z),
  }
}

function landmarkBaseFootprint(place) {
  const base = {
    transit: { width: 68, depth: 31 },
    finance: { width: 32, depth: 32 },
    cafe: { width: 30, depth: 24 },
    hospital: { width: 42, depth: 32 },
    workshop: { width: 32, depth: 25 },
    retail: { width: 36, depth: 25 },
    school: { width: 40, depth: 30 },
    leisure: { width: 38, depth: 30 },
    logistics: { width: 63, depth: 46 },
    park: { width: 68, depth: 68 },
  }[place.kind] || { width: 28, depth: 24 }

  return {
    width: base.width * (place.scale || 1),
    depth: base.depth * (place.scale || 1),
  }
}

function fitFootprintToZone(footprint, zone) {
  if (!zone) return { ...footprint, scale: 1 }
  const maxWidth = zone.width * 0.88
  const maxDepth = zone.depth * 0.88
  const scale = Math.min(1, maxWidth / footprint.width, maxDepth / footprint.depth)
  return {
    width: footprint.width * scale,
    depth: footprint.depth * scale,
    scale,
  }
}

function landmarkInteriorFor(place, footprint) {
  const interior = LANDMARK_INTERIORS[place.kind]
  if (!interior) return null

  const scale = footprint.scale || 1
  const width = Math.max(10, Math.min(interior.width * scale, footprint.width - 2))
  const depth = Math.max(9, Math.min(interior.depth * scale, footprint.depth - 2))
  const doorLimit = Math.max(3.4, width - 4)

  const floorCount = Math.max(1, Math.floor((place.kind === 'finance' ? 9 : place.kind === 'hospital' ? 4 : place.kind === 'logistics' ? 2 : 3) * Math.max(0.72, scale)))
  const lobbyZones = place.kind === 'hospital'
    ? ['reception', 'triage', 'elevator hall', 'waiting']
    : place.kind === 'transit'
      ? ['ticketing', 'platform access', 'escalator hall', 'retail kiosks']
      : place.kind === 'logistics'
        ? ['dispatch desk', 'loading office', 'stairs', 'secure storage']
        : ['reception', 'public lobby', 'vertical core', 'service room']

  return {
    ...interior,
    width,
    depth,
    height: Math.max(5.4, interior.height * Math.max(0.72, scale)),
    doorWidth: Math.min(Math.max(3.8, interior.doorWidth * scale), doorLimit),
    lobbyDepth: Math.min(Math.max(6, interior.lobbyDepth * scale), Math.max(6, depth - 3)),
    entranceSide: 'front',
    solidWalls: true,
    entryRule: 'front-door-only',
    floorCount,
    lobbyZones,
    floorDirectory: floorDirectoryFor({
      kind: place.kind,
      floors: floorCount,
      zones: lobbyZones,
      verticalCore: interior.verticalCore,
      unitCount: Math.max(2, Math.floor((width + depth) / 12)),
      publicAccess: 'public landmark',
    }),
    partitionGrid: place.kind === 'cafe' || place.kind === 'retail' ? 'open-front-retail' : place.kind === 'finance' ? 'secure-core' : 'public-lobby',
  }
}

function landmarkSet(roads) {
  return LANDMARK_BLUEPRINTS.map(place => {
    const blockReference = blockReferenceForPoint(place.x, place.z)
    const zone = buildableZoneForBlock(blockReference.x, blockReference.z, roads)
    const footprint = fitFootprintToZone(landmarkBaseFootprint(place), zone)
    const x = zone
      ? clamp(place.x, zone.minX + footprint.width / 2, zone.maxX - footprint.width / 2)
      : place.x
    const z = zone
      ? clamp(place.z, zone.minZ + footprint.depth / 2, zone.maxZ - footprint.depth / 2)
      : place.z

    return {
      ...place,
      x,
      z,
      y: terrainHeight(x, z),
      radius: Math.max(14, Math.min(footprint.width, footprint.depth) / 2),
      footprint,
      zoning: zone
        ? {
            requested: { x: place.x, z: place.z },
            blockCenter: blockReference,
            buildable: zone,
            roadSetback: BUILDING_ROAD_SETBACK,
            envelopeW: footprint.width,
            envelopeD: footprint.depth,
          }
        : null,
      ...addressInfoForPoint(x, z, roads),
      interior: landmarkInteriorFor(place, footprint),
    }
  })
}

function createBuildings(rng, landmarks, roads) {
  const buildings = []
  const landmarkMask = (x, z) => landmarks.some(place => Math.hypot(x - place.x, z - place.z) < place.radius + 34)
  let id = 0
  const slotSets = {
    1: [{ x: 0, z: 0 }],
    2: [{ x: -0.22, z: -0.16 }, { x: 0.22, z: 0.16 }],
    3: [{ x: -0.24, z: -0.22 }, { x: 0.24, z: -0.22 }, { x: 0, z: 0.24 }],
    4: [{ x: -0.24, z: -0.24 }, { x: 0.24, z: -0.24 }, { x: -0.24, z: 0.24 }, { x: 0.24, z: 0.24 }],
  }

  for (let x = -CITY_GRID_HALF + ROAD_SPACING / 2; x < CITY_GRID_HALF; x += ROAD_SPACING) {
    for (let z = -CITY_GRID_HALF + ROAD_SPACING / 2; z < CITY_GRID_HALF; z += ROAD_SPACING) {
      const distance = Math.hypot(x, z)
      if (distance > 930 || distance < 120 || landmarkMask(x, z)) continue

      const district = districtAt(x, z)
      const growthPlan = blockGrowthPlan(x, z, district, rng)
      if (growthPlan.landUse === 'green-pocket') continue
      const zone = buildableZoneForBlock(x, z, roads)
      if (!zone) continue

      const count = Math.max(1, Math.min(4, growthPlan.parcelCount || 1))
      const slots = slotSets[Math.min(4, count)]

      for (let i = 0; i < count; i += 1) {
        const type = chooseBuildingTypeForPlan(district, growthPlan, rng)
        const slot = slots[i] || slots[0]
        const single = count === 1
        const footprintScale = clamp(growthPlan.footprintScale || 1, 0.72, single ? 1.08 : count === 2 ? 1 : 0.92)
        const maxW = single
          ? zone.width * (type === 'house' ? 0.42 : 0.58) * footprintScale
          : zone.width * (type === 'house' ? 0.28 : 0.32) * footprintScale
        const maxD = single
          ? zone.depth * (type === 'apartment' ? 0.48 : type === 'house' ? 0.42 : 0.56) * footprintScale
          : zone.depth * (type === 'house' ? 0.28 : 0.31) * footprintScale
        const minW = type === 'house' ? 7.2 : 11
        const minD = type === 'house' ? 7.2 : 11
        if (maxW < minW || maxD < minD) continue
        const w = clamp(type === 'house' ? 7.5 + rng() * 6.5 : 12 + rng() * Math.max(7, maxW - 12), minW, maxW)
        const d = clamp(type === 'house' ? 7.5 + rng() * 6.5 : 12 + rng() * Math.max(7, maxD - 12), minD, maxD)
        const jitterX = single ? zone.width * 0.025 : zone.width * 0.015
        const jitterZ = single ? zone.depth * 0.025 : zone.depth * 0.015
        const bx = clamp(zone.cx + slot.x * zone.width + (rng() - 0.5) * jitterX, zone.minX + w * 0.68, zone.maxX - w * 0.68)
        const bz = clamp(zone.cz + slot.z * zone.depth + (rng() - 0.5) * jitterZ, zone.minZ + d * 0.72, zone.maxZ - d * 0.72)
        const base = terrainHeight(bx, bz)
        const baseHeight = type === 'skyscraper'
          ? 44 + rng() * 92
          : type === 'office'
            ? 16 + rng() * 42
            : type === 'apartment'
              ? 10 + rng() * 24
              : 4.5 + rng() * 6.5
        const height = Math.max(type === 'house' ? 3.4 : 5.2, baseHeight * (growthPlan.heightMultiplier || 1))

        const address = addressInfoForPoint(bx, bz, roads)
        const form = createBuildingForm(type, rng, district, growthPlan)
        const entryFace = entryFaceForPoint(bx, bz, address.roadId, roads)

        buildings.push({
          id: `b${id++}`,
          x: bx,
          z: bz,
          y: base,
          ...address,
          w,
          d,
          h: height,
          type,
          district: district.name,
          districtId: district.id,
          rot: 0,
          tint: rng(),
          entryFace,
          facadePlan: createFacadePlan(type, form, entryFace, rng, growthPlan),
          interior: createBuildingInterior(type, form, w, d, height, entryFace, rng),
          growthPlan,
          proceduralSource: {
            model: 'RealCity procedural-city-rule-port',
            compatibleReference: 'magnificus/Procedural-Cities MIT',
            conceptReferences: ['phiresky/procedural-cities AGPL concepts', 'aljanue Blender addon concepts'],
          },
          zoning: {
            blockCenter: { x, z },
            buildable: zone,
            roadSetback: BUILDING_ROAD_SETBACK,
            envelopeW: w * 1.36,
            envelopeD: d * 1.44,
            publicRealm: growthPlan.publicRealm,
            subdivisionPressure: growthPlan.subdivisionPressure,
          },
          form,
        })
      }
    }
  }

  return buildings
}

function createBuildingForm(type, rng, district, growthPlan = {}) {
  if (type === 'house') {
    const profile = growthPlan.heat > 0.55
      ? pick(rng, ['duplex', 'rowhouse', 'courtyard'])
      : pick(rng, ['cottage', 'duplex', 'rowhouse', 'villa', 'courtyard'])
    return {
      profile,
      roof: pick(rng, profile === 'rowhouse' ? ['flat', 'gable', 'shed'] : ['gable', 'hip', 'shed']),
      bodyRatio: 0.66 + rng() * 0.12,
      wing: profile === 'villa' || profile === 'courtyard' || rng() > 0.58,
      porch: rng() > 0.28,
      garage: rng() > 0.62,
      chimney: rng() > 0.36,
      facade: pick(rng, ['brick', 'stucco', 'timber', 'painted']),
      cityPattern: growthPlan.pattern || 'residential',
      parcelSource: growthPlan.source || 'realcity',
    }
  }

  if (type === 'apartment') {
    return {
      profile: growthPlan.publicRealm === 'active-frontage'
        ? pick(rng, ['terraced', 'l_block', 'balcony_stack'])
        : pick(rng, ['bar', 'terraced', 'l_block', 'balcony_stack']),
      roof: pick(rng, ['flat', 'terrace', 'utility']),
      podium: rng() > 0.52,
      wing: rng() > 0.42,
      balconies: true,
      bodyRatio: 0.82 + rng() * 0.1,
      facade: pick(rng, ['concrete', 'warm_panel', 'brick_base']),
      cityPattern: growthPlan.pattern || 'mixed-grid',
      parcelSource: growthPlan.source || 'realcity',
    }
  }

  if (type === 'office') {
    return {
      profile: growthPlan.heat > 0.66
        ? pick(rng, ['podium_tower', 'atrium', 'offset_core'])
        : pick(rng, ['slab', 'podium_tower', 'atrium', 'offset_core']),
      roof: pick(rng, ['flat', 'green', 'mechanical']),
      podium: true,
      wing: rng() > 0.5,
      balconies: false,
      bodyRatio: 0.74 + rng() * 0.18,
      facade: pick(rng, ['stone_grid', 'glass_band', 'metal_panel']),
      cityPattern: growthPlan.pattern || 'office-grid',
      parcelSource: growthPlan.source || 'realcity',
    }
  }

  return {
    profile: pick(rng, ['needle', 'setback', 'twin_core', 'crown']),
    roof: pick(rng, ['crown', 'antenna', 'mechanical']),
    podium: true,
    wing: rng() > 0.7,
    balconies: false,
    bodyRatio: 0.78 + rng() * 0.16,
    facade: pick(rng, ['blue_glass', 'silver_glass', 'dark_glass']),
    districtType: district.type,
    cityPattern: growthPlan.pattern || 'core-growth',
    parcelSource: growthPlan.source || 'realcity',
  }
}

function createTrees(rng, landmarks, roads) {
  const trees = []
  for (let i = 0; i < 760; i += 1) {
    const angle = rng() * TAU
    const radius = 620 + rng() * 500
    const x = Math.cos(angle) * radius + (rng() - 0.5) * 120
    const z = Math.sin(angle) * radius + (rng() - 0.5) * 120
    const nearPlace = landmarks.some(place => place.kind !== 'park' && Math.hypot(x - place.x, z - place.z) < place.radius + 16)
    if (nearPlace || pointInRoadReserve(x, z, roads, 8)) continue
    trees.push({ id: `tree_${i}`, x, z, y: terrainHeight(x, z), scale: 0.65 + rng() * 1.55, tint: rng() })
  }
  return trees
}

function createTraffic(rng, roads) {
  const candidates = roads.filter(road => road.main)
  return Array.from({ length: 120 }, (_, i) => {
    const road = pick(rng, candidates)
    const direction = rng() > 0.5 ? 1 : -1
    const laneOffset = road.width * (road.main ? 0.27 : 0.22)
    const lane = road.axis === 'x' ? direction * laneOffset : -direction * laneOffset
    const taxi = rng() < 0.3
    const bodyStyle = taxi ? pick(rng, ['sedan', 'minivan']) : pick(rng, ['sedan', 'hatchback', 'suv', 'van', 'coupe'])
    const dimensions = {
      sedan: { width: 2.05, height: 0.72, length: 4.35, cabinLength: 1.82, cabinHeight: 0.58 },
      hatchback: { width: 1.95, height: 0.72, length: 3.85, cabinLength: 1.72, cabinHeight: 0.62 },
      suv: { width: 2.18, height: 0.9, length: 4.55, cabinLength: 2.05, cabinHeight: 0.72 },
      van: { width: 2.22, height: 0.96, length: 4.85, cabinLength: 2.58, cabinHeight: 0.78 },
      minivan: { width: 2.16, height: 0.9, length: 4.78, cabinLength: 2.4, cabinHeight: 0.72 },
      coupe: { width: 1.98, height: 0.64, length: 4.05, cabinLength: 1.42, cabinHeight: 0.48 },
    }[bodyStyle]
    const driverName = `${pick(rng, GIVEN_NAMES)} ${pick(rng, FAMILY_NAMES)}`
    const turnIntent = pick(rng, ['straight', 'straight', 'straight', 'right', 'left'])
    return {
      id: `car_${i}`,
      kind: taxi ? 'taxi' : 'private',
      bodyStyle,
      dimensions,
      driverName,
      driverTemperament: pick(rng, ['calm', 'careful', 'hurried', 'patient']),
      roadId: road.id,
      road,
      direction,
      lane,
      laneRule: 'right-hand',
      turnIntent,
      turnLaneRule: turnIntent === 'straight'
        ? 'through-lane'
        : turnIntent === 'right'
          ? 'right-turn-yield-area'
          : 'left-turn-pocket-before-stop-bar',
      turnSignalDistanceMeters: road.main ? 52 : 34,
      plannedTurnSignalSide: turnIntent === 'left' ? 'left-side-turn' : turnIntent === 'right' ? 'right-side-turn' : null,
      t: rng(),
      speed: 7 + rng() * 10,
      brake: 0,
      phase: rng() * TAU,
      color: taxi ? '#f6c445' : pick(rng, ['#e8504f', '#f3f4f6', '#1f2937', '#3b82f6', '#16a34a', '#f59e0b', '#7c3aed', '#94a3b8']),
    }
  })
}

function nearestRoadToPoint(roads, x, z, predicate = () => true) {
  let best = null
  let bestDistance = Infinity
  for (const road of roads) {
    if (!predicate(road)) continue
    const distance = roadDistanceToPoint(road, x, z)
    if (distance < bestDistance) {
      best = road
      bestDistance = distance
    }
  }
  return best
}

function curbPointForRoad(road, ratio = 0.5, side = 1) {
  const along = road.from + (road.to - road.from) * clamp(ratio, 0.04, 0.96)
  const curb = road.width / 2 + 4.6
  if (road.axis === 'x') return { x: along, z: road.z + side * curb }
  return { x: road.x + side * curb, z: along }
}

function createTrafficFlowObserved(mainRoads) {
  return mainRoads.slice(0, 18).flatMap((road, index) => [-1, 1].map(direction => {
    const intensity = clamp(road.trafficWeight + (index % 4) * 0.08 + (direction > 0 ? 0.04 : 0), 0.2, 1.8)
    const averageVehicleSpeedKph = Math.round(24 + road.trafficWeight * 18 - intensity * 3)
    const laneDirection = road.axis === 'x'
      ? direction > 0 ? 'eastbound' : 'westbound'
      : direction > 0 ? 'northbound' : 'southbound'
    return {
      id: `traffic_flow_${road.id}_${direction > 0 ? 'pos' : 'neg'}`,
      type: 'TrafficFlowObserved',
      roadId: road.id,
      roadName: road.name,
      laneId: `${road.id}_${direction > 0 ? 'positive' : 'negative'}`,
      laneDirection,
      reversedLane: direction < 0,
      vehicleType: 'car',
      intensity: Number(intensity.toFixed(2)),
      occupancy: Number(clamp(0.18 + intensity * 0.22, 0.08, 0.82).toFixed(2)),
      averageHeadwayTime: Number(clamp(6.8 - intensity * 2.1, 1.2, 7.5).toFixed(2)),
      averageGapDistance: Number(clamp(46 - intensity * 13, 9, 48).toFixed(1)),
      averageVehicleSpeedKph,
      congestionLevel: intensity > 1.25 ? 'medium' : 'low',
      queueLengthEstimate: Math.round(clamp((intensity - 0.72) * 8, 0, 12)),
    }
  }))
}

function pressureSummaryForFlows(flows, roadId) {
  const matched = flows.filter(flow => flow.roadId === roadId)
  if (!matched.length) {
    return {
      roadId,
      pressure: 0,
      flowCount: 0,
      queueEstimate: 0,
      maxOccupancy: 0,
      minHeadway: null,
      dominantLaneId: null,
    }
  }
  const pressure = matched.reduce((sum, flow) => sum + pressureForFlow(flow), 0) / matched.length
  const queueEstimate = matched.reduce((sum, flow) => sum + (Number(flow.queueLengthEstimate) || 0), 0)
  const maxOccupancy = Math.max(...matched.map(flow => Number(flow.occupancy) || 0))
  const minHeadway = Math.min(...matched.map(flow => Number(flow.averageHeadwayTime) || Infinity))
  const dominant = [...matched].sort((a, b) => pressureForFlow(b) - pressureForFlow(a))[0]
  return {
    roadId,
    pressure: Number(pressure.toFixed(3)),
    flowCount: matched.length,
    queueEstimate: Number(queueEstimate.toFixed(2)),
    maxOccupancy: Number(maxOccupancy.toFixed(2)),
    minHeadway: Number(minHeadway.toFixed(2)),
    dominantLaneId: dominant?.laneId || null,
  }
}

function greenSecondsForPressure(axisPressure, oppositePressure) {
  return Number(clamp(
    20 + ((axisPressure?.pressure || 0) - (oppositePressure?.pressure || 0)) * 5.5 + (axisPressure?.queueEstimate || 0) * 0.2,
    TRAFFIC_SIGNAL_MIN_GREEN_SECONDS,
    TRAFFIC_SIGNAL_MAX_GREEN_SECONDS,
  ).toFixed(2))
}

function createIntersectionControllers(roads, trafficFlowObserved = []) {
  const horizontal = roads.filter(road => road.main && road.axis === 'x')
  const vertical = roads.filter(road => road.main && road.axis === 'z')
  const controllers = []
  for (const h of horizontal) {
    for (const v of vertical) {
      if (Math.hypot(v.x, h.z) > CITY_GRID_HALF * 0.94) continue
      const detectorDistance = 38
      const xPressure = pressureSummaryForFlows(trafficFlowObserved, h.id)
      const zPressure = pressureSummaryForFlows(trafficFlowObserved, v.id)
      const xGreen = greenSecondsForPressure(xPressure, zPressure)
      const zGreen = greenSecondsForPressure(zPressure, xPressure)
      controllers.push({
        id: `tl_${h.id}_${v.id}`,
        model: 'SUMO actuated tlLogic',
        x: v.x,
        z: h.z,
        roads: [h.id, v.id],
        linkOrder: SMART_MOBILITY_STANDARDS.sumo.linkOrder,
        phases: SUMO_TL_LOGIC.map(phase => ({
          id: phase.id,
          duration: phase.duration,
          state: phase.sumoState,
          vehicleLinks: phase.vehicleLinks,
          movementLinks: phase.movementLinks,
          protectedLeftTurn: phase.protectedLeftTurn || null,
          pedestrianLinks: phase.pedestrianLinks,
          rule: phase.rule,
        })),
        stopBars: [
          { roadId: h.id, direction: 1, x: v.x - v.width * 0.92, z: h.z },
          { roadId: h.id, direction: -1, x: v.x + v.width * 0.92, z: h.z },
          { roadId: v.id, direction: 1, x: v.x, z: h.z - h.width * 0.92 },
          { roadId: v.id, direction: -1, x: v.x, z: h.z + h.width * 0.92 },
        ],
        pedestrianCrossings: [
          { crossedAxis: 'x', controlledLink: 'ped_cross_x', rule: 'walk only while z-protected-green is active' },
          { crossedAxis: 'z', controlledLink: 'ped_cross_z', rule: 'walk only while x-protected-green is active' },
        ],
        detectors: [
          { id: `loop_${h.id}_${v.id}_x_pos`, type: 'SUMO-style inductionLoop', roadId: h.id, controlledLink: 'x_vehicle_forward', laneDirection: 1, x: v.x - detectorDistance, z: h.z, distanceToStopBar: detectorDistance, source: 'TrafficFlowObserved' },
          { id: `loop_${h.id}_${v.id}_x_neg`, type: 'SUMO-style inductionLoop', roadId: h.id, controlledLink: 'x_vehicle_reverse', laneDirection: -1, x: v.x + detectorDistance, z: h.z, distanceToStopBar: detectorDistance, source: 'TrafficFlowObserved' },
          { id: `loop_${h.id}_${v.id}_z_pos`, type: 'SUMO-style inductionLoop', roadId: v.id, controlledLink: 'z_vehicle_forward', laneDirection: 1, x: v.x, z: h.z - detectorDistance, distanceToStopBar: detectorDistance, source: 'TrafficFlowObserved' },
          { id: `loop_${h.id}_${v.id}_z_neg`, type: 'SUMO-style inductionLoop', roadId: v.id, controlledLink: 'z_vehicle_reverse', laneDirection: -1, x: v.x, z: h.z + detectorDistance, distanceToStopBar: detectorDistance, source: 'TrafficFlowObserved' },
        ],
        actuationPolicy: {
          mode: 'actuated-detector-pressure',
          minGreenSeconds: TRAFFIC_SIGNAL_MIN_GREEN_SECONDS,
          maxGreenSeconds: TRAFFIC_SIGNAL_MAX_GREEN_SECONDS,
          extensionSeconds: 3,
          protectedLeftTurnSeconds: TRAFFIC_SIGNAL_LEFT_TURN_SECONDS,
          pressureSignals: ['intensity', 'occupancy', 'averageHeadwayTime', 'averageGapDistance', 'queueLengthEstimate'],
          activeAlgorithm: 'extend green for the higher detector-pressure axis while preserving yellow/all-red clearance',
          dominantAxis: xPressure.pressure >= zPressure.pressure ? 'x' : 'z',
          detectorPressure: { x: xPressure, z: zPressure },
          actuatedGreenSeconds: { x: xGreen, z: zGreen },
        },
      })
    }
  }
  return controllers
}

function createMobilitySystem(roads, landmarks) {
  const mainRoads = roads.filter(road => road.main)
  const stations = landmarks.slice(0, 10).map((place, index) => {
    const road = roads.find(item => item.id === place.roadId) || nearestRoadToPoint(roads, place.x, place.z, road => road.main) || roads[0]
    const ratio = road.axis === 'x'
      ? (clamp(place.x, road.from, road.to) - road.from) / Math.max(1, road.to - road.from)
      : (clamp(place.z, road.from, road.to) - road.from) / Math.max(1, road.to - road.from)
    const side = road.axis === 'x'
      ? place.z >= road.z ? 1 : -1
      : place.x >= road.x ? 1 : -1
    const point = curbPointForRoad(road, ratio, side)
    const capacity = 10 + (index % 4) * 4
    const bikes = Math.max(2, Math.round(capacity * (0.36 + (index % 5) * 0.08)))
    const scooters = Math.max(1, Math.round(capacity * (0.18 + (index % 3) * 0.07)))
    return {
      id: `gbfs_station_${place.id}`,
      name: `${place.name} Mobility Dock`,
      landmarkId: place.id,
      roadId: road.id,
      roadName: road.name,
      address: place.address,
      x: Number(point.x.toFixed(2)),
      z: Number(point.z.toFixed(2)),
      lonLat: worldToLngLat(point.x, point.z),
      capacity,
      numBikesAvailable: Math.min(capacity, bikes),
      numDocksAvailable: Math.max(0, capacity - bikes),
      numScootersAvailable: scooters,
      parkingRule: 'dock-or-painted-parking-box-only',
      sidewalkClearanceMeters: 2.2,
      status: 'active',
    }
  })

  const curbZones = mainRoads.flatMap((road, roadIndex) => [0.18, 0.5, 0.82].map((ratio, zoneIndex) => {
    const index = roadIndex * 3 + zoneIndex
    const point = curbPointForRoad(road, ratio, (roadIndex + zoneIndex) % 2 === 0 ? 1 : -1)
    const purpose = index % 4 === 0 ? 'taxi-stand' : index % 4 === 1 ? 'delivery-loading' : index % 4 === 2 ? 'bus-stop' : 'short-stay-parking'
    return {
      id: `curb_${road.id}_${index}`,
      type: 'ParkingSpot',
      roadId: road.id,
      roadName: road.name,
      purpose,
      x: Number(point.x.toFixed(2)),
      z: Number(point.z.toFixed(2)),
      maxDwellMinutes: purpose === 'delivery-loading' ? 12 : purpose === 'taxi-stand' ? 6 : purpose === 'bus-stop' ? 1 : 18,
      enforcement: 'no-stopping-outside-marked-curb-zone',
    }
  }))

  const geofencingZones = [
    {
      id: 'central-core-slow-ride',
      type: 'RestrictedTrafficArea',
      rule: 'shared bikes and scooters are limited to 8 kph and must park at docks',
      maxSpeedKph: 8,
      rideAllowed: true,
      parkingAllowed: false,
      center: { x: 0, z: 0 },
      radius: 220,
    },
    {
      id: 'station-crossing-no-parking',
      type: 'RestrictedTrafficArea',
      rule: 'no parking within crosswalk approaches and station entrance clear zones',
      maxSpeedKph: 5,
      rideAllowed: false,
      parkingAllowed: false,
      center: { x: 0, z: -ROAD_SPACING * 2 },
      radius: 120,
    },
    {
      id: 'outer-hills-low-speed',
      type: 'RestrictedTrafficArea',
      rule: 'downhill micromobility traffic slows for winding residential streets',
      maxSpeedKph: 12,
      rideAllowed: true,
      parkingAllowed: true,
      center: { x: 680, z: 680 },
      radius: 260,
    },
  ]
  const trafficFlowObserved = createTrafficFlowObserved(mainRoads)
  const intersectionControllers = createIntersectionControllers(roads, trafficFlowObserved)

  return {
    standards: SMART_MOBILITY_STANDARDS,
    intersectionControllers,
    gbfs: {
      systemInformation: {
        systemId: 'realcity-shared-mobility',
        language: 'en',
        operator: 'RealCity Mobility Authority',
        timezone: 'Asia/Seoul',
      },
      vehicleTypes: [
        { vehicleTypeId: 'pedal_bike', formFactor: 'bicycle', propulsionType: 'human', maxPermittedSpeedKph: 18 },
        { vehicleTypeId: 'e_scooter', formFactor: 'scooter', propulsionType: 'electric', maxPermittedSpeedKph: 18 },
      ],
      stationInformation: stations.map(station => ({
        stationId: station.id,
        name: station.name,
        lonLat: station.lonLat,
        capacity: station.capacity,
        address: station.address,
      })),
      stationStatus: stations.map(station => ({
        stationId: station.id,
        numBikesAvailable: station.numBikesAvailable,
        numScootersAvailable: station.numScootersAvailable,
        numDocksAvailable: station.numDocksAvailable,
        isInstalled: true,
        isRenting: true,
        isReturning: true,
      })),
      geofencingZones,
      stations,
    },
    smartCity: {
      dataModels: SMART_MOBILITY_STANDARDS.smartCities.entities,
      curbZones,
      trafficFlowObserved,
    },
    gatsim: {
      disruptionEvents: [
        { id: 'school_release', timeWindow: '15:00-16:20', affectedPlace: 'mirae_school', policy: 'students delay crossing until protected WALK and couriers re-route around school curb queues' },
        { id: 'station_peak', timeWindow: '08:00-09:30', affectedPlace: 'central_station', policy: 'commuters prefer transit sidewalks, taxis queue at marked stands, NPCs update departure time if late' },
        { id: 'depot_loading', timeWindow: '10:00-12:00', affectedPlace: 'south_depot', policy: 'delivery vehicles use loading curb zones and pedestrians avoid depot driveways' },
      ],
      agentDecisionSignals: ['current signal phase', 'curb zone availability', 'shared mobility dock status', 'traffic flow observed', 'personal schedule pressure'],
      adaptiveBehaviors: ['delay departure', 'walk to mobility dock', 'hail taxi at legal curb zone', 're-route to next crosswalk', 'remember congested segment'],
    },
  }
}

function createAppearance(rng, role, gender, age, index = 0) {
  const palette = pick(rng, FASHION_PALETTES)
  const body = BODY_ARCHETYPES[(index + Math.floor(rng() * BODY_ARCHETYPES.length)) % BODY_ARCHETYPES.length]
  const walk = WALK_STYLES[(index * 2 + Math.floor(rng() * WALK_STYLES.length)) % WALK_STYLES.length]
  const pattern = OUTFIT_PATTERNS[(index * 3 + Math.floor(rng() * OUTFIT_PATTERNS.length)) % OUTFIT_PATTERNS.length]
  const outerwear = OUTERWEAR[(index * 5 + Math.floor(rng() * OUTERWEAR.length)) % OUTERWEAR.length]
  const accessory = ACCESSORIES[(index * 7 + Math.floor(rng() * ACCESSORIES.length)) % ACCESSORIES.length]
  const ageBand = age < 24 ? 'young' : age > 62 ? 'senior' : 'adult'
  const roleBag = ['courier', 'student', 'teacher', 'engineer'].includes(role)
  const formal = ['banker', 'security', 'doctor'].includes(role)
  const hue = (index * 47 + Math.floor(rng() * 31)) % 360
  const accentHue = (hue + 145 + Math.floor(rng() * 56)) % 360
  const neutralHue = (hue + 210 + Math.floor(rng() * 50)) % 360
  const topColor = formal
    ? role === 'doctor'
      ? colorFromHue(198 + index * 7, 18, 88)
      : role === 'security'
        ? colorFromHue(214 + index * 5, 26, 20)
        : colorFromHue(218 + index * 9, 28, 28)
    : colorFromHue(hue, 42 + rng() * 22, 36 + rng() * 18)
  const jacketColor = formal
    ? role === 'doctor'
      ? colorFromHue(205 + index * 11, 16, 94)
      : role === 'security'
        ? colorFromHue(218 + index * 8, 26, 16)
        : colorFromHue(accentHue, 20 + rng() * 18, 68 + rng() * 10)
    : pattern === 'two-tone' || pattern === 'layered'
      ? colorFromHue(accentHue, 36 + rng() * 22, 52 + rng() * 18)
      : palette.jacket
  const pantsColor = role === 'doctor'
    ? colorFromHue(neutralHue, 18, 28)
    : colorFromHue(neutralHue, 22 + rng() * 18, 16 + rng() * 16)
  const accessoryColor = colorFromHue(accentHue + 36, 48 + rng() * 26, 38 + rng() * 18)
  const skinHue = 22 + rng() * 22
  const skinColor = colorFromHue(skinHue, 32 + rng() * 20, 55 + rng() * 21)
  const grayHair = ageBand === 'senior' && rng() > 0.55
  const hairColor = grayHair
    ? colorFromHue(35 + rng() * 25, 10 + rng() * 12, 44 + rng() * 18)
    : colorFromHue(16 + rng() * 34, 24 + rng() * 32, 12 + rng() * 26)
  const glassesStyle = accessory.includes('glasses') ? accessory : (rng() > 0.88 ? pick(rng, ['round glasses', 'square glasses']) : 'none')
  const scarfStyle = accessory === 'scarf' || rng() > 0.9 ? pick(rng, ['thin', 'wide']) : 'none'
  return {
    signature: `${body.id}-${walk.id}-${pattern}-${outerwear}-${accessory}-${hue}-${index}`,
    bodyArchetype: body.id,
    walkStyle: walk,
    outfitPattern: pattern,
    outerwear,
    accessory,
    heightScale: clamp(0.96 + body.height + rng() * 0.12 + (ageBand === 'senior' ? -0.035 : 0), 0.84, 1.2),
    shoulderScale: clamp(1 + body.shoulder + (gender === 'man' ? 0.025 : gender === 'woman' ? -0.015 : 0) + (rng() - 0.5) * 0.09, 0.78, 1.26),
    bodyScale: clamp(1 + body.body + (rng() - 0.5) * 0.08, 0.82, 1.24),
    legScale: clamp(1 + body.leg + (rng() - 0.5) * 0.09, 0.82, 1.26),
    headScale: clamp(1 + body.head + (rng() - 0.5) * 0.08, 0.88, 1.14),
    ageBand,
    hairStyle: pick(rng, gender === 'man' ? ['short', 'cap', 'swept', 'shaved'] : ['bob', 'long', 'bun', 'cap']),
    hatStyle: role === 'courier' || role === 'security' || rng() > 0.82 ? pick(rng, ['cap', 'beanie']) : 'none',
    bagStyle: roleBag || rng() > 0.6 ? pick(rng, ['backpack', 'shoulder', 'briefcase']) : 'none',
    bottomStyle: !formal && rng() > 0.72 ? 'skirt' : 'pants',
    topColor,
    jacketColor,
    pantsColor,
    shoeColor: colorFromHue(neutralHue + 24, 16 + rng() * 12, 8 + rng() * 8),
    accessoryColor,
    skinColor,
    hairColor,
    glassesStyle,
    scarfStyle,
    styleBrief: `${outerwear}, ${pattern}, ${accessory}, ${body.id}, ${walk.id}`,
  }
}

function buildingTypeLabel(type) {
  if (type === 'skyscraper') return 'tower'
  if (type === 'apartment') return 'residence'
  if (type === 'house') return 'house'
  if (type === 'office') return 'office'
  return 'building'
}

function frontageForBuilding(building, roadsById) {
  const road = roadsById.get(building.roadId)
  const setback = 3.4
  if (!road) {
    return {
      x: building.x,
      z: building.z - building.d / 2 - setback,
      y: terrainHeight(building.x, building.z - building.d / 2 - setback),
    }
  }

  if (road.axis === 'x') {
    const side = road.z >= building.z ? 1 : -1
    const x = clamp(building.x, road.from + 4, road.to - 4)
    const z = building.z + side * (building.d / 2 + setback)
    return { x, z, y: terrainHeight(x, z) }
  }

  const side = road.x >= building.x ? 1 : -1
  const x = building.x + side * (building.w / 2 + setback)
  const z = clamp(building.z, road.from + 4, road.to - 4)
  return { x, z, y: terrainHeight(x, z) }
}

function createAddressBook(buildings, roads) {
  const roadsById = new Map(roads.map(road => [road.id, road]))
  return buildings
    .filter(building => building.address && building.roadName)
    .map(building => {
      const frontage = frontageForBuilding(building, roadsById)
      const typeLabel = buildingTypeLabel(building.type)
      return {
        id: `addr_${building.id}`,
        buildingId: building.id,
        name: `${building.address} ${typeLabel}`,
        kind: 'address',
        buildingType: building.type,
        district: building.district,
        address: building.address,
        roadId: building.roadId,
        roadName: building.roadName,
        addressNumber: building.addressNumber,
        x: frontage.x,
        z: frontage.z,
        y: frontage.y,
        entryRule: 'sidewalk-frontage',
      }
    })
}

function createSchedule(role) {
  if (role === 'doctor' || role === 'security' || role === 'courier') {
    return [
      { start: 0, end: 6.2, target: 'home', activity: 'resting' },
      { start: 6.2, end: 7.1, target: 'third', activity: 'commuting' },
      { start: 7.1, end: 18.5, target: 'work', activity: 'on shift' },
      { start: 18.5, end: 21.0, target: 'third', activity: 'errands' },
      { start: 21.0, end: 24, target: 'home', activity: 'home life' },
    ]
  }
  if (role === 'student' || role === 'teacher') {
    return [
      { start: 0, end: 7.0, target: 'home', activity: 'resting' },
      { start: 7.0, end: 8.2, target: 'third', activity: 'commuting' },
      { start: 8.2, end: 15.7, target: 'work', activity: 'class' },
      { start: 15.7, end: 19.4, target: 'third', activity: 'after school' },
      { start: 19.4, end: 24, target: 'home', activity: 'home life' },
    ]
  }
  if (role === 'barista' || role === 'shopkeeper') {
    return [
      { start: 0, end: 5.1, target: 'home', activity: 'resting' },
      { start: 5.1, end: 15.2, target: 'work', activity: 'serving customers' },
      { start: 15.2, end: 18.0, target: 'third', activity: 'break' },
      { start: 18.0, end: 22.2, target: 'work', activity: 'evening rush' },
      { start: 22.2, end: 24, target: 'home', activity: 'closing down' },
    ]
  }
  return [
    { start: 0, end: 6.7, target: 'home', activity: 'resting' },
    { start: 6.7, end: 8.4, target: 'third', activity: 'commuting' },
    { start: 8.4, end: 17.7, target: 'work', activity: 'working' },
    { start: 17.7, end: 21.6, target: 'third', activity: 'social time' },
    { start: 21.6, end: 24, target: 'home', activity: 'home life' },
  ]
}

function createNPCs(rng, buildings, landmarks, roads) {
  const socialPlaces = landmarks.filter(place => ['cafe', 'park', 'retail', 'leisure', 'transit'].includes(place.kind))
  const byId = new Map(landmarks.map(place => [place.id, place]))
  const homes = buildings.filter(building => building.type === 'apartment' || building.type === 'house')
  const roadsById = new Map(roads.map(road => [road.id, road]))
  const usedNames = new Set()

  return Array.from({ length: 160 }, (_, i) => {
    const roleInfo = pick(rng, ROLE_LIBRARY)
    const home = pick(rng, homes)
    const work = byId.get(roleInfo.workplace) || landmarks[0]
    const third = pick(rng, socialPlaces)
    const gender = pick(rng, ['woman', 'man', 'nonbinary'])
    const name = uniqueName(rng, usedNames, i)
    const frontage = frontageForBuilding(home, roadsById)
    const hx = frontage ? frontage.x + (rng() - 0.5) * 4.4 : home.x + (rng() - 0.5) * home.w
    const hz = frontage ? frontage.z + (rng() - 0.5) * 4.4 : home.z + (rng() - 0.5) * home.d

    const age = 18 + Math.floor(rng() * 57)
    const personality = pick(rng, PERSONALITIES)
    const speechStyle = createSpeechStyle(rng, roleInfo.role, personality, i)
    const appearance = createAppearance(rng, roleInfo.role, gender, age, i)
    const dailyGoals = DAILY_GOALS[roleInfo.role] || ['follow today schedule', 'check in with a friend', 'return home safely']
    const dailyGoal = dailyGoals[(i + Math.floor(rng() * dailyGoals.length)) % dailyGoals.length]
    const needProfile = {
      energy: clamp(0.52 + rng() * 0.42 - (age > 62 ? 0.08 : 0), 0.25, 0.98),
      hunger: clamp(0.18 + rng() * 0.38, 0.05, 0.78),
      social: clamp(0.28 + rng() * 0.56, 0.08, 0.96),
      urgency: clamp(roleInfo.pace * 0.42 + rng() * 0.34, 0.12, 0.94),
    }

    // The first few citizens are ATANOR ambassadors — their minds are our engine (routed through
    // /api/realcity/agent) and they are rendered in a signature colour + glow so the player can spot
    // and talk to ATANOR the moment they connect. Everyone else keeps the local brain/colour.
    const isAtanor = i < ATANOR_AMBASSADORS
    return {
      id: `npc_${i}`,
      name,
      gender,
      age,
      role: roleInfo.role,
      job: roleInfo.job,
      brain: isAtanor ? 'atanor' : 'local',
      color: isAtanor ? ATANOR_SIGNATURE_COLOR : roleInfo.color,
      pace: roleInfo.pace * (appearance.walkStyle?.speed || 1),
      personality,
      speechStyle,
      voice: speechStyle.voice,
      gestureStyle: speechStyle.gesture,
      appearance,
      autonomy: {
        dailyGoal,
        needProfile,
        relationshipStyle: RELATIONSHIP_STYLES[(i + Math.floor(rng() * RELATIONSHIP_STYLES.length)) % RELATIONSHIP_STYLES.length],
        memoryStyle: personality,
        cognitiveArchitecture: 'realcity-generative-gobt-v1',
        memoryPolicy: 'score by recency, importance, and current-place/request relevance',
        reflectionPolicy: 'summarize needs, recent memories, relationships, and selected utility policy',
        planningPolicy: 'choose a utility-scored GOAP-like goal, then execute through route/taxi/social behavior-tree leaves',
        normPolicy: 'traffic, crosswalk, collision, and building affordances constrain every language plan',
        routineTolerance: clamp(0.35 + rng() * 0.56, 0.18, 0.96),
      },
      personaSignature: `${personality}-${speechStyle.signature}`,
      styleBrief: `${appearance.styleBrief}, ${speechStyle.label}, ${speechStyle.voice}`,
      home: {
        x: hx,
        z: hz,
        y: terrainHeight(hx, hz),
        name: `${name.split(' ')[1]} residence`,
        address: home.address,
        buildingId: home.id,
        roadName: frontage?.roadName || home.roadName,
        entryRule: frontage ? 'home-sidewalk-frontage' : 'home-building-offset',
      },
      workId: work.id,
      thirdId: third.id,
      schedule: createSchedule(roleInfo.role),
      offset: { x: (rng() - 0.5) * 30, z: (rng() - 0.5) * 30 },
    }
  })
}

function createTiles(buildings, landmarks, roads = []) {
  const tiles = new Map()
  const placeInTile = (item) => `${Math.floor((item.x + CITY_HALF) / TILE_SIZE)}:${Math.floor((item.z + CITY_HALF) / TILE_SIZE)}`
  const emptyBounds = () => ({ minX: Infinity, minY: CITY_BASE_Y, minZ: Infinity, maxX: -Infinity, maxY: CITY_BASE_Y, maxZ: -Infinity })
  const expand = (bounds, item) => {
    const width = item.w || item.interior?.width || item.form?.width || 12
    const depth = item.d || item.interior?.depth || item.form?.depth || 12
    const height = item.h || item.interior?.height || item.form?.height || 8
    bounds.minX = Math.min(bounds.minX, item.x - width / 2)
    bounds.maxX = Math.max(bounds.maxX, item.x + width / 2)
    bounds.minZ = Math.min(bounds.minZ, item.z - depth / 2)
    bounds.maxZ = Math.max(bounds.maxZ, item.z + depth / 2)
    bounds.minY = Math.min(bounds.minY, item.y || CITY_BASE_Y)
    bounds.maxY = Math.max(bounds.maxY, (item.y || CITY_BASE_Y) + height)
  }
  const ensureTile = key => {
    if (!tiles.has(key)) {
      const [, gxText, gzText] = key.match(/^tile_(\d+)_(\d+)$/) || []
      const gx = Number(gxText)
      const gz = Number(gzText)
      const minX = Number.isFinite(gx) ? gx * TILE_SIZE - CITY_HALF : -CITY_HALF
      const minZ = Number.isFinite(gz) ? gz * TILE_SIZE - CITY_HALF : -CITY_HALF
      tiles.set(key, {
        id: key,
        buildings: [],
        landmarks: [],
        roadSegments: [],
        terrainPatchCount: 1,
        bounds: { minX, minY: CITY_BASE_Y, minZ, maxX: minX + TILE_SIZE, maxY: CITY_BASE_Y + 1, maxZ: minZ + TILE_SIZE },
        contentBounds: emptyBounds(),
      })
    }
    return tiles.get(key)
  }

  const tileSpan = Math.ceil(CITY_WORLD_SIZE / TILE_SIZE)
  for (let gx = 0; gx < tileSpan; gx += 1) {
    for (let gz = 0; gz < tileSpan; gz += 1) {
      ensureTile(`tile_${gx}_${gz}`)
    }
  }

  for (const building of buildings) {
    const key = `tile_${placeInTile(building).replace(':', '_')}`
    const tile = ensureTile(key)
    tile.buildings.push(building.id)
    expand(tile.contentBounds, building)
  }

  for (const landmark of landmarks) {
    const key = `tile_${placeInTile(landmark).replace(':', '_')}`
    const tile = ensureTile(key)
    tile.landmarks.push(landmark.id)
    expand(tile.contentBounds, landmark)
  }

  const roadIntersectsTile = (road, bounds) => {
    const halfWidth = (road.width || ROAD_WIDTH) / 2
    if (road.axis === 'x') {
      return road.z + halfWidth >= bounds.minZ &&
        road.z - halfWidth <= bounds.maxZ &&
        road.to >= bounds.minX &&
        road.from <= bounds.maxX
    }
    return road.x + halfWidth >= bounds.minX &&
      road.x - halfWidth <= bounds.maxX &&
      road.to >= bounds.minZ &&
      road.from <= bounds.maxZ
  }

  for (const road of roads) {
    for (const tile of tiles.values()) {
      if (roadIntersectsTile(road, tile.bounds)) tile.roadSegments.push(road.id)
    }
  }

  return [...tiles.values()].map(tile => {
    const content = tile.contentBounds.minX === Infinity ? tile.bounds : tile.contentBounds
    const bounds = {
      minX: Math.min(tile.bounds.minX, content.minX),
      minY: CITY_BASE_Y,
      minZ: Math.min(tile.bounds.minZ, content.minZ),
      maxX: Math.max(tile.bounds.maxX, content.maxX),
      maxY: Math.max(tile.bounds.maxY, content.maxY),
      maxZ: Math.max(tile.bounds.maxZ, content.maxZ),
    }
    const center = {
      x: (bounds.minX + bounds.maxX) / 2,
      y: (bounds.minY + bounds.maxY) / 2,
      z: (bounds.minZ + bounds.maxZ) / 2,
    }
    const half = {
      x: Math.max(1, (bounds.maxX - bounds.minX) / 2),
      y: Math.max(1, (bounds.maxY - bounds.minY) / 2),
      z: Math.max(1, (bounds.maxZ - bounds.minZ) / 2),
    }
    const terrainPatchCount = tile.terrainPatchCount || 0
    const roadSegmentCount = tile.roadSegments.length
    const featureCount = tile.buildings.length + tile.landmarks.length + roadSegmentCount + terrainPatchCount
    return {
      ...tile,
      bounds,
      center,
      halfAxes: half,
      boundingVolume: {
        box: [center.x, center.y, center.z, half.x, 0, 0, 0, half.y, 0, 0, 0, half.z],
      },
      format: '3d-tiles-1.1-procedural-content',
      contentUri: `realcity://${tile.id}.glb`,
      content: {
        uri: `realcity://${tile.id}.glb`,
        metadata: {
          class: 'ProceduralCityTile',
          properties: {
            buildingCount: tile.buildings.length,
            landmarkCount: tile.landmarks.length,
            roadSegmentCount,
            terrainPatchCount,
            featureCount,
            lod: featureCount > 36 ? 'near-detail' : featureCount > 14 ? 'mid-massing' : 'far-shell',
          },
        },
      },
      geometricError: featureCount > 36 ? 64 : featureCount > 14 ? 96 : 128,
      refine: featureCount > 28 ? 'REPLACE' : 'ADD',
    }
  }).sort((a, b) => a.id.localeCompare(b.id))
}

function createTileset(tiles) {
  const bounds = tiles.reduce((acc, tile) => ({
    minX: Math.min(acc.minX, tile.bounds.minX),
    minY: Math.min(acc.minY, tile.bounds.minY),
    minZ: Math.min(acc.minZ, tile.bounds.minZ),
    maxX: Math.max(acc.maxX, tile.bounds.maxX),
    maxY: Math.max(acc.maxY, tile.bounds.maxY),
    maxZ: Math.max(acc.maxZ, tile.bounds.maxZ),
  }), { minX: Infinity, minY: CITY_BASE_Y, minZ: Infinity, maxX: -Infinity, maxY: CITY_BASE_Y + 1, maxZ: -Infinity })
  const center = {
    x: (bounds.minX + bounds.maxX) / 2,
    y: (bounds.minY + bounds.maxY) / 2,
    z: (bounds.minZ + bounds.maxZ) / 2,
  }
  const half = {
    x: Math.max(1, (bounds.maxX - bounds.minX) / 2),
    y: Math.max(1, (bounds.maxY - bounds.minY) / 2),
    z: Math.max(1, (bounds.maxZ - bounds.minZ) / 2),
  }
  return {
    asset: {
      version: '1.1',
      tilesetVersion: 'realcity-procedural-2026.05',
      generator: 'RealCity procedural city engine',
    },
    geometricError: 512,
    schema: {
      id: 'RealCityTiles',
      classes: {
        ProceduralCityTile: {
          properties: {
            buildingCount: { type: 'SCALAR', componentType: 'UINT16' },
            landmarkCount: { type: 'SCALAR', componentType: 'UINT16' },
            roadSegmentCount: { type: 'SCALAR', componentType: 'UINT16' },
            terrainPatchCount: { type: 'SCALAR', componentType: 'UINT16' },
            featureCount: { type: 'SCALAR', componentType: 'UINT16' },
            lod: { type: 'STRING' },
          },
        },
      },
    },
    root: {
      boundingVolume: {
        box: [center.x, center.y, center.z, half.x, 0, 0, 0, half.y, 0, 0, 0, half.z],
      },
      geometricError: 512,
      refine: 'REPLACE',
      metadata: {
        class: 'ProceduralCityTile',
        properties: {
          buildingCount: tiles.reduce((sum, tile) => sum + tile.buildings.length, 0),
          landmarkCount: tiles.reduce((sum, tile) => sum + tile.landmarks.length, 0),
          roadSegmentCount: tiles.reduce((sum, tile) => sum + tile.roadSegments.length, 0),
          terrainPatchCount: tiles.reduce((sum, tile) => sum + (tile.terrainPatchCount || 0), 0),
          featureCount: tiles.reduce((sum, tile) => sum + tile.content.metadata.properties.featureCount, 0),
          lod: 'root',
        },
      },
      children: tiles.map(tile => ({
        boundingVolume: tile.boundingVolume,
        geometricError: tile.geometricError,
        refine: tile.refine,
        content: tile.content,
      })),
    },
  }
}

function worldToLngLat(x, z) {
  const extent = 0.095
  const safeX = Number.isFinite(Number(x)) ? Number(x) : 0
  const safeZ = Number.isFinite(Number(z)) ? Number(z) : 0
  return [(safeX / CITY_WORLD_SIZE) * extent, (safeZ / CITY_WORLD_SIZE) * extent]
}

function createGeoJSON(roads, landmarks) {
  return {
    type: 'FeatureCollection',
    features: [
      ...roads.filter(road => road.main).map(road => ({
        type: 'Feature',
        properties: { layer: 'road', id: road.id, name: road.name, tier: road.tier },
        geometry: {
          type: 'LineString',
          coordinates: road.axis === 'x'
            ? [worldToLngLat(road.from, road.z), worldToLngLat(road.to, road.z)]
            : [worldToLngLat(road.x, road.from), worldToLngLat(road.x, road.to)],
        },
      })),
      ...landmarks.map(place => ({
        type: 'Feature',
        properties: { layer: 'place', id: place.id, kind: place.kind, name: place.name, address: place.address },
        geometry: { type: 'Point', coordinates: worldToLngLat(place.x, place.z) },
      })),
    ],
  }
}

function buildCollisionIndex(buildings) {
  const cell = 120
  const map = new Map()
  for (const building of buildings) {
    const gx = Math.floor((building.x + CITY_HALF) / cell)
    const gz = Math.floor((building.z + CITY_HALF) / cell)
    const key = `${gx}:${gz}`
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(building)
  }
  return (x, z) => {
    const gx = Math.floor((x + CITY_HALF) / cell)
    const gz = Math.floor((z + CITY_HALF) / cell)
    const nearby = []
    for (let dx = -1; dx <= 1; dx += 1) {
      for (let dz = -1; dz <= 1; dz += 1) {
        const group = map.get(`${gx + dx}:${gz + dz}`)
        if (group) nearby.push(...group)
      }
    }
    return nearby
  }
}

export function createRealCity(seed = 20260525) {
  const rng = mulberry32(seed)
  const roads = roadGrid()
  const landmarks = landmarkSet(roads)
  const buildings = createBuildings(rng, landmarks, roads)
  const trees = createTrees(rng, landmarks, roads)
  const cars = createTraffic(rng, roads)
  const npcs = createNPCs(rng, buildings, landmarks, roads)
  const addressBook = createAddressBook(buildings, roads)
  const tiles = createTiles(buildings, landmarks, roads)
  const tileset = createTileset(tiles)
  const geojson = createGeoJSON(roads, landmarks)
  const mobilitySystem = createMobilitySystem(roads, landmarks)
  const getNearbyBuildings = buildCollisionIndex(buildings)

  return {
    seed,
    roads,
    buildings,
    trees,
    landmarks,
    addressBook,
    cars,
    npcs,
    tiles,
    tileset,
    geojson,
    mobilitySystem,
    worldToLngLat,
    districtAt,
    getNearbyBuildings,
    socialNorms: {
      pedestrian: 'NPCs prefer sidewalks, building entrances, plazas, and crosswalks; drive lanes are avoided except at crossings. Signalized crossings require protected WALK, while lower-tier crossings use conservative vehicle-gap acceptance.',
      traffic: 'Cars use right-hand lanes, obey alternating traffic lights at main intersections, yield near pedestrians, track detector-like traffic pressure, and taxis use named-road addresses for pickup and drop-off.',
      sharedMobility: 'GBFS-shaped bike and scooter docks expose station information, station status, vehicle types, geofenced slow/no-park zones, and sidewalk clearance rules.',
      planting: 'Trees and planters stay outside the road reserve so streets remain drivable and readable.',
      addressSystem: 'Virtual road-name addresses use numbered lots on named roads, e.g. 83 Station-daero, and resolve to sidewalk frontage points.',
      zoning: `Buildings are restricted to per-block buildable envelopes with a ${BUILDING_ROAD_SETBACK}m setback from road reserves.`,
      npcDiversity: 'Every NPC carries a distinct name, body archetype, walking cadence, outfit/accessory signature, voice register, gesture style, and speech flavor.',
      npcAutonomy: 'Every NPC has a daily goal, mutable needs, relationship style, short memory feed, and a generative-agent style memory/reflection/planning layer that selects behavior-tree actions through utility scores.',
      npcMobility: 'Long-distance late commuters can autonomously hail a cruising fleet taxi, wait curbside, board from the passenger side, ride lane-following routes, and continue from the dropoff curb.',
      humanReactions: 'Idle NPCs within conversational distance turn toward the player, expose a glancing-at-player state, and may pulse a short social acknowledgement.',
      collision: 'Buildings, landmark interiors, pedestrians, and vehicles are treated as solid bodies; contacts push actors apart, make pedestrians stumble or fall, and force drivers to brake.',
      streetHierarchy: 'Sidewalks are segmented before intersections, curbs mark the road edge, and zebra crosswalks with stop bars are the only pedestrian surfaces crossing traffic lanes.',
      facadeSystem: 'Procedural facades use bright wall palettes, mullion grids, reflective/lit window cells, balcony rails, and trim so buildings read as walls and glass rather than black blocks.',
      proceduralCityPlanning: 'Roads and parcels carry a heatmap-growth profile inspired by MIT-licensed Procedural-Cities: denser active frontages near civic/transport heat, quieter branching residential blocks outside, and sidewalk furniture plans on every named road.',
    },
    zoningRules: {
      roadSetback: BUILDING_ROAD_SETBACK,
      buildableEnvelope: 'Each generated building is clamped inside the rectangle between adjacent roads after subtracting road half-widths and setbacks.',
      rotationPolicy: 'Procedural buildings stay axis-aligned with the street grid until parcel-aware rotated lots are introduced.',
      parcelSubdivision: 'Blocks use heatmap-driven parcel counts, footprint scale, public-realm labels, and facade-density bias before building placement.',
    },
    proceduralSources: PROCEDURAL_CITY_SOURCE_MODEL,
    trafficRules: {
      drivingSide: 'right-hand',
      laneRule: 'Opposite lanes carry opposite directions; east-west positive traffic uses the south/right lane, north-south positive traffic uses the west/right lane.',
      turnLanePolicy: 'Main roads expose shared through lanes plus marked left-turn pockets and right-turn yield areas before intersections; vehicle samples publish turn intent and signal side.',
      signalModel: 'SUMO-inspired actuated tlLogic',
      baseSignalProgram: SUMO_TL_LOGIC,
      signalProgram: actuatedSignalProgram(mobilitySystem),
      signalPhases: SUMO_TL_LOGIC.map(phase => phase.id),
      signalCycleSeconds: Number(actuatedSignalProgram(mobilitySystem).reduce((sum, phase) => sum + phase.duration, 0).toFixed(2)),
      yellowSeconds: TRAFFIC_SIGNAL_YELLOW_SECONDS,
      allRedSeconds: TRAFFIC_SIGNAL_ALL_RED_SECONDS,
      protectedLeftTurnSeconds: TRAFFIC_SIGNAL_LEFT_TURN_SECONDS,
      minGreenSeconds: TRAFFIC_SIGNAL_MIN_GREEN_SECONDS,
      maxGreenSeconds: TRAFFIC_SIGNAL_MAX_GREEN_SECONDS,
      linkOrder: SMART_MOBILITY_STANDARDS.sumo.linkOrder,
      intersectionControllers: mobilitySystem.intersectionControllers.length,
      pedestrianCrossingLinks: 'Pedestrian crossings are controlled as separate links after vehicle links and expose crossX/crossZ WALK states.',
      signals: `Main intersections use a SUMO-style actuated tlLogic program with detector-pressure green extensions, SUMO g/G movement links, a ${TRAFFIC_SIGNAL_LEFT_TURN_SECONDS}s protected-left window at the end of each main green, yellow clearance, all-red clearance, and separate pedestrian crossing links. Pedestrians may start only on protected WALK while the crossed vehicle axis is red; all-red/yellow/protected-left windows are no-start states.`,
      yielding: 'Drivers brake for pedestrians in or near a lane, stop at stop bars for red/all-red signal approaches, and treat turning as a separate conflict check: left turns slow in the pocket, yield during permissive g, gain protected G priority in the late left-turn window, and accepted turns follow curved lane-level steering arcs into the receiving road.',
      followingDistance: 'Drivers track the nearest vehicle in the same lane and reduce speed before the gap falls below a temperament-adjusted safety distance.',
      pedestrianGapAcceptance: 'Priority-zebra and uncontrolled crossings use a SUMO-style conservative gap rule: pedestrians wait if an approaching vehicle would reach the crossing before the configured gap window.',
      detectorPolicy: 'Each main intersection exposes four SUMO induction-loop-style detector records and an active actuated policy keyed to TrafficFlowObserved intensity, occupancy, headway, gap distance, and queue pressure.',
      movementLinkPolicy: SMART_MOBILITY_STANDARDS.sumo.leftTurnModel,
      actuatedPressureByAxis: trafficPressureByAxis(mobilitySystem),
      smartCityCurbZones: mobilitySystem.smartCity.curbZones.length,
      gbfsStations: mobilitySystem.gbfs.stations.length,
      gatsimDisruptions: mobilitySystem.gatsim.disruptionEvents.length,
    },
    integrations: {
      mapLibre: 'live procedural GeoJSON layer',
      cesium3DTiles: `${tiles.length} procedural tiles with 3D Tiles 1.1 bounding volumes, content URIs, metadata schema, and runtime LOD telemetry`,
      tripo3D: `${landmarks.length} landmark prompts ready for asset replacement`,
      gbfs: `${mobilitySystem.gbfs.stations.length} dock stations with station_information, station_status, vehicle_types, and geofencing_zones`,
      smartCities: `${mobilitySystem.smartCity.curbZones.length} curb/parking/loading zones plus TrafficFlowObserved road segments`,
      gatsim: `${mobilitySystem.gatsim.disruptionEvents.length} generative-agent transport disruption policies for rerouting, delay, and mode choice`,
    },
  }
}
