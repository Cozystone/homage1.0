# ATANOR Cloud Brain — deployable, always-on image for a small VPS.
# Runs the REAL Python engine: continuous public-web learning + relation
# discovery + the graph/metrics API. Build from the repo root:
#   docker build -f deploy/Dockerfile -t atanor-cloud .
# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/packages:/app/apps/api \
    ATANOR_AUTO_LEARN=1 \
    ATANOR_CLOUD_PORT=8500 \
    HOMAGE_DISABLE_BGE_M3=1

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin atanor

COPY deploy/requirements-cloud.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -r /tmp/requirements.txt

# The cloud brain imports both `packages.X` and bare `X` (e.g. rag_engine, cgsr),
# so PYTHONPATH includes /app AND /app/packages. Copy the whole engine.
COPY apps/api /app/apps/api
COPY packages /app/packages

RUN mkdir -p /app/data && chown -R atanor:atanor /app

USER atanor
# The accumulated graph (candidate store) lives here — keep it on a volume so the
# brain keeps everything it has learned across restarts/redeploys.
VOLUME ["/app/data"]
EXPOSE 8500

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8500/api/cloud-brain/learning/continuous/metrics', timeout=4).read()" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8500", "--app-dir", "apps/api"]
