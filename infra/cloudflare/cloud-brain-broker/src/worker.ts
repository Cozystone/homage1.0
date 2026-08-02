export interface Env {
  ATANOR_BROKER_API_KEY?: string
  ATANOR_ALLOWED_ORIGINS?: string
  ATANOR_CLOUD_MODE?: string
  ATANOR_DEV_SEED_PUBLIC_TASKS?: string
  ATANOR_NODES: KVNamespace
  ATANOR_TASKS: KVNamespace
  ATANOR_CREDITS: KVNamespace
  ATANOR_FRAGMENTS?: R2Bucket
  ATANOR_FRAGMENTS_KV?: KVNamespace
  ATANOR_DB?: D1Database
  ATANOR_TASK_QUEUE?: Queue
}

const SERVICE = "atanor-cloud-brain-broker"
const ACTIVE_PEER_WINDOW_MS = 120_000
const TASK_TIMEOUT_MS = 180_000
const MAX_PAYLOAD_BYTES = 64_000
const MAX_FRAGMENT_BYTES = 96_000
const SINGLE_PEER_PENDING = "single_peer_pending"

const TASK_TYPES = new Set([
  "public_source_fetch",
  "public_fragment_validation",
  "source_noise_check",
  "duplicate_relation_check",
  "graph_delta_compression",
  "public_alias_review",
  "freshness_check",
])

const FORBIDDEN_KEYS = new Set([
  "raw_text",
  "raw_document",
  "private_payload",
  "payload_vault",
  "chat_log",
  "local_path",
  "file_path",
  "absolute_path",
  "private_graph",
  "device_name",
  "ip",
])

const FORBIDDEN_MARKERS = [
  "C:\\",
  "file://",
  "localhost",
  "127.0.0.1",
  "0.0.0.0",
  "::1",
  "192.168.",
  "10.",
  "172.16.",
  "/Users/",
  "/home/",
  "../",
  "..\\",
  "AppData",
  "payload_vault",
  "homage.db",
  "atanor.db",
  "powershell",
  "cmd.exe",
  "bash -c",
  "eval(",
  "exec(",
  "<script",
]

type JsonMap = Record<string, unknown>

function nowIso(): string {
  return new Date().toISOString()
}

function jsonResponse(env: Env, request: Request, body: unknown, status = 200): Response {
  const origin = request.headers.get("Origin") || ""
  const allowed = (env.ATANOR_ALLOWED_ORIGINS || "http://127.0.0.1:3022,http://localhost:3022")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
  const allowOrigin = allowed.includes(origin) ? origin : allowed[0] || "*"
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": allowOrigin,
      "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type,Authorization,X-ATANOR-API-Key",
    },
  })
}

async function readJson(request: Request): Promise<JsonMap> {
  const text = await request.text()
  if (new TextEncoder().encode(text).byteLength > MAX_PAYLOAD_BYTES) throw new Error("payload too large")
  const payload = text ? JSON.parse(text) : {}
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("JSON body must be an object")
  return payload as JsonMap
}

function isAuthorized(env: Env, request: Request, path: string): boolean {
  if (request.method === "GET" && ["/cloud/status", "/cloud/network"].includes(path)) return true
  if (!env.ATANOR_BROKER_API_KEY) return false
  const supplied =
    request.headers.get("X-ATANOR-API-Key") ||
    (request.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "")
  return supplied === env.ATANOR_BROKER_API_KEY
}

function encodedSize(value: unknown): number {
  return new TextEncoder().encode(JSON.stringify(value)).byteLength
}

function containsForbidden(value: unknown): boolean {
  const encoded = JSON.stringify(value)
  const lowered = encoded.toLowerCase()
  if (FORBIDDEN_MARKERS.some((marker) => lowered.includes(marker.toLowerCase()))) return true
  if (value && typeof value === "object") {
    if (Array.isArray(value)) return value.some(containsForbidden)
    for (const [key, nested] of Object.entries(value as JsonMap)) {
      if (FORBIDDEN_KEYS.has(key.toLowerCase())) return true
      if (containsForbidden(nested)) return true
    }
  }
  return false
}

function assertSafePublicUrl(sourceUrl: unknown): void {
  if (!sourceUrl) return
  const value = String(sourceUrl)
  let parsed: URL
  try {
    parsed = new URL(value)
  } catch {
    throw new Error("source_url must be a valid URL")
  }
  if (!["http:", "https:"].includes(parsed.protocol)) throw new Error("source_url must be http(s)")
  const host = parsed.hostname.toLowerCase()
  if (
    host === "localhost" ||
    host.endsWith(".local") ||
    host.endsWith(".internal") ||
    host.startsWith("127.") ||
    host.startsWith("10.") ||
    host.startsWith("192.168.") ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(host) ||
    host === "::1"
  ) {
    throw new Error("source_url must not point to local/private network")
  }
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize)
  if (value && typeof value === "object") {
    const input = value as JsonMap
    const output: JsonMap = {}
    for (const key of Object.keys(input).sort()) {
      if (
        [
          "created_by_peer_hash",
          "submitted_by_peer_hash",
          "submitted_at",
          "created_at",
          "duplicate_submission_count",
          "peer_count",
          "storage_backend",
          "object_key",
        ].includes(key)
      ) {
        continue
      }
      output[key] = canonicalize(input[key])
    }
    return output
  }
  return value
}

