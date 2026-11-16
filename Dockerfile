# Multi-stage build.
#   builder  installs the dependencies into a virtualenv (/opt/venv)
#   runtime  copies only that venv and the application code
# The runtime image contains neither a pip cache nor pip itself nor any
# compiler, and runs as an unprivileged user.

ARG PYTHON_IMAGE=python:3.12-slim

FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# --- builder -----------------------------------------------------------------
FROM base AS builder
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt .
# Only binary wheels: no source builds, so no compiler is needed or installed.
RUN pip install --only-binary=:all: -r requirements.txt \
 && pip uninstall --yes pip

# --- runtime -----------------------------------------------------------------
FROM base AS runtime

# Install available Debian security updates for zlib.
RUN apt-get update \
 && apt-get install -y --no-install-recommends --only-upgrade zlib1g \
 && rm -rf /var/lib/apt/lists/*

ARG APP_VERSION=0.0.0-dev
ARG GIT_COMMIT=unknown
LABEL org.opencontainers.image.title="weatherwatch" \
      org.opencontainers.image.description="WeatherWatch – Wetter-App (CDS212 Abschlussprojekt)" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_COMMIT}"

# The base image ships pip for the system interpreter; the app never needs it
# at runtime, so it goes. Then create a system user without login shell.
RUN python -m pip uninstall --yes pip \
 && groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home \
            --home-dir /nonexistent --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv
# Code stays owned by root: the app user can read but not modify it.
COPY app/ ./app/
COPY wsgi.py gunicorn.conf.py ./

ENV PATH=/opt/venv/bin:$PATH \
    APP_VERSION=${APP_VERSION} \
    GIT_COMMIT=${GIT_COMMIT} \
    PORT=8000

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=2).status == 200 else 1)"]

# Exec form: gunicorn is PID 1 and receives SIGTERM directly (graceful stop).
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
