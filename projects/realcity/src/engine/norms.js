// norms.js — social-rules registry that ATANOR can edit (CT world-system, 2026-07-21).
// Self-driving side-effect module: publishes an API to BOTH window.__REALCITY_NORMS__ and
// city.systems.norms, persists the whole registry to localStorage 'rc_norms', and on boot
// re-applies any saved building renames once the city handle exists.
//
// API: { list(), add({id?,kind,statement}), setRule(sameShape), renameBuilding(idOrName,newName),
//        applyFromAtanor(edit), registry }
//   applyFromAtanor(edit) routes edit = { id, kind:'rename_building'|'set_norm'|'set_rule', payload }.
//
// Moral floor: any statement/name matching /harm|steal|deceive|attack|weapon|kill/i or longer than
// 200 chars is rejected (the mutation is not applied and not persisted).

const STORAGE_KEY = 'rc_norms'
const TICK_MS = 1000
const MAX_LEN = 200
const FORBIDDEN = /harm|steal|deceive|attack|weapon|kill/i

const DEFAULTS = [
  { id: 'cross-at-signal', kind: 'rule', statement: 'Cross the street only at a signalized crosswalk on a protected WALK.' },
  { id: 'quiet-night', kind: 'norm', statement: 'Keep noise low between 22:00 and 06:00.' },
  { id: 'greet-acquaintance', kind: 'norm', statement: 'Greet acquaintances you recognise when passing.' },
  { id: 'queue-at-stops', kind: 'norm', statement: 'Queue in order at transit stops and taxi stands.' },
]

// registry is the single source of truth; every row is { id, kind, statement, ... }.
let registry = DEFAULTS.map(row => ({ ...row }))
let seq = 0

function isAllowed(text) {
  if (typeof text !== 'string') return false
  const trimmed = text.trim()
  if (!trimmed || trimmed.length > MAX_LEN) return false
  if (FORBIDDEN.test(trimmed)) return false
  return true
}

function slugify(text) {
  return String(text)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40)
}

function persist() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(registry))
  } catch (_) {
    /* ignore quota / privacy-mode errors */
  }
}

function upsert(row) {
  const idx = registry.findIndex(r => r.id === row.id)
  if (idx >= 0) registry[idx] = { ...registry[idx], ...row }
  else registry.push(row)
}

function add(input) {
  try {
    if (!input || typeof input !== 'object') return false
    const statement = input.statement
    if (!isAllowed(statement)) return false
    const kind = input.kind === 'rule' ? 'rule' : 'norm'
    let id = typeof input.id === 'string' && input.id ? input.id : ''
    if (!id) {
      id = slugify(statement) || kind
      while (registry.some(r => r.id === id)) id = `${kind}-${++seq}`
    }
    const row = { id, kind, statement: statement.trim() }
    upsert(row)
    persist()
    return row
  } catch (_) {
    return false
  }
}

function setRule(input) {
  try {
    if (!input || typeof input !== 'object') return false
    return add({ id: input.id, kind: 'rule', statement: input.statement })
  } catch (_) {
    return false
  }
}

function findLandmark(city, idOrName) {
  const list = (city && Array.isArray(city.landmarks)) ? city.landmarks : null
  if (!list) return null
  return list.find(p => p && (p.id === idOrName || p.name === idOrName)) || null
}

function applyRename(city, target, newName) {
  const place = findLandmark(city, target)
  if (!place) return false
  if (place.name === newName) return place // already applied (idempotent)
  const old = place.name
  if (!Array.isArray(place.aliases)) place.aliases = []
  if (old && !place.aliases.includes(old)) place.aliases.push(old)
  place.name = newName
  return place
}

function renameBuilding(idOrName, newName) {
  try {
    if (typeof newName !== 'string' || !isAllowed(newName)) return false
    const city = window.__REALCITY_CITY__
    const place = applyRename(city, idOrName, newName.trim())
    if (!place) return false
    // Record (or update) a persistent name row so the rename survives reloads.
    upsert({
      id: `name:${place.id}`,
      kind: 'name',
      statement: `renamed to ${place.name}`,
      target: place.id,
      to: place.name,
    })
    persist()
    return true
  } catch (_) {
    return false
  }
}

function applyFromAtanor(edit) {
  try {
    if (!edit || typeof edit !== 'object') return false
    const payload = edit.payload || {}
    switch (edit.kind) {
      case 'rename_building':
        return renameBuilding(payload.id || payload.target || edit.id, payload.newName || payload.name || payload.to)
      case 'set_norm':
        return !!add({ id: payload.id || edit.id, kind: 'norm', statement: payload.statement })
      case 'set_rule':
        return !!setRule({ id: payload.id || edit.id, statement: payload.statement })
      default:
        return false
    }
  } catch (_) {
    return false
  }
}

function list() {
  return registry.map(row => ({ ...row }))
}

const api = { list, add, setRule, renameBuilding, applyFromAtanor, get registry() { return registry } }

function restore() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const saved = JSON.parse(raw)
    if (!Array.isArray(saved)) return
    // Merge saved rows over the defaults so newly-shipped defaults still appear.
    for (const row of saved) {
      if (row && typeof row.id === 'string') upsert(row)
    }
  } catch (_) {
    /* corrupt payload -> keep defaults */
  }
}

function reapplyRenames(city) {
  for (const row of registry) {
    if (row && row.kind === 'name' && row.target && typeof row.to === 'string') {
      applyRename(city, row.target, row.to)
    }
  }
}

function boot() {
  if (typeof window === 'undefined') return
  restore()
  // API is city-independent (except renameBuilding), so expose it immediately.
  window.__REALCITY_NORMS__ = api

  let lastCity = null

  const loop = () => {
    try {
      const city = window.__REALCITY_CITY__
      if (city) {
        if (!city.systems) city.systems = {}
        if (city.systems.norms !== api) city.systems.norms = api
        // Re-apply saved renames once per distinct city instance (handles remount / HMR).
        if (city !== lastCity) {
          reapplyRenames(city)
          lastCity = city
        }
      }
    } catch (_) {
      /* never throw out of the loop */
    }
  }

  setInterval(loop, TICK_MS)
  loop()
  console.log('[realcity] norms online')
}

boot()

export {}