async function sha256Hex(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(typeof value === "string" ? value : JSON.stringify(canonicalize(value)))
  const digest = await crypto.subtle.digest("SHA-256", bytes)
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("")
}

async function boundPeerIdentity(payload: JsonMap): Promise<{ nodePublicId: string; peerIdHash: string }> {
  const nodePublicId = String(payload.node_public_id || payload.node_id || "").trim()
  if (!nodePublicId) throw new Error("node_id is required")
  const peerIdHash = await sha256Hex(`peer:${nodePublicId}`)
  for (const field of ["peer_id_hash", "created_by_peer_hash", "submitted_by_peer_hash"]) {
    const supplied = String(payload[field] || "").trim().toLowerCase()
    if (supplied && supplied !== peerIdHash) {
      throw new Error(`${field} does not match node identity`)
    }
  }
  return { nodePublicId, peerIdHash }
}

function fragmentPeerPayload(payload: JsonMap): JsonMap {
  const provenance =
    payload.provenance && typeof payload.provenance === "object" && !Array.isArray(payload.provenance)
      ? payload.provenance as JsonMap
      : {}
  return {
    ...payload,
    node_public_id:
      payload.node_public_id ||
      payload.node_id ||
      payload.source_peer_id ||
      provenance.source_peer_id,
  }
}

async function requireRegisteredFragmentPeer(
  env: Env,
  payload: JsonMap,
): Promise<{ nodePublicId: string; peerIdHash: string }> {
  const identity = await boundPeerIdentity(fragmentPeerPayload(payload))
  await requireRegisteredPeer(env, identity)
  return identity
}

async function getJson<T = JsonMap>(kv: KVNamespace, key: string): Promise<T | null> {
  return (await kv.get(key, "json")) as T | null
}

async function putJson(kv: KVNamespace, key: string, value: unknown): Promise<void> {
  await kv.put(key, JSON.stringify(value))
}

async function listJson(kv: KVNamespace, prefix: string, limit = 100): Promise<JsonMap[]> {
  const listing = await kv.list({ prefix, limit })
  const rows: JsonMap[] = []
  for (const item of listing.keys) {
    const row = await getJson(kv, item.name)
    if (row && typeof row === "object") rows.push(row as JsonMap)
  }
  return rows
}

async function registryGet(kv: KVNamespace, key: string): Promise<string[]> {
  const value = await kv.get(key, "json")
  return Array.isArray(value) ? value.map(String).filter(Boolean) : []
}

async function registryAdd(kv: KVNamespace, key: string, value: string, limit = 1000): Promise<string[]> {
  const values = await registryGet(kv, key)
  const next = Array.from(new Set([value, ...values])).slice(0, limit)
  await kv.put(key, JSON.stringify(next))
  return next
}

async function registryObjects(kv: KVNamespace, registryKey: string, prefix: string, limit = 200): Promise<JsonMap[]> {
  const ids = (await registryGet(kv, registryKey)).slice(0, limit)
  const rows: JsonMap[] = []
  for (const id of ids) {
    const row = await getJson(kv, `${prefix}${id}`)
    if (row && typeof row === "object") rows.push(row as JsonMap)
  }
  return rows
}

async function requireRegisteredPeer(
  env: Env,
  identity: { nodePublicId: string; peerIdHash: string },
): Promise<JsonMap> {
  const peer = await getJson(env.ATANOR_NODES, `peer:${identity.peerIdHash}`)
  if (!peer) throw new Error("peer must register before broker mutation")
  const registeredNode = String(peer.node_public_id || "")
  if (registeredNode && registeredNode !== identity.nodePublicId) {
    throw new Error("registered peer identity mismatch")
  }
  return peer
}

function isActivePeer(peer: JsonMap, now = Date.now()): boolean {
  const lastSeen = Date.parse(String(peer.last_seen || peer.last_seen_at || ""))
  const state = String(peer.state || peer.contributor_state || "idle")
  return Number.isFinite(lastSeen) && now - lastSeen <= ACTIVE_PEER_WINDOW_MS && !["offline", "error", "disabled"].includes(state)
}

