// economy.js — closed-ledger city economy (CT-track world system, self-driving).
//
// Money model is a strictly closed transfer ledger: every coin starts in a citizen wallet or the
// cityFund, and every operation (wage, purchase, nightly sweep) MOVES value between wallets, shop
// tills, and the cityFund — nothing is minted or burned, so audit() drift stays 0. The supply chain
// only refills goods (stock), which live outside the money ledger, so deliveries are "free goods"
// drawn from a depotReserve and never touch the coin total.
//
// Sources: shops are derived from city.landmarks (cafe -> coffee/meal, market/retail -> goods/food);
// wallets are keyed by city.npcs[i].id. No other module is imported — cross-talk is via the
// window.__REALCITY_CITY__ handle, window.__REALCITY_ECON__, and window CustomEvents.
//
// Public API -> window.__REALCITY_ECON__ = { shops, wallets, buy(agentId,shopId,item), audit() }
//              (also attached to city.systems.economy)

const TICK_MS = 1000
const STORAGE_KEY = 'rc_econ'
const CITY_FUND_INITIAL = 250000 // starting public treasury (part of initial coin issuance)
const DEPOT_RESERVE_INITIAL = 100000 // goods units at the depot (goods side, NOT money)
const HUNGER_THRESHOLD = 0.75
const HUNGER_DRIFT_PER_HOUR = 0.05
const MEAL_HUNGER_RESET = 0.15
const DELIVERY_EVERY_HOURS = 6
const NIGHT_SWEEP_HOUR = 2
const PERSIST_EVERY_TICKS = 60 // ~60s at a ~1s tick

const HOURS_BY_KIND = {
  cafe: { open: 6, close: 20 },
  market: { open: 8, close: 22 },
}

// Wealth weight per role: biases starting balance (40..120) and income (6..14) while staying in range.
const ROLE_WEALTH = {
  banker: 0.95, doctor: 0.9, engineer: 0.72, security: 0.6, teacher: 0.62,
  shopkeeper: 0.55, courier: 0.5, retiree: 0.5, barista: 0.42, artist: 0.4,
  gardener: 0.38, student: 0.22,
}

// ---- module state -------------------------------------------------------------------------------
let cityRef = null
let started = false
let shops = []
let shopsById = new Map()
let wallets = new Map()
let cityFund = CITY_FUND_INITIAL
let depotReserve = DEPOT_RESERVE_INITIAL
let initialIssuance = 0
let internalMinutes = 10 * 60 + 30 // fallback sim-clock (10:30) if city.systems.clock is absent
let lastHour = null
let hourCounter = 0
let tickCount = 0
const internalHunger = new Map()

