# ATANOR Quickstart

This quickstart starts the local backend and web UI. Cloud Brain contribution
is optional and disabled by default.

## 1. Install Dependencies

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r apps/api/requirements.txt
npm install
```

Copy the local-first environment template before starting services:

```powershell
Copy-Item .env.example .env
```

## 2. Start Backend

```powershell
$env:PYTHONPATH="apps/api;packages/rag_engine;packages/guard;packages/ontology_forge;packages/datagate;packages/knowledge_bakery;packages/neuro_efficiency;packages/trainer;packages/model;packages/cost_model"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8500 --app-dir apps/api
```

## 3. Start Web UI

```powershell
npm --workspace apps/web run dev -- --hostname 127.0.0.1 --port 3022
```

Open:

```text
http://127.0.0.1:3022/?lang=ko
```

## 4. Optional: Verify Cloudflare Broker

```powershell
$env:ATANOR_CLOUD_PROVIDER="cloudflare"
$env:ATANOR_CLOUD_MODE="remote"
$env:ATANOR_CLOUD_ENDPOINT="https://your-worker.workers.dev"
$env:ATANOR_CONTRIBUTION_ENABLED="true"
python -m apps.api.app.workers.contributor_node --once
```

One peer is a real minimum runtime state, but fragments remain
`single_peer_pending` until multi-peer verification is implemented.