function fragmentStore(env: Env): "r2" | "kv" | "misconfigured" {
  if (env.ATANOR_FRAGMENTS) return "r2"
  if (env.ATANOR_FRAGMENTS_KV) return "kv"
  return "misconfigured"
}

async function networkSnapshot(env: Env): Promise<JsonMap> {
  const peers = await registryObjects(env.ATANOR_NODES, "registry:peers", "peer:", 200)
  const tasks = await registryObjects(env.ATANOR_TASKS, "registry:tasks", "task:", 200)
  const credits = await registryObjects(env.ATANOR_CREDITS, "registry:credits", "credit:", 200)
  const fragmentHashes = env.ATANOR_FRAGMENTS || env.ATANOR_FRAGMENTS_KV ? await registryGet(env.ATANOR_TASKS, "registry:fragments") : []
  const activePeers = peers.filter((peer) => isActivePeer(peer)).length
  const queuedTasks = tasks.filter((task) => String(task.status) === "queued").length
  const assignedTasks = tasks.filter((task) => ["assigned", "running"].includes(String(task.status))).length
  const submittedFragments = fragmentHashes.length
  const verifiedFragments = tasks.filter((task) => ["accepted", "multi_peer_verified"].includes(String(task.status))).length
  const pendingCredits = credits.reduce((sum, item) => sum + Number(item.pending_credit || item.amount_estimated || 0), 0)
  const networkState =
    activePeers >= 2 ? "active_multi_peer" : activePeers === 1 ? "active_single_peer" : "remote_broker_connected"
  return {
    network_state: networkState,
    active_peers: activePeers,
    queued_tasks: queuedTasks,
    assigned_tasks: assignedTasks,
    submitted_fragments: submittedFragments,
    verified_fragments: verifiedFragments,
    pending_credits: Number(pendingCredits.toFixed(3)),
  }
}

async function status(env: Env): Promise<JsonMap> {
  const store = fragmentStore(env)
  let snapshot: JsonMap = { network_state: "degraded", active_peers: 0, submitted_fragments: 0 }
  let kvQuotaOk = true
  try {
    snapshot = await networkSnapshot(env)
  } catch (error) {
    kvQuotaOk = false
    snapshot = { network_state: "degraded", active_peers: 0, submitted_fragments: 0, error: error instanceof Error ? error.message : "KV quota or registry read failed" }
  }
  return {
    service: SERVICE,
    provider: "cloudflare",
    mode: env.ATANOR_CLOUD_MODE || "dev",
    status: store === "misconfigured" ? "degraded" : "ok",
    broker_state: "remote_connected",
    storage_role: "broker_index_only",
    full_payload_storage: false,
    kv_quota_ok: kvQuotaOk,
    remote_persistence_verified: false,
    schema: "atanor.cloud-broker.v2",
    raw_private_payload_storage: false,
    fragment_store: store,
    r2_available: Boolean(env.ATANOR_FRAGMENTS),
    kv_available: Boolean(env.ATANOR_FRAGMENTS_KV),
    d1_available: Boolean(env.ATANOR_DB),
    queue_available: Boolean(env.ATANOR_TASK_QUEUE),
    ...snapshot,
    storage: {
      worker: true,
      fragment_store: store,
      r2_fragments: Boolean(env.ATANOR_FRAGMENTS),
      kv_fragments: Boolean(env.ATANOR_FRAGMENTS_KV),
      kv_registry: true,
      d1_optional: Boolean(env.ATANOR_DB),
      queues_optional: Boolean(env.ATANOR_TASK_QUEUE),
    },
    warnings:
      store === "r2"
        ? []
        : store === "kv"
          ? ["R2 is not enabled; using KV fragment storage for small public fragments."]
          : ["No fragment storage binding is configured."],
  }
}

async function announceShards(env: Env, payload: JsonMap): Promise<JsonMap> {
  if (containsForbidden(payload)) throw new Error("shard announcement contains private/local markers")
  const peerId = String(payload.peer_id || payload.peer_id_hash || "")
  if (!peerId) throw new Error("peer_id is required")
  const shards = Array.isArray(payload.shards) ? payload.shards as JsonMap[] : []
  for (const shard of shards) {
    const shardId = String(shard.shard_id || "")
    if (!shardId) continue
    const metadata = {
      ...shard,
      peer_id: peerId,
      storage_role: "broker_index_only",
      full_payload_storage: false,
      announced_at: nowIso(),
    }
    await putJson(env.ATANOR_TASKS, `shard-location:${shardId}:${peerId}`, metadata)
    await registryAdd(env.ATANOR_TASKS, "registry:shard-locations", `${shardId}:${peerId}`, 5000)
    await registryAdd(env.ATANOR_TASKS, "registry:shards", shardId, 5000)
  }
  return { accepted: true, broker_state: "remote_connected", storage_role: "broker_index_only", shards_announced: shards.length, network: await networkSnapshot(env) }
}

