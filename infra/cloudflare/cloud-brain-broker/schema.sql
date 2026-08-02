-- Optional D1 schema for ATANOR Cloud Brain Broker metadata.
-- The first Worker scaffold can run with KV + R2 only. Use this when D1
-- relational queries become necessary.

CREATE TABLE IF NOT EXISTS cloud_nodes (
  node_id TEXT PRIMARY KEY,
  device_label TEXT,
  app_version TEXT,
  contributor_state TEXT,
  registered_at TEXT,
  last_seen_at TEXT,
  capabilities_json TEXT NOT NULL DEFAULT '{}',
  resource_limits_json TEXT NOT NULL DEFAULT '{}',
  trust_score REAL NOT NULL DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS cloud_tasks (
  task_id TEXT PRIMARY KEY,
  task_type TEXT NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  assigned_node_id TEXT,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  credit_estimate REAL NOT NULL DEFAULT 0,
  privacy_classification TEXT NOT NULL DEFAULT 'public_only'
);

CREATE TABLE IF NOT EXISTS cloud_fragments (
  fragment_id TEXT PRIMARY KEY,
  shard_id TEXT NOT NULL,
  object_key TEXT NOT NULL,
  concept_ids_json TEXT NOT NULL DEFAULT '[]',
  checksum TEXT NOT NULL,
  trust_score REAL NOT NULL DEFAULT 0.5,
  freshness_score REAL NOT NULL DEFAULT 0.5,
  conflict_markers_json TEXT NOT NULL DEFAULT '[]',
  schema_version TEXT NOT NULL DEFAULT 'atanor.cloud-fragment.v1',
  raw_payload_exported INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  expires_at TEXT
);

CREATE TABLE IF NOT EXISTS cloud_credits (
  credit_id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  amount_estimated REAL NOT NULL DEFAULT 0,
  amount_confirmed REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',
  reason TEXT,
  created_at TEXT NOT NULL,
  confirmed_at TEXT
);
