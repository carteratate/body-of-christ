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

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