async function registerFragmentLocation(env: Env, payload: JsonMap): Promise<JsonMap> {
  if (containsForbidden(payload)) throw new Error("fragment location contains private/local markers")
  if (payload.privacy_scope && payload.privacy_scope !== "public") throw new Error("privacy_scope must be public")
  const contentHash = String(payload.content_hash || "")
  const peerId = String(payload.peer_id || payload.peer_id_hash || "")
  if (!contentHash || !peerId) throw new Error("content_hash and peer_id are required")
  const metadata = {
    fragment_id: String(payload.fragment_id || `fragment_${contentHash.slice(0, 16)}`),
    content_hash: contentHash,
    shard_id: String(payload.shard_id || "public-default"),
    peer_id: peerId,
    trust_state: String(payload.trust_state || "unverified"),
    verification_state: String(payload.verification_state || "seed_aligned_pending_verification"),
    location_kind: String(payload.location_kind || "peer"),
    storage_role: "broker_index_only",
    full_payload_storage: false,
    registered_at: nowIso(),
  }
  await putJson(env.ATANOR_TASKS, `fragment-location:${contentHash}:${peerId}`, metadata)
  await registryAdd(env.ATANOR_TASKS, "registry:fragment-locations", `${contentHash}:${peerId}`, 5000)
  return { accepted: true, broker_state: "remote_connected", storage_role: "broker_index_only", location: metadata }
}

async function fragmentLocations(env: Env, url: URL): Promise<JsonMap> {
  const query = (url.searchParams.get("query") || url.searchParams.get("q") || "").toLowerCase()
  const limit = Math.min(25, Math.max(1, Number(url.searchParams.get("limit") || "8")))
  const ids = (await registryGet(env.ATANOR_TASKS, "registry:fragment-locations")).slice(0, 200)
  const locations: JsonMap[] = []
  for (const id of ids) {
    if (locations.length >= limit) break
    const row = await getJson(env.ATANOR_TASKS, `fragment-location:${id}`)
    if (!row) continue
    if (query && !JSON.stringify(row).toLowerCase().includes(query)) continue
    locations.push(row as JsonMap)
  }
  return { query, locations, count: locations.length, broker_state: "remote_connected", storage_role: "broker_index_only", full_payload_storage: false }
}

async function registerNode(env: Env, payload: JsonMap): Promise<JsonMap> {
  if (containsForbidden(payload)) throw new Error("register-node payload contains private/local markers")
  const { nodePublicId, peerIdHash } = await boundPeerIdentity(payload)
  const now = nowIso()
  const existing = (await getJson(env.ATANOR_NODES, `peer:${peerIdHash}`)) || {}
  const peer = {
    ...existing,
    peer_id_hash: peerIdHash,
    node_public_id: nodePublicId,
    region_bucket: String(payload.region_bucket || "anonymous-region"),
    capabilities: payload.capabilities || {},
    resource_limits: payload.resource_limits || {},
    privacy_mode: payload.privacy_mode || "public_tasks_only",
    version: payload.version || payload.app_version || "unknown",
    state: "active",
    contribution_score: Number((existing as JsonMap).contribution_score || 0),
    current_task_id: (existing as JsonMap).current_task_id || null,
    registered_at: (existing as JsonMap).registered_at || now,
    last_seen: now,
  }
  await putJson(env.ATANOR_NODES, `peer:${peerIdHash}`, peer)
  await registryAdd(env.ATANOR_NODES, "registry:peers", peerIdHash)
  return { accepted: true, peer_id_hash: peerIdHash, broker_state: "remote_connected", network: await networkSnapshot(env) }
}

async function heartbeat(env: Env, payload: JsonMap): Promise<JsonMap> {
  if (containsForbidden(payload)) throw new Error("heartbeat payload contains private/local markers")
  const identity = await boundPeerIdentity(payload)
  const { nodePublicId, peerIdHash } = identity
  const key = `peer:${peerIdHash}`
  const existing = await requireRegisteredPeer(env, identity)
  const peer = {
    ...existing,
    peer_id_hash: peerIdHash,
    node_public_id: nodePublicId,
    state: String(payload.state || payload.contributor_state || "active"),
    last_seen: nowIso(),
  }
  await putJson(env.ATANOR_NODES, key, peer)
  await registryAdd(env.ATANOR_NODES, "registry:peers", peerIdHash)
  return { accepted: true, peer_id_hash: peerIdHash, last_seen: peer.last_seen, broker_state: "remote_connected", network: await networkSnapshot(env) }
}

