# Brain Link peer — a "virtual PC" that contributes compute to the shared pool.
# Built FROM the real ATANOR engine image so the peer runs the actual
# graph-native neuro-symbolic extraction (cgsr) — NO external LLM, NO sLLM, NO
# regex/rule-based. Distributed compute = the real engine across machines.
#   docker build -f deploy/Dockerfile -t atanor-cloud:local .      (engine, from repo root)
#   docker build -t atanor-brain-link-peer:latest deploy/brain_link_peer
FROM atanor-cloud:local
COPY peer_worker.py /app/peer_worker.py
ENV COORDINATOR_URL=http://host.docker.internal:8502 \
    PEER_ID=docker-peer-1 \
    PEER_LABEL="Docker virtual PC" \
    HOMAGE_DISABLE_BGE_M3=1
WORKDIR /app
CMD ["python", "peer_worker.py"]
