import { CITY_HALF } from './cityEngine'

function pushOutOfBox(px, pz, cx, cz, hw, hd) {
  const dx = px - cx
  const dz = pz - cz
  const pushX = hw - Math.abs(dx)
  const pushZ = hd - Math.abs(dz)
  if (pushX < pushZ) return [cx + Math.sign(dx || 1) * hw, pz]
  return [px, cz + Math.sign(dz || 1) * hd]
}

function localPoint(item, x, z) {
  const dx = x - item.x
  const dz = z - item.z
  const cos = Math.cos(item.rot || 0)
  const sin = Math.sin(item.rot || 0)
  return {
    x: dx * cos - dz * sin,
    z: dx * sin + dz * cos,
  }
}

function worldPoint(item, lx, lz) {
  const cos = Math.cos(item.rot || 0)
  const sin = Math.sin(item.rot || 0)
  return {
    x: item.x + lx * cos + lz * sin,
    z: item.z - lx * sin + lz * cos,
  }
}

function solidDimensions(item) {
  return {
    width: item.w || item.interior?.width || item.footprint?.width || 0,
    depth: item.d || item.interior?.depth || item.footprint?.depth || 0,
  }
}

function entryFaceForItem(item) {
  return item.interior?.entryPortal?.face || item.interior?.entryFace || item.facadePlan?.entryFace || item.entryFace || 'south'
}

function insideLocal(local, hw, hd) {
  return Math.abs(local.x) < hw && Math.abs(local.z) < hd
}

function atEntryDoor(item, local, radius = 0.72) {
  const { width, depth } = solidDimensions(item)
  if (!width || !depth) return false
  const face = entryFaceForItem(item)
  const doorWidth = item.interior?.entryPortal?.width || item.interior?.doorWidth || item.doorWidth || 2.4
  const halfDoor = doorWidth / 2 + radius * 0.85
  const threshold = 2.2 + radius
  if (face === 'north') return Math.abs(local.x) <= halfDoor && local.z >= depth / 2 - threshold
  if (face === 'south') return Math.abs(local.x) <= halfDoor && local.z <= -depth / 2 + threshold
  if (face === 'east') return Math.abs(local.z) <= halfDoor && local.x >= width / 2 - threshold
  return Math.abs(local.z) <= halfDoor && local.x <= -width / 2 + threshold
}

function pushOutOfSolid(item, local, hw, hd) {
  const [lx, lz] = pushOutOfBox(local.x, local.z, 0, 0, hw, hd)
  return worldPoint(item, lx, lz)
}

function clampToInterior(item, local, hw, hd) {
  const lx = Math.max(-hw, Math.min(hw, local.x))
  const lz = Math.max(-hd, Math.min(hd, local.z))
  return worldPoint(item, lx, lz)
}

function resolveSolidInteriorCollision(item, previousX, previousZ, nextX, nextZ, radius = 0.72) {
  const { width, depth } = solidDimensions(item)
  if (!width || !depth) return [nextX, nextZ]

  const prev = localPoint(item, previousX, previousZ)
  const next = localPoint(item, nextX, nextZ)
  const collisionHw = width / 2 + radius
  const collisionHd = depth / 2 + radius
  const interiorHw = Math.max(0.1, width / 2 - radius * 0.2)
  const interiorHd = Math.max(0.1, depth / 2 - radius * 0.2)
  const prevInsideInterior = insideLocal(prev, interiorHw, interiorHd)
  const nextInsideEnvelope = insideLocal(next, collisionHw, collisionHd)

  if (!prevInsideInterior && nextInsideEnvelope && !atEntryDoor(item, next, radius)) {
    const pushed = pushOutOfSolid(item, next, collisionHw, collisionHd)
    return [pushed.x, pushed.z]
  }

  if (prevInsideInterior && !nextInsideEnvelope) {
    const exitsThroughDoor = atEntryDoor(item, prev, radius) || atEntryDoor(item, next, radius)
    if (!exitsThroughDoor) {
      const clamped = clampToInterior(item, next, interiorHw, interiorHd)
      return [clamped.x, clamped.z]
    }
  }

  return [nextX, nextZ]
}

export function resolveLandmarkCollision(city, previousX, previousZ, nextX, nextZ, radius = 0.72) {
  let px = nextX
  let pz = nextZ

  for (const place of city.landmarks || []) {
    const interior = place.interior
    if (!interior?.solidWalls) continue
    ;[px, pz] = resolveSolidInteriorCollision(place, previousX, previousZ, px, pz, radius)
  }

  return [px, pz]
}

export function currentInterior(city, x, z) {
  for (const place of city.landmarks || []) {
    const interior = place.interior
    if (!interior) continue
    const local = localPoint(place, x, z)
    if (Math.abs(local.x) < interior.width / 2 && Math.abs(local.z) < interior.depth / 2) {
      return {
        id: place.id,
        name: place.name,
        kind: place.kind,
        verticalCore: interior.verticalCore,
        floorCount: interior.floorCount || 1,
        floorHeight: interior.floorHeight || 4.2,
        floorDirectory: interior.floorDirectory || [],
      }
    }
  }

  const colliders = city.getNearbyBuildings?.(x, z) || city.buildings || []
  for (const building of colliders) {
    const interior = building.interior
    if (!interior?.solidWalls || building.h < 3) continue
    const local = localPoint(building, x, z)
    if (Math.abs(local.x) < building.w / 2 && Math.abs(local.z) < building.d / 2) {
      return {
        id: building.id,
        name: building.name || building.address || `${building.type || 'City'} building`,
        kind: building.type,
        address: building.address,
        verticalCore: interior.verticalCore,
        floorCount: interior.floors || 1,
        floorHeight: interior.floorHeight || 3.6,
        publicAccess: interior.publicAccess,
        floorDirectory: interior.floorDirectory || [],
      }
    }
  }
  return null
}