function validateTaskPayload(payload: JsonMap): void {
  if (payload.privacy_classification !== "public_only") throw new Error("privacy_classification must be public_only")
  if (!TASK_TYPES.has(String(payload.task_type || ""))) throw new Error("unknown task_type")
  if (containsForbidden(payload)) throw new Error("task contains private/local/executable markers")
  if (encodedSize(payload) > MAX_PAYLOAD_BYTES) throw new Error("task payload too large")
  const taskPayload = (payload.payload || {}) as JsonMap
  assertSafePublicUrl(taskPayload.source_url)
}

async function enqueueTask(env: Env, payload: JsonMap): Promise<JsonMap> {
  const seedEnabled = String(env.ATANOR_DEV_SEED_PUBLIC_TASKS || "false").toLowerCase() === "true"
  if (!seedEnabled && String(payload.source || "") !== "broker_internal") {
    throw new Error("task enqueue is disabled unless ATANOR_DEV_SEED_PUBLIC_TASKS=true")
  }
  const task = {
    schema_version: "atanor.contribution-task.v1",
    task_id: String(payload.task_id || `task_${crypto.randomUUID()}`),
    task_type: String(payload.task_type || "public_fragment_validation"),
    privacy_classification: "public_only",
    payload_hash: await sha256Hex(payload.payload || {}),
    payload: payload.payload || {},
    assigned_peer: null,
    status: "queued",
    created_at: nowIso(),
    assigned_at: null,
    submitted_at: null,
    expires_at: new Date(Date.now() + TASK_TIMEOUT_MS).toISOString(),
    verification_state: "queued",
    max_runtime_ms: Number(payload.max_runtime_ms || 2500),
    max_memory_mb: Number(payload.max_memory_mb || 64),
    max_output_bytes: Number(payload.max_output_bytes || 8192),
    trust_requirement: Number(payload.trust_requirement || 0),
    credit_estimate: Number(payload.credit_estimate || 1),
  }
  validateTaskPayload(task)
  await putJson(env.ATANOR_TASKS, `task:${task.task_id}`, task)
  await registryAdd(env.ATANOR_TASKS, "registry:tasks", String(task.task_id))
  return { accepted: true, task, broker_state: "remote_connected", network: await networkSnapshot(env) }
}

async function pollTask(env: Env, payload: JsonMap): Promise<JsonMap> {
  const { nodePublicId, peerIdHash } = await boundPeerIdentity(payload)
  await heartbeat(env, {
    node_id: nodePublicId,
    peer_id_hash: peerIdHash,
    state: "polling",
  })
  const tasks = await registryObjects(env.ATANOR_TASKS, "registry:tasks", "task:", 100)
  const now = Date.now()
  for (const task of tasks.sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))) {
    const status = String(task.status || "queued")
    const assignedAt = Date.parse(String(task.assigned_at || ""))
    const expiredAssignment = ["assigned", "running"].includes(status) && Number.isFinite(assignedAt) && now - assignedAt > TASK_TIMEOUT_MS
    if (status !== "queued" && !expiredAssignment) continue
    const updated = {
      ...task,
      assigned_peer: peerIdHash,
      status: "assigned",
      assigned_at: nowIso(),
      verification_state: "assigned",
    }
    await putJson(env.ATANOR_TASKS, `task:${updated.task_id}`, updated)
    const peer = (await getJson(env.ATANOR_NODES, `peer:${peerIdHash}`)) || { peer_id_hash: peerIdHash }
    await putJson(env.ATANOR_NODES, `peer:${peerIdHash}`, { ...peer, state: "busy", current_task_id: updated.task_id, last_seen: nowIso() })
    return { state: "task_available", task: updated, broker_state: "remote_connected", network: await networkSnapshot(env) }
  }
  return { state: "no_task", task: null, broker_state: "remote_connected", network: await networkSnapshot(env) }
}

function fragmentFromSubmission(payload: JsonMap): JsonMap {
  const result = (payload.result_payload || {}) as JsonMap
  const nodes = Array.isArray(result.nodes) ? result.nodes : []
  const edges = Array.isArray(result.edges) ? result.edges : Array.isArray(result.accepted_edges) ? result.accepted_edges : []
  const evidence = Array.isArray(result.evidence) ? result.evidence : Array.isArray(result.evidence_summaries) ? result.evidence_summaries : []
  return {
    schema_version: "atanor.cloud-fragment.v1",
    shard_id: String(result.shard_id || "public-default"),
    source_hash: String(result.source_hash || payload.checksum || ""),
    source_url: String(result.source_url || ""),
    privacy_classification: "public_only",
    raw_payload_exported: false,
    nodes,
    edges,
    evidence,
    verification_state: "single_peer_pending",
    confidence: Number(result.confidence || 0.35),
    requires_cross_check: true,
  }
}

function suppliedContentHash(fragment: JsonMap): string | null {
  const value = String(fragment.content_hash || "")
  return /^[0-9a-f]{64}$/i.test(value) ? value.toLowerCase() : null
}