// ---- helpers ------------------------------------------------------------------------------------
function num(value, fallback = 0) {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function clamp01(value) {
  return Math.max(0, Math.min(1, value))
}

function hashStr(str) {
  let h = 2166136261
  for (let i = 0; i < str.length; i += 1) {
    h ^= str.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

function rngFromSeed(seed) {
  let v = seed >>> 0
  return () => {
    v = (v + 0x6d2b79f5) >>> 0
    let t = v
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function intRange(rng, min, max) {
  return min + Math.floor(rng() * (max - min + 1))
}

function phaseForHour(hour) {
  const h = ((Math.floor(hour) % 24) + 24) % 24
  if (h >= 5 && h < 8) return 'dawn'
  if (h >= 8 && h < 17) return 'day'
  if (h >= 17 && h < 20) return 'dusk'
  return 'night'
}

// Prefer the shared clock system when present; otherwise fall back to the internal sim-clock.
function currentHour(city) {
  const clock = city?.systems?.clock
  if (clock && Number.isFinite(Number(clock.hour))) {
    return (((Math.floor(Number(clock.hour)) % 24) + 24) % 24)
  }
  return (((Math.floor(internalMinutes / 60) % 24) + 24) % 24)
}

function agentsOf(city) {
  if (Array.isArray(city?.agents) && city.agents.length) return city.agents
  if (Array.isArray(city?.npcs)) return city.npcs
  return []
}

function agentPos(agent) {
  const pos = agent?.pos
  if (pos && Number.isFinite(Number(pos.x)) && Number.isFinite(Number(pos.z))) {
    return { x: Number(pos.x), z: Number(pos.z) }
  }
  const home = agent?.home
  if (home && Number.isFinite(Number(home.x)) && Number.isFinite(Number(home.z))) {
    return { x: Number(home.x), z: Number(home.z) }
  }
  return { x: num(agent?.offset?.x), z: num(agent?.offset?.z) }
}

function shopKindFor(landmark) {
  const kind = String(landmark?.kind || '')
  const key = `${landmark?.id || ''} ${landmark?.name || ''}`.toLowerCase()
  if (kind === 'cafe') return 'cafe'
  if (kind === 'retail' || /\b(market|shop|grocer|store|mart)\b/.test(key)) return 'market'
  return null
}

function itemsForKind(kind) {
  return kind === 'cafe' ? ['coffee', 'meal'] : ['goods', 'food']
}

function shopOpen(shop, hour) {
  if (hour == null) return true
  const { open, close } = shop.hours
  return hour >= open && hour < close
}

function foodItemFor(shop) {
  if (shop.items.includes('meal')) return 'meal'
  if (shop.items.includes('food')) return 'food'
  return shop.items[0] || null
}

// ---- construction ------------------------------------------------------------------------------
function buildShops(city) {
  const landmarks = Array.isArray(city?.landmarks) ? city.landmarks : []
  const built = []
  for (const place of landmarks) {
    const kind = shopKindFor(place)
    if (!kind) continue
    const rng = rngFromSeed(hashStr(`shop:${place.id}`))
    const items = itemsForKind(kind)
    const stock = {}
    const prices = {}
    const par = {}
    for (const item of items) {
      const qty = intRange(rng, 20, 40)
      stock[item] = qty
      par[item] = qty
      prices[item] = intRange(rng, 3, 12)
    }
    built.push({
      id: place.id,
      name: place.name || place.id,
      kind,
      x: num(place.x),
      z: num(place.z),
      till: 0,
      hours: { ...(HOURS_BY_KIND[kind] || HOURS_BY_KIND.market) },
      items,
      stock,
      prices,
      par,
    })
  }
  return built
}

function buildWallets(city) {
  const map = new Map()
  for (const agent of agentsOf(city)) {
    if (!agent?.id) continue
    const role = String(agent.role || 'resident')
    const weight = ROLE_WEALTH[role] ?? 0.5
    const rng = rngFromSeed(hashStr(`wallet:${agent.id}`))
    const balance = Math.max(40, Math.min(120, Math.round(40 + weight * 80 + (rng() - 0.5) * 12)))
    const income = Math.max(6, Math.min(14, Math.round(6 + weight * 8 + (rng() - 0.5) * 2)))
    map.set(agent.id, {
      id: agent.id,
      role,
      balance,
      income,
      employed: role !== 'retiree',
    })
    internalHunger.set(agent.id, clamp01(num(agent?.autonomy?.needProfile?.hunger, 0.3)))
  }
  return map
}

function loadPersisted() {
  try {
    if (typeof localStorage === 'undefined') return
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    const balances = data?.balances
    if (!balances || typeof balances !== 'object') return
    for (const [id, value] of Object.entries(balances)) {
      const wallet = wallets.get(id)
      if (wallet && Number.isFinite(Number(value))) {
        wallet.balance = Math.max(0, Math.round(Number(value)))
      }
    }
  } catch {
    /* corrupt payload — ignore, keep freshly seeded balances */
  }
}

function persist() {
  try {
    if (typeof localStorage === 'undefined') return
    const balances = {}
    for (const [id, wallet] of wallets) balances[id] = wallet.balance
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ balances, savedAt: Date.now() }))
  } catch {
    /* storage full / unavailable — non-fatal */
  }
}

function computeIssuance() {
  let total = cityFund
  for (const wallet of wallets.values()) total += wallet.balance
  for (const shop of shops) total += shop.till
  return total
}

// ---- public ledger ops -------------------------------------------------------------------------
function buy(agentId, shopId, item) {
  try {
    const wallet = wallets.get(agentId)
    if (!wallet) return { ok: false, reason: 'no-wallet' }
    const shop = shopsById.get(shopId)
    if (!shop) return { ok: false, reason: 'no-shop' }
    if (!(item in shop.prices)) return { ok: false, reason: 'no-item' }
    if (!shopOpen(shop, currentHour(cityRef))) return { ok: false, reason: 'closed' }
    const stock = shop.stock[item] || 0
    if (stock <= 0) return { ok: false, reason: 'out-of-stock' }
    const price = shop.prices[item]
    if (wallet.balance < price) return { ok: false, reason: 'insufficient-funds' }
    // closed transfer: coin moves wallet -> till, one unit of goods leaves stock.
    shop.stock[item] = stock - 1
    wallet.balance -= price
    shop.till += price
    return { ok: true, agentId, shopId, item, price, balance: wallet.balance, till: shop.till }
  } catch {
    return { ok: false, reason: 'error' }
  }
}

function audit() {
  const total = computeIssuance()
  const drift = Math.abs(total - initialIssuance)
  return { ok: drift < 0.01, total, drift, initialIssuance, cityFund, depotReserve }
}

// ---- hourly economy step -----------------------------------------------------------------------
function hungerOf(agent) {
  const live = agent?.needs?.hunger
  if (Number.isFinite(Number(live))) return Number(live)
  const stored = internalHunger.get(agent.id)
  return Number.isFinite(stored) ? stored : num(agent?.autonomy?.needProfile?.hunger, 0.3)
}

function nearestOpenFoodShop(agent, hour) {
  const pos = agentPos(agent)
  let best = null
  let bestDist = Infinity
  for (const shop of shops) {
    if (!shopOpen(shop, hour)) continue
    const item = foodItemFor(shop)
    if (!item || (shop.stock[item] || 0) <= 0) continue
    const d = Math.hypot(shop.x - pos.x, shop.z - pos.z)
    if (d < bestDist) {
      bestDist = d
      best = shop
    }
  }
  return best
}

function payWages() {
  for (const wallet of wallets.values()) {
    if (!wallet.employed) continue
    const pay = wallet.income
    if (cityFund < pay) continue // treasury empty this hour — money stays put, ledger still closed
    cityFund -= pay
    wallet.balance += pay
  }
}

function feedHungryCitizens(city, hour) {
  for (const agent of agentsOf(city)) {
    if (!agent?.id) continue
    // drift the internal hunger model up so the demo stays visibly alive even without live needs
    const drifted = clamp01(hungerOf(agent) + HUNGER_DRIFT_PER_HOUR)
    if (!Number.isFinite(Number(agent?.needs?.hunger))) internalHunger.set(agent.id, drifted)
    const hunger = Number.isFinite(Number(agent?.needs?.hunger)) ? Number(agent.needs.hunger) : drifted
    if (hunger <= HUNGER_THRESHOLD) continue
    const wallet = wallets.get(agent.id)
    if (!wallet) continue
    const shop = nearestOpenFoodShop(agent, hour)
    if (!shop) continue
    const item = foodItemFor(shop)
    const result = buy(agent.id, shop.id, item)
    if (result.ok) {
      internalHunger.set(agent.id, MEAL_HUNGER_RESET)
      if (agent.needs && Number.isFinite(Number(agent.needs.hunger))) {
        agent.needs.hunger = Math.min(agent.needs.hunger, MEAL_HUNGER_RESET)
      }
    }
  }
}

function runDelivery() {
  for (const shop of shops) {
    let delivered = 0
    for (const item of shop.items) {
      const par = shop.par[item]
      const current = shop.stock[item] || 0
      if (current < par) {
        delivered += par - current
        shop.stock[item] = par
      }
    }
    if (delivered > 0) {
      depotReserve = Math.max(0, depotReserve - delivered) // goods side only, never touches coins
      dispatchDelivery(shop.id)
    }
  }
}

function nightlySweep() {
  for (const shop of shops) {
    if (shop.till > 0) {
      cityFund += shop.till // closed transfer: till -> cityFund
      shop.till = 0
    }
  }
}

function hourlyStep(city, hour) {
  payWages()
  feedHungryCitizens(city, hour)
  hourCounter += 1
  if (hourCounter % DELIVERY_EVERY_HOURS === 0) runDelivery()
  if (hour === NIGHT_SWEEP_HOUR) nightlySweep()
}

// ---- events ------------------------------------------------------------------------------------
function dispatchDelivery(shopId) {
  try {
    if (typeof window !== 'undefined' && typeof CustomEvent === 'function') {
      window.dispatchEvent(new CustomEvent('realcity:delivery', { detail: { shopId } }))
    }
  } catch {
    /* event dispatch is best-effort */
  }
}

// ---- lifecycle ---------------------------------------------------------------------------------
function init(city) {
  cityRef = city
  shops = buildShops(city)
  shopsById = new Map(shops.map(shop => [shop.id, shop]))
  wallets = buildWallets(city)
  cityFund = CITY_FUND_INITIAL
  depotReserve = DEPOT_RESERVE_INITIAL
  loadPersisted()
  initialIssuance = computeIssuance()

  const api = {
    shops,
    wallets,
    buy,
    audit,
    get cityFund() { return cityFund },
    get depotReserve() { return depotReserve },
    get initialIssuance() { return initialIssuance },
  }
  if (typeof window !== 'undefined') window.__REALCITY_ECON__ = api
  city.systems = city.systems || {}
  city.systems.economy = api

  // eslint-disable-next-line no-console
  console.log(`[realcity:economy] ${shops.length} shops, ${wallets.size} wallets, issuance ${initialIssuance}`)
}

function tick(city, dt) {
  // advance the fallback sim-clock only when the real clock system is not driving time
  if (!(city?.systems?.clock && Number.isFinite(Number(city.systems.clock.hour)))) {
    internalMinutes = (internalMinutes + dt * 1.25) % (24 * 60)
  }
  const hour = currentHour(city)
  if (lastHour === null) lastHour = hour
  else if (hour !== lastHour) {
    lastHour = hour
    hourlyStep(city, hour)
  }
  tickCount += 1
  if (tickCount % PERSIST_EVERY_TICKS === 0) persist()
}

function boot() {
  if (typeof window === 'undefined') return
  let lastTs = Date.now()
  setInterval(() => {
    try {
      const city = window.__REALCITY_CITY__
      if (!city) return
      const now = Date.now()
      const dt = Math.min(3, Math.max(0, (now - lastTs) / 1000))
      lastTs = now
      if (!started) {
        started = true
        init(city)
      }
      tick(city, dt)
    } catch {
      /* self-driving loop must never throw */
    }
  }, TICK_MS)
}

boot()

export {}
