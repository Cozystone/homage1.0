#!/usr/bin/env bash
# One-shot ATANOR Cloud Brain setup for a fresh Ubuntu/Debian VM (free-tier VPS).
# After you create the VM, SSH in and paste ONE line:
#
#   curl -fsSL https://raw.githubusercontent.com/Cozystone/ATANOR-Demo/main/deploy/setup-vm.sh | bash
#
# It installs Docker, pulls the public repo, builds the cloud-brain image, and
# starts it (auto-restart). After ~1-2 min the brain is learning and serving on
# port 8500.
set -euo pipefail

echo "==> [1/3] Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

echo "==> [2/3] Source"
cd "${HOME}"
if [ ! -d ATANOR-Demo ]; then
  git clone --depth 1 --branch demo https://github.com/Cozystone/ATANOR-Demo.git
fi
cd ATANOR-Demo
git fetch origin demo
git checkout -B demo FETCH_HEAD

echo "==> [3/3] Build + run"
sudo docker compose -f deploy/docker-compose.yml up -d --build

echo
echo "Done. The cloud brain is starting. Verify in ~60s:"
echo "  curl http://localhost:8500/api/cloud-brain/learning/continuous/metrics"
echo
echo "Caddy is enabled by default in docker-compose.yml, fronting the brain with"
echo "HTTPS on 80/443 (edit deploy/Caddyfile's domain to match this VM before"
echo "first boot). Set CLOUD_BRAIN_BASE in the frontend to that HTTPS URL."