async function storeFragment(env: Env, fragment: JsonMap, peerHash: string): Promise<JsonMap> {
  const pendingFragment = {
    ...fragment,
    verification_state: SINGLE_PEER_PENDING,
    requires_cross_check: true,
  }
  if (pendingFragment.raw_payload_exported !== false) throw new Error("raw_payload_exported must be false")
  if (pendingFragment.privacy_classification !== "public_only") throw new Error("fragment privacy_classification must be public_only")
  if (containsForbidden(pendingFragment)) throw new Error("fragment contains private/local markers")
  if (encodedSize(pendingFragment) > MAX_FRAGMENT_BYTES) throw new Error("fragment too large")
  assertSafePublicUrl(pendingFragment.source_url)
  const contentHash = suppliedContentHash(pendingFragment) || (await sha256Hex(pendingFragment))
  const fragmentId = `frag_${contentHash.slice(0, 16)}`
  const storageBackend = fragmentStore(env)
  if (storageBackend === "misconfigured") throw new Error("fragment storage binding is missing")
  const objectKey = `fragments/${contentHash}.json`
  const existing =
    env.ATANOR_FRAGMENTS_KV && storageBackend === "kv"
      ? ((await env.ATANOR_FRAGMENTS_KV.get(objectKey, "json")) as JsonMap | null)
      : null
  const stored = {
    ...pendingFragment,
    fragment_id: fragmentId,
    content_hash: contentHash,
    created_by_peer_hash: peerHash,
    created_at: nowIso(),
    storage_backend: storageBackend,
    duplicate_submission_count: Number(existing?.duplicate_submission_count || 0) + (existing ? 1 : 0),
    peer_count: Math.max(1, Number(existing?.peer_count || 0) + (existing ? 0 : 1)),
  }
  if (env.ATANOR_FRAGMENTS && storageBackend === "r2") {
    await env.ATANOR_FRAGMENTS.put(objectKey, JSON.stringify(stored), { httpMetadata: { contentType: "application/json; charset=utf-8" } })
  } else {
    await env.ATANOR_FRAGMENTS_KV!.put(objectKey, JSON.stringify(stored))
  }
  await registryAdd(env.ATANOR_TASKS, "registry:fragments", contentHash, 5000)
  const shardId = String(stored.shard_id || "public-default")
  const shardKey = `shard:${shardId}`
  const shard = (await getJson(env.ATANOR_TASKS, shardKey)) || {
    shard_id: shardId,
    topic_key: shardId,
    fragment_hashes: [],
    peer_count: 0,
    fragment_count: 0,
    hot_score: 0,
    freshness_score: 0,
    verification_score: 0,
  }
  const hashes = Array.from(new Set([...(Array.isArray(shard.fragment_hashes) ? shard.fragment_hashes.map(String) : []), contentHash]))
  await putJson(env.ATANOR_TASKS, shardKey, {
    ...shard,
    fragment_hashes: hashes,
    peer_count: Math.max(1, Number(shard.peer_count || 0)),
    fragment_count: hashes.length,
    hot_score: Number(shard.hot_score || 0) + 1,
    freshness_score: 1,
    verification_score: Number(shard.verification_score || 0.2),
    updated_at: nowIso(),
  })
  await registryAdd(env.ATANOR_TASKS, "registry:shards", shardId)
  return stored
}

async function submitTask(env: Env, payload: JsonMap): Promise<JsonMap> {
  if (containsForbidden(payload)) throw new Error("task result contains private/local markers")
  const taskId = String(payload.task_id || "")
  const identity = await boundPeerIdentity(payload)
  const peerHash = identity.peerIdHash
  if (!taskId) throw new Error("task_id is required")
  const registeredPeer = await requireRegisteredPeer(env, identity)
  const task = await getJson(env.ATANOR_TASKS, `task:${taskId}`)
  if (!task) throw new Error("task not found")
  if (String(task.assigned_peer || "") !== peerHash) throw new Error("task is assigned to another peer")
  const fragment = await storeFragment(env, fragmentFromSubmission(payload), peerHash)
  const updatedTask = {
    ...task,
    status: "submitted",
    submitted_at: nowIso(),
    verification_state: "single_peer_pending",
    result_content_hash: fragment.content_hash,
    fragment_id: fragment.fragment_id,
  }
  await putJson(env.ATANOR_TASKS, `task:${taskId}`, updatedTask)
  const creditKey = `credit:${peerHash}`
  const credit = (await getJson(env.ATANOR_CREDITS, creditKey)) || {
    peer_id_hash: peerHash,
    pending_credit: 0,
    confirmed_credit: 0,
    rejected_tasks: 0,
    accepted_fragments: 0,
  }
  await putJson(env.ATANOR_CREDITS, creditKey, {
    ...credit,
    pending_credit: Number(credit.pending_credit || 0) + Number(task.credit_estimate || 1),
    accepted_fragments: Number(credit.accepted_fragments || 0) + 1,
    last_updated: nowIso(),
  })
  await registryAdd(env.ATANOR_CREDITS, "registry:credits", peerHash)
  await putJson(env.ATANOR_NODES, `peer:${peerHash}`, {
    ...registeredPeer,
    state: "active",
    current_task_id: null,
    last_seen: nowIso(),
  })
  return {
    accepted: true,
    state: "verification_pending",
    verification_state: "single_peer_pending",
    requires_cross_check: true,
    fragment_id: fragment.fragment_id,
    content_hash: fragment.content_hash,
    storage_backend: fragment.storage_backend,
    broker_state: "remote_connected",
    network: await networkSnapshot(env),
  }
}

