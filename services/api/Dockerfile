FROM python:3.11-slim

# Run as non-root user
RUN adduser --disabled-password --gecos "" appuser

WORKDIR /app

# Exactly the versions CI tested (scripts/lock_python_deps.sh writes the lock), then
# the app itself with no further resolution.
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY pyproject.toml .
COPY app/ app/
RUN pip install --no-cache-dir --no-deps .

USER appuser

# exec makes uvicorn PID 1, so Railway's SIGTERM reaches it and the lifespan teardown
# (guest drain, client closes) runs. Open streams get 75 s to finish, so the service's
# draining time (RAILWAY_DEPLOYMENT_DRAINING_SECONDS) should allow that plus the 30 s
# guest drain and the cleanup after it.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-graceful-shutdown 75"]
