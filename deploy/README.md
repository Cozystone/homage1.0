# ATANOR Cloud Brain — VPS deployment (runs without your PC)

This runs the **real Python engine** (continuous public-web learning + relation
discovery + the graph/metrics API) on an always-on server, so the shared cloud
brain keeps learning and is viewable by everyone even when your PC is off.

## Architecture (what runs where)

```
                 ┌─────────────────── VPS (always on) ──────────────────┐
   public web →  │  ATANOR Cloud Brain (FastAPI, Docker)                │
   (Wikipedia)   │   • LEARN  : continuous loop ingests + verifies      │
                 │   • DISCOVER: random concept-pair relation checks    │
                 │   • STORE  : candidate graph on a Docker volume      │
                 │   • SERVE  : /api/cloud-brain/... graph + metrics     │
                 └───────────────▲──────────────────────────────────────┘
                                 │ HTTPS
        every user's frontend ───┘  (all see the SAME growing brain)
```

The graph (concepts / relations / constructions) accumulates on the `atanor-data`
Docker volume, so it survives restarts and redeploys — the brain only grows.

## Deploy (5 steps)

1. **Get a small VPS** (1–2 GB RAM is plenty: Hetzner, DigitalOcean, Vultr, Fly.io
   machine, etc.) and install Docker + the compose plugin.
2. **One-line setup** — SSH into the VM and paste:
   ```sh
   curl -fsSL https://raw.githubusercontent.com/Cozystone/ATANOR-Demo/demo/deploy/setup-vm.sh | bash
   ```
   (installs Docker, pulls the public repo, builds + starts the brain). Or do it
   manually: copy the repo and run
   ```sh
   docker compose -f deploy/docker-compose.yml up -d --build
   ```

## Free always-on hosts

The learning loop must run 24/7, so **serverless free tiers that sleep when idle
(Render free, Cloud Run, Koyeb free) won't work** — the brain would stop growing.
Use a real always-on free VM:

- **Oracle Cloud "Always Free"** — free *forever* VM (AMD micro 1 GB, or ARM
  Ampere if available). Best truly-free option. Signup needs a card for identity
  verification only (not charged within free limits).
- **Google Cloud free tier** — one `e2-micro` VM free per month in US regions.
  Card required for verification.

1 GB RAM is enough for this image (FastAPI + numpy; no torch).
   The brain begins learning immediately. Check it:
   ```sh
   curl http://localhost:8500/api/cloud-brain/learning/continuous/metrics
   ```
4. **Put HTTPS in front** (the frontend needs an HTTPS endpoint). Easiest: point a
   domain's A record at the VPS, then enable the `caddy` service in
   `docker-compose.yml` (uncomment it + set `DOMAIN` in `Caddyfile`) and re-run
   `up -d`. Caddy fetches a real certificate automatically. Now the brain is at
   `https://cloud.yourdomain.com`.
5. **Point the frontend at it.** In the web app's environment set:
   ```
   API_BASE_URL=https://cloud.yourdomain.com
   ```
   (Vercel: Project → Settings → Environment Variables, then redeploy. Locally:
   `apps/web/.env.local`.) Every viewer now sees the same shared, growing brain.

## Optional — seed with what it has already learned

The container starts learning from scratch by default. To carry over the graph
your local instance already built, copy the candidate store into the volume
before/while the container runs, e.g.:

```sh
# from the local machine: tar the existing candidate store
tar czf store.tgz -C "<local>/data/cloud_brain" candidate_runs
# on the VPS: extract into the named volume
docker run --rm -v atanor-data:/app/data -v "$PWD":/in alpine \
  sh -c "mkdir -p /app/data/cloud_brain && tar xzf /in/store.tgz -C /app/data/cloud_brain"
docker compose -f deploy/docker-compose.yml restart atanor-cloud
```

## Validated
The minimal dependency set was verified in a **clean virtualenv** (only
`requirements-cloud.txt`, `HOMAGE_DISABLE_BGE_M3=1`): `app.main` imports cleanly
and the server answers `/api/cloud-brain/learning/continuous/metrics`,
`/surface-graph/graph`, and `/candidate/status` — so the Docker image builds and
serves without torch / sentence_transformers. (Full `docker build` still depends
on your Docker daemon being up.)

## Firehose — fast bulk ingest (the "거대 발화그래프")

The cloud brain has a **firehose** that streams sentences from local corpora at
disk speed and counts unique utterances — separate from (and far faster than) the
slow concept/relation extraction. Out of the box it ingests a small **diverse seed**
(formal docs + casual speech + slang, EN + KO). For sustained **~10k sentences/sec**,
drop large public corpora into a directory and point the firehose at it:

```sh
# in docker-compose.yml, add to the atanor-cloud service:
#   environment:
#     - ATANOR_CORPORA_DIR=/app/data/corpora
#   (and put *.txt / *.jsonl corpora into the atanor-data volume's corpora/ dir)
```

Good diverse public sources (download once into the corpora dir): a Wikipedia
sentence dump (formal), OpenSubtitles (dialogue/slang), a tweets/Reddit dump
(colloquial), Korean colloquial sets (e.g. NSMC). Note: scraping Instagram etc.
is **not** done — that violates their ToS and needs auth; use legitimately public
corpora. The UI shows ingest rate (fast) vs concepts (slow) separately — "본 문장"
is not claimed as "이해한 개념".

## Notes
- Only **public** (Wikipedia-derived) knowledge lives in the cloud brain — no
  private/local data is sent here, by design.
- Federating many instances through a central broker is supported later via the
  `ATANOR_CLOUD_MODE=remote` env (see `.env.example`); not required for a single
  shared instance.