async function putFragment(env: Env, payload: JsonMap): Promise<JsonMap> {
  const { peerIdHash: peerHash } = await requireRegisteredFragmentPeer(env, payload)
  const fragment = await storeFragment(env, { ...payload, privacy_classification: "public_only", raw_payload_exported: false }, peerHash)
  return {
    accepted: true,
    fragment_id: fragment.fragment_id,
    content_hash: fragment.content_hash,
    raw_payload_exported: false,
    broker_state: "remote_connected",
    storage_backend: fragment.storage_backend,
    network: await networkSnapshot(env),
  }
}

async function submitPublicFragment(env: Env, payload: JsonMap): Promise<JsonMap> {
  if (payload.privacy_scope !== "public") throw new Error("privacy_scope must be public")
  if (payload.source_scope !== "cloud") throw new Error("source_scope must be cloud")
  const { peerIdHash: peerHash } = await requireRegisteredFragmentPeer(env, payload)
  const fragment = await storeFragment(
    env,
    {
      ...payload,
      privacy_classification: "public_only",
      raw_payload_exported: false,
      shard_id: payload.shard_id || "public-remote-submit",
      evidence: payload.evidence || [payload.text || ""].filter(Boolean),
    },
    peerHash,
  )
  return {
    accepted: true,
    fragment_id: fragment.fragment_id,
    content_hash: fragment.content_hash,
    verification_state: fragment.verification_state,
    raw_payload_exported: false,
    broker_state: "remote_connected",
    storage_backend: fragment.storage_backend,
    network: await networkSnapshot(env),
  }
}

async function queryFragments(env: Env, url: URL): Promise<JsonMap> {
  const limit = Math.min(25, Math.max(1, Number(url.searchParams.get("limit") || "8")))
  const contentHash = url.searchParams.get("content_hash") || ""
  const topic = (url.searchParams.get("q") || url.searchParams.get("topic") || url.searchParams.get("concept_id") || "").toLowerCase()
  const store = fragmentStore(env)
  if (store === "misconfigured") throw new Error("fragment storage binding is missing")
  const keys =
    contentHash && env.ATANOR_FRAGMENTS_KV && store === "kv"
      ? [{ name: `fragments/${contentHash}.json` }]
      : (await registryGet(env.ATANOR_TASKS, "registry:fragments")).slice(0, 100).map((hash) => ({ name: `fragments/${hash}.json` }))
  const fragments: JsonMap[] = []
  for (const object of keys) {
    if (fragments.length >= limit) break
    const key = object.name
    const stored = env.ATANOR_FRAGMENTS ? await env.ATANOR_FRAGMENTS.get(key) : null
    const fragment = stored ? ((await stored.json()) as JsonMap) : env.ATANOR_FRAGMENTS_KV ? ((await env.ATANOR_FRAGMENTS_KV.get(key, "json")) as JsonMap | null) : null
    if (!fragment) continue
    if (contentHash && fragment.content_hash !== contentHash) continue
    if (topic) {
      const haystack = JSON.stringify([fragment.shard_id, fragment.nodes, fragment.edges, fragment.evidence]).toLowerCase()
      if (!haystack.includes(topic)) continue
    }
    fragments.push(fragment)
  }
  return { state: "completed", fragments, count: fragments.length, raw_payload_exported: false, broker_state: "remote_connected", storage_backend: store }
}

async function readFragment(env: Env, url: URL): Promise<JsonMap> {
  const contentHash = url.searchParams.get("content_hash") || ""
  if (!/^[0-9a-f]{64}$/i.test(contentHash)) throw new Error("valid content_hash is required")
  const store = fragmentStore(env)
  if (store === "misconfigured") throw new Error("fragment storage binding is missing")
  const key = `fragments/${contentHash.toLowerCase()}.json`
  const stored = env.ATANOR_FRAGMENTS ? await env.ATANOR_FRAGMENTS.get(key) : null
  const fragment = stored ? ((await stored.json()) as JsonMap) : env.ATANOR_FRAGMENTS_KV ? ((await env.ATANOR_FRAGMENTS_KV.get(key, "json")) as JsonMap | null) : null
  return {
    found: Boolean(fragment),
    fragment: fragment || null,
    raw_payload_exported: false,
    broker_state: "remote_connected",
    storage_backend: store,
  }
}

