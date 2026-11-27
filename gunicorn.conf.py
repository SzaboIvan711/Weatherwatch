"""Gunicorn settings, read from the environment.

One worker process with several threads by default: prometheus_client keeps
metrics per process, so with a single process every scrape of /metrics sees
all requests of the container. Scale out with replicas (Kubernetes), not with
worker processes. See ADR 0004.
"""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("GUNICORN_WORKERS", "1"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"

# A request that hangs longer than this is killed; the upstream API call is
# bounded far below (timeouts + retries in app/weather.py).
timeout = 30
# SIGTERM -> finish in-flight requests within this window (Kubernetes gives 30s).
graceful_timeout = 20
keepalive = 5

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
proc_name = "weatherwatch"

# Disable unused Gunicorn control socket.
control_socket_disable = True
