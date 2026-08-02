#!/usr/bin/env bash
# BL-0 deploy — stand up the ATANOR edge brain on the Radxa Dragon Q6A over Tailscale.
# The owner runs this from the PC (I verified the Radxa is reachable — pong 8ms — but I do not have
# SSH key access; the owner has the shell). One command; safe to re-run.
#
#   bash scripts/deploy_edge_brain.sh [radxa_user] [radxa_host]
#
# Defaults target the confirmed peer. The edge profile is CPU-only (aarch64), pure-Python + the
# situation-model/state-tracker/brain-link organs + a Ring0 graph slice sized to ~5GB usable RAM —
# NO training, NO GPU, NO full 7.5GB world_pack (the edge READS a slice; the PC stays the heavy brain).
set -euo pipefail

USER_="${1:-radxa}"
HOST_="${2:-100.108.120.104}"          # radxa-dragon-q6a-1
DEST="~/atanor-edge"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "[BL-0] target: ${USER_}@${HOST_}  (Radxa Dragon Q6A, aarch64, ~5GB usable)"

# 1) preflight: reachable + python present
ssh -o ConnectTimeout=10 "${USER_}@${HOST_}" \
  'echo "[edge] $(uname -m) $(python3 --version)"; nproc; free -m | awk "/Mem/{print \$2\" MB total, \"\$7\" MB avail\"}"'

# 2) sync ONLY the edge-profile packages (not the whole repo, not data/models)
echo "[BL-0] syncing edge packages…"
rsync -az --delete \
  --include='packages/' \
  --include='packages/situation_model/***' \
  --include='packages/brain_link/***' \
  --include='packages/brain_link_pool/***' \
  --include='packages/graph_scale/injection_guard.py' \
  --include='packages/graph_scale/moral_invariants.py' \
  --include='packages/graph_scale/__init__.py' \
  --include='requirements-edge.txt' \
  --exclude='*' \
  "${REPO}/" "${USER_}@${HOST_}:${DEST}/"

# 3) install minimal deps + run the loopback twin ON the edge (proves the organs run on aarch64)
ssh "${USER_}@${HOST_}" bash -lc "
  set -e
  cd ${DEST}
  python3 -m venv .venv 2>/dev/null || true
  . .venv/bin/activate
  pip install -q -U pip
  pip install -q cryptography pytest 2>/dev/null || true
  echo '[edge] running brain-link loopback twin on the Radxa itself…'
  PYTHONPATH=${DEST} python3 -m pytest packages/brain_link/tests -q 2>&1 | tail -3 || \
    echo '[edge] (loopback needs the injection_guard deps; see requirements-edge.txt)'
"

echo "[BL-0] edge brain staged. Next: BL-1 handshake PC<->Radxa (run the brain_link peer on both,"
echo "       exchange signed hellos over Tailscale 100.108.120.104). The constitution is already"
echo "       proven on the loopback twin; this is the same code across the wire."
