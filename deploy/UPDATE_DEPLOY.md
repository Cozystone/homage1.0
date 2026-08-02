# Updating the live Oracle VM Cloud Brain (paste-ready)

This session's changes (predicate-anchored relation edges + neuroplasticity consolidation
wired into the worker + clean decomposer) are pushed to **ATANOR-Demo `demo` branch**.
The VM builds its image from this repo and keeps its graph on the `atanor-data` Docker
volume, so a rebuild **preserves everything the cloud brain already learned** — it only
gains the new code.

You run these on the VM (I can't: no SSH key here, and I must not handle credentials).

---

## 1. SSH into the VM
```sh
ssh <your-user>@155.248.183.108     # e.g. ubuntu@ or opc@ — whatever you set up
```

## 2. Pull the new code + rebuild (RECOMMENDED — gets ALL changes incl. the new file)
```sh
cd ~/ATANOR-Demo
git fetch origin
git checkout demo && git pull --ff-only origin demo     # deploy the demo branch directly
sudo docker compose -f deploy/docker-compose.yml up -d --build
```
- `--build` rebuilds `atanor-cloud:latest` with the new code; the `atanor-data` volume
  (the learned graph) is untouched.
- If you prefer the VM to stay on `main`: first merge `demo` → `main` on GitHub (open the
  PR at https://github.com/Cozystone/ATANOR-Demo/pull/new/demo and merge), then on the VM
  `git checkout main && git pull --ff-only && sudo docker compose ... up -d --build`.

## 3. Verify the new engine is live
```sh
# container healthy + learning
curl -s http://localhost:8500/api/cloud-brain/learning/continuous/metrics | python3 -m json.tool | head
curl -s http://localhost:8500/api/cloud-brain/status | python3 -m json.tool | head
# confirm predicate edges + plasticity weights are being written (inside the container)
sudo docker exec -it $(sudo docker ps -qf name=atanor-cloud) sh -c \
  'f=$(ls -dt /app/data/cloud_brain/candidate_runs/*/relations.jsonl | head -1); \
   echo "relation types:"; grep -o "\"relation\": *\"[^\"]*\"" "$f" | sort | uniq -c | sort -rn | head; \
   echo "with plasticity weight:"; grep -c "info_weight" "$f"'
```
Expect: `relation` types beyond `IS_A` (predicate verbs like 생산하다/위치하다), `_OF` noise
absent, and a growing `info_weight` count once the worker has run a few plasticity ticks
(default every 30 learn ticks; tune with `ATANOR_PLASTICITY_EVERY` in the compose env).

## 4. (optional) tune plasticity cadence
In `deploy/docker-compose.yml` under `atanor-cloud: environment:` add any of:
```yaml
      - ATANOR_PLASTICITY_EVERY=30        # consolidate every N learn ticks
      - ATANOR_PLASTICITY_HALFLIFE_DAYS=60
      - ATANOR_PLASTICITY_FLOOR=0.04
```
then `sudo docker compose -f deploy/docker-compose.yml up -d` (no rebuild needed for env).

---

## Notes / honesty
- The VM serves the **cloud-brain graph + learner** (port 8500), not the local answer-pack
  demo — so the base_brain promotion / answer-pack changes are for the LOCAL :8502 demo,
  not this VM. What the VM gains: clean predicate-association edges in NEW learning + the
  neuroplasticity consolidation (informativeness weight + decay + prune = bounded memory).
- The VM's own accumulated graph is separate from the local `clean_seed_v2`; it keeps
  growing on the volume. No reset.
- Rollback if a rebuild misbehaves: `git checkout <previous-sha>` then `up -d --build`; the
  volume (graph) is never touched by a rebuild.

---

## 2026-07-09 — waitlist endpoint (사전예약 저장)

The landing's download section is now a waitlist box POSTing to the VM:
`POST /api/waitlist` (router: `apps/api/app/routers/waitlist.py`, wired in `main.py`).
Entries append to `data/waitlist/waitlist.jsonl` on the `atanor-data` volume.
Deploy = the same rebuild as above (`git pull` + `docker compose up -d --build`).
Verify: `curl -s https://136.114.69.152.sslip.io/api/waitlist/count`
Until the VM rebuild, the landing form saves signups in the visitor's browser and
auto-resends on their next visit — nothing is lost, but rebuild soon.
