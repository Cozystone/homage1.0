import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import test from "node:test"

import worker from "./worker.ts"


class MemoryKv {
  constructor() {
    this.values = new Map()
  }

  async get(key, type) {
    const value = this.values.get(key)
    if (value === undefined) return null
    return type === "json" ? JSON.parse(value) : value
  }

  async put(key, value) {
    this.values.set(key, String(value))
  }

  async list({ prefix = "", limit = 1000 } = {}) {
    const keys = [...this.values.keys()]
      .filter((key) => key.startsWith(prefix))
      .slice(0, limit)
      .map((name) => ({ name }))
    return { keys, list_complete: true, cacheStatus: null }
  }
}


function peerHash(nodeId) {
  return createHash("sha256").update(`peer:${nodeId}`).digest("hex")
}


function makeEnv({ apiKey } = {}) {
  return {
    ATANOR_BROKER_API_KEY: apiKey,
    ATANOR_NODES: new MemoryKv(),
    ATANOR_TASKS: new MemoryKv(),
    ATANOR_CREDITS: new MemoryKv(),
    ATANOR_FRAGMENTS_KV: new MemoryKv(),
  }
}


function request(path, { apiKey, body, method = "POST" } = {}) {
  const headers = { "Content-Type": "application/json" }
  if (apiKey) headers["X-ATANOR-API-Key"] = apiKey
  return new Request(`https://broker.example${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}


async function registerPeer(env, nodeId) {
  const expectedHash = peerHash(nodeId)
  const response = await worker.fetch(
    request("/cloud/register-node", {
      apiKey: "test-secret",
      body: {
        node_id: nodeId,
        node_public_id: nodeId,
        peer_id_hash: expectedHash,
      },
    }),
    env,
  )
  assert.equal(response.status, 200)
  return expectedHash
}


function fragmentPayload(nodeId, overrides = {}) {
  return {
    node_id: nodeId,
    peer_id_hash: peerHash(nodeId),
    raw_payload_exported: false,
    privacy_classification: "public_only",
    source_url: `https://example.com/public/${nodeId}`,
    shard_id: "public-test",
    nodes: [{ concept_id: `concept-${nodeId}` }],
    edges: [],
    evidence: [`Public evidence from ${nodeId}.`],
    ...overrides,
  }
}


test("missing broker key fails closed for mutation but public status remains readable", async () => {
  const env = makeEnv()
  const mutation = await worker.fetch(
    request("/cloud/register-node", {
      body: { node_public_id: "public-node" },
    }),
    env,
  )
  assert.equal(mutation.status, 401)
  assert.equal(env.ATANOR_NODES.values.size, 0)

  const status = await worker.fetch(
    request("/cloud/status", { method: "GET" }),
    env,
  )
  assert.equal(status.status, 200)
})


test("caller cannot supply a peer hash that disagrees with its node identity", async () => {
  const env = makeEnv({ apiKey: "test-secret" })
  const response = await worker.fetch(
    request("/cloud/register-node", {
      apiKey: "test-secret",
      body: {
        node_public_id: "legitimate-node",
        peer_id_hash: "f".repeat(64),
      },
    }),
    env,
  )
  assert.equal(response.status, 422)
  assert.equal(await env.ATANOR_NODES.get(`peer:${"f".repeat(64)}`), null)
})