// Circular props (trees, poles, hydrants, benches) published by CityScape as
// city.obstacles = [{x, z, r}]. They are bucketed into an 8u spatial grid that is
// built lazily on first use and cached on city.__obstacleGrid, rebuilt only when the
// obstacle count changes. Cell keys are numeric so lookups allocate nothing per call.
const OBSTACLE_CELL = 8
const OBSTACLE_KEY_OFFSET = 1000000
const OBSTACLE_KEY_STRIDE = 4000000

function obstacleCellKey(cellX, cellZ) {
  return (cellX + OBSTACLE_KEY_OFFSET) * OBSTACLE_KEY_STRIDE + (cellZ + OBSTACLE_KEY_OFFSET)
}

function obstacleGridFor(city) {
  const obstacles = city.obstacles
  if (!obstacles || obstacles.length === 0) return null

  const cached = city.__obstacleGrid
  if (cached && cached.count === obstacles.length) return cached

  const grid = new Map()
  let maxR = 0
  for (let i = 0; i < obstacles.length; i += 1) {
    const o = obstacles[i]
    if (o.r > maxR) maxR = o.r
    const key = obstacleCellKey(Math.floor(o.x / OBSTACLE_CELL), Math.floor(o.z / OBSTACLE_CELL))
    let bucket = grid.get(key)
    if (!bucket) {
      bucket = []
      grid.set(key, bucket)
    }
    bucket.push(o)
  }

  const built = { grid, maxR, count: obstacles.length }
  city.__obstacleGrid = built
  return built
}

export function obstacleAt(city, x, z, radius = 0.72) {
  const packed = obstacleGridFor(city)
  if (!packed) return false
  const reach = Math.ceil((packed.maxR + radius) / OBSTACLE_CELL)
  const baseX = Math.floor(x / OBSTACLE_CELL)
  const baseZ = Math.floor(z / OBSTACLE_CELL)
  for (let gx = baseX - reach; gx <= baseX + reach; gx += 1) {
    for (let gz = baseZ - reach; gz <= baseZ + reach; gz += 1) {
      const bucket = packed.grid.get(obstacleCellKey(gx, gz))
      if (!bucket) continue
      for (let i = 0; i < bucket.length; i += 1) {
        const o = bucket[i]
        const dx = x - o.x
        const dz = z - o.z
        const minDist = o.r + radius
        if (dx * dx + dz * dz < minDist * minDist) return true
      }
    }
  }
  return false
}

export function resolveBuildingCollision(city, previousX, previousZ, x, z, radius = 0.72) {
  let px = x
  let pz = z
  const colliders = city.getNearbyBuildings?.(px, pz) || city.buildings || []

  for (const building of colliders) {
    if (building.h < 3) continue
    ;[px, pz] = resolveSolidInteriorCollision(building, previousX, previousZ, px, pz, radius)
  }

  ;[px, pz] = resolveLandmarkCollision(city, previousX, previousZ, px, pz, radius)

  const packed = obstacleGridFor(city)
  if (packed) {
    const reach = Math.ceil((packed.maxR + radius) / OBSTACLE_CELL)
    const baseX = Math.floor(px / OBSTACLE_CELL)
    const baseZ = Math.floor(pz / OBSTACLE_CELL)
    for (let gx = baseX - reach; gx <= baseX + reach; gx += 1) {
      for (let gz = baseZ - reach; gz <= baseZ + reach; gz += 1) {
        const bucket = packed.grid.get(obstacleCellKey(gx, gz))
        if (!bucket) continue
        for (let i = 0; i < bucket.length; i += 1) {
          const o = bucket[i]
          const dx = px - o.x
          const dz = pz - o.z
          const minDist = o.r + radius
          const distSq = dx * dx + dz * dz
          if (distSq >= minDist * minDist) continue
          const dist = Math.sqrt(distSq)
          if (dist > 1e-6) {
            const scale = minDist / dist
            px = o.x + dx * scale
            pz = o.z + dz * scale
          } else {
            px = o.x + minDist
          }
        }
      }
    }
  }

  px = Math.max(-CITY_HALF + 15, Math.min(CITY_HALF - 15, px))
  pz = Math.max(-CITY_HALF + 15, Math.min(CITY_HALF - 15, pz))
  return [px, pz]
}

export function countSolidWallOverlaps(city, samples = [], radius = 0.72) {
  let overlaps = 0
  for (const sample of samples) {
    const buildings = city.getNearbyBuildings?.(sample.x, sample.z) || city.buildings || []
    const buildingHit = buildings.some(building => {
      if (building.h < 3) return false
      const local = localPoint(building, sample.x, sample.z)
      return insideLocal(local, building.w / 2 + radius, building.d / 2 + radius) && !atEntryDoor(building, local, radius)
    })
    if (buildingHit) {
      overlaps += 1
      continue
    }

    const landmarkHit = (city.landmarks || []).some(place => {
      const interior = place.interior
      if (!interior?.solidWalls) return false
      const local = localPoint(place, sample.x, sample.z)
      return insideLocal(local, interior.width / 2 + radius, interior.depth / 2 + radius) && !atEntryDoor(place, local, radius)
    })
    if (landmarkHit) overlaps += 1
  }
  return overlaps
}
