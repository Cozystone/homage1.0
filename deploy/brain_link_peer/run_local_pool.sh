#!/usr/bin/env bash
# Local 32-thread boost: spin up N Brain Link peers on THIS machine. Each peer is
# a process that runs the real cgsr engine, so N peers = N-way parallel learning
# across the local CPU cores (e.g. the 9950X3D's 32 threads). All contributions
# merge into the shared contributed store via the coordinator.
#   ./run_local_pool.sh 16
set -e
N="${1:-8}"
docker rm -f $(docker ps -aq --filter "name=atanor-peer-") 2>/dev/null || true
for i in $(seq 1 "$N"); do
  docker run -d --name "atanor-peer-$i" --add-host=host.docker.internal:host-gateway \
    -e PEER_ID="local-peer-$i" -e PEER_LABEL="local core $i" \
    -e BATCH=40 atanor-brain-link-peer:latest >/dev/null
done
echo "started $N local peers (parallel cgsr learning). Watch:"
echo "  curl -s http://localhost:8502/api/brain-link/pool/status"