async function shards(env: Env): Promise<JsonMap> {
  const rows = await registryObjects(env.ATANOR_TASKS, "registry:shards", "shard:", 100)
  return { shards: rows, broker_state: "remote_connected" }
}

async function peers(env: Env): Promise<JsonMap> {
  const rows = await registryObjects(env.ATANOR_NODES, "registry:peers", "peer:", 100)
  return {
    peers: rows.map((peer) => ({
      peer_id_hash: peer.peer_id_hash,
      region_bucket: peer.region_bucket,
      capabilities: peer.capabilities,
      resource_limits: peer.resource_limits,
      last_seen: peer.last_seen,
      state: peer.state,
      contribution_score: peer.contribution_score,
      current_task_id: peer.current_task_id,
      privacy_mode: peer.privacy_mode,
      version: peer.version,
    })),
    broker_state: "remote_connected",
  }
}

async function credits(env: Env, url: URL): Promise<JsonMap> {
  const peerHash = url.searchParams.get("peer_id_hash") || url.searchParams.get("node_id") || ""
  const rows = await registryObjects(env.ATANOR_CREDITS, "registry:credits", "credit:", 100)
  const credits = peerHash ? rows.filter((row) => row.peer_id_hash === peerHash) : rows
  return { credits, broker_state: "remote_connected" }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url)
    const path = url.pathname
    if (request.method === "OPTIONS") return jsonResponse(env, request, {}, 204)
    if (!isAuthorized(env, request, path)) return jsonResponse(env, request, { error: "unauthorized" }, 401)
    try {
      if (request.method === "GET" && path === "/cloud/status") return jsonResponse(env, request, await status(env))
      if (request.method === "GET" && path === "/cloud/network") return jsonResponse(env, request, { broker_state: "remote_connected", ...(await networkSnapshot(env)) })
      if (request.method === "GET" && path === "/cloud/peers") return jsonResponse(env, request, await peers(env))
      if (request.method === "GET" && path === "/cloud/shards") return jsonResponse(env, request, await shards(env))
      if (request.method === "GET" && path === "/cloud/credits") return jsonResponse(env, request, await credits(env, url))
      if (request.method === "GET" && path === "/cloud/fragments/query") return jsonResponse(env, request, await queryFragments(env, url))
      if (request.method === "GET" && path === "/cloud/fragments/read") return jsonResponse(env, request, await readFragment(env, url))
      if (request.method === "POST" && path === "/cloud/register-node") return jsonResponse(env, request, await registerNode(env, await readJson(request)))
      if (request.method === "POST" && path === "/cloud/peers/register") return jsonResponse(env, request, await registerNode(env, await readJson(request)))
      if (request.method === "POST" && path === "/cloud/heartbeat") return jsonResponse(env, request, await heartbeat(env, await readJson(request)))
      if (request.method === "POST" && path === "/cloud/peers/heartbeat") return jsonResponse(env, request, await heartbeat(env, await readJson(request)))
      if (request.method === "POST" && path === "/cloud/shards/announce") return jsonResponse(env, request, await announceShards(env, await readJson(request)))
      if (request.method === "POST" && path === "/cloud/fragments/register") return jsonResponse(env, request, await registerFragmentLocation(env, await readJson(request)))
      if (request.method === "GET" && path === "/cloud/fragments/locations") return jsonResponse(env, request, await fragmentLocations(env, url))
      if (request.method === "POST" && path === "/cloud/tasks/enqueue") return jsonResponse(env, request, await enqueueTask(env, await readJson(request)))
      if (request.method === "POST" && path === "/cloud/tasks/poll") return jsonResponse(env, request, await pollTask(env, await readJson(request)))
      if (request.method === "POST" && path === "/cloud/tasks/submit") return jsonResponse(env, request, await submitTask(env, await readJson(request)))
      if (request.method === "POST" && path === "/cloud/fragments/put") return jsonResponse(env, request, await putFragment(env, await readJson(request)))
      if (request.method === "POST" && path === "/cloud/fragments/submit") return jsonResponse(env, request, await submitPublicFragment(env, await readJson(request)))
      return jsonResponse(env, request, { error: "not_found", path, method: request.method }, 404)
    } catch (error) {
      return jsonResponse(env, request, { error: error instanceof Error ? error.message : "internal_error" }, 422)
    }
  },
}
