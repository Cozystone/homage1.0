FROM python:3.11-slim@sha256:00af38ae2ed311628970782e8a2d7f014d8909dbc63cb97bc0a158187f4db045

ARG SOURCE_SHA256
LABEL org.atanor.science-e4-local.role="local-fixture-evaluator" \
      org.atanor.science-e4-local.context-sha256="${SOURCE_SHA256}" \
      org.atanor.science-e4-local.authority="none"

WORKDIR /opt/atanor-probe
COPY fixture_evaluator.py /opt/atanor-probe/fixture_evaluator.py

USER 10002:10002
ENTRYPOINT ["/usr/bin/env", "-i", "LANG=C.UTF-8", "PATH=/usr/local/bin:/usr/bin:/bin", "python", "-I", "-B", "/opt/atanor-probe/fixture_evaluator.py"]