test("unknown caller cannot manufacture freshness while a registered caller can heartbeat", async () => {
  const env = makeEnv({ apiKey: "test-secret" })
  const unknownNode = "never-registered"
  const unknownHash = peerHash(unknownNode)
  const forged = await worker.fetch(
    request("/cloud/heartbeat", {
      apiKey: "test-secret",
      body: {
        node_id: unknownNode,
        peer_id_hash: unknownHash,
        state: "active",
      },
    }),
    env,
  )
  assert.equal(forged.status, 422)
  assert.equal(await env.ATANOR_NODES.get(`peer:${unknownHash}`), null)

  const nodeId = "registered-node"
  const expectedHash = peerHash(nodeId)
  const registration = await worker.fetch(
    request("/cloud/register-node", {
      apiKey: "test-secret",
      body: {
        node_id: nodeId,
        node_public_id: nodeId,
        peer_id_hash: expectedHash,
      },
    }),
    env,
  )
  assert.equal(registration.status, 200)

  const heartbeat = await worker.fetch(
    request("/cloud/heartbeat", {
      apiKey: "test-secret",
      body: {
        node_id: nodeId,
        peer_id_hash: expectedHash,
        state: "polling",
      },
    }),
    env,
  )
  assert.equal(heartbeat.status, 200)
  const stored = await env.ATANOR_NODES.get(
    `peer:${expectedHash}`,
    "json",
  )
  assert.equal(stored.peer_id_hash, expectedHash)
  assert.equal(stored.node_public_id, nodeId)
  assert.equal(stored.state, "polling")
  assert.equal(typeof stored.last_seen, "string")
})


test("unregistered caller cannot put a fragment under a self-minted peer hash", async () => {
  const env = makeEnv({ apiKey: "test-secret" })
  const nodeId = "unregistered-fragment-node"
  const response = await worker.fetch(
    request("/cloud/fragments/put", {
      apiKey: "test-secret",
      body: fragmentPayload(nodeId),
    }),
    env,
  )

  assert.equal(response.status, 422)
  assert.deepEqual(
    await env.ATANOR_TASKS.get("registry:fragments", "json"),
    null,
  )
  assert.equal(env.ATANOR_FRAGMENTS_KV.values.size, 0)
})


test("registered caller cannot put a fragment under a conflicting created-by peer", async () => {
  const env = makeEnv({ apiKey: "test-secret" })
  const nodeId = "registered-fragment-node"
  await registerPeer(env, nodeId)
  const response = await worker.fetch(
    request("/cloud/fragments/put", {
      apiKey: "test-secret",
      body: fragmentPayload(nodeId, {
        created_by_peer_hash: "f".repeat(64),
      }),
    }),
    env,
  )

  assert.equal(response.status, 422)
  assert.deepEqual(
    await env.ATANOR_TASKS.get("registry:fragments", "json"),
    null,
  )
  assert.equal(env.ATANOR_FRAGMENTS_KV.values.size, 0)
})


test("registered peer can put and submit but cannot inject verified state", async () => {
  const env = makeEnv({ apiKey: "test-secret" })
  const nodeId = "legitimate-fragment-node"
  const expectedHash = await registerPeer(env, nodeId)
  const putPayload = fragmentPayload(nodeId, {
    verification_state: "multi_peer_verified",
    provenance: { source_peer_id: nodeId },
  })
  delete putPayload.node_id
  delete putPayload.peer_id_hash

  const putResponse = await worker.fetch(
    request("/cloud/fragments/put", {
      apiKey: "test-secret",
      body: putPayload,
    }),
    env,
  )
  assert.equal(putResponse.status, 200)
  const putResult = await putResponse.json()
  const putStored = await env.ATANOR_FRAGMENTS_KV.get(
    `fragments/${putResult.content_hash}.json`,
    "json",
  )
  assert.equal(putStored.created_by_peer_hash, expectedHash)
  assert.equal(putStored.verification_state, "single_peer_pending")
  assert.equal(putStored.requires_cross_check, true)

  const submitResponse = await worker.fetch(
    request("/cloud/fragments/submit", {
      apiKey: "test-secret",
      body: {
        ...fragmentPayload(nodeId, {
          source_url: "https://example.com/public/submit-control",
          verification_state: "multi_peer_verified",
        }),
        privacy_scope: "public",
        source_scope: "cloud",
      },
    }),
    env,
  )
  assert.equal(submitResponse.status, 200)
  const submitResult = await submitResponse.json()
  assert.equal(submitResult.verification_state, "single_peer_pending")
  const submitStored = await env.ATANOR_FRAGMENTS_KV.get(
    `fragments/${submitResult.content_hash}.json`,
    "json",
  )
  assert.equal(submitStored.created_by_peer_hash, expectedHash)
  assert.equal(submitStored.verification_state, "single_peer_pending")
  assert.equal(submitStored.requires_cross_check, true)
})
