const ROOM_TTL_MS = 15000
const MAX_NAME_LENGTH = 28
const MAX_ROOM_LENGTH = 32

function roomsStore() {
  const key = '__REALCITY_MULTIPLAYER_ROOMS__'
  if (!globalThis[key]) globalThis[key] = new Map()
  return globalThis[key]
}

function cleanText(value, fallback, maxLength) {
  const text = String(value || '').trim().replace(/[^\w\s.-]/g, '').replace(/\s+/g, ' ').slice(0, maxLength)
  return text || fallback
}

function cleanColor(value) {
  const text = String(value || '').trim()
  return /^#[0-9a-f]{6}$/i.test(text) ? text : '#4aadff'
}

function cleanNumber(value, fallback = 0, min = -5000, max = 5000) {
  const number = Number(value)
  if (!Number.isFinite(number)) return fallback
  return Math.max(min, Math.min(max, number))
}

function cleanPose(pose = {}) {
  return {
    x: cleanNumber(pose.x),
    y: cleanNumber(pose.y, 1, -200, 500),
    z: cleanNumber(pose.z),
    heading: cleanNumber(pose.heading, 0, -Math.PI * 8, Math.PI * 8),
    speed: cleanNumber(pose.speed, 0, 0, 80),
    district: cleanText(pose.district, 'RealCity', 48),
  }
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let raw = ''
    req.on('data', chunk => {
      raw += chunk
      if (raw.length > 12000) {
        reject(new Error('Payload too large'))
        req.destroy()
      }
    })
    req.on('end', () => {
      if (!raw) {
        resolve({})
        return
      }
      try {
        resolve(JSON.parse(raw))
      } catch {
        reject(new Error('Invalid JSON'))
      }
    })
    req.on('error', reject)
  })
}

function pruneRoom(room, now = Date.now()) {
  for (const [id, player] of room.players.entries()) {
    if (now - player.updatedAt > ROOM_TTL_MS) room.players.delete(id)
  }
}

function serializeRoom(room, ownId = '') {
  pruneRoom(room)
  const players = [...room.players.values()]
    .sort((a, b) => a.joinedAt - b.joinedAt)
    .map(player => ({
      ...player,
      isSelf: player.id === ownId,
    }))

  return {
    ok: true,
    roomId: room.id,
    serverTime: Date.now(),
    ttlMs: ROOM_TTL_MS,
    playerCount: players.length,
    peers: players.filter(player => player.id !== ownId),
    players,
  }
}

function roomFor(roomId) {
  const rooms = roomsStore()
  const id = cleanText(roomId, 'lobby', MAX_ROOM_LENGTH).toLowerCase()
  if (!rooms.has(id)) {
    rooms.set(id, {
      id,
      createdAt: Date.now(),
      players: new Map(),
    })
  }
  return rooms.get(id)
}

export async function handleMultiplayerRequest(req, res) {
  res.setHeader('Cache-Control', 'no-store')
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type')

  if (req.method === 'OPTIONS') {
    res.statusCode = 204
    res.end()
    return
  }

  try {
    const url = new URL(req.url || '/api/multiplayer', 'http://realcity.local')
    if (req.method === 'GET') {
      const room = roomFor(url.searchParams.get('roomId') || 'lobby')
      const ownId = cleanText(url.searchParams.get('playerId'), '', 48)
      res.statusCode = 200
      res.end(JSON.stringify(serializeRoom(room, ownId)))
      return
    }

    if (req.method !== 'POST') {
      res.statusCode = 405
      res.end(JSON.stringify({ ok: false, error: 'Method not allowed' }))
      return
    }

    const body = await readBody(req)
    const room = roomFor(body.roomId)
    const playerId = cleanText(body.playerId, `player-${Math.random().toString(36).slice(2, 8)}`, 48)

    if (body.action === 'leave') {
      room.players.delete(playerId)
      res.statusCode = 200
      res.end(JSON.stringify(serializeRoom(room, playerId)))
      return
    }

    const now = Date.now()
    const previous = room.players.get(playerId)
    const player = {
      id: playerId,
      name: cleanText(body.name, 'Guest', MAX_NAME_LENGTH),
      color: cleanColor(body.color),
      pose: cleanPose(body.pose),
      status: cleanText(body.status, 'exploring', 64),
      joinedAt: previous?.joinedAt || now,
      updatedAt: now,
    }
    room.players.set(playerId, player)
    pruneRoom(room, now)

    res.statusCode = 200
    res.end(JSON.stringify(serializeRoom(room, playerId)))
  } catch (error) {
    res.statusCode = 400
    res.end(JSON.stringify({ ok: false, error: error instanceof Error ? error.message : String(error) }))
  }
}
